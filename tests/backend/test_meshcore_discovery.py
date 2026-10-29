# SPDX-License-Identifier: MIT
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from meshchatnext.src.backend.meshcore_nodes import MeshCoreNodes
from meshchatnext.src.backend.meshcore_session import MeshCoreSession

OWNER, PEER = "a1" * 32, "b2" * 32


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.callback = None
        self.unsub = Mock()

        def subscribe(kind, callback):
            self.callback = callback
            return SimpleNamespace(unsubscribe=self.unsub)

        self.commands = SimpleNamespace(send_node_discover_req=AsyncMock())
        self.client = SimpleNamespace(commands=self.commands, subscribe=subscribe)
        self.session = SimpleNamespace(
            _client=self.client, _lock=asyncio.Lock(), _payload=MeshCoreSession._payload
        )
        self.store = SimpleNamespace(record_node_discovery=Mock(return_value=True))
        self.messages = SimpleNamespace(
            session=self.session,
            _types=SimpleNamespace(DISCOVER_RESPONSE="discover"),
            owner=OWNER,
            store=self.store,
            _check=Mock(),
        )
        self.nodes = MeshCoreNodes(self.messages)
        self.nodes.DISCOVERY_WINDOW = 0
        self.payloads = []

        async def send(**kwargs):
            self.options = kwargs
            for body in self.payloads:
                self.callback(
                    SimpleNamespace(
                        payload={
                            "tag": kwargs["tag"].to_bytes(4, "little").hex(),
                            **body,
                        }
                    )
                )
            return SimpleNamespace(payload={}, is_error=lambda: False)

        self.commands.send_node_discover_req.side_effect = send

    async def test_filters_infrastructure_and_correlates_full_keys_deduplicated(self):
        self.payloads = [
            {"pubkey": PEER, "node_type": 2},
            {"pubkey": PEER, "node_type": 2},
            {"pubkey": "c3" * 32, "node_type": 3},
            {"pubkey": "d4" * 32, "node_type": 4},
            {"pubkey": "e5" * 32, "node_type": 1},
            {"pubkey": "f6" * 32, "node_type": True},
            {"pubkey": PEER[:16], "node_type": 2},
            {"pubkey": OWNER, "node_type": 2},
            {"pubkey": "ff" * 32, "node_type": 2, "tag": "00000000"},
        ]
        result = await self.nodes.discover()
        self.assertEqual([r["kind"] for r in result["nodes"]], [2, 3, 4])
        self.assertEqual(self.options["filter"], 0x1C)
        self.assertFalse(self.options["prefix_only"])
        self.assertEqual(self.store.record_node_discovery.call_count, 3)
        self.unsub.assert_called_once()

    async def test_no_replies_are_not_reported_as_successful_device_discovery(self):
        result = await self.nodes.discover()
        self.assertEqual(result["nodes"], [])
        self.store.record_node_discovery.assert_not_called()

    async def test_rate_limit_prevents_second_radio_transmission(self):
        await self.nodes.discover()
        with self.assertRaisesRegex(ValueError, "Wait 30"):
            await self.nodes.discover()
        self.commands.send_node_discover_req.assert_awaited_once()

    async def test_rejected_request_unsubscribes_and_never_persists(self):
        self.commands.send_node_discover_req.return_value = None
        self.commands.send_node_discover_req.side_effect = None
        with self.assertRaises(ConnectionError):
            await self.nodes.discover()
        self.unsub.assert_called_once()
        self.store.record_node_discovery.assert_not_called()

    async def test_disconnection_does_not_save_partial_results(self):
        self.payloads = [{"pubkey": PEER, "node_type": 2}]
        self.messages._check.side_effect = [None, None, ConnectionError("disconnected")]
        with self.assertRaises(ConnectionError):
            await self.nodes.discover()
        self.store.record_node_discovery.assert_not_called()
        self.unsub.assert_called_once()

    async def test_cancellation_cleans_subscription(self):
        self.nodes.DISCOVERY_WINDOW = 10
        task = asyncio.create_task(self.nodes.discover())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.unsub.assert_called_once()
        self.store.record_node_discovery.assert_not_called()

    async def test_conflicting_saved_type_is_not_returned_as_discovered(self):
        self.payloads = [{"pubkey": PEER, "node_type": 2}]
        self.store.record_node_discovery.return_value = False
        self.assertEqual((await self.nodes.discover())["nodes"], [])

    async def test_extended_discovery_correlates_raw_full_key_and_saves_profile(self):
        import struct

        callbacks = {}

        def subscribe(kind, callback):
            callbacks[kind] = callback
            return SimpleNamespace(unsubscribe=Mock())

        self.client.subscribe = subscribe
        self.messages._types.CONTROL_DATA = "raw"
        self.store.record_peer_radio2 = Mock()

        async def send(control, data):
            self.assertEqual(control, 0x82)
            self.assertEqual(data[0], 0x1C)
            header = bytes([0x92, 0]) + data[1:5] + bytes.fromhex(PEER)
            trailer = bytes([1, 5]) + struct.pack("<IIBB", 911150, 250000, 7, 5)
            for packet, hops in (
                (header + trailer, 1),
                (header[:2] + bytes(4) + header[6:] + trailer, 0),
                (header[:14] + trailer, 0),
            ):
                callbacks["raw"](
                    SimpleNamespace(payload={"payload": packet, "path_len": hops})
                )
            self.assertEqual(self.store.record_peer_radio2.call_count, 0)
            callbacks["raw"](
                SimpleNamespace(payload={"payload": header + trailer, "path_len": 0})
            )
            callbacks["discover"](
                SimpleNamespace(
                    payload={"tag": data[1:5].hex(), "pubkey": PEER, "node_type": 2}
                )
            )
            return SimpleNamespace(payload={}, is_error=lambda: False)

        self.commands.send_control_data = AsyncMock(side_effect=send)
        result = await self.nodes.discover()
        self.assertEqual(len(result["nodes"]), 1)
        self.assertEqual(result["nodes"][0]["radio2"]["state"], "enabled")
        self.commands.send_node_discover_req.assert_not_awaited()
        self.store.record_peer_radio2.assert_called_once()
        self.assertEqual(
            self.store.record_peer_radio2.call_args.args[:2], (OWNER, PEER)
        )

    async def test_extended_owner_switch_discards_results_and_unsubscribes_both(self):
        subscriptions = []

        def subscribe(kind, callback):
            unsub = Mock()
            subscriptions.append(unsub)
            return SimpleNamespace(unsubscribe=unsub)

        self.client.subscribe = subscribe
        self.messages._types.CONTROL_DATA = "raw"
        self.store.record_peer_radio2 = Mock()

        async def send(*args):
            self.messages.owner = "c3" * 32
            return SimpleNamespace(payload={}, is_error=lambda: False)

        self.commands.send_control_data = AsyncMock(side_effect=send)
        with self.assertRaisesRegex(ConnectionError, "changed"):
            await self.nodes.discover()
        self.store.record_node_discovery.assert_not_called()
        self.store.record_peer_radio2.assert_not_called()
        self.assertEqual(len(subscriptions), 2)
        for unsub in subscriptions:
            unsub.assert_called_once()

    async def test_missing_firmware_command_never_sends(self):
        del self.commands.send_node_discover_req
        with self.assertRaisesRegex(ValueError, "does not support"):
            await self.nodes.discover()
        self.unsub.assert_not_called()
