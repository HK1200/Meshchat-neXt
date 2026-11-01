import asyncio
import io
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from meshchatnext.src.backend import appcontainer_broker as broker


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_mode", ["auto", "1"])
async def test_supervisor_forces_containment_and_authenticated_graceful_quit(
    monkeypatch, tmp_path, requested_mode
):
    monkeypatch.setenv("MESHCHAT_APPCONTAINER", requested_mode)
    monkeypatch.setenv("MESHCHAT_APPCONTAINER_CONTROL_STDIN", "1")
    monkeypatch.setattr(
        broker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"meshchatnext-stop\n"))
    )
    monkeypatch.setattr(broker, "child_pipe_address", lambda leaf: "private-address")
    captured = {}

    def child(exe, argv, **kwargs):
        captured.update(kwargs)
        kwargs["on_child_started"](42)
        assert kwargs["stop_event"].wait(5), "supervisor must stop worker"
        return broker.sandbox.LaunchResult(
            ok=True, exit_code=0, used_appcontainer=True, fell_back=False
        )

    monkeypatch.setattr(broker.sandbox, "launch_backend_sandboxed", child)

    async def shutdown(address, pid, token):
        assert address == "private-address" and pid == 42
        assert len(token) == 64
        assert token == captured["env"]["MESHCHAT_APPCONTAINER_SHUTDOWN_TOKEN"]
        captured["stop_event"].set()

    shutdown_mock = AsyncMock(side_effect=shutdown)
    monkeypatch.setattr(broker, "request_child_shutdown", shutdown_mock)
    result = await asyncio.wait_for(
        broker._supervise(
            "backend",
            ["--no-https", "--port", str(free_port())],
            storage_dir=str(tmp_path),
            reticulum_config_dir=str(tmp_path),
            log_dir=str(tmp_path),
        ),
        8,
    )
    assert result.ok and result.used_appcontainer and not result.fell_back
    assert captured["forced"] is True
    assert captured["env"]["MESHCHAT_APPCONTAINER"] == requested_mode
    assert captured["extra_ro_files"] is None
    for name in ("TEMP", "TMP", "TMPDIR"):
        assert captured["env"][name] == str(tmp_path / ".appcontainer-temp")
    shutdown_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_port_bind_failure_never_spawns_child(monkeypatch, tmp_path):
    monkeypatch.setattr(broker, "child_pipe_address", lambda leaf: "private-address")
    child = Mock(side_effect=AssertionError("must not start before bind"))
    monkeypatch.setattr(broker.sandbox, "launch_backend_sandboxed", child)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(OSError):
            await broker._supervise(
                "backend",
                ["--no-https", "--port", str(listener.getsockname()[1])],
                storage_dir=str(tmp_path),
                reticulum_config_dir=str(tmp_path),
                log_dir=str(tmp_path),
            )
    child.assert_not_called()


@pytest.mark.asyncio
async def test_tls_failure_cannot_silently_downgrade(monkeypatch, tmp_path):
    child = Mock()
    monkeypatch.setattr(broker.sandbox, "launch_backend_sandboxed", child)
    with pytest.raises(OSError):
        await broker._supervise(
            "backend",
            [
                "--ssl-cert",
                str(tmp_path / "missing-cert"),
                "--ssl-key",
                str(tmp_path / "missing-key"),
            ],
            storage_dir=str(tmp_path),
            reticulum_config_dir=str(tmp_path),
            log_dir=str(tmp_path),
        )
    child.assert_not_called()


def test_broker_failure_reports_no_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        broker, "_supervise", AsyncMock(side_effect=PermissionError("blocked"))
    )
    result = broker.launch_brokered_backend(
        "backend",
        [],
        storage_dir=str(tmp_path),
        reticulum_config_dir=str(tmp_path),
        log_dir=str(tmp_path),
    )
    assert not result.ok and not result.used_appcontainer and not result.fell_back
    assert "blocked" in result.error


