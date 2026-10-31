import asyncio
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend import appcontainer_pipe as pipe


class MemoryWriter:
    def __init__(self):
        self.data = bytearray()
        self.closed = False
        self.wait_closed = AsyncMock()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        await asyncio.sleep(0)

    def can_write_eof(self):
        return False

    def close(self):
        self.closed = True


def reader_with(data):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_proxy_forwards_both_directions_and_closes(monkeypatch):
    client = MemoryWriter()
    child = MemoryWriter()
    connector = AsyncMock(return_value=(reader_with(b"child response"), child))
    monkeypatch.setattr(pipe, "connect_child_pipe", connector)
    await pipe.proxy_connection(
        reader_with(b"client request"), client, address="private", expected_pid=42
    )
    connector.assert_awaited_once_with("private", 42)
    assert child.data == b"client request"
    assert client.data == b"child response"
    assert child.closed and client.closed
    client.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_proxy_connection_failure_closes_client(monkeypatch):
    client = MemoryWriter()
    monkeypatch.setattr(
        pipe, "connect_child_pipe", AsyncMock(side_effect=PermissionError("wrong PID"))
    )
    with pytest.raises(PermissionError, match="wrong PID"):
        await pipe.proxy_connection(
            reader_with(b"secret"), client, address="private", expected_pid=42
        )
    assert client.closed and client.data == b""
    client.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,accepted",
    [
        (b"HTTP/1.1 200 OK\r\n", True),
        (b"HTTP/1.1 403 Forbidden\r\n", False),
        (b"", False),
    ],
)
async def test_shutdown_is_authenticated_and_response_checked(
    monkeypatch, response, accepted
):
    writer = MemoryWriter()
    connector = AsyncMock(return_value=(reader_with(response), writer))
    monkeypatch.setattr(pipe, "connect_child_pipe", connector)
    if accepted:
        await pipe.request_child_shutdown("private", 42, "a" * 64)
    else:
        with pytest.raises(RuntimeError, match="refused"):
            await pipe.request_child_shutdown("private", 42, "a" * 64)
    connector.assert_awaited_once_with("private", 42)
    assert b"POST /__meshchatnext_container_quit__ HTTP/1.1" in writer.data
    assert b"X-MeshchatNext-Supervisor: " + b"a" * 64 in writer.data
    assert writer.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("address,pid", [("bad", 42), ("private", 0), ("private", -1)])
async def test_pipe_target_rejects_invalid_identity_before_windows_api(address, pid):
    with pytest.raises(ValueError, match="Invalid broker target"):
        await pipe.connect_child_pipe(address, pid)


def test_pipe_server_requires_actual_container_token(monkeypatch):
    from meshchatnext.src.backend import appcontainer_security

    monkeypatch.setattr(appcontainer_security, "is_appcontainer_process", lambda: False)
    with pytest.raises(RuntimeError, match="requires an AppContainer token"):
        pipe.run_private_pipe_app(
            None, address="private", use_https=True, shutdown_callback=None
        )


def test_pipe_server_rejects_missing_control_token(monkeypatch):
    from meshchatnext.src.backend import appcontainer_security

    monkeypatch.setattr(appcontainer_security, "is_appcontainer_process", lambda: True)
    monkeypatch.delenv("MESHCHAT_APPCONTAINER_SHUTDOWN_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="Missing private supervisor"):
        pipe.run_private_pipe_app(
            None, address="private", use_https=True, shutdown_callback=None
        )


@pytest.mark.asyncio
async def test_client_half_close_does_not_truncate_delayed_response(monkeypatch):
    client = MemoryWriter()
    child = MemoryWriter()
    response = asyncio.StreamReader()
    monkeypatch.setattr(
        pipe, "connect_child_pipe", AsyncMock(return_value=(response, child))
    )

    async def respond():
        await asyncio.sleep(0.02)
        response.feed_data(b"complete delayed response")
        response.feed_eof()

    producer = asyncio.create_task(respond())
    try:
        await pipe.proxy_connection(
            reader_with(b"request"), client, address="private", expected_pid=42
        )
        assert client.data == b"complete delayed response"
        assert child.closed and client.closed
    finally:
        await producer


@pytest.mark.asyncio
async def test_proxy_cancellation_after_client_eof_closes_both_ends(monkeypatch):
    client, child = MemoryWriter(), MemoryWriter()
    response = asyncio.StreamReader()
    monkeypatch.setattr(
        pipe, "connect_child_pipe", AsyncMock(return_value=(response, child))
    )
    task = asyncio.create_task(
        pipe.proxy_connection(
            reader_with(b"request"), client, address="private", expected_pid=42
        )
    )
    await asyncio.sleep(0.01)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed and child.closed


@pytest.mark.asyncio
async def test_proxy_propagates_supported_half_close(monkeypatch):
    client, child = MemoryWriter(), MemoryWriter()
    response = asyncio.StreamReader()
    child.can_write_eof = lambda: True

    def eof():
        response.feed_data(b"response after EOF")
        response.feed_eof()

    child.write_eof = eof
    monkeypatch.setattr(
        pipe, "connect_child_pipe", AsyncMock(return_value=(response, child))
    )
    await pipe.proxy_connection(
        reader_with(b"request"), client, address="private", expected_pid=42
    )
    assert client.data == b"response after EOF"
    assert client.closed and child.closed
