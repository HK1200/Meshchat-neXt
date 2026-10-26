# SPDX-License-Identifier: MIT
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from meshchatnext.src.backend.meshcore_notifications import (
    deliver_notification,
    notification_text,
)
from meshchatnext.src.backend.meshcore_service import MeshCoreService
from meshchatnext.src.backend.meshcore_store import MeshCoreStore, notification_key

OWNER, PEER, CHANNEL = "a1" * 32, "b2" * 32, "c3" * 32


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MeshCoreStore(Path(self.temp.name) / "history")
        self.store.bind(OWNER, "Radio")
        self.store.replace_contacts(
            OWNER, {PEER: {"public_key": PEER, "adv_name": "Peer", "type": 1}}
        )
        self.store.replace_channels(
            OWNER,
            [{"slot": 1, "channel_id": CHANNEL, "name": "#field", "kind": "public"}],
        )

    async def asyncTearDown(self):
        self.temp.cleanup()

    def incoming(self, stamp=1, kind="direct"):
        return self.store.receive(
            OWNER,
            kind,
            {
                "pubkey_prefix": PEER[:12],
                "channel_idx": 1,
                "sender_timestamp": stamp,
                "text": "Peer: hello",
            },
        )

    async def test_fresh_only_identity_scoped_and_read_messages_suppressed(self):
        event = self.incoming()
        self.assertEqual(event["name"], "Peer")
        self.assertIsNone(self.incoming())
        self.assertTrue(self.store.notification_allowed(event))
        self.store.mark_read(OWNER, PEER, event["created"])
        self.assertFalse(self.store.notification_allowed(event))
        self.assertNotEqual(
            event["notification_key"], notification_key(PEER, "direct", PEER)
        )
        self.assertNotEqual(
            event["notification_key"], notification_key(OWNER, "channel", PEER)
        )

    async def test_channel_mute_and_banishment_are_rechecked_at_dispatch(self):
        event = self.incoming(kind="channel")
        self.assertTrue(self.store.notification_allowed(event))
        self.store.channel_preference(OWNER, CHANNEL, muted=True)
        self.assertFalse(self.store.notification_allowed(event))
        self.store.channel_preference(OWNER, CHANNEL, muted=False)
        self.store.banish_channel_sender(OWNER, CHANNEL, event["id"])
        self.assertFalse(self.store.notification_allowed(event))
        self.store.unbanish_channel_sender(OWNER, CHANNEL, "Peer")
        self.assertTrue(self.store.notification_allowed(event))
        self.assertEqual(len(self.store.channel_history(OWNER, CHANNEL)), 1)

    async def test_mentions_only_matches_full_current_name_and_preserves_unread(self):
        self.store.channel_preference(OWNER, CHANNEL, muted=False, mentions_only=True)
        event = self.incoming(kind="channel")
        for text, allowed in [
            ("Peer: hello", False),
            ("Peer: Radio", False),
            ("Peer: @[Radio 2]", False),
            ("Peer: @[radio] hello", True),
            ("@[Radio]: hello", False),
        ]:
            self.assertEqual(
                self.store.notification_allowed({**event, "text": text}), allowed
            )
        self.assertEqual(
            self.store.ui_snapshot(OWNER, "account")["channels"][0]["unread"], 1
        )
        self.store.update_profile_name(OWNER, "New name")
        self.assertFalse(
            self.store.notification_allowed({**event, "text": "Peer: @[Radio]"})
        )
        mentioned = {**event, "text": "Peer: @[New name]"}
        self.assertTrue(self.store.notification_allowed(mentioned))
        self.store.channel_preference(OWNER, CHANNEL, muted=True)
        self.assertFalse(self.store.notification_allowed(mentioned))
        self.store.channel_preference(OWNER, CHANNEL, muted=False)
        self.store.banish_channel_sender(OWNER, CHANNEL, event["id"])
        self.assertFalse(self.store.notification_allowed(mentioned))
        # Persist the preference across a process/store reopen.
        self.assertTrue(
            MeshCoreStore(self.store.path).ui_snapshot(OWNER, "account")["channels"][0][
                "mentions_only"
            ]
        )

    async def test_unmentioned_followup_does_not_swallow_a_mention(self):
        self.store.channel_preference(OWNER, CHANNEL, muted=False, mentions_only=True)
        sink = AsyncMock()
        service = MeshCoreService(
            Path(self.temp.name) / "mention-service", notification_sink=sink
        )
        service._store = self.store
        await service.start()
        try:
            event = self.incoming(10, kind="channel")
            service._queue_notification({**event, "text": "Peer: @[Radio] hello"})
            service._queue_notification(
                {**event, "id": "followup", "text": "Peer: ordinary message"}
            )
            for _ in range(100):
                if sink.await_count:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(sink.await_count, 1)
            self.assertIn("@[Radio]", sink.call_args.args[0]["text"])
        finally:
            await service.close()

    async def test_worker_coalesces_and_alert_failures_do_not_stop_future_delivery(
        self,
    ):
        sink = AsyncMock(side_effect=[RuntimeError("notification unavailable"), None])
        service = MeshCoreService(
            Path(self.temp.name) / "service", notification_sink=sink
        )
        service._store = self.store
        await service.start()
        try:
            service._queue_notification(self.incoming(1))
            service._queue_notification(self.incoming(2))
            for _ in range(100):
                if sink.await_count:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(sink.await_count, 1)
            service._queue_notification(self.incoming(3))
            for _ in range(100):
                if sink.await_count == 2:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(sink.await_count, 2)
        finally:
            await service.close()

    async def test_native_alert_is_labelled_and_respects_dnd_and_open_thread(self):
        owner = SimpleNamespace(websocket_broadcast=AsyncMock())
        event = self.incoming(kind="channel")
        notify = Mock()
        bridge = SimpleNamespace(
            _notify_java=notify,
            _dnd_enabled=lambda: False,
            _is_open_conversation=lambda key: False,
        )
        with patch.dict("sys.modules", {"meshchatnext.android_push_bridge": bridge}):
            await deliver_notification(owner, event)
            notify.assert_called_once_with(
                "MeshCore · #field",
                "Peer: hello",
                event["id"],
                event["notification_key"],
            )
            for dnd, opened in [(True, False), (False, True)]:
                notify.reset_mock()
                bridge._dnd_enabled = lambda value=dnd: value
                bridge._is_open_conversation = lambda key, value=opened: value
                await deliver_notification(owner, event)
                notify.assert_not_called()
        self.assertEqual(owner.websocket_broadcast.await_count, 3)


def test_media_notifications_are_readable_and_network_labelled():
    assert notification_text(
        {"kind": "direct", "name": "Peer", "text": "VI1:1:14:c:2s"}
    ) == ("MeshCore · Peer", "Photo")
    assert notification_text(
        {"kind": "channel", "name": "Test", "text": "Peer: VI1:1:14:c:2s @[Radio]"}
    ) == ("MeshCore · Test", "Peer: Photo · @[Radio]")
    assert (
        notification_text({"kind": "channel", "text": "Peer: VE3:1:1:2:2"})[1]
        == "Peer: Voice clip · 2 seconds"
    )
    assert (
        notification_text({"kind": "direct", "text": "VI1:broken"})[1] == "VI1:broken"
    )
