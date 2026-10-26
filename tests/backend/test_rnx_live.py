# SPDX-License-Identifier: 0BSD

"""Live RNX session smoke tests.

These start real rnx subprocesses through RNXSession and drive them over a
local TCP Reticulum link. They are opt-in because they spawn Reticulum
processes and take a few seconds.

Enable with: MESHCHAT_LIVE_RNX=1
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import shutil
import socket
import tempfile
import textwrap
import time

import pytest

from meshchatnext.src.backend.rnx_manager import (
    _MESHCHATNEXT_RUN_MODULE_FLAG,
    _RNX_MODULE,
    RNXSession,
)

_RUN = os.environ.get("MESHCHAT_LIVE_RNX") == "1"
_RNX_AVAILABLE = importlib.util.find_spec(_RNX_MODULE) is not None


class _LiveManager:
    def __init__(self, reticulum_config_dir: str, storage_dir: str | None = None):
        self.reticulum_config_dir = reticulum_config_dir
        self.storage_dir = storage_dir or reticulum_config_dir
        self.changes = 0
        self.outputs = 0

    def _on_session_change(self, _session):
        self.changes += 1

    def _on_session_output(self, _session, _chunk):
        self.outputs += 1

    def save(self):
        return None


def _force_pipe_mode(monkeypatch, session_cls=RNXSession):
    # PTY children often get SIGHUP under pytest capture. Use pipes for live smoke.
    monkeypatch.setattr(session_cls, "_supports_pty", staticmethod(lambda: False))


def _wait_for_listen_address(session: RNXSession, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if session.listen_address:
            return session.listen_address
        if session.status == RNXSession.STATUS_FAILED:
            raise AssertionError(
                f"rnx failed before listen address: {session.last_error!r} "
                f"output={session.to_dict(include_output_tail=True).get('output_text')!r}",
            )
        time.sleep(0.2)
    payload = session.to_dict(include_output_tail=True)
    raise AssertionError(
        f"timed out waiting for rnx listen address; status={session.status} "
        f"output={payload.get('output_text')!r}",
    )


def _wait_for_output(
    session: RNXSession,
    needle: str,
    timeout: float = 35.0,
) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = session.to_dict(include_output_tail=True)
        text = payload.get("output_text") or ""
        if needle in text:
            return text
        if session.status == RNXSession.STATUS_FAILED:
            raise AssertionError(
                f"session failed before output {needle!r}: {session.last_error!r} "
                f"output={text!r}",
            )
        if (
            session.status != RNXSession.STATUS_RUNNING
            and needle not in text
            and session._process is None
        ):
            raise AssertionError(
                f"session stopped before output {needle!r}; status={session.status} "
                f"exit={session.last_exit_code} output={text!r}",
            )
        time.sleep(0.25)
    payload = session.to_dict(include_output_tail=True)
    raise AssertionError(
        f"timed out waiting for {needle!r}; status={session.status} "
        f"output={payload.get('output_text')!r}",
    )


def _write_tcp_pair(listen_dir: str, conn_dir: str, port: int) -> None:
    listen_cfg = textwrap.dedent(
        f"""\
        [reticulum]
          enable_transport = Yes
          share_instance = No
          shared_instance_port = {37000 + (port % 1000)}
          instance_name = rnx_live_listen_{port}
          panic_on_interface_error = No

        [logging]
          loglevel = 4

        [interfaces]
          [[TCP Server]]
            type = TCPServerInterface
            enabled = Yes
            listen_ip = 127.0.0.1
            listen_port = {port}
        """,
    )
    conn_cfg = textwrap.dedent(
        f"""\
        [reticulum]
          enable_transport = Yes
          share_instance = No
          shared_instance_port = {38000 + (port % 1000)}
          instance_name = rnx_live_conn_{port}
          panic_on_interface_error = No

        [logging]
          loglevel = 4

        [interfaces]
          [[TCP Client]]
            type = TCPClientInterface
            enabled = Yes
            target_host = 127.0.0.1
            target_port = {port}
        """,
    )
    os.makedirs(listen_dir, exist_ok=True)
    os.makedirs(conn_dir, exist_ok=True)
    with open(os.path.join(listen_dir, "config"), "w", encoding="utf-8") as handle:  # nosec: PTC-W6004
        handle.write(listen_cfg)
    with open(os.path.join(conn_dir, "config"), "w", encoding="utf-8") as handle:
        handle.write(conn_cfg)


@pytest.mark.integration
@pytest.mark.skipif(not _RUN, reason="Set MESHCHAT_LIVE_RNX=1 to run live RNX tests")
@pytest.mark.skipif(
    not _RNX_AVAILABLE,
    reason="RNS.Utilities.rnx is not installed",
)
def test_rnx_live_listen_session_reports_address(monkeypatch):
    _force_pipe_mode(monkeypatch)
    tmpdir = tempfile.mkdtemp(prefix="meshchat_rnx_live_")
    manager = _LiveManager(tmpdir)
    session = RNXSession(
        manager,
        "live-listen",
        {
            "mode": "listen",
            "no_auth": True,
            "quiet": 1,
            "config_path": tmpdir,
        },
    )
    try:
        started = session.start()
        assert started["status"] == RNXSession.STATUS_RUNNING
        assert started["pid"]
        assert "-m" in started["last_command"] or "rnx" in started["last_command"]
        assert "--meshchatnext-run-module" not in started["last_command"]
        env = session._build_env()
        assert env.get("PYTHONUNBUFFERED") == "1"

        address = _wait_for_listen_address(session)
        assert len(address) >= 16
        assert all(ch in "0123456789abcdef" for ch in address)
        assert session.status == RNXSession.STATUS_RUNNING
    finally:
        session.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)

    assert session.status == RNXSession.STATUS_STOPPED
    assert session.listen_address


@pytest.mark.integration
@pytest.mark.skipif(not _RUN, reason="Set MESHCHAT_LIVE_RNX=1 to run live RNX tests")
@pytest.mark.skipif(
    not _RNX_AVAILABLE,
    reason="RNS.Utilities.rnx is not installed",
)
def test_rnx_live_meshchatnext_run_module_launcher_starts_listener(
    monkeypatch, tmp_path
):
    """Frozen-style launcher: Meshchat neXt re-entry flag, executed via a shim script."""
    from meshchatnext.src.backend import rnx_manager as rnx_mod

    shim = tmp_path / "meshchatnext_shim.py"
    shim.write_text(
        textwrap.dedent(
            """            import runpy
            import sys

            marker = "--meshchatnext-run-module"
            if len(sys.argv) < 3 or sys.argv[1] != marker:
                raise SystemExit("shim expected --meshchatnext-run-module")
            module_name = sys.argv[2]
            sys.argv = [sys.argv[0], *sys.argv[3:]]
            runpy.run_module(module_name, run_name="__main__", alter_sys=True)
            """,
        ),
        encoding="utf-8",
    )

    real_python = rnx_mod.sys.executable

    def _frozen_style_launcher():
        return [real_python, str(shim), _MESHCHATNEXT_RUN_MODULE_FLAG, _RNX_MODULE]

    monkeypatch.setattr(rnx_mod.RNXSession, "_is_frozen_executable", lambda: True)
    monkeypatch.setattr(
        rnx_mod.RNXSession,
        "_resolve_rnx_launcher",
        staticmethod(_frozen_style_launcher),
    )
    _force_pipe_mode(monkeypatch, rnx_mod.RNXSession)

    tmpdir = tempfile.mkdtemp(prefix="meshchat_rnx_runmod_live_")
    manager = _LiveManager(tmpdir)
    session = rnx_mod.RNXSession(
        manager,
        "live-run-module",
        {
            "mode": "listen",
            "no_auth": True,
            "quiet": 1,
            "config_path": tmpdir,
        },
    )
    try:
        command = session._build_command()
        assert command[1:4] == [str(shim), _MESHCHATNEXT_RUN_MODULE_FLAG, _RNX_MODULE]
        assert "-m" not in command
        started = session.start()
        assert started["status"] == RNXSession.STATUS_RUNNING
        assert _MESHCHATNEXT_RUN_MODULE_FLAG in started["last_command"]
        address = _wait_for_listen_address(session)
        assert len(address) >= 16
    finally:
        session.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.skipif(not _RUN, reason="Set MESHCHAT_LIVE_RNX=1 to run live RNX tests")
@pytest.mark.skipif(
    not _RNX_AVAILABLE,
    reason="RNS.Utilities.rnx is not installed",
)
def test_rnx_live_listen_execute_echo_roundtrip(monkeypatch):
    """Full listener/executor path over a local TCP Reticulum link.

    The executor runs a one-shot remote command and exits, so pipe mode is
    fine for both ends. The command output must come back through the link.
    """
    _force_pipe_mode(monkeypatch)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    listen_dir = tempfile.mkdtemp(prefix="meshchat_rnx_e2e_listen_")
    conn_dir = tempfile.mkdtemp(prefix="meshchat_rnx_e2e_conn_")
    _write_tcp_pair(listen_dir, conn_dir, port)

    listen_manager = _LiveManager(listen_dir)
    conn_manager = _LiveManager(conn_dir)
    listen = RNXSession(
        listen_manager,
        "e2e-listen",
        {
            "mode": "listen",
            "no_auth": True,
            "quiet": 1,
            "config_path": listen_dir,
        },
    )
    execute = RNXSession(
        conn_manager,
        "e2e-execute",
        {
            "mode": "execute",
            "destination": "pending",
            "config_path": conn_dir,
            "remote_command": "echo MESHCHAT_RNX_E2E_OK",
            "quiet": 1,
            "timeout": 30,
        },
    )
    try:
        listen.start()
        # Quiet listeners emit nothing: the manager derives the address
        # from the identity file rather than parsing subprocess output.
        address = _wait_for_listen_address(listen, timeout=30.0)
        assert listen.listen_address == address

        # Allow TCP link + announce to settle before the executor path request.
        time.sleep(2.0)

        execute.config["destination"] = address
        execute.start()
        assert execute.status == RNXSession.STATUS_RUNNING

        output = _wait_for_output(execute, "MESHCHAT_RNX_E2E_OK", timeout=40.0)
        assert "MESHCHAT_RNX_E2E_OK" in output

        deadline = time.time() + 20.0
        while time.time() < deadline and execute.status == RNXSession.STATUS_RUNNING:
            time.sleep(0.2)
        assert execute.status in (
            RNXSession.STATUS_STOPPED,
            RNXSession.STATUS_FAILED,
        )
        if execute.last_exit_code is not None:
            assert execute.last_exit_code == 0
    finally:
        with contextlib.suppress(Exception):
            execute.stop()
        with contextlib.suppress(Exception):
            listen.stop()
        shutil.rmtree(listen_dir, ignore_errors=True)
        shutil.rmtree(conn_dir, ignore_errors=True)