@pytest.mark.asyncio
async def test_supervisor_caps_sessions_and_cleans_up_on_cancel(monkeypatch, tmp_path):
    from tests.backend.test_appcontainer_pipe_transport import MemoryWriter

    monkeypatch.delenv("MESHCHAT_APPCONTAINER_CONTROL_STDIN", raising=False)
    monkeypatch.setattr(broker, "child_pipe_address", lambda leaf: "private")
    captured = {}
    server = SimpleNamespace(close=Mock(), wait_closed=AsyncMock())

    async def start(callback, *args, **kwargs):
        captured["incoming"] = callback
        return server

    def child(exe, argv, **kwargs):
        kwargs["on_child_started"](42)
        captured["started"] = True
        assert kwargs["stop_event"].wait(5)
        return broker.sandbox.LaunchResult(
            ok=True, exit_code=0, used_appcontainer=True, fell_back=False
        )

    entered = []

    async def proxy(reader, writer, **kwargs):
        entered.append(writer)
        try:
            await asyncio.Event().wait()
        finally:
            writer.close()

    monkeypatch.setattr(broker.asyncio, "start_server", start)
    monkeypatch.setattr(broker.sandbox, "launch_backend_sandboxed", child)
    monkeypatch.setattr(broker, "proxy_connection", proxy)
    supervisor = asyncio.create_task(
        broker._supervise(
            "backend",
            ["--no-https"],
            storage_dir=str(tmp_path),
            reticulum_config_dir=None,
            log_dir=None,
        )
    )
    clients = []
    try:
        for _ in range(100):
            if captured.get("started"):
                break
            await asyncio.sleep(0.001)
        assert captured.get("started")
        clients.extend(
            asyncio.create_task(captured["incoming"](None, MemoryWriter()))
            for _ in range(32)
        )
        await asyncio.sleep(0)
        assert len(entered) == 32
        excess = MemoryWriter()
        await captured["incoming"](None, excess)
        assert excess.closed
        excess.wait_closed.assert_awaited_once()
        assert len(entered) == 32
    finally:
        supervisor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await supervisor
        await asyncio.gather(*clients, return_exceptions=True)
    assert all(writer.closed for writer in entered)
    server.close.assert_called_once()
    server.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_static_files_stream_without_socket_sendfile(monkeypatch, tmp_path):
    """Exercise aiohttp in a fresh child with the actual broker environment."""
    import subprocess
    import sys

    monkeypatch.delenv("AIOHTTP_NOSENDFILE", raising=False)
    monkeypatch.delenv("MESHCHAT_APPCONTAINER_CONTROL_STDIN", raising=False)
    monkeypatch.setattr(broker, "child_pipe_address", lambda leaf: "private-address")
    asset = tmp_path / "asset.bin"
    asset.write_bytes(bytes(range(256)) * 3000)
    outcome = {}
    probe = r"""
import asyncio,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from aiohttp.web_fileresponse import FileResponse
async def main():
    payload=Path(sys.argv[1]).read_bytes()
    chunks=[]
    async def write(data): chunks.append(bytes(data))
    writer=SimpleNamespace(write=write,drain=AsyncMock())
    loop=asyncio.get_running_loop()
    unsupported=AsyncMock(side_effect=RuntimeError('sendfile unsupported for pipe transport'))
    request=SimpleNamespace(_loop=loop,transport=object())
    response=FileResponse(sys.argv[1],chunk_size=8192)
    with patch('aiohttp.web_fileresponse.StreamResponse.prepare',AsyncMock(return_value=writer)),patch.object(loop,'sendfile',unsupported):
        with open(sys.argv[1],'rb') as stream:
            await response._sendfile(request,stream,19,len(payload)-43)
    assert b''.join(chunks)==payload[19:-24]
    assert len(chunks)>1 and max(map(len,chunks))<=8192
    unsupported.assert_not_awaited()
    writer.drain.assert_awaited_once()
asyncio.run(main())
"""

    def child(exe, argv, **kwargs):
        result = subprocess.run(
            [sys.executable, "-c", probe, str(asset)],
            env=kwargs["env"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        outcome["result"] = result
        return broker.sandbox.LaunchResult(
            ok=result.returncode == 0,
            exit_code=result.returncode,
            used_appcontainer=True,
            fell_back=False,
        )

    monkeypatch.setattr(broker.sandbox, "launch_backend_sandboxed", child)
    result = await broker._supervise(
        "backend",
        ["--no-https", "--port", str(free_port())],
        storage_dir=str(tmp_path),
        reticulum_config_dir=str(tmp_path),
        log_dir=str(tmp_path),
    )
    assert result.ok, outcome["result"].stderr
    assert "AIOHTTP_NOSENDFILE" not in broker.os.environ
