# SPDX-License-Identifier: MIT
import asyncio
import hashlib
import tempfile
import unittest
from pathlib import Path

from meshchatnext.src.backend.meshcore_channels import (
    PUBLIC_GROUP_KEY,
    ChannelUpdateError,
    MeshCoreChannels,
    metadata,
)
from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from tests.backend.test_meshcore_messaging import OWNER, Client, Session, Types, event


class ChannelClient(Client):
    def __init__(self):
        super().__init__()
        self.slots = [("Public", PUBLIC_GROUP_KEY), ("", bytes(16)), ("", bytes(16))]
        self.writes = []
        self.sent_channels = 0
        self.corrupt_readback = False
        self.channel_response = None

    async def send_device_query(self):
        return event(Types.CONTACTS, {"max_channels": len(self.slots)})

    async def get_channel(self, slot):
        name, key = self.slots[slot]
        return event(
            Types.CHANNEL_INFO,
            {"channel_idx": slot, "channel_name": name, "channel_secret": key},
        )

    async def send(self, frame, expected):
        if frame[0] == 0x20:
            self.writes.append(frame)
            name = frame[2:34].split(b"\x00")[0].decode()
            if self.corrupt_readback:
                name += "x"
            self.slots[frame[1]] = (
                name,
                bytes(16) if self.corrupt_readback else frame[34:50],
            )
            return event(Types.OK, {})
        return await super().send(frame, expected)

    async def send_chan_msg(self, slot, text, **options):
        self.sent_channels += 1
        return self.channel_response or event(Types.OK, {})


class ChannelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MeshCoreStore(Path(self.temp.name) / "history.sqlite")
        self.session = Session()
        self.session._client = self.client = ChannelClient()
        self.messages = MeshCoreMessaging(self.session, self.store, event_types=Types)
        await self.messages.open()
        self.channels = MeshCoreChannels(self.messages)

    async def asyncTearDown(self):
        await self.messages.close()
        self.temp.cleanup()

    async def test_config_import_preserves_arbitrary_names_exact_keys_and_default_slot(
        self,
    ):
        key = bytes(range(16))
        self.assertTrue(await self.channels.import_channel("Private team", key))
        self.assertEqual(self.client.slots[1], ("Private team", key))
        self.assertFalse(await self.channels.import_channel("Renamed in backup", key))
        self.assertEqual(self.client.slots[0], ("Public", PUBLIC_GROUP_KEY))
        self.assertEqual(self.client.slots[1], ("Private team", key))
        self.assertEqual(len(self.client.writes), 1)

    async def test_late_other_slot_reply_waits_for_matching_channel_without_requery(
        self,
    ):
        calls = []
        before = len(self.client.subscribers)

        async def query(slot):
            calls.append(slot)
            asyncio.get_running_loop().call_soon(
                self.client.emit,
                Types.CHANNEL_INFO,
                {
                    "channel_idx": slot,
                    "channel_name": "Expected",
                    "channel_secret": bytes(16),
                },
            )
            return event(
                Types.CHANNEL_INFO,
                {
                    "channel_idx": slot - 1,
                    "channel_name": "Stale",
                    "channel_secret": bytes([1]) * 16,
                },
            )

        self.client.get_channel = query
        row, key = await self.channels._read(1)
        self.assertEqual(row["name"], "Expected")
        self.assertEqual(key, bytes(16))
        self.assertEqual(calls, [1])
        self.assertEqual(len(self.client.subscribers), before)

    async def test_missing_matching_channel_times_out_and_unsubscribes(self):
        before = len(self.client.subscribers)
        self.channels.READ_TIMEOUT = 0.02

        async def query(slot):
            return event(
                Types.CHANNEL_INFO,
                {
                    "channel_idx": 0,
                    "channel_name": "Stale",
                    "channel_secret": bytes(16),
                },
            )

        self.client.get_channel = query
        with self.assertRaisesRegex(ConnectionError, "Matching channel response"):
            await self.channels._read(1)
        self.assertEqual(len(self.client.subscribers), before)

    async def test_matching_channel_still_rejects_invalid_secret(self):
        async def query(slot):
            return event(
                Types.CHANNEL_INFO,
                {
                    "channel_idx": slot,
                    "channel_name": "Test",
                    "channel_secret": b"invalid",
                },
            )

        self.client.get_channel = query
        with self.assertRaisesRegex(ConnectionError, "Unsupported channel key"):
            await self.channels._read(1)

    async def test_refresh_is_read_only_and_redacts_keys(self):
        rows = await self.channels.refresh()
        self.assertEqual(rows[0]["kind"], "public")
        self.assertEqual(rows[1]["kind"], "empty")
        self.assertNotIn("channel_secret", str(rows))
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.client.fetches, 0)

    async def test_public_case_normalization_matches_other_clients(self):
        row = await self.channels.add_public("MiXeD-Case")
        self.assertEqual(row["name"], "#mixed-case")
        self.assertEqual(await self.channels.add_public("#MIXED-CASE"), row)

    async def test_public_derivation_and_duplicate_join(self):
        row = await self.channels.add_public("local")
        self.assertEqual(row["slot"], 1)
        self.assertEqual(row["name"], "#local")
        self.assertEqual(
            self.client.slots[1][1], hashlib.sha256(b"#local").digest()[:16]
        )
        self.assertEqual(await self.channels.add_public("#local"), row)
        self.assertEqual(len(self.client.writes), 1)

    async def test_private_plain_label_keeps_explicit_key_and_export_is_explicit(self):
        key = bytes(range(16))
        row = await self.channels.add_private("#secret", key=key)
        self.assertEqual(row["kind"], "private")
        self.assertEqual(self.client.slots[1], ("secret", key))
        self.assertEqual(await self.channels.add_private("secret", key=key), row)
        self.assertEqual(
            await self.channels.export_key(1, expected_channel_id=row["channel_id"]),
            key,
        )
        self.assertNotIn(key.hex(), str(row))
        with self.assertRaises(ValueError):
            await self.channels.export_key(1, expected_channel_id="wrong")

    async def test_generated_private_keys_are_random(self):
        first = await self.channels.add_private("#one")
        second = await self.channels.add_private("#two")
        self.assertNotEqual(first["channel_id"], second["channel_id"])
        self.assertEqual(first["kind"], "private")

    async def test_invalid_names_and_public_or_zero_private_key_never_write(self):
        for name in ("", "#", "has space", "#é" * 20, "#nul\x00"):
            with self.assertRaises(ValueError):
                await self.channels.add_public(name)
        for key in (
            bytes(16),
            b"short",
            PUBLIC_GROUP_KEY,
            hashlib.sha256(b"#private").digest()[:16],
        ):
            with self.assertRaises(ValueError):
                await self.channels.add_private("#private", key=key)
        self.assertEqual(self.client.writes, [])

    async def test_full_radio_never_overwrites_default_or_existing_channel(self):
        await self.channels.add_public("#one")
        await self.channels.add_public("#two")
        with self.assertRaises(ValueError):
            await self.channels.add_public("#three")
        self.assertEqual(len(self.client.writes), 2)
        self.assertEqual(self.client.slots[0], ("Public", PUBLIC_GROUP_KEY))

    async def test_failed_write_readback_is_uncertain_and_invalidates_binding(self):
        row = await self.channels.add_public("#one")
        self.client.corrupt_readback = True
        with self.assertRaises(ChannelUpdateError):
            await self.channels.remove(1, expected_channel_id=row["channel_id"])
        # For removal use corrupt name too to make actual readback differ.

    async def test_channel_text_limit_includes_sender_name_and_no_delivery_receipt(
        self,
    ):
        row = await self.channels.add_public("#one")
        with self.assertRaises(ValueError):
            await self.channels.send(
                1, "é" * 77, expected_channel_id=row["channel_id"], request_id="bad"
            )
        saved = await self.channels.send(
            1, "é" * 76, expected_channel_id=row["channel_id"], request_id="one"
        )
        self.assertEqual(saved["state"], "submitted")
        again = await self.channels.send(
            1, "é" * 76, expected_channel_id=row["channel_id"], request_id="one"
        )
        self.assertEqual(again["id"], saved["id"])
        self.assertEqual(self.client.sent_channels, 1)
        self.store.receipt(OWNER, "01020304", __import__("time").time())
        self.assertEqual(
            (await self.channels.history(row["channel_id"]))[0]["state"], "submitted"
        )

    async def test_slot_reuse_keeps_old_history_separate(self):
        old = await self.channels.add_public("#old")
        self.client.incoming = [
            event(
                Types.CHANNEL_MSG_RECV,
                {"channel_idx": 1, "sender_timestamp": 100, "text": "peer: old"},
            )
        ]
        await self.channels.remove(1, expected_channel_id=old["channel_id"])
        new = await self.channels.add_public("#new")
        self.store.receive(
            OWNER,
            "channel",
            {"channel_idx": 1, "sender_timestamp": 101, "text": "peer: new"},
        )
        self.assertEqual(
            [row["text"] for row in await self.channels.history(old["channel_id"])],
            ["peer: old"],
        )
        self.assertEqual(
            [row["text"] for row in await self.channels.history(new["channel_id"])],
            ["peer: new"],
        )

    async def test_stale_slot_identity_blocks_removal_and_send(self):
        old = await self.channels.add_public("#old")
        self.client.slots[1] = ("#changed", b"c" * 16)
        with self.assertRaises(ValueError):
            await self.channels.remove(1, expected_channel_id=old["channel_id"])
        with self.assertRaises(ValueError):
            await self.channels.send(
                1, "test", expected_channel_id=old["channel_id"], request_id="bad"
            )
        with self.assertRaises(ValueError):
            await self.channels.remove(0, expected_channel_id=old["channel_id"])
        self.assertEqual(self.client.sent_channels, 0)

    async def test_uncertain_channel_send_is_persisted_without_retry(self):
        row = await self.channels.add_private("#private", key=b"p" * 16)
        self.client.channel_response = event(Types.ERROR, {"reason": "timeout"})
        saved = await self.channels.send(
            1, "test", expected_channel_id=row["channel_id"], request_id="one"
        )
        self.assertEqual(saved["state"], "unknown")
        await self.channels.send(
            1, "test", expected_channel_id=row["channel_id"], request_id="one"
        )
        self.assertEqual(self.client.sent_channels, 1)
        reopened = MeshCoreStore(self.store.path)
        self.assertEqual(
            reopened.channel_history(OWNER, row["channel_id"])[0]["state"], "unknown"
        )
        self.assertEqual(
            reopened.channel_history("another-owner", row["channel_id"]), []
        )

    async def test_same_name_with_different_keys_has_separate_history(self):
        one = metadata(1, "#same", b"a" * 16)
        two = metadata(1, "#same", b"b" * 16)
        self.assertNotEqual(one["channel_id"], two["channel_id"])
        self.store.replace_channels(OWNER, [one])
        self.store.receive(
            OWNER, "channel", {"channel_idx": 1, "sender_timestamp": 1, "text": "old"}
        )
        self.store.replace_channels(OWNER, [two])
        self.store.receive(
            OWNER, "channel", {"channel_idx": 1, "sender_timestamp": 2, "text": "new"}
        )
        self.assertEqual(len(self.store.channel_history(OWNER, one["channel_id"])), 1)
        self.assertEqual(len(self.store.channel_history(OWNER, two["channel_id"])), 1)

    async def test_identical_wire_content_on_reused_slot_is_not_deduplicated_across_keys(
        self,
    ):
        payload = {"channel_idx": 1, "sender_timestamp": 100, "text": "same: text"}
        for key in (b"a" * 16, b"b" * 16):
            row = metadata(1, "#same", key)
            self.store.replace_channels(OWNER, [row])
            self.store.receive(OWNER, "channel", payload)
            self.assertEqual(
                len(self.store.channel_history(OWNER, row["channel_id"])), 1
            )

    async def test_unbound_channel_packets_are_preserved_without_guessing_identity(
        self,
    ):
        self.store.receive(OWNER, "channel", {"channel_idx": 1, "text": "unbound"})
        rows = self.store.channel_history(OWNER, None)
        self.assertEqual(rows[0]["text"], "unbound")

    async def test_restart_does_not_replay_stranded_channel_submission(self):
        row = await self.channels.add_public("#test")
        self.store.prepare_channel_send(OWNER, row, "pending", "stranded")
        self.store.bind(OWNER, "local")
        saved = await self.channels.send(
            1, "pending", expected_channel_id=row["channel_id"], request_id="stranded"
        )
        self.assertEqual(saved["state"], "unknown")
        self.assertEqual(self.client.sent_channels, 0)
