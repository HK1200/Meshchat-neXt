# SPDX-License-Identifier: MIT
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from meshchatnext.src.backend.meshcore_tools import (
    MeshCoreTools,
    channel_scope,
    region_name,
)

OWNER, OTHER, CHANNEL, PEER = "a1" * 32, "b2" * 32, "c3" * 32, "d4" * 32


def ok(payload=None):
    return SimpleNamespace(payload=payload or {}, is_error=lambda: False)


class RegionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = MeshCoreStore(Path(self.temp.name) / "history.sqlite")
        self.store.bind(OWNER, "owner")
        self.store.replace_channels(
            OWNER,
            [{"slot": 1, "channel_id": CHANNEL, "name": "#test", "kind": "public"}],
        )

    def test_hidden_public_channel_suppresses_alerts_without_deleting_history_or_other_owner(
        self,
    ):
        event = {
            "owner": OWNER,
            "target": CHANNEL,
            "kind": "channel",
            "created": 123,
            "text": "Peer: hi",
        }
        self.assertTrue(self.store.notification_allowed(event))
        self.store.channel_visibility(OWNER, CHANNEL, True)
        self.assertTrue(self.store.channel_ui(OWNER)[0]["hidden"])
        self.assertFalse(self.store.notification_allowed(event))
        self.assertEqual(
            MeshCoreStore(self.store.path).channel_ui(OWNER)[0]["hidden"], 1
        )
        with self.assertRaises(ValueError):
            self.store.channel_visibility(OTHER, CHANNEL, True)
        self.store.channel_visibility(OWNER, CHANNEL, False)
        self.assertTrue(self.store.notification_allowed(event))
        self.assertFalse(self.store.channel_ui(OWNER)[0]["hidden"])

    def test_public_region_validation_and_utf8_rejection(self):
        self.assertEqual(region_name("lynden"), "#lynden")
        self.assertEqual(region_name("#wa/whatcom"), "#wa/whatcom")
        for value in (
            "",
            None,
            True,
            "$private",
            "with space",
            "#☃",
            "#" + "a" * 30,
            "#foo;reboot",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                region_name(value)

    def test_channel_defaults_and_overrides_are_scoped_by_radio_and_never_modify_contacts(
        self,
    ):
        self.store.set_region_default(OWNER, "#lynden")
        self.assertEqual(self.store.channel_scope(OWNER, CHANNEL), "#lynden")
        self.store.channel_scope(OWNER, CHANNEL, "*")
        self.assertEqual(self.store.channel_scope(OWNER, CHANNEL), "*")
        self.store.channel_scope(OWNER, CHANNEL, None)
        self.assertEqual(self.store.channel_scope(OWNER, CHANNEL), "#lynden")
        self.assertEqual(self.store.channel_scope(OTHER, CHANNEL), None)
        self.assertEqual(self.store.contacts(OWNER), [])
        with self.assertRaises(ValueError):
            self.store.channel_scope(OTHER, CHANNEL, "#wrong")
        self.assertEqual(self.store.channel_ui(OWNER)[0]["scope"], None)

    def test_preferences_survive_restart_and_automation_is_off_by_default(self):
        self.assertFalse(self.store.region_automation(OWNER)["enabled"])
        self.store.region_automation(OWNER, enabled=True, scanned=123)
        again = MeshCoreStore(self.store.path)
        self.assertEqual(
            again.region_automation(OWNER), {"enabled": True, "last_scan": 123}
        )
        self.assertFalse(again.region_automation(OTHER)["enabled"])


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.listeners = {}

        def subscribe(kind, fn):
            self.listeners[kind] = fn
            return SimpleNamespace(unsubscribe=lambda: self.listeners.pop(kind, None))

        self.commands = SimpleNamespace(
            set_flood_scope=AsyncMock(return_value=ok()),
            send_advert=AsyncMock(return_value=ok()),
            get_stats_radio=AsyncMock(
                return_value=ok(
                    {
                        "noise_floor": -115,
                        "last_rssi": -98,
                        "last_snr": 3,
                        "secret": "hidden",
                    }
                )
            ),
            send_trace=AsyncMock(),
            req_regions_async=AsyncMock(),
        )
        self.session = SimpleNamespace(
            _lock=asyncio.Lock(),
            _client=SimpleNamespace(commands=self.commands, subscribe=subscribe),
            _payload=MeshCoreSession._payload,
            _close=AsyncMock(),
        )
        self.store = SimpleNamespace(
            regions=Mock(return_value=[]),
            save_region=Mock(),
            set_region_default=Mock(),
            announces=Mock(return_value=[{"peer": PEER, "kind": 2}]),
            region_automation=Mock(return_value={"enabled": False, "last_scan": 0}),
        )
        self.messages = SimpleNamespace(
            session=self.session,
            _check=Mock(),
            owner=OWNER,
            store=self.store,
            rx_log=[],
            _types=SimpleNamespace(TRACE_DATA="trace", BINARY_RESPONSE="binary"),
        )
        self.nodes = SimpleNamespace(discover=AsyncMock(return_value={"nodes": []}))
        self.tools = MeshCoreTools(self.messages, self.nodes)
        self.tools.TIMEOUT = 0.01

    async def asyncTearDown(self):
        await self.tools.close()

    async def test_channel_scope_resets_on_success_and_body_error(self):
        async with channel_scope(self.session, "#lynden"):
            pass
        self.assertEqual(
            [x.args for x in self.commands.set_flood_scope.await_args_list],
            [("#lynden",), (None,)],
        )
        self.commands.set_flood_scope.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "body"):
            async with channel_scope(self.session, "*"):
                raise RuntimeError("body")
        self.assertEqual(
            self.commands.set_flood_scope.await_args_list[-1].args, (None,)
        )

    async def test_failed_reset_closes_meshcore_before_any_next_message(self):
        self.commands.set_flood_scope.side_effect = [ok(), None]
        with self.assertRaisesRegex(ConnectionError, "Scope reset"):
            async with channel_scope(self.session, "#lynden"):
                pass
        self.session._close.assert_awaited_once()

    async def test_failed_scope_application_still_resets(self):
        self.commands.set_flood_scope.side_effect = [None, ok()]
        with self.assertRaises(ConnectionError):
            async with channel_scope(self.session, "#lynden"):
                self.fail("must not send")
        self.assertEqual(self.commands.set_flood_scope.await_count, 2)

    async def test_cancellation_still_clears_channel_override(self):
        with self.assertRaises(asyncio.CancelledError):
            async with channel_scope(self.session, "#lynden"):
                raise asyncio.CancelledError()
        self.assertEqual(
            self.commands.set_flood_scope.await_args_list[-1].args, (None,)
        )

    async def test_local_and_flood_announces_are_explicit_and_rate_limited(self):
        self.assertEqual((await self.tools.announce(False))["kind"], "local")
        self.commands.send_advert.assert_awaited_once_with(flood=False)
        with self.assertRaises(ValueError):
            await self.tools.announce(True)
        self.tools._last_announce = None
        self.assertEqual((await self.tools.announce(True))["kind"], "flood")
        with self.assertRaises(ValueError):
            await self.tools.announce(1)

    async def test_radio_stats_excludes_unknown_fields_and_invalid_sentinels(self):
        self.assertEqual((await self.tools.radio_stats())["noise_floor"], -115)
        self.assertNotIn("secret", await self.tools.radio_stats())
        self.commands.get_stats_radio.return_value = ok(
            {"noise_floor": 32767, "last_snr": float("nan")}
        )
        self.assertEqual(await self.tools.radio_stats(), {"noise_floor": None})

    async def test_channel_default_is_local_and_does_not_write_radio_global_scope(self):
        await self.tools.set_default_region("#lynden")
        self.store.set_region_default.assert_called_once_with(OWNER, "#lynden")
        self.commands.set_flood_scope.assert_not_awaited()

    async def test_trace_accepts_early_correlated_reply_and_ignores_other_tags(self):
        async def send(**kw):
            self.listeners["trace"](
                SimpleNamespace(payload={"tag": 0, "auth": kw["auth_code"]})
            )
            self.listeners["trace"](
                SimpleNamespace(
                    payload={
                        "tag": kw["tag"],
                        "auth": kw["auth_code"],
                        "path": [{"hash": "ab", "snr": 3}],
                        "path_len": 1,
                    }
                )
            )
            return ok()

        self.commands.send_trace.side_effect = send
        result = await self.tools.trace("ab,cd")
        self.assertEqual(result["state"], "verified")
        self.assertFalse(self.listeners)
        with self.assertRaises(ValueError):
            await self.tools.trace("ab,cd")

    async def test_trace_timeout_is_unconfirmed_and_cleans_listener(self):
        self.commands.send_trace.return_value = ok()
        self.assertEqual((await self.tools.trace("ab"))["state"], "unconfirmed")
        self.assertFalse(self.listeners)

    async def test_region_reply_tags_and_names_are_validated_before_saving(self):
        ack = bytes.fromhex("12345678")

        async def send(*args, **kwargs):
            self.listeners["binary"](
                SimpleNamespace(
                    payload={
                        "tag": ack.hex(),
                        "data": (ack + b"#lynden #wa #lynden").hex(),
                    }
                )
            )
            return ok({"expected_ack": ack})

        self.commands.req_regions_async.side_effect = send
        result = await self.tools.discover_regions(PEER)
        self.assertEqual(result["regions"], ["#lynden", "#wa"])
        self.assertEqual(self.store.save_region.call_count, 2)
        self.assertFalse(self.listeners)

    async def test_region_scan_has_bounded_queries_and_persisted_cooldown(self):
        self.nodes.discover.return_value = {
            "nodes": [{"peer": str(i).zfill(64), "kind": 2} for i in range(8)]
        }
        self.tools.discover_regions = AsyncMock(
            return_value={"state": "verified", "regions": ["#lynden"]}
        )
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "meshchatnext.src.backend.meshcore_tools.asyncio.sleep", new=AsyncMock()
        ):
            await self.tools.start_region_scan()
            await self.tools._region_task
        self.assertEqual(self.tools.discover_regions.await_count, 3)
        self.assertEqual(self.tools.region_scan["found"], 1)
        self.store.region_automation.return_value = {
            "enabled": True,
            "last_scan": time.time(),
        }
        with self.assertRaises(ValueError):
            await self.tools.start_region_scan()
        self.assertEqual(
            (await self.tools.start_region_scan(automatic=True))["state"], "cooldown"
        )
