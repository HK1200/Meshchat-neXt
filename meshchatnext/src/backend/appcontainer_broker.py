# SPDX-License-Identifier: 0BSD
"""Bounded loopback TLS forwarding for a headless AppContainer backend.

No firewall exemptions: the contained process serves a private named pipe.
The supervisor verifies the actual server PID and cannot be impersonated by it.
"""

from __future__ import annotations

import asyncio
import ctypes
import ipaddress
import logging
import os
import secrets
import ssl
import sys
import threading
from pathlib import Path

from meshchatnext.src.backend import appcontainer_sandbox as sandbox
from meshchatnext.src.backend.appcontainer_pipe import (
    proxy_connection,
    request_child_shutdown,
)
from meshchatnext.src.env_config import MeshchatEnv
from meshchatnext.src.env_utils import env_str
from meshchatnext.src.ssl_self_signed import generate_ssl_certificate

logger = logging.getLogger(__name__)


def _flag(argv, name, default=None):
    # argparse uses the last occurrence of a scalar option.
    value = default
    for index, arg in enumerate(argv):
        if arg == name and index + 1 < len(argv):
            value = argv[index + 1]
        elif arg.startswith(name + "="):
            value = arg.split("=", 1)[1]
    return value


def broker_settings(argv, storage_dir):
    env = MeshchatEnv.load()
    host = _flag(argv, "--host", env.host)
    try:
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError
    except ValueError:
        raise ValueError("AppContainer broker requires a loopback --host") from None
    port = int(_flag(argv, "--port", env.port))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid AppContainer broker port")
    use_https = not ("--no-https" in argv or env.no_https)
    cert = _flag(argv, "--ssl-cert", env.ssl_cert)
    key = _flag(argv, "--ssl-key", env.ssl_key)
    if bool(cert) != bool(key):
        raise ValueError("Both SSL certificate and key must be supplied")
    custom = bool(cert)
    if not custom:
        directory = Path(storage_dir) / "ssl"
        cert, key = str(directory / "cert.pem"), str(directory / "key.pem")
    if not cert or not key:
        raise ValueError("Both SSL certificate and key must be supplied")
    return host, port, use_https, os.path.abspath(cert), os.path.abspath(key), custom


def child_pipe_address(leaf):
    """Derive the target locally, never accepting a child-provided address."""
    sid = sandbox.ensure_appcontainer_profile()
    value = ctypes.c_wchar_p()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    convert = advapi.ConvertSidToStringSidW
    convert.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
    try:
        if not convert(sid, ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        session = ctypes.c_ulong()
        if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            raise ctypes.WinError(ctypes.get_last_error())
        return rf"\\.\pipe\Sessions\{session.value}\AppContainerNamedObjects\{value.value}\{leaf}"
    finally:
        if value:
            sandbox._local_free(ctypes.cast(value, ctypes.c_void_p))
        sandbox._local_free(sid)


async def _supervise(exe, argv, *, storage_dir, reticulum_config_dir, log_dir):
    host, port, https, cert, key, custom = broker_settings(argv, storage_dir)
    tls = None
    child_args = list(argv)
    if https:
        if not custom:
            generate_ssl_certificate(cert, key)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)  # Fail closed; never silently downgrade.
        child_args += ["--ssl-cert", cert, "--ssl-key", key]

    leaf = "MeshchatNext-" + secrets.token_hex(16)
    address = child_pipe_address(leaf)
    env = os.environ.copy()
    private_temp = Path(storage_dir) / ".appcontainer-temp"
    private_temp.mkdir(parents=True, exist_ok=True)
    for name in ("TEMP", "TMP", "TMPDIR"):
        env[name] = str(private_temp)
    env["MESHCHAT_APPCONTAINER_PIPE"] = rf"\\.\pipe\LOCAL\{leaf}"
    # This supervisor owns fallback; a contained child may never serve TCP.
    env["MESHCHAT_APPCONTAINER"] = "1"
    token = secrets.token_hex(32)
    env["MESHCHAT_APPCONTAINER_SHUTDOWN_TOKEN"] = token
    stop = threading.Event()
    quit_requested = threading.Event()
    if env_str("MESHCHAT_APPCONTAINER_CONTROL_STDIN") == "1":

        def read_control():
            try:
                while True:
                    line = sys.stdin.buffer.readline(64)
                    if not line or line == b"meshchatnext-stop\n":
                        quit_requested.set()
                        return
            except (OSError, AttributeError):
                quit_requested.set()

        threading.Thread(
            target=read_control, name="AppContainer quit control", daemon=True
        ).start()
    child_pid = []
    results = []
    sessions = set()

    def worker():
        results.append(
            sandbox.launch_backend_sandboxed(
                exe,
                child_args,
                storage_dir=storage_dir,
                reticulum_config_dir=reticulum_config_dir,
                log_dir=log_dir,
                forced=True,
                env=env,
                on_child_started=child_pid.append,
                child_log_path=str(
                    Path(log_dir or storage_dir) / "appcontainer-child.log"
                ),
                stop_event=stop,
                extra_ro_files=[cert, key] if https and custom else None,
            )
        )

    async def incoming(reader, writer):
        task = asyncio.current_task()
        if len(sessions) >= 32 or not child_pid:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            return
        sessions.add(task)
        try:
            await proxy_connection(
                reader, writer, address=address, expected_pid=child_pid[0]
            )
        except (ConnectionError, OSError):
            logger.debug("AppContainer client disconnected", exc_info=True)
        finally:
            sessions.discard(task)

    # Reserve the port before starting the child, avoiding an orphan on bind failure.
    server = await asyncio.start_server(incoming, host, port, ssl=tls)
    thread = threading.Thread(target=worker, name="AppContainer supervisor")
    try:
        thread.start()
        shutdown_sent = False
        shutdown_deadline = None
        while thread.is_alive():
            if quit_requested.is_set() and child_pid and not shutdown_sent:
                shutdown_sent = True
                shutdown_deadline = asyncio.get_running_loop().time() + 15
                try:
                    await request_child_shutdown(address, child_pid[0], token)
                except (OSError, RuntimeError, TimeoutError):
                    logger.warning(
                        "Graceful AppContainer shutdown failed", exc_info=True
                    )
                    stop.set()
            if (
                shutdown_deadline
                and asyncio.get_running_loop().time() > shutdown_deadline
            ):
                stop.set()
            await asyncio.sleep(0.1)
        if not results:
            raise RuntimeError("AppContainer supervisor exited without a result")
        return results[0]
    finally:
        server.close()
        await server.wait_closed()
        for task in tuple(sessions):
            task.cancel()
        if sessions:
            await asyncio.gather(*tuple(sessions), return_exceptions=True)
        stop.set()
        if thread.is_alive():
            await asyncio.to_thread(thread.join, 30)
        if thread.is_alive():
            raise RuntimeError("AppContainer supervisor cleanup did not finish")


def launch_brokered_backend(exe, argv, *, storage_dir, reticulum_config_dir, log_dir):
    try:
        return asyncio.run(
            _supervise(
                exe,
                argv,
                storage_dir=storage_dir,
                reticulum_config_dir=reticulum_config_dir,
                log_dir=log_dir,
            )
        )
    except Exception as exc:
        logger.exception("AppContainer broker failed")
        return sandbox.LaunchResult(
            ok=False, error=str(exc), used_appcontainer=False, fell_back=False
        )
