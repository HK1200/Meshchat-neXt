# SPDX-License-Identifier: MIT
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from meshchatnext.src.backend.meshcore_nodes import MeshCoreNodes
from meshchatnext.src.backend.meshcore_store import MeshCoreStore

PEER = "b2" * 32
OTHER = "c3" * 32


class NodeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.types = SimpleNamespace(
            LOGIN_SUCCESS="success",
            LOGIN_FAILED="failed",
            STATUS_RESPONSE="status",
            PATH_RESPONSE="path",
            MSG_SENT="sent",
            ERROR="error",
            OK="ok",
        )
        self.listeners = {}
        self.subs = []

        def subscribe(kind, callback):
            self.listeners[kind] = callback
            sub = SimpleNamespace(unsubscribe=lambda: self.listeners.pop(kind, None))
            self.subs.append(sub)
            return sub

        self.commands = SimpleNamespace(
            _send_login_raw=AsyncMock(),
            send=AsyncMock(),
            send_logout=AsyncMock(return_value=SimpleNamespace(type="ok")),
        )
        self.session = SimpleNamespace(
            _lock=asyncio.Lock(),
            _client=SimpleNamespace(subscribe=subscribe, commands=self.commands),
        )
        self.messages = SimpleNamespace(
            session=self.session,
            owner="a1" * 32,
            store=SimpleNamespace(outgoing_clock=lambda owner, peer: 0),
            _types=self.types,
            _check=lambda: None,
            sync_contacts=AsyncMock(
                return_value=[{"peer": PEER, "kind": 3, "active": 1}]
            ),
            send_direct=AsyncMock(return_value={"state": "accepted"}),
            _drain_pending=AsyncMock(),
            _fetch_message=AsyncMock(return_value=False),
        )
        self.nodes = MeshCoreNodes(self.messages)
        self.nodes.TIMEOUT = 0.02
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": False}
        )

    def response(self, kind, payload, peer=PEER):
        self.listeners[kind](
            SimpleNamespace(
                type=kind,
                payload={"pubkey_prefix": peer[:12], **payload},
                attributes={},
            )
        )
        return SimpleNamespace(type="sent", payload={})

    async def test_room_login_has_no_local_expiry_but_logout_clears_it(self):
        await self.nodes.login(PEER, "secret")
        self.assertIsNone(self.nodes.logins[PEER][0])
        with patch(
            "meshchatnext.src.backend.meshcore_nodes.time.monotonic",
            return_value=10**12,
        ):
            self.assertEqual(self.nodes.snapshot()[PEER]["state"], "verified")
            self.assertIsNone(self.nodes.snapshot()[PEER]["expires_in"])
        await self.nodes.logout(PEER)
        self.assertNotIn(PEER, self.nodes.snapshot())

    async def test_repeater_login_keeps_its_existing_expiry(self):
        self.messages.sync_contacts.return_value = [
            {"peer": PEER, "kind": 2, "active": 1}
        ]
        await self.nodes.login(PEER, "secret")
        self.assertIsNotNone(self.nodes.logins[PEER][0])
        with patch(
            "meshchatnext.src.backend.meshcore_nodes.time.monotonic",
            return_value=10**12,
        ):
            self.assertNotIn(PEER, self.nodes.snapshot())

    async def test_login_early_matching_response_and_room_post(self):
        self.assertEqual((await self.nodes.login(PEER, "secret"))["state"], "verified")
        self.assertFalse(self.listeners)
        self.assertEqual(self.nodes.operations[PEER]["stage"], "login_verified")
        self.assertNotIn("secret", str(self.nodes.operations))
        self.assertIn(PEER, self.nodes.snapshot())
        self.assertEqual(
            (await self.nodes.send_room(PEER, "post", request_id="stable"))["state"],
            "accepted",
        )
        self.messages.send_direct.assert_awaited_once_with(
            PEER, "post", request_id="stable", room=True
        )
        await self.nodes.logout(PEER)
        self.assertNotIn(PEER, self.nodes.snapshot())
        with self.assertRaises(ValueError):
            await self.nodes.send_room(PEER, "post", request_id="stable2")

    async def test_unrelated_response_cannot_authorize_and_timeout_blocks_retry(self):
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {}, OTHER
        )
        self.assertEqual((await self.nodes.login(PEER, "secret"))["state"], "uncertain")
        self.assertFalse(self.listeners)
        self.assertNotIn(PEER, self.nodes.snapshot())
        self.assertEqual(self.nodes.operations[PEER]["stage"], "server_timeout")
        self.assertEqual(self.nodes.operations[PEER]["other_responses"], 1)
        with self.assertRaises(ValueError):
            await self.nodes.login(PEER, "secret")
        self.assertEqual(self.commands._send_login_raw.await_count, 1)

    async def test_ambiguous_prefix_wrong_kind_invalid_password_send_nothing(self):
        self.messages.sync_contacts.return_value.append(
            {"peer": PEER[:12] + "d4" * 26, "kind": 3, "active": 1}
        )
        with self.assertRaises(ValueError):
            await self.nodes.login(PEER, "secret")
        self.messages.sync_contacts.return_value = [
            {"peer": PEER, "kind": 1, "active": 1}
        ]
        with self.assertRaises(ValueError):
            await self.nodes.login(PEER, "secret")
        with self.assertRaises(ValueError):
            await self.nodes.login(PEER, "\0")
        self.commands._send_login_raw.assert_not_awaited()

    async def test_denied_login_and_fresh_instance_forgets_authorization(self):
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "failed", {}
        )
        self.assertEqual((await self.nodes.login(PEER, "wrong"))["state"], "denied")
        self.assertFalse(self.nodes.snapshot())
        self.assertFalse(MeshCoreNodes(self.messages).snapshot())
        with self.assertRaises(ValueError):
            await self.nodes.status(PEER)

    async def test_status_requires_login_matches_peer_and_sanitizes(self):
        await self.nodes.login(PEER, "secret")
        self.commands.send.side_effect = lambda *args: self.response(
            "status", {"battery_mv": 4000, "raw": "private", "invalid": float("nan")}
        )
        result = await self.nodes.status(PEER)
        self.assertEqual(result["values"], {"battery_mv": 4000})
        self.assertFalse(self.listeners)
        self.nodes.logins[PEER] = (0, False)
        self.assertFalse(self.nodes.snapshot())

    async def test_route_can_probe_after_login_timeout_without_authorizing(self):
        self.nodes.uncertain.add(PEER)
        self.commands.send.side_effect = lambda *args: self.response(
            "path", {"out_path_len": 1, "in_path_len": 2}
        )
        result = await self.nodes.route(PEER)
        self.assertEqual(
            result, {"state": "route_received", "out_hops": 1, "in_hops": 2}
        )
        self.assertFalse(self.nodes.snapshot())
        self.assertIn(PEER, self.nodes.uncertain)

    async def test_route_timeout_does_not_block_an_independent_login(self):
        self.commands.send.return_value = SimpleNamespace(type="sent", payload={})
        result = await self.nodes.route(PEER)
        self.assertEqual(result["state"], "uncertain")
        self.assertNotIn(PEER, self.nodes.uncertain)
        self.assertEqual((await self.nodes.login(PEER, "secret"))["state"], "verified")

    async def test_first_explicit_operation_imports_only_the_advertised_server(self):
        self.messages.owner = "a1" * 32
        self.messages.store = SimpleNamespace(
            outgoing_clock=lambda owner, peer: 0,
            announces=lambda owner: [
                {"peer": PEER, "kind": 3, "name": "Americana", "advertised": 123}
            ],
        )
        self.messages.sync_contacts.side_effect = [
            [],
            [{"peer": PEER, "kind": 3, "active": 1}],
        ]
        self.messages.import_contact = AsyncMock(return_value=True)
        result = await self.nodes.login(PEER, "secret")
        self.assertEqual(result["state"], "verified")
        imported = self.messages.import_contact.call_args.args[0]
        self.assertEqual(imported["type"], 3)
        self.assertEqual(imported["public_key"], PEER)
        self.assertEqual(imported["out_path_len"], -1)

    async def test_admin_requires_verified_role_and_matches_only_cli_peer(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock()
        await self.nodes.login(PEER, "member")
        with self.assertRaises(ValueError):
            await self.nodes.admin(PEER, "version")
        self.commands.send_cmd.assert_not_awaited()
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")

        def cli(*args, **kwargs):
            self.response("contact", {"txt_type": 2, "text": "room post"})
            self.response("contact", {"txt_type": 1, "text": "wrong server"}, OTHER)
            return self.response("contact", {"txt_type": 1, "text": "v1.18.0"})

        self.commands.send_cmd.side_effect = cli
        result = await self.nodes.admin(PEER, "version")
        self.assertEqual(result, {"state": "admin_response", "text": "v1.18.0"})
        self.commands.send_cmd.assert_awaited_once_with(
            PEER, "ver", timestamp=101, dst_type=3
        )
        self.assertFalse(self.listeners)
        for action, value in (
            ("set-radio", "910.525,62.5,7,8"),
            ("reboot", ""),
            ("erase", ""),
            ("set-name", "bad\ncommand"),
            ("set-hash", "4"),
        ):
            with self.assertRaises(ValueError):
                await self.nodes.admin(PEER, action, value)
        self.assertEqual(self.commands.send_cmd.await_count, 1)
        await self.nodes.admin(PEER, "set-hash", "3")
        self.assertEqual(
            self.commands.send_cmd.call_args.args[1], "set path.hash.mode 2"
        )

    async def test_admin_timeout_blocks_retry_and_reboot_clears_login(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock(return_value=SimpleNamespace(type="sent"))
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")
        self.assertEqual(
            (await self.nodes.admin(PEER, "version"))["state"], "uncertain"
        )
        with self.assertRaises(ValueError):
            await self.nodes.admin(PEER, "version")
        self.assertFalse(self.listeners)
        self.nodes.uncertain.clear()
        self.assertEqual(
            (await self.nodes.admin(PEER, "reboot", confirmed=True))["state"],
            "submitted",
        )
        self.assertNotIn(PEER, self.nodes.snapshot())

    async def test_admin_waits_past_room_post_before_radio_overwrites_timestamp(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            side_effect=[
                SimpleNamespace(payload={"time": 100}),
                SimpleNamespace(payload={"time": 104}),
            ]
        )
        self.messages.store.outgoing_clock = lambda owner, peer: 102
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock(
            side_effect=lambda *args, **kwargs: self.response(
                "contact", {"txt_type": 1, "text": "version"}
            )
        )
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        self.messages.store.outgoing_clock = lambda owner, peer: 0
        await self.nodes.login(PEER, "admin")
        self.messages.store.outgoing_clock = lambda owner, peer: 102
        with patch(
            "meshchatnext.src.backend.meshcore_nodes.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            result = await self.nodes.admin(PEER, "version")
        sleep.assert_awaited_once_with(3.1)
        self.assertEqual(result["state"], "admin_response")
        self.commands.send_cmd.assert_awaited_once_with(
            PEER, "ver", timestamp=105, dst_type=3
        )

    async def test_room_password_uses_private_wire_path_and_redacts_response(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock()
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")
        for value in ("", "x" * 16, " leading", "trailing ", "bad\nvalue"):
            with self.assertRaises(ValueError):
                await self.nodes.admin(PEER, "set-room-password", value, confirmed=True)
        with self.assertRaises(ValueError):
            await self.nodes.admin(PEER, "set-room-password", "temporary")
        self.commands.send.side_effect = lambda *args: self.response(
            "contact", {"txt_type": 1, "text": "OK"}
        )
        result = await self.nodes.admin(
            PEER, "set-room-password", "temporary", confirmed=True
        )
        self.assertEqual(result["text"], "Room password changed.")
        self.commands.send_cmd.assert_not_awaited()
        frame = self.commands.send.call_args.args[0]
        self.assertEqual(
            frame,
            b"\x02\x01\x00"
            + (101).to_bytes(4, "little")
            + bytes.fromhex(PEER[:12])
            + b"set guest.password temporary",
        )
        self.assertNotIn("temporary", str(self.nodes.operations))
        self.commands.send.side_effect = lambda *args: self.response(
            "contact",
            {"txt_type": 1, "text": "unknown config: guest.password temporary"},
        )
        result = await self.nodes.admin(
            PEER, "set-room-password", "temporary", confirmed=True
        )
        self.assertNotIn("temporary", result["text"])
        self.messages.sync_contacts.return_value = [
            {"peer": PEER, "kind": 2, "active": 1}
        ]
        with self.assertRaises(ValueError):
            await self.nodes.admin(
                PEER, "set-room-password", "temporary", confirmed=True
            )

    async def test_server_clock_position_access_and_advert_interval_commands(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock(
            side_effect=lambda *args, **kwargs: self.response(
                "contact", {"txt_type": 1, "text": "OK"}
            )
        )
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")
        for action, value, command in (
            ("clock", "", "clock"),
            ("sync-clock", "", "clock sync"),
            ("latitude", "", "get lat"),
            ("longitude", "", "get lon"),
            ("set-latitude", "-90", "set lat -90.000000"),
            ("set-longitude", "180", "set lon 180.000000"),
            ("local-interval", "", "get advert.interval"),
            ("flood-interval", "", "get flood.advert.interval"),
            ("set-local-interval", "0", "set advert.interval 0"),
            ("set-local-interval", "60", "set advert.interval 60"),
            ("set-flood-interval", "168", "set flood.advert.interval 168"),
            ("room-access", "", "get allow.read.only"),
            ("set-read-only", "off", "set allow.read.only off"),
        ):
            with self.subTest(action=action):
                self.assertEqual(
                    (await self.nodes.admin(PEER, action, value))["state"],
                    "admin_response",
                )
                self.assertEqual(self.commands.send_cmd.call_args.args[1], command)
        for action, value in (
            ("set-latitude", "nan"),
            ("set-latitude", "90.1"),
            ("set-longitude", "-181"),
            ("set-local-interval", "61"),
            ("set-local-interval", "-1"),
            ("set-local-interval", "30"),
            ("set-flood-interval", "2"),
            ("set-flood-interval", "169"),
            ("set-read-only", "maybe"),
        ):
            with (
                self.subTest(action=action, value=value),
                self.assertRaises(ValueError),
            ):
                await self.nodes.admin(PEER, action, value)

    async def test_hash_readout_converts_firmware_modes_to_bytes(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")
        for raw, expected in (
            ("> 0", "1 byte"),
            ("> 1", "2 bytes"),
            ("2", "3 bytes"),
            ("> 3", "unavailable"),
        ):
            with self.subTest(raw=raw):
                self.commands.send_cmd = AsyncMock(
                    side_effect=lambda *args, raw=raw, **kwargs: self.response(
                        "contact", {"txt_type": 1, "text": raw}
                    )
                )
                result = await self.nodes.admin(PEER, "hash")
                self.assertIn(expected, result["text"])

    async def test_admin_fetches_reply_when_message_waiting_push_is_lost(self):
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock(return_value=SimpleNamespace(type="sent"))
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")
        self.nodes.TIMEOUT = 0.1
        self.nodes.CLI_POLL_INTERVAL = 0.001
        fetched = 0

        async def queued_reply():
            nonlocal fetched
            fetched += 1
            if fetched == 1:
                self.response("contact", {"txt_type": 1, "text": "unrelated"}, OTHER)
            else:
                self.response("contact", {"txt_type": 1, "text": "> on"})
            return True

        self.messages._fetch_message.side_effect = queued_reply
        result = await self.nodes.admin(PEER, "room-access")
        self.assertEqual(result["text"], "> on")
        self.commands.send_cmd.assert_awaited_once()
        self.assertEqual(fetched, 2)
        self.assertTrue(self.nodes.operations[PEER]["response_via_queue_poll"])
        self.assertEqual(self.nodes.operations[PEER]["queue_polls"], 1)
        self.assertFalse(self.listeners)
        self.assertNotIn(PEER, self.nodes.uncertain)

    async def test_repeater_admin_fetches_reply_without_waiting_push(self):
        self.messages.sync_contacts.return_value = [
            {"peer": PEER, "kind": 2, "active": 1}
        ]
        self.types.CONTACT_MSG_RECV = "contact"
        self.session._payload = lambda event: event.payload
        self.commands.get_time = AsyncMock(
            return_value=SimpleNamespace(payload={"time": 100})
        )
        self.messages.store.reserve_command_clock = lambda owner, peer, floor: floor
        self.commands.send_cmd = AsyncMock(return_value=SimpleNamespace(type="sent"))
        self.commands._send_login_raw.side_effect = lambda *args: self.response(
            "success", {"is_admin": True}
        )
        await self.nodes.login(PEER, "admin")
        self.nodes.TIMEOUT = 0.1
        self.nodes.CLI_POLL_INTERVAL = 0.001

        async def queued_reply():
            self.response("contact", {"txt_type": 1, "text": "repeater firmware"})
            return True

        self.messages._fetch_message.side_effect = queued_reply
        result = await self.nodes.admin(PEER, "version")
        self.assertEqual(result["text"], "repeater firmware")
        self.commands.send_cmd.assert_awaited_once_with(
            PEER, "ver", timestamp=101, dst_type=2
        )
        self.assertTrue(self.nodes.operations[PEER]["response_via_queue_poll"])
        self.assertFalse(self.listeners)


class RoomStoreTests(unittest.TestCase):
    def test_room_posts_are_durable_and_do_not_become_direct_conversations(self):
        owner = "a1" * 32
        with tempfile.TemporaryDirectory() as folder:
            store = MeshCoreStore(Path(folder) / "history")
            store.bind(owner, "Client")
            store.replace_contacts(
                owner, {PEER: {"public_key": PEER, "adv_name": "Room", "type": 3}}
            )
            with self.assertRaises(ValueError):
                store.prepare_send(owner, PEER, "post", "direct")
            _row, fresh = store.prepare_send(
                owner, PEER, "post", "room-post", room=True
            )
            self.assertTrue(fresh)
            _, replay = store.prepare_send(owner, PEER, "post", "room-post", room=True)
            self.assertFalse(replay)
            event = store.receive(
                owner,
                "direct",
                {
                    "pubkey_prefix": PEER[:12],
                    "sender_timestamp": 1,
                    "txt_type": 2,
                    "signature": "abcd1234",
                    "text": "room response",
                },
            )
            self.assertEqual(event["name"], "Room")
            self.assertEqual(len(store.history(owner, PEER)), 2)
            import time

            floor = int(time.time()) + 8
            fresh_row, _ = store.prepare_send(
                owner,
                PEER,
                "clock test",
                "floor-post",
                room=True,
                timestamp_floor=floor,
            )
            self.assertGreaterEqual(fresh_row["timestamp"], floor)
            self.assertEqual(store.outgoing_clock(owner, PEER), fresh_row["timestamp"])
            self.assertEqual(store.ui_snapshot(owner, "account")["conversations"], [])

    # Route checks are deliberately independent of server authentication.
