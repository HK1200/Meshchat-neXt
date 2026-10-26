# SPDX-License-Identifier: MIT
import tempfile
import time
import unittest
from pathlib import Path

from meshchatnext.src.backend.meshcore_store import MeshCoreStore, notification_key

OWNER = "a1" * 32
PEER = "b2" * 32
OTHER = "c3" * 32


class UiStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = MeshCoreStore(Path(self.temp.name) / "db")
        self.store.bind(OWNER, "local")
        self.store.replace_contacts(
            OWNER,
            {
                PEER: {"public_key": PEER, "adv_name": "Same Name", "type": 1},
                OTHER: {"public_key": OTHER, "adv_name": "Same Name", "type": 1},
            },
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_channel_order_persists_without_changing_slots_or_preferences(self):
        channels = [
            {"slot": 1, "channel_id": PEER, "name": "#one", "kind": "public"},
            {"slot": 5, "channel_id": OTHER, "name": "#two", "kind": "private"},
        ]
        self.store.replace_channels(OWNER, channels)
        self.store.channel_preference(OWNER, PEER, muted=True)
        self.store.reorder_channels(OWNER, [OTHER, PEER])
        reopened = MeshCoreStore(Path(self.temp.name) / "db")
        reopened.replace_channels(OWNER, channels)
        rows = reopened.channel_ui(OWNER)
        self.assertEqual([row["channel_id"] for row in rows], [OTHER, PEER])
        self.assertEqual([row["slot"] for row in rows], [5, 1])
        self.assertEqual(rows[1]["muted"], 1)
        for invalid in ([PEER], [PEER, PEER], [PEER, "d4" * 32]):
            with self.assertRaises(ValueError):
                reopened.reorder_channels(OWNER, invalid)
        self.assertEqual(
            [row["channel_id"] for row in reopened.channel_ui(OWNER)], [OTHER, PEER]
        )
        with self.assertRaises(ValueError):
            reopened.reorder_channels("d4" * 32, [OTHER, PEER])
        new = {"slot": 0, "channel_id": "e5" * 32, "name": "#new", "kind": "public"}
        reopened.replace_channels(OWNER, [*channels, new])
        self.assertEqual(
            [row["name"] for row in reopened.channel_ui(OWNER)],
            ["#two", "#one", "#new"],
        )

    def test_first_unread_window_is_not_limited_to_latest_thousand(self):
        channel = "d4" * 32
        self.store.replace_channels(
            OWNER,
            [{"slot": 0, "channel_id": channel, "name": "#test", "kind": "public"}],
        )
        with self.store._connect() as db:
            db.executemany(
                "INSERT INTO channel_messages (owner,id,channel_id,slot,direction,text,timestamp,state,created,fingerprint,payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        OWNER,
                        f"m{i:04}",
                        channel,
                        0,
                        "in",
                        "Alice: test",
                        i,
                        "received",
                        i,
                        f"fp{i}",
                        "{}",
                    )
                    for i in range(1, 1003)
                ],
            )
        self.store.channel_preference(OWNER, channel, through=1)
        view = self.store.message_view(OWNER, "channel", channel)
        self.assertEqual(view["first_unread"]["id"], "m0002")
        self.assertNotIn(
            "m0002",
            [row["id"] for row in self.store.channel_history(OWNER, channel, 1000)],
        )
        window = self.store.message_window(OWNER, "channel", channel, anchor="m0002")
        self.assertEqual(window[0]["id"], "m0002")
        self.assertEqual(window[0]["sender"], "Alice")
        self.assertEqual(len(window), 1000)
        next_page = self.store.message_window(
            OWNER, "channel", channel, after=window[-1]["id"]
        )
        self.assertEqual([row["id"] for row in next_page], ["m1002"])
        with self.assertRaises(ValueError):
            self.store.message_window(OTHER, "channel", channel, anchor="m0002")

    def test_notification_target_is_owner_scoped_and_resolves_network_kind(self):
        channel = "d4" * 32
        self.store.replace_channels(
            OWNER,
            [{"slot": 0, "channel_id": channel, "name": "#test", "kind": "public"}],
        )
        key = notification_key(OWNER, "channel", channel)
        self.assertEqual(
            self.store.notification_target(OWNER, key),
            {"owner": OWNER, "target": channel, "kind": "channel"},
        )
        self.assertIsNone(self.store.notification_target(OTHER, key))
        direct = notification_key(OWNER, "direct", PEER)
        self.assertEqual(
            self.store.notification_target(OWNER, direct)["kind"], "direct"
        )
        self.store.replace_contacts(
            OWNER, {OTHER: {"public_key": OTHER, "adv_name": "Room", "type": 3}}
        )
        self.assertEqual(
            self.store.notification_target(
                OWNER, notification_key(OWNER, "direct", OTHER)
            )["kind"],
            "room",
        )

    def test_command_clock_is_durable_and_does_not_create_chat_posts(self):
        floor = int(time.time()) + 8
        first = self.store.reserve_command_clock(OWNER, PEER, floor)
        reopened = MeshCoreStore(self.store.path)
        second = reopened.reserve_command_clock(OWNER, PEER, floor)
        self.assertEqual(first, floor)
        self.assertEqual(second, floor + 1)
        self.assertEqual(reopened.outgoing_clock(OWNER, PEER), second)
        self.assertEqual(reopened.history(OWNER, PEER), [])
        with self.assertRaises(ValueError):
            reopened.reserve_command_clock(OWNER, PEER, int(time.time()) + 1000)

    def test_repeated_announces_update_one_device_without_adding_a_contact(self):
        radio = {
            "public_key": "d4" * 32,
            "adv_name": "repeater",
            "type": 2,
            "last_advert": 10,
            "out_path_len": 3,
            "out_path_hash_mode": 2,
        }
        self.store.save_announce(OWNER, radio, 100)
        self.store.save_announce(
            OWNER, {**radio, "adv_name": "new name", "last_advert": 20}, 200
        )
        self.store.touch_announce(OWNER, radio["public_key"], 300)
        # An older contact-table snapshot must not roll back the advertised name.
        self.store.save_announce(OWNER, radio)
        rows = self.store.ui_snapshot(OWNER, "account")["announces"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["name"], rows[0]["heard"], rows[0]["path_bytes"]),
            ("new name", 300, 3),
        )
        self.assertEqual(rows[0]["saved"], 0)
        self.assertEqual(len(self.store.contacts(OWNER)), 2)
        self.assertEqual(self.store.announces(OTHER), [])
        self.assertEqual(MeshCoreStore(self.store.path).announces(OWNER), rows)

    def test_discovery_becomes_saved_only_after_explicit_contact_add(self):
        radio = {
            "public_key": "d4" * 32,
            "adv_name": "client",
            "type": 1,
            "last_advert": 10,
        }
        self.store.save_announce(OWNER, radio)
        self.assertEqual(self.store.announces(OWNER)[0]["saved"], 0)
        self.store.replace_contacts(OWNER, {radio["public_key"]: radio})
        self.assertEqual(self.store.announces(OWNER)[0]["saved"], 1)

    def test_channel_banishment_is_local_name_scoped_reversible_and_excludes_unread(
        self,
    ):
        channel, other_channel = "d4" * 32, "e5" * 32
        self.store.replace_channels(
            OWNER,
            [
                {"slot": 0, "channel_id": channel, "name": "#local", "kind": "public"},
                {
                    "slot": 1,
                    "channel_id": other_channel,
                    "name": "#other",
                    "kind": "private",
                },
            ],
        )
        for slot, text, stamp in [
            (0, "Alice: first", 1),
            (0, "Bob: second", 2),
            (1, "Alice: third", 3),
        ]:
            self.store.receive(
                OWNER,
                "channel",
                {"channel_idx": slot, "text": text, "sender_timestamp": stamp},
            )
        alice = next(
            row
            for row in self.store.channel_history(OWNER, channel)
            if row["sender"] == "Alice"
        )
        self.store.banish_channel_sender(OWNER, channel, alice["id"])
        self.assertEqual(
            [row["sender"] for row in self.store.channel_history(OWNER, channel)],
            ["Bob"],
        )
        self.assertEqual(
            self.store.channel_history(OWNER, other_channel)[0]["sender"], "Alice"
        )
        self.assertEqual(
            [row["unread"] for row in self.store.channel_ui(OWNER)], [1, 1]
        )
        blocks = self.store.channel_banishments(OWNER)
        self.assertEqual(
            (blocks[0]["sender"], blocks[0]["channel_name"]), ("Alice", "#local")
        )
        self.assertEqual(self.store.channel_banishments(OTHER), [])
        with self.assertRaises(ValueError):
            self.store.banish_channel_sender(OWNER, other_channel, alice["id"])
        reopened = MeshCoreStore(self.store.path)
        self.assertEqual(reopened.channel_banishments(OWNER), blocks)
        reopened.unbanish_channel_sender(OWNER, channel, "Alice")
        self.assertEqual(len(reopened.channel_history(OWNER, channel)), 2)
        self.assertEqual([row["unread"] for row in reopened.channel_ui(OWNER)], [2, 1])

    def test_channel_read_and_mute_preferences_follow_identity_not_slot(self):
        channel = "d4" * 32
        row = {"slot": 1, "channel_id": channel, "name": "#local", "kind": "public"}
        self.store.replace_channels(OWNER, [row])
        self.store.receive(
            OWNER,
            "channel",
            {"channel_idx": 1, "text": "Alice: first", "sender_timestamp": 1},
        )
        through = self.store.channel_history(OWNER, channel)[0]["created"]
        self.store.channel_preference(OWNER, channel, through=through, muted=True)
        self.store.receive(
            OWNER,
            "channel",
            {"channel_idx": 1, "text": "Alice: later", "sender_timestamp": 2},
        )
        self.store.replace_channels(OWNER, [{**row, "slot": 2}])
        actual = MeshCoreStore(self.store.path).channel_ui(OWNER)[0]
        self.assertEqual((actual["unread"], actual["muted"], actual["slot"]), (1, 1, 2))
        with self.assertRaises(ValueError):
            self.store.channel_preference(OTHER, channel, muted=True)

    def test_discovered_sensors_require_explicit_save_and_preserve_announces(self):
        sensor = "e5" * 32
        self.assertTrue(self.store.record_node_discovery(OWNER, sensor, 4, 100))
        self.assertEqual(self.store.nodes(OWNER), [])
        self.store.node_preference(OWNER, sensor, True)
        self.assertEqual(self.store.nodes(OWNER)[0]["kind"], 4)
        self.assertEqual(self.store.nodes(OTHER), [])
        self.store.save_announce(
            OWNER,
            {"public_key": sensor, "type": 4, "adv_name": "Weather", "last_advert": 50},
            101,
        )
        self.store.record_node_discovery(OWNER, sensor, 4, 102)
        self.assertEqual(self.store.nodes(OWNER)[0]["name"], "Weather")
        self.assertFalse(self.store.record_node_discovery(OWNER, sensor, 2, 103))
        self.assertEqual(self.store.nodes(OWNER)[0]["kind"], 4)
        self.assertEqual(len(self.store.contacts(OWNER)), 2)

    def test_saved_nodes_stay_separate_from_contacts_and_refresh_details(self):
        radio = {
            "public_key": "d4" * 32,
            "adv_name": "repeater",
            "type": 2,
            "last_advert": 10,
        }
        self.store.save_announce(OWNER, radio, 100)
        self.store.node_preference(OWNER, radio["public_key"], True)
        self.store.save_announce(OWNER, {**radio, "adv_name": "renamed"}, 200)
        self.assertEqual(self.store.nodes(OWNER)[0]["name"], "renamed")
        self.assertEqual(len(self.store.contacts(OWNER)), 2)
        self.assertEqual(self.store.nodes(OTHER), [])
        self.assertEqual(
            MeshCoreStore(self.store.path).nodes(OWNER), self.store.nodes(OWNER)
        )
        with self.assertRaises(ValueError):
            self.store.node_preference(OWNER, PEER, True)
        self.store.node_preference(OWNER, radio["public_key"], False)
        self.assertEqual(self.store.nodes(OWNER), [])
        self.assertEqual(len(self.store.announces(OWNER)), 1)

    def test_names_never_create_links_and_explicit_links_are_account_scoped(self):
        self.assertEqual(self.store.ui_snapshot(OWNER, "rns-account")["links"], [])
        self.assertEqual(
            len(self.store.ui_snapshot(OWNER, "rns-account")["contacts"]), 2
        )
        self.store.link_contact(OWNER, "rns-account", 12, PEER)
        self.assertEqual(
            self.store.ui_snapshot(OWNER, "rns-account")["links"],
            [{"contact": 12, "peer": PEER}],
        )
        self.assertEqual(
            self.store.ui_snapshot(OWNER, "other-rns-account")["links"], []
        )
        self.assertEqual(self.store.ui_snapshot(OTHER, "rns-account")["links"], [])
        with self.assertRaises(ValueError):
            self.store.link_contact(OWNER, "rns-account", 13, PEER)
        self.store.link_contact(OWNER, "rns-account", 12, None)
        self.assertEqual(self.store.ui_snapshot(OWNER, "rns-account")["links"], [])

    def test_read_marker_does_not_clear_later_or_other_peer_messages(self):
        self.store.receive(
            OWNER,
            "direct",
            {"pubkey_prefix": PEER[:12], "sender_timestamp": 1, "text": "first"},
        )
        through = self.store.history(OWNER, PEER)[0]["created"]
        self.store.receive(
            OWNER,
            "direct",
            {"pubkey_prefix": PEER[:12], "sender_timestamp": 2, "text": "second"},
        )
        self.store.receive(
            OWNER,
            "direct",
            {"pubkey_prefix": OTHER[:12], "sender_timestamp": 3, "text": "third"},
        )
        self.store.mark_read(OWNER, PEER, through)
        rows = {
            row["peer"]: row
            for row in self.store.ui_snapshot(OWNER, "account")["conversations"]
        }
        self.assertEqual(rows[PEER]["unread"], 1)
        self.assertEqual(rows[OTHER]["unread"], 1)
        self.store.mark_read(OWNER, PEER, time.time())
        self.assertEqual(
            {
                row["peer"]: row["unread"]
                for row in self.store.ui_snapshot(OWNER, "account")["conversations"]
            }[PEER],
            0,
        )

    def test_snapshot_and_link_survive_database_reopen(self):
        self.store.link_contact(OWNER, "account", 12, PEER)
        reopened = MeshCoreStore(self.store.path)
        self.assertEqual(
            reopened.ui_snapshot(OWNER, "account")["links"],
            [{"contact": 12, "peer": PEER}],
        )
        with self.assertRaises(ValueError):
            self.store.link_contact(OWNER, "account", 12, "invalid-key")


class OfflineUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnected_history_and_links_require_the_expected_meshcore_owner(
        self,
    ):
        import json

        from meshchatnext.src.backend.meshcore_service import MeshCoreService

        with tempfile.TemporaryDirectory() as folder:
            store = MeshCoreStore(Path(folder) / "history.sqlite")
            store.bind(OWNER, "local")
            store.replace_contacts(
                OWNER, {PEER: {"public_key": PEER, "adv_name": "radio peer", "type": 1}}
            )
            store.receive(
                OWNER,
                "direct",
                {"pubkey_prefix": PEER[:12], "sender_timestamp": 1, "text": "saved"},
            )
            (Path(folder) / "ui-owner.json").write_text(json.dumps(OWNER))
            service = MeshCoreService(folder)
            snapshot = await service.ui("account", peer=PEER)
            self.assertFalse(snapshot["connected"])
            self.assertEqual(snapshot["messages"][0]["text"], "saved")
            with self.assertRaises(ValueError):
                await service.ui(
                    "account",
                    contact=12,
                    link_peer=PEER,
                    linking=True,
                    expected_owner=OTHER,
                )
            snapshot = await service.ui(
                "account",
                contact=12,
                link_peer=PEER,
                linking=True,
                expected_owner=OWNER,
            )
            self.assertEqual(snapshot["links"], [{"contact": 12, "peer": PEER}])
            await service.close()
