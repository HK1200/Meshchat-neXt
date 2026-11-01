import asyncio
import ctypes
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from meshchatnext.src.backend import appcontainer_pipe as pipe


class Call:
    def __init__(self, callback):
        self.callback = callback
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


def error(code):
    return OSError(code, "native failure")


@pytest.mark.parametrize("mode", ["success", "convert-denied", "create-denied"])
@pytest.mark.parametrize("first", [False, True])
def test_pipe_creation_is_private_local_bounded_and_frees_descriptor(
    monkeypatch, mode, first
):
    def convert(sddl, revision, out, size):
        assert sddl == "private-only" and revision == 1
        ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(42)
        return mode != "convert-denied"

    native_create = Call(lambda *args: None if mode == "create-denied" else 123)
    free = Call(lambda _: None)
    kernel = SimpleNamespace(CreateNamedPipeW=native_create, LocalFree=free)
    advapi = SimpleNamespace(
        ConvertStringSecurityDescriptorToSecurityDescriptorW=Call(convert)
    )
    monkeypatch.setattr(pipe, "_kernel", lambda: kernel)
    monkeypatch.setattr(pipe.ctypes, "WinDLL", lambda *a, **k: advapi, raising=False)
    monkeypatch.setattr(pipe.ctypes, "WinError", error, raising=False)
    monkeypatch.setattr(pipe.ctypes, "get_last_error", lambda: 5, raising=False)
    if mode == "success":
        assert pipe._new_pipe("private-address", "private-only", first) == 123
    else:
        with pytest.raises(OSError):
            pipe._new_pipe("private-address", "private-only", first)
    assert len(free.calls) == (0 if mode == "convert-denied" else 1)
    if native_create.calls:
        address, flags, pipe_mode, instances, out_size, in_size, timeout, attributes = (
            native_create.calls[0]
        )
        assert address == "private-address"
        assert flags == 3 | 0x40000000 | (0x00080000 if first else 0)
        assert pipe_mode == 0x8  # Kernel rejects remote clients.
        assert (instances, out_size, in_size, timeout) == (64, 65536, 65536, 0)
        assert attributes is not None


def test_pipe_acl_uses_actual_user_and_container_not_environment(monkeypatch):
    sid = Mock(
        side_effect=lambda kind: "S-1-5-21-user" if kind == 1 else "S-1-15-2-container"
    )
    monkeypatch.setattr(pipe, "token_sid", sid)
    assert (
        pipe.private_pipe_sddl()
        == "D:P(D;;GA;;;NU)(A;;GA;;;S-1-5-21-user)(A;;GA;;;S-1-15-2-container)"
    )
    assert [call.args for call in sid.call_args_list] == [(1,), (31,)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "retry",
        "open-denied",
        "pid-mismatch",
        "pid-query-denied",
        "transport-failure",
        "waiter-failure",
        "waiter-cancel",
    ],
)
async def test_client_uses_anonymous_qos_verifies_server_pid_and_cleans_up(
    monkeypatch, mode
):
    attempts = 0

    def create(*args):
        nonlocal attempts
        attempts += 1
        return (
            None
            if mode == "open-denied" or (mode == "retry" and attempts == 1)
            else 123
        )

    def query(handle, output):
        assert handle == 123
        ctypes.cast(output, ctypes.POINTER(ctypes.c_ulong))[0] = (
            99 if mode == "pid-mismatch" else 42
        )
        return mode != "pid-query-denied"

    kernel = SimpleNamespace(
        CreateFileW=Call(create), GetNamedPipeServerProcessId=Call(query)
    )
    monkeypatch.setattr(pipe, "_kernel", lambda: kernel)
    monkeypatch.setattr(
        pipe.ctypes,
        "get_last_error",
        lambda: 2 if mode == "retry" else 5,
        raising=False,
    )
    monkeypatch.setattr(pipe.ctypes, "WinError", error, raising=False)
    close = Mock()
    monkeypatch.setattr(pipe, "_close", close)
    handles = []

    class Handle:
        def __init__(self, value):
            self.value = value
            self.closed = False
            handles.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setitem(
        sys.modules, "asyncio.windows_utils", SimpleNamespace(PipeHandle=Handle)
    )
    transport = SimpleNamespace(close=Mock(), is_closing=lambda: True)
    loop = asyncio.get_running_loop()

    def make_transport(handle, protocol, waiter):
        assert handle.value == 123
        if mode == "transport-failure":
            raise RuntimeError("transport failed")
        if mode == "waiter-failure":
            waiter.set_exception(RuntimeError("connection failed"))
        elif mode == "waiter-cancel":
            waiter.cancel()
        else:
            waiter.set_result(None)
        return transport

    monkeypatch.setattr(
        loop, "_make_duplex_pipe_transport", make_transport, raising=False
    )
    if mode in ("success", "retry"):
        reader, writer = await pipe.connect_child_pipe(r"\\.\pipe\Sessions\private", 42)
        assert isinstance(reader, asyncio.StreamReader)
        assert len(handles) == 1
        close.assert_not_called()  # Ownership transferred to the pipe transport.
        writer.close()
        transport.close.assert_called_once()
    else:
        with pytest.raises((OSError, RuntimeError, asyncio.CancelledError)):
            await pipe.connect_child_pipe(r"\\.\pipe\Sessions\private", 42)
        if mode == "transport-failure":
            # Once wrapped, only PipeHandle owns the raw OS handle.
            assert handles[0].closed
            close.assert_not_called()
        elif mode in ("waiter-failure", "waiter-cancel"):
            transport.close.assert_called_once()
            close.assert_not_called()
        else:
            assert close.call_count == (0 if mode == "open-denied" else 1)
    for args in kernel.CreateFileW.calls:
        assert args[1:] == (0xC0000000, 0, None, 3, 0x40000000 | 0x00100000, None)
    assert attempts == (2 if mode == "retry" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["accepted", "cancelled", "closed-during-accept"])
