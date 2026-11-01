# SPDX-License-Identifier: 0BSD
"""Private LPAC HTTP pipe and loopback TLS broker.

No network exemptions. The broker opens the child pipe with anonymous SQOS,
verifies the server PID and forwards bytes only; it exposes no file/command API.
"""

from __future__ import annotations

import asyncio
import ctypes
import hmac
import re

from aiohttp import web

from meshchatnext.src.backend.appcontainer_security import token_sid
from meshchatnext.src.env_utils import env_str

PIPE_PREFIX = "MeshchatNext-"


def _kernel():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _close(handle):
    fn = _kernel().CloseHandle
    fn.argtypes = [ctypes.c_void_p]
    fn(handle)


def private_pipe_sddl():
    # Deny network logons; only the current user and this actual container SID.
    return f"D:P(D;;GA;;;NU)(A;;GA;;;{token_sid(1)})(A;;GA;;;{token_sid(31)})"


def _new_pipe(address, sddl, first):
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    descriptor = ctypes.c_void_p()
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("descriptor", ctypes.c_void_p),
            ("inherit", ctypes.c_int),
        ]

    attributes = SecurityAttributes(
        ctypes.sizeof(SecurityAttributes), descriptor, False
    )
    kernel = _kernel()
    create = kernel.CreateNamedPipeW
    create.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(SecurityAttributes),
    ]
    create.restype = ctypes.c_void_p
    try:
        # Overlapped duplex byte pipe; reject remote clients in the kernel.
        flags = 3 | 0x40000000 | (0x00080000 if first else 0)
        handle = create(
            address, flags, 0x8, 64, 65536, 65536, 0, ctypes.byref(attributes)
        )
        if handle in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        return handle
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(descriptor)


class PipeListener:
    def __init__(self, address, protocol_factory):
        if not re.fullmatch(r"\\\\\.\\pipe\\LOCAL\\MeshchatNext-[0-9a-f]{32}", address):
            raise ValueError("Invalid private AppContainer pipe name")
        from asyncio.windows_events import PipeServer
        from asyncio.windows_utils import PipeHandle

        sddl = private_pipe_sddl()

        class RestrictedPipeServer(PipeServer):
            def _server_pipe_handle(self, first):
                if self.closed():
                    return None
                pipe = PipeHandle(_new_pipe(self._address, sddl, first))
                self._free_instances.add(pipe)
                return pipe

        self.server = RestrictedPipeServer(address)
        self.factory = protocol_factory
        self.task = asyncio.create_task(self._accept())

    async def _accept(self):
        loop = asyncio.get_running_loop()
        pipe = None
        try:
            while not self.server.closed():
                pipe = self.server._get_unconnected_pipe()
                await loop._proactor.accept_pipe(pipe)
                self.server._free_instances.discard(pipe)
                if self.server.closed():
                    pipe.close()
                    break
                loop._make_duplex_pipe_transport(
                    pipe, self.factory(), extra={"meshchat_private_pipe": True}
                )
                pipe = None
        except asyncio.CancelledError:
            pass
        finally:
            if pipe is not None:
                pipe.close()

    def close(self):
        self.task.cancel()
        self.server.close()

    async def wait_closed(self):
        await self.task


class PrivatePipeSite(web.BaseSite):
    def __init__(self, runner, address):
        super().__init__(runner)
        self.address = address

    @property
    def name(self):
        return self.address

    async def start(self):
        await super().start()
        self._server = PipeListener(self.address, self._runner.server)


def trusted_pipe_middleware(scheme, *, shutdown_token=None, shutdown_callback=None):
    if scheme not in ("http", "https"):
        raise ValueError("Invalid broker scheme")

    @web.middleware
    async def middleware(request, handler):
        if request.transport is None or not request.transport.get_extra_info(
            "meshchat_private_pipe"
        ):
            raise web.HTTPForbidden(text="Private pipe required")
        if request.path == "/__meshchatnext_container_quit__":
            supplied = request.headers.get("X-MeshchatNext-Supervisor", "")
            if (
                request.method != "POST"
                or not re.fullmatch(r"[0-9a-f]{64}", supplied)
                or not shutdown_token
                or not hmac.compare_digest(supplied, shutdown_token)
                or shutdown_callback is None
            ):
                raise web.HTTPForbidden()

            callback = shutdown_callback

            async def finish():
                await asyncio.sleep(0.1)
                await callback()

            request.app["meshchatnext_container_quit_task"] = asyncio.create_task(
                finish()
            )
            return web.Response(text="Shutting down")
        return await handler(request.clone(scheme=scheme, remote="127.0.0.1"))

    return middleware


