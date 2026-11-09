# SPDX-License-Identifier: MIT
import asyncio
import tempfile
import unittest
from enum import Enum, auto
from pathlib import Path
from types import SimpleNamespace

from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
from meshchatnext.src.backend.meshcore_store import MeshCoreStore

OWNER = "a1" * 32
PEER = "b2" * 32
OTHER = "c3" * 32


class Types(Enum):
    RX_LOG_DATA = auto()
    ADVERTISEMENT = auto()
    NEW_CONTACT = auto()
    PATH_UPDATE = auto()
    OK = auto()
    CHANNEL_INFO = auto()
    ACK = auto()
    MESSAGES_WAITING = auto()
    MSG_SENT = auto()
    CONTACTS = auto()
    ERROR = auto()
    CONTACT_MSG_RECV = auto()
    CHANNEL_MSG_RECV = auto()
    CHANNEL_DATA_RECV = auto()
    NO_MORE_MSGS = auto()


def event(kind, payload):
    return SimpleNamespace(
        type=kind, payload=payload, attributes={}, is_error=lambda: kind == Types.ERROR
    )


class Client:
    def __init__(self):
        self.commands = self
        self.subscribers = []
        self.sent = 0
        self.attempts = []
        self.resets = []
        self.out_path_len = -1
        self.early_ack = False
        self.response = None
        self.incoming = []
        self.fetches = 0
        self.contacts = {PEER: {"public_key": PEER, "adv_name": "test", "type": 1}}

    def subscribe(self, kind, callback):
        pair = (kind, callback)
        self.subscribers.append(pair)
        return SimpleNamespace(unsubscribe=lambda: self.subscribers.remove(pair))

    def emit(self, kind, payload):
        for match, callback in list(self.subscribers):
            if kind == match:
                callback(event(kind, payload))

    async def send_appstart(self):
        return event(
            Types.CONTACTS,
            {"public_key": OWNER, "name": "local", "private_key": "excluded"},
        )

    async def send(self, frame, expected):
        if frame != b"\x04":
            raise AssertionError("Unexpected write")
        return event(Types.CONTACTS, self.contacts)

    async def reset_path(self, peer):
        self.resets.append(peer)
        self.out_path_len = -1
        return event(Types.OK, {})

    async def send_msg(self, peer, text, **kwargs):
        self.sent += 1
        self.attempts.append(kwargs)
        if self.early_ack:
            self.emit(Types.ACK, {"code": "01020304"})
            await asyncio.sleep(0)
        return self.response or event(
            Types.MSG_SENT,
            {
                "expected_ack": bytes.fromhex(
                    "01020304" if kwargs.get("attempt") == 0 else "02030405"
                ),
                "suggested_timeout": 100,
                "type": int(self.out_path_len == -1),
            },
        )

    async def get_msg(self):
        self.fetches += 1
        return self.incoming.pop(0) if self.incoming else event(Types.NO_MORE_MSGS, {})


class Session:
    def __init__(self):
        self._client = Client()
        self._lock = asyncio.Lock()
        self.is_connected = True

    @staticmethod
    def _payload(value):
        if value.is_error():
            raise ConnectionError("request failed")
        return value.payload

    async def _close(self):
        self.is_connected = False
        self._client = None


class MessagingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "messages.sqlite"
        self.store = MeshCoreStore(self.path)
        self.session = Session()
        self.client = self.session._client
        self.messenger = MeshCoreMessaging(self.session, self.store, event_types=Types)
        self.identity = await self.messenger.open()

    async def test_cli_responses_do_not_become_chat_messages_or_alerts(self):
        self.client.incoming.append(
            event(
                Types.CONTACT_MSG_RECV,
                {
                    "pubkey_prefix": PEER[:12],
                    "txt_type": 1,
                    "text": "server configuration",
                    "sender_timestamp": 123,
                },
            )
        )
        self.assertTrue(await self.messenger._fetch_message())
        self.assertEqual(self.store.history(OWNER, PEER), [])

    async def test_config_import_restores_removed_contact_and_keeps_existing_active_contact(
        self,
    ):
        row = {
            "public_key": OTHER,
            "type": 3,
            "flags": 1,
            "adv_name": "Room server",
            "last_advert": 100,
            "adv_lat": 1.25,
            "adv_lon": -2.5,
            "out_path": "",
            "out_path_len": -1,
            "out_path_hash_mode": -1,
        }
        self.store.replace_contacts(OWNER, {**self.client.contacts, OTHER: row})
        writes = []

        async def add(contact):
            writes.append(contact)
            self.client.contacts[contact["public_key"]] = dict(contact)
            return event(Types.OK, {})

        self.client.add_contact = add
        self.assertTrue(await self.messenger.import_contact(row))
        self.assertEqual(self.client.contacts[OTHER]["type"], 3)
        self.assertFalse(
            await self.messenger.import_contact({**row, "adv_name": "Do not replace"})
        )
        self.assertEqual(self.client.contacts[OTHER]["adv_name"], "Room server")
        self.assertEqual(len(writes), 1)

    async def asyncTearDown(self):
        await self.messenger.close()
        self.temp.cleanup()

    async def test_announce_pushes_refresh_one_record_without_sending_or_adding(self):
        self.client.emit(
            Types.NEW_CONTACT,
            {"public_key": OTHER, "adv_name": "new", "type": 2, "last_advert": 10},
        )
        self.client.contacts[PEER].update(last_advert=20, adv_name="renamed")
        self.client.emit(Types.ADVERTISEMENT, {"public_key": PEER})
        for _ in range(100):
            rows = self.store.announces(OWNER)
            if len(rows) == 2:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["peer"]: row["name"] for row in rows}, {PEER: "renamed", OTHER: "new"}
        )
        self.client.emit(
            Types.NEW_CONTACT,
            {"public_key": OTHER, "adv_name": "updated", "type": 2, "last_advert": 30},
        )
        for _ in range(100):
            rows = self.store.announces(OWNER)
            if any(row["name"] == "updated" for row in rows):
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(row["name"] == "updated" for row in rows))
        self.assertEqual(len(self.store.contacts(OWNER)), 1)
        self.assertEqual(self.client.sent, 0)
        self.assertEqual(self.client.fetches, 0)
        self.assertIsNone(self.messenger._failure)

    async def settle(self):
        for _ in range(100):
            if self.messenger._failure:
                raise self.messenger._failure
            if (
                self.client.fetches
                and not self.client.incoming
                and not self.session._lock.locked()
            ):
                return
            await asyncio.sleep(0.01)
        raise AssertionError("Receive worker did not settle")

    async def test_open_reads_only_and_does_not_export_identity_secret(self):
        self.assertEqual(self.identity, {"public_key": OWNER, "name": "local"})
        self.assertEqual(self.client.fetches, 0)
        self.assertEqual(self.client.sent, 0)
        self.assertEqual(len(self.store.contacts(OWNER)), 1)

    async def test_flood_is_default_and_expired_routes_are_reset(self):
        import time

        self.client.out_path_len = 1
        self.client.emit(Types.PATH_UPDATE, {"public_key": PEER})
        self.messenger._direct_routes[PEER] = time.monotonic() - 301
        result = await self.messenger.send_direct(PEER, "hello", request_id="flood")
        self.assertEqual(result["sent_route"], "flood")
        self.assertEqual(self.client.resets, [PEER])
        self.assertFalse(self.messenger._flood_retries)

    async def test_flood_retry_keeps_timestamp_and_accepts_the_original_late_ack(self):
        from unittest.mock import patch

        self.client.out_path_len = 1
        self.client.emit(Types.PATH_UPDATE, {"public_key": PEER})
        original = self.messenger._send_receipt

        def immediate(event):
            ack, _, route = original(event)
            return ack, 0, route

        with patch.object(self.messenger, "_send_receipt", side_effect=immediate):
            result = await self.messenger.send_direct(PEER, "hello", request_id="retry")
            self.assertEqual(result["sent_route"], "direct")
            await asyncio.gather(*self.messenger._flood_retries)
        first, second = self.client.attempts
        self.assertEqual(first["timestamp"], second["timestamp"])
        self.assertEqual((first["attempt"], second["attempt"]), (0, 1))
        self.assertEqual(self.client.resets, [PEER])
        self.client.emit(Types.ACK, {"code": "01020304"})
        await self.messenger._acks.join()
        row = await self.messenger.send_direct(PEER, "hello", request_id="retry")
        self.assertEqual(row["state"], "delivered")
        self.assertEqual(row["sent_route"], "direct_then_flood")
        self.assertEqual(self.client.sent, 2)

    async def test_direct_ack_cancels_flood_retry(self):
        self.client.out_path_len = 1
        self.client.early_ack = True
        self.client.emit(Types.PATH_UPDATE, {"public_key": PEER})
        result = await self.messenger.send_direct(PEER, "hello", request_id="confirmed")
        await self.messenger._acks.join()
        await self.messenger._retry_on_flood(result, 0)
        self.assertEqual(self.client.sent, 1)
        self.assertEqual(self.client.resets, [])
        self.assertEqual((await self.messenger.history(PEER))[0]["state"], "delivered")

    async def test_fast_ack_and_idempotency_survive_reopening_database(self):
        self.client.early_ack = True
        await self.messenger.send_direct(PEER, "hello", request_id="one")
        await self.messenger._acks.join()
        rows = await self.messenger.history(PEER)
        self.assertEqual(rows[0]["state"], "delivered")
        self.assertEqual(
            MeshCoreStore(self.path).history(OWNER)[0]["state"], "delivered"
        )
        again = await self.messenger.send_direct(PEER, "hello", request_id="one")
        self.assertEqual(again["state"], "delivered")
        self.assertEqual(self.client.sent, 1)
        with self.assertRaises(ValueError):
            await self.messenger.send_direct(PEER, "different", request_id="one")

    async def test_invalid_utf8_length_nul_or_unknown_contact_never_transmit(self):
        for text in ("é" * 81, "", "bad\x00text"):
            with self.assertRaises(ValueError):
                await self.messenger.send_direct(PEER, text, request_id="bad")
        with self.assertRaises(ValueError):
            await self.messenger.send_direct(OTHER, "hello", request_id="bad")
        self.assertEqual(self.client.sent, 0)
        await self.messenger.send_direct(PEER, "é" * 80, request_id="valid")
        self.assertEqual(self.client.sent, 1)

    async def test_timeout_is_uncertain_and_is_not_replayed(self):
        self.client.response = event(Types.ERROR, {"reason": "timeout"})
        result = await self.messenger.send_direct(PEER, "hello", request_id="one")
        self.assertEqual(result["state"], "unknown")
        await self.messenger.send_direct(PEER, "hello", request_id="one")
        self.assertEqual(self.client.sent, 1)

    async def test_room_preflight_is_distinct_and_existing_result_needs_no_clock(self):
        import time
        from unittest.mock import AsyncMock

        self.store.replace_contacts(OWNER, {PEER: {"public_key": PEER, "type": 3}})
        self.client.get_time = AsyncMock(
            return_value=event(Types.OK, {"time": int(time.time()) + 120})
        )
        with self.assertRaisesRegex(ValueError, "clock") as caught:
            await self.messenger.send_direct(
                PEER, "hello", request_id="clock", room=True
            )
        self.assertTrue(caught.exception.meshcore_not_sent)
        self.assertEqual(self.client.sent, 0)
        self.client.get_time.return_value = event(Types.OK, {"time": int(time.time())})
        first = await self.messenger.send_direct(
            PEER, "hello", request_id="one", room=True
        )
        self.assertEqual(first["state"], "accepted")
        self.client.get_time.side_effect = ConnectionError("Clock unavailable")
        again = await self.messenger.send_direct(
            PEER, "hello", request_id="one", room=True
        )
        self.assertEqual(again["state"], "accepted")
        self.assertEqual(self.client.sent, 1)
        self.client.response = event(
            Types.MSG_SENT, {"expected_ack": b"bad", "suggested_timeout": 100}
        )
        self.client.get_time.side_effect = None
        with self.assertRaisesRegex(ValueError, "receipt token") as caught:
            await self.messenger.send_direct(
                PEER, "hello2", request_id="two", room=True
            )
        self.assertFalse(getattr(caught.exception, "meshcore_not_sent", False))
        self.assertEqual(
            self.store.send_result(OWNER, PEER, "hello2", "two")["state"], "unknown"
        )

    async def test_numeric_firmware_error_is_rejected(self):
        self.client.response = event(Types.ERROR, {"error_code": 2})
        result = await self.messenger.send_direct(PEER, "hello", request_id="one")
        self.assertEqual(result["state"], "rejected")

    async def test_receive_duplicates_and_channels_commit_before_next_fetch(self):
        payload = {
            "pubkey_prefix": PEER[:12],
            "sender_timestamp": 123,
            "txt_type": 0,
            "text": "reply",
            "path_len": 2,
        }
        self.client.incoming = [
            event(Types.CONTACT_MSG_RECV, payload),
            event(Types.CONTACT_MSG_RECV, {**payload, "path_len": 3}),
            event(
                Types.CHANNEL_MSG_RECV,
                {"channel_idx": 1, "sender_timestamp": 124, "text": "channel"},
            ),
            event(
                Types.CHANNEL_DATA_RECV,
                {"channel_idx": 1, "sender_timestamp": 125, "data": b"\x00\xff"},
            ),
        ]
        await self.messenger.start_receiving()
        await self.settle()
        rows = await self.messenger.history()
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(await self.messenger.history(PEER)), 1)
        self.assertIn("00ff", str(rows))

    async def test_receive_storage_failure_stops_queue_without_fetching_next(self):
        self.client.incoming = [
            event(Types.CONTACT_MSG_RECV, {"text": "first"}),
            event(Types.CONTACT_MSG_RECV, {"text": "second"}),
        ]

        def fail(*args):
            raise OSError("disk full")

        self.store.receive = fail
        await self.messenger.start_receiving()
        for _ in range(100):
            if self.messenger.status()["processing_failed"]:
                break
            await asyncio.sleep(0.01)
        self.assertTrue(self.messenger.status()["processing_failed"])
        self.assertEqual(self.client.fetches, 1)
        self.assertEqual(len(self.client.incoming), 1)
        with self.assertRaises(RuntimeError):
            await self.messenger.send_direct(PEER, "hello", request_id="blocked")

    async def test_ambiguous_prefix_blocks_send_and_does_not_misattribute_receive(self):
        collision = PEER[:12] + "cc" * 26
        self.client.contacts[collision] = {"public_key": collision, "type": 1}
        await self.messenger.sync_contacts()
        with self.assertRaises(ValueError):
            await self.messenger.send_direct(PEER, "hello", request_id="bad")
        self.store.receive(
            OWNER, "direct", {"pubkey_prefix": PEER[:12], "text": "unknown"}
        )
        self.assertIsNone(self.store.history(OWNER)[0]["peer"])

    async def test_restart_marks_stranded_submission_unknown_and_isolates_identity(
        self,
    ):
        self.store.prepare_send(OWNER, PEER, "hello", "stranded")
        reopened = MeshCoreStore(self.path)
        reopened.bind(OWNER, "local")
        self.assertEqual(reopened.history(OWNER)[0]["state"], "unknown")
        reopened.bind(OTHER, "different")
        self.assertEqual(reopened.history(OTHER), [])
        self.assertEqual(reopened.contacts(OTHER), [])

    async def test_ack_collision_does_not_deliver_two_messages_and_late_ack_works(self):
        self.store.prepare_send(OWNER, PEER, "first", "one")
        self.store.result(OWNER, "one", "accepted", "01020304", -1)
        self.assertEqual(self.store.history(OWNER)[0]["state"], "unconfirmed")
        self.store.receipt(OWNER, "01020304", __import__("time").time())
        self.assertEqual(self.store.history(OWNER)[0]["state"], "delivered")
        self.store.prepare_send(OWNER, PEER, "second", "two")
        self.store.result(OWNER, "two", "accepted", "01020304", 10)
        self.assertEqual(self.store.history(OWNER)[0]["state"], "accepted")

    async def test_failed_contact_snapshot_preserves_previous_contacts(self):
        with self.assertRaises(ValueError):
            self.store.replace_contacts(
                OWNER, {"bad": {"public_key": "bad", "type": 1}}
            )
        self.assertEqual(len(self.store.contacts(OWNER)), 1)

    async def test_manual_drain_storage_failure_stops_subsequent_fetches(self):
        self.client.incoming = [
            event(Types.CONTACT_MSG_RECV, {"text": "first"}),
            event(Types.CONTACT_MSG_RECV, {"text": "second"}),
        ]

        def fail(*args):
            raise OSError("disk full")

        self.store.receive = fail
        async with self.session._lock:
            with self.assertRaises(OSError):
                await self.messenger._drain_pending()
            with self.assertRaises(RuntimeError):
                await self.messenger._drain_pending()
        self.assertEqual(self.client.fetches, 1)


class DatagramStoreTests(unittest.TestCase):
    def test_equal_binary_datagrams_without_timestamp_are_both_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MeshCoreStore(Path(directory) / "history.sqlite")
            for _ in range(2):
                store.receive(
                    OWNER, "channel_data", {"channel_idx": 1, "data": b"same"}
                )
            self.assertEqual(len(store.history(OWNER)), 2)