async def test_listener_accept_close_and_cancel_cleanup(monkeypatch, mode):
    handles = []
    servers = []
    transports = []

    class Handle:
        def __init__(self, value):
            self.value = value
            self.closed = False
            handles.append(self)

        def close(self):
            self.closed = True

    class Server:
        def __init__(self, address):
            self._address = address
            self._free_instances = set()
            self._closed = False
            servers.append(self)

        def closed(self):
            return self._closed

        def close(self):
            self._closed = True

        def _get_unconnected_pipe(self):
            return self._server_pipe_handle(False)

    async def accept(handle):
        if mode == "cancelled":
            raise asyncio.CancelledError
        if mode == "closed-during-accept":
            servers[0].close()

    def transport(handle, protocol, **kwargs):
        transports.append((handle, protocol, kwargs))
        servers[0].close()

    fake_loop = SimpleNamespace(
        _proactor=SimpleNamespace(accept_pipe=accept),
        _make_duplex_pipe_transport=transport,
    )
    monkeypatch.setitem(
        sys.modules, "asyncio.windows_events", SimpleNamespace(PipeServer=Server)
    )
    monkeypatch.setitem(
        sys.modules, "asyncio.windows_utils", SimpleNamespace(PipeHandle=Handle)
    )
    monkeypatch.setattr(pipe.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(pipe, "private_pipe_sddl", lambda: "private-sddl")
    create = Mock(return_value=123)
    monkeypatch.setattr(pipe, "_new_pipe", create)
    factory = Mock(return_value="protocol")
    listener = pipe.PipeListener(r"\\.\pipe\LOCAL\MeshchatNext-" + "a" * 32, factory)
    await listener.wait_closed()
    assert create.call_args.args[1:] == ("private-sddl", False)
    if mode == "accepted":
        assert transports == [
            (handles[0], "protocol", {"extra": {"meshchat_private_pipe": True}})
        ]
        assert not handles[0].closed
        assert not servers[0]._free_instances
    else:
        assert not transports and handles[0].closed
    listener.close()
    assert servers[0].closed()


def test_listener_rejects_outside_pipe_namespace():
    with pytest.raises(ValueError, match="Invalid private"):
        pipe.PipeListener(r"\\remote\pipe\outside", Mock())


@pytest.mark.asyncio
async def test_private_site_registers_listener_with_runner(monkeypatch):
    from aiohttp import web

    runner = web.AppRunner(web.Application())
    await runner.setup()
    listener = SimpleNamespace(close=Mock(), wait_closed=AsyncMock())
    factory = Mock(return_value=listener)
    monkeypatch.setattr(pipe, "PipeListener", factory)
    site = pipe.PrivatePipeSite(runner, "private")
    try:
        await site.start()
        assert site.name == "private"
        assert site in runner.sites
        factory.assert_called_once_with("private", runner.server)
    finally:
        await runner.cleanup()
    listener.close.assert_called_once()