async def connect_child_pipe(address, expected_pid):
    if expected_pid <= 0 or not address.startswith("\\\\.\\pipe\\Sessions\\"):
        raise ValueError("Invalid broker target")
    kernel = _kernel()
    create = kernel.CreateFileW
    create.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    create.restype = ctypes.c_void_p
    # SECURITY_SQOS_PRESENT with SECURITY_ANONYMOUS (zero) blocks impersonation.
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        handle = create(address, 0xC0000000, 0, None, 3, 0x40000000 | 0x00100000, None)
        if handle not in (None, ctypes.c_void_p(-1).value):
            break
        error = ctypes.get_last_error()
        if error not in (2, 231) or asyncio.get_running_loop().time() >= deadline:
            raise ctypes.WinError(error)
        await asyncio.sleep(0.02)
    try:
        query = kernel.GetNamedPipeServerProcessId
        query.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        pid = ctypes.c_ulong()
        if not query(handle, ctypes.byref(pid)) or pid.value != expected_pid:
            raise PermissionError("Private pipe server PID mismatch")
        from asyncio.windows_utils import PipeHandle

        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader(limit=65536)
        protocol = asyncio.StreamReaderProtocol(reader)
        waiter = loop.create_future()
        pipe_handle = PipeHandle(handle)
        handle = None  # PipeHandle owns it from this point, including failures.
        try:
            transport = loop._make_duplex_pipe_transport(pipe_handle, protocol, waiter)
        except BaseException:
            pipe_handle.close()
            raise
        try:
            await waiter
        except BaseException:
            transport.close()
            raise
        return reader, asyncio.StreamWriter(transport, protocol, reader, loop)
    finally:
        if handle is not None:
            _close(handle)


async def proxy_connection(reader, writer, *, address, expected_pid):
    pipe_writer = None
    tasks = []
    try:
        pipe_reader, pipe_writer = await connect_child_pipe(address, expected_pid)

        async def copy(source, destination):
            while data := await source.read(65536):
                destination.write(data)
                await destination.drain()

        tasks = [
            asyncio.create_task(copy(reader, pipe_writer)),
            asyncio.create_task(copy(pipe_reader, writer)),
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        # A client may finish sending while the backend is still responding.
        # Keep the response direction alive; supervisor cancellation still owns
        # the lifetime of this bounded session. Named pipes cannot half-close.
        if tasks[0] in done and tasks[1] not in done:
            if pipe_writer.can_write_eof():
                pipe_writer.write_eof()
            await tasks[1]
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if pipe_writer is not None:
            pipe_writer.close()
        writer.close()
        await writer.wait_closed()


def run_private_pipe_app(app, *, address, use_https, shutdown_callback):
    """Serve HTTP only on the private pipe; the supervisor terminates TLS."""
    from meshchatnext.src.backend.appcontainer_security import is_appcontainer_process

    if not is_appcontainer_process():
        raise RuntimeError("Private pipe server requires an AppContainer token")
    token = env_str("MESHCHAT_APPCONTAINER_SHUTDOWN_TOKEN") or ""
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise RuntimeError("Missing private supervisor shutdown token")
    app.middlewares.insert(
        0,
        trusted_pipe_middleware(
            "https" if use_https else "http",
            shutdown_token=token,
            shutdown_callback=shutdown_callback,
        ),
    )

    async def sites():
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            await PrivatePipeSite(runner, address).start()
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    asyncio.run(sites())


async def request_child_shutdown(address, expected_pid, token):
    """One bounded, authenticated control operation over the private pipe."""
    reader, writer = await connect_child_pipe(address, expected_pid)
    try:
        writer.write(
            (
                "POST /__meshchatnext_container_quit__ HTTP/1.1\r\n"
                "Host: localhost\r\nContent-Length: 0\r\nConnection: close\r\n"
                f"X-MeshchatNext-Supervisor: {token}\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), 5)
        if not line.startswith(b"HTTP/1.1 200 "):
            raise RuntimeError("Contained backend refused supervisor shutdown")
    finally:
        writer.close()
