# SPDX-License-Identifier: 0BSD

"""Cross-event-loop forwarding for ReticulumMeshChat.websocket_broadcast.

Per-identity background loops run asyncio.run on daemon threads, so a
broadcast awaited from them lands on a foreign loop. The send must be
re-dispatched onto AsyncUtils.main_loop where the aiohttp transports live.
"""

from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import patch

import pytest

from meshchatnext.meshchat import ReticulumMeshChat
from meshchatnext.src.backend.async_utils import AsyncUtils as RealAsyncUtils


class _FakeWs:
    """Plain object so attribute probes behave like a real ws client."""


def _bare_app():
    app = ReticulumMeshChat.__new__(ReticulumMeshChat)
    app.websocket_clients = []
    app.ws_seq_state = None
    app.ws_counters = None
    app._ws_coalesce = None
    app._websocket_broadcast_lock = asyncio.Lock()
    return app


@pytest.fixture
def foreign_main_loop():
    # The autouse global_mocks fixture replaces meshchatnext.meshchat.AsyncUtils
    # with a MagicMock, so swap the real class back for these tests.
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    old = RealAsyncUtils.main_loop
    RealAsyncUtils.main_loop = loop
    try:
        with patch("meshchatnext.meshchat.AsyncUtils", RealAsyncUtils):
            yield loop
    finally:
        RealAsyncUtils.main_loop = old
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()


async def test_broadcast_from_foreign_loop_sends_on_main_loop(foreign_main_loop):
    app = _bare_app()
    seen = {}
    client = _FakeWs()

    async def send_str(data):
        seen["on_main_loop"] = asyncio.get_running_loop() is foreign_main_loop
        seen["payload"] = json.loads(data)

    client.send_str = send_str
    app.websocket_clients = [client]

    # This coroutine runs on the pytest loop while AsyncUtils.main_loop
    # points at a different running loop, matching the daemon-thread case.
    await app.websocket_broadcast(json.dumps({"type": "test.event"}))

    assert seen["on_main_loop"] is True
    assert seen["payload"]["type"] == "test.event"


async def test_broadcast_on_main_loop_sends_inline():
    app = _bare_app()
    seen = {}
    client = _FakeWs()

    async def send_str(data):
        seen["loop"] = asyncio.get_running_loop()

    client.send_str = send_str
    app.websocket_clients = [client]

    old = RealAsyncUtils.main_loop
    RealAsyncUtils.main_loop = asyncio.get_running_loop()
    try:
        with patch("meshchatnext.meshchat.AsyncUtils", RealAsyncUtils):
            await app.websocket_broadcast(json.dumps({"type": "test.event"}))
    finally:
        RealAsyncUtils.main_loop = old

    assert seen["loop"] is asyncio.get_running_loop()


class _ExplodingLock:
    """Fails the test if the broadcast touches the shared asyncio lock."""

    async def __aenter__(self):
        raise AssertionError("broadcast touched the shared lock on a foreign loop")

    async def __aexit__(self, *exc):
        return False


async def test_broadcast_from_foreign_loop_drops_when_main_loop_dead():
    app = _bare_app()
    app._websocket_broadcast_lock = _ExplodingLock()
    client = _FakeWs()
    client.send_str = lambda data: pytest.fail("send attempted after main loop died")
    app.websocket_clients = [client]

    # A loop that is not running models the shutdown window: the aiohttp
    # loop has stopped but AsyncUtils.main_loop still points at it.
    dead_loop = asyncio.new_event_loop()

    old = RealAsyncUtils.main_loop
    RealAsyncUtils.main_loop = dead_loop
    try:
        with patch("meshchatnext.meshchat.AsyncUtils", RealAsyncUtils):
            await app.websocket_broadcast(json.dumps({"type": "test.event"}))
    finally:
        RealAsyncUtils.main_loop = old
        dead_loop.close()


async def test_android_hook_keeps_scheduled_announces_running(
    foreign_main_loop, monkeypatch, db,
):
    """The Android hook must preserve internal cross-loop broadcast options."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from meshchatnext import android_push_bridge
    from meshchatnext.src.backend.config_manager import ConfigManager

    class AndroidApp(ReticulumMeshChat):
        pass

    monkeypatch.setattr(android_push_bridge, "_ws_hook_installed", False)
    monkeypatch.setattr(android_push_bridge, "_is_chaquopy_android", lambda: True)
    notifications = []
    monkeypatch.setattr(android_push_bridge, "_notify_java", lambda *a: notifications.append(a))
    android_push_bridge.install_websocket_hook(AndroidApp)
    app = AndroidApp.__new__(AndroidApp)
    app.__dict__.update(_bare_app().__dict__)
    app.running = True
    app.demo_mode = False
    config = ConfigManager(db)
    config.auto_announce_enabled.set(True)
    config.auto_announce_interval_seconds.set(60)
    config.telephone_announce_enabled.set(True)
    ctx = SimpleNamespace(
        config=config, running=True, session_id="android-test", identity_hash="test",
        message_router=MagicMock(), telephone_manager=MagicMock(),
        local_lxmf_destination=SimpleNamespace(hash=b"test"), forwarding_manager=None,
    )
    app.current_context = ctx
    clock = [1000.0]
    monkeypatch.setattr("meshchatnext.meshchat.time.time", lambda: clock[0])
    ticks = []

    async def next_tick(seconds):
        ticks.append(seconds)
        clock[0] += 61
        if len(ticks) == 2:
            ctx.running = False

    monkeypatch.setattr("meshchatnext.meshchat.asyncio.sleep", next_tick)
    await app.announce_loop("android-test", context=ctx)
    assert ctx.message_router.announce.call_count == 2
    assert ctx.telephone_manager.announce.call_count == 2
    assert config.last_announced_at.get() == 1061
    assert notifications == []  # Announcing is not an incoming-message alert.
