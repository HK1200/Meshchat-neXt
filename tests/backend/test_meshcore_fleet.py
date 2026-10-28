# SPDX-License-Identifier: MIT
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from meshchatnext.src.backend.meshcore_fleet import MeshCoreFleet
from meshchatnext.src.backend.meshcore_service import MeshCoreService
from tests.backend.test_meshcore_service import Channels, Messages, Session


class RadioSession(Session):
    def __init__(self):
        super().__init__()
        self.target = None

    async def connect(self, kind, target):
        self.target = target
        if target == "slow":
            await asyncio.sleep(60)
        if target == "away":
            raise ConnectionError("out of range")
        self.identity = ("b2" if target == "second" else "a1") * 32
        self.is_connected = True


def service(folder, **kwargs):
    return MeshCoreService(
        folder,
        **kwargs,
        session_factory=RadioSession,
        messenger_factory=Messages,
        channel_factory=Channels,
        poll_interval=0.01,
        retry_max=0.04,
    )


class FleetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        RadioSession.instances = []
        self.temp = tempfile.TemporaryDirectory()
        self.fleet = MeshCoreFleet(self.temp.name, service_factory=service)
        await self.fleet.start()

    async def asyncTearDown(self):
        await self.fleet.close()
        self.temp.cleanup()

    async def wait(self, predicate):
        for _ in range(150):
            if predicate():
                return
            await asyncio.sleep(0.01)
        self.fail("Independent radio did not reach expected state")

    async def add(self, target="second"):
        result = await self.fleet.add(kind="ble", target=target, label=target)
        return result["added_radio_id"]

    async def test_two_live_radios_recover_independently(self):
        await self.fleet.connect(kind="ble", target="first", receive=True)
        key = await self.add()
        second = self.fleet.resolve(key)
        first = self.fleet.resolve("default")
        await self.wait(lambda: second.status()["connected"])
        original = first.session
        lost = second.session
        second.session.is_connected = False
        await self.wait(
            lambda: second.session is not lost and second.status()["connected"]
        )
        self.assertIs(first.session, original)
        self.assertTrue(first.status()["receiving"])
        self.assertTrue(second.status()["receiving"])

    async def test_away_radio_does_not_block_live_radio_and_persists_intent(self):
        await self.fleet.connect(kind="usb", target="first")
        key = await self.add("away")
        await asyncio.sleep(0.06)
        self.assertTrue(self.fleet.resolve("default").status()["connected"])
        saved = json.loads(
            (Path(self.temp.name) / "radios" / key / "connection.json").read_text()
        )
        self.assertTrue(saved["auto_reconnect"])
        await self.fleet.close()
        self.fleet = MeshCoreFleet(self.temp.name, service_factory=service)
        await self.fleet.start()
        await self.wait(lambda: self.fleet.resolve("default").status()["connected"])
        self.assertEqual(self.fleet.resolve(key)._selection["target"], "away")

    async def test_slow_unavailable_radio_does_not_block_either_inbox_view(self):
        await self.fleet.connect(kind="usb", target="first")
        key = await self.add("slow")
        await self.wait(lambda: self.fleet.resolve(key)._lock.locked())
        result = await asyncio.wait_for(self.fleet.ui("account"), 0.5)
        self.assertTrue(result["connected"])
        result = await asyncio.wait_for(self.fleet.ui("account", radio_id=key), 0.5)
        self.assertFalse(result["connected"])

    async def test_disabling_slow_radio_does_not_wait_for_bluetooth_timeout(self):
        key = await self.add("slow")
        await self.wait(lambda: self.fleet.resolve(key)._lock.locked())
        await asyncio.wait_for(self.fleet.set_enabled(key, False), 0.5)
        self.assertFalse(self.fleet.resolve(key).status()["auto_reconnect"])

    async def test_manual_radio_connects_once_without_background_retries(self):
        row = await self.fleet.add(
            kind="ble", target="second", label="Manual", auto_reconnect=False
        )
        radio = self.fleet.resolve(row["added_radio_id"])
        # Adding a manual radio schedules exactly one initial attempt. Wait for
        # that attempt, rather than assuming disk work completes within 1.5s.
        initial = tuple(self.fleet._initial_tasks)
        self.assertEqual(len(initial), 1)
        await asyncio.wait_for(asyncio.gather(*initial), timeout=5)
        self.assertTrue(radio.status()["connected"], radio.status())
        original = radio.session
        original.is_connected = False
        await asyncio.sleep(0.06)
        self.assertIs(radio.session, original)

    async def test_identity_clone_is_blocked_without_closing_original(self):
        await self.fleet.connect(kind="ble", target="first")
        key = await self.add("clone")
        await self.wait(
            lambda: self.fleet.resolve(key).status()["state"] == "identity_changed"
        )
        self.assertTrue(self.fleet.resolve("default").status()["connected"])
        self.assertIsNone(self.fleet.resolve(key).messages)

    async def test_duplicate_device_and_wrong_radio_owner_are_rejected(self):
        await self.fleet.connect(kind="ble", target="first")
        with self.assertRaises(ValueError):
            await self.add("FIRST")
        with self.assertRaises(ValueError):
            self.fleet.resolve("default", "b2" * 32)
        with self.assertRaises(ValueError):
            self.fleet.resolve("../bad")

    async def test_disable_retains_device_but_stops_retry_and_restart(self):
        key = await self.add()
        radio = self.fleet.resolve(key)
        await self.wait(lambda: radio.status()["connected"])
        await self.fleet.set_enabled(key, False)
        count = len(RadioSession.instances)
        await asyncio.sleep(0.07)
        self.assertEqual(len(RadioSession.instances), count)
        self.assertFalse(radio.status()["connected"])
        self.assertEqual(radio._selection["target"], "second")
        await self.fleet.close()
        self.fleet = MeshCoreFleet(self.temp.name, service_factory=service)
        await self.fleet.start()
        await asyncio.sleep(0.05)
        self.assertFalse(self.fleet.resolve(key).status()["connected"])
        await self.fleet.set_enabled(key, True)
        await self.wait(lambda: self.fleet.resolve(key).status()["connected"])

    async def test_view_and_selection_survive_restart_without_moving_legacy_history(
        self,
    ):
        await self.fleet.connect(kind="usb", target="first")
        key = await self.add()
        await self.wait(lambda: self.fleet.resolve(key).status()["connected"])
        await self.fleet.configure(
            view="separate", active=key, radio_id=key, label="Portable"
        )
        await self.fleet.close()
        self.fleet = MeshCoreFleet(self.temp.name, service_factory=service)
        await self.fleet.start()
        self.assertEqual(self.fleet.status()["radio_id"], key)
        self.assertEqual(self.fleet.status()["inbox_mode"], "separate")
        self.assertEqual(self.fleet.resolve(key).folder, Path(self.temp.name))
        self.assertTrue((Path(self.temp.name) / "history.sqlite").exists())

    async def test_combined_inbox_labels_same_peer_without_merging_owners(self):
        await self.fleet.connect(kind="ble", target="first")
        key = await self.add()
        await self.wait(lambda: self.fleet.resolve(key).status()["connected"])
        with self.fleet._store._connect() as db:
            for index, owner in enumerate(["a1" * 32, "b2" * 32]):
                db.execute(
                    "INSERT INTO contacts(owner,peer,name,kind,active) VALUES(?,?,?,?,?)",
                    (owner, "c3" * 32, "Peer", 1, 1),
                )
                db.execute(
                    "INSERT INTO messages(owner,id,peer,direction,text,timestamp,state,created) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        owner,
                        str(index),
                        "c3" * 32,
                        "in",
                        "hello",
                        index + 1,
                        "received",
                        index + 1,
                    ),
                )
        result = await self.fleet.ui("reticulum-account")
        self.assertEqual(
            {row["radio_id"] for row in result["conversations"]}, {"default", key}
        )
        await self.fleet.configure(view="separate", active=key)
        result = await self.fleet.ui("reticulum-account")
        self.assertEqual(len(result["conversations"]), 1)
        self.assertEqual(result["conversations"][0]["owner"], "b2" * 32)


class FleetHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from types import SimpleNamespace

        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from meshchatnext.src.backend.meshcore_http import register_meshcore_routes

        self.temp = tempfile.TemporaryDirectory()
        self.fleet = MeshCoreFleet(self.temp.name, service_factory=service)
        await self.fleet.start()
        await self.fleet.connect(kind="ble", target="first")
        routes = web.RouteTableDef()
        owner = SimpleNamespace(
            meshcore_service=self.fleet,
            identity=SimpleNamespace(hash=bytes.fromhex("d4" * 16)),
        )
        register_meshcore_routes(routes, owner)
        app = web.Application()
        app.add_routes(routes)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.fleet.close()
        self.temp.cleanup()

    async def test_api_add_select_view_and_explicit_identity_routing(self):
        response = await self.client.post(
            "/api/v1/meshcore/radio-add",
            json={"kind": "ble", "target": "second", "label": "Portable"},
        )
        self.assertEqual(response.status, 200)
        key = (await response.json())["result"]["added_radio_id"]
        for _ in range(100):
            if self.fleet.resolve(key).status()["connected"]:
                break
            await asyncio.sleep(0.01)
        response = await self.client.get(
            "/api/v1/meshcore/identity", params={"radio": key}
        )
        self.assertEqual((await response.json())["result"]["public_key"], "b2" * 32)
        response = await self.client.get(
            "/api/v1/meshcore/ui", params={"radio": key, "owner": "a1" * 32}
        )
        self.assertEqual(response.status, 400)
        response = await self.client.post(
            "/api/v1/meshcore/radio-configure", json={"active": key, "view": "separate"}
        )
        self.assertEqual(response.status, 200)
        response = await self.client.get(
            "/api/v1/meshcore/status", params={"radio": "default"}
        )
        self.assertEqual((await response.json())["radio_id"], "default")
        response = await self.client.get(
            "/api/v1/meshcore/status", params={"radio": "unknown"}
        )
        self.assertEqual(response.status, 400)

    async def test_invalid_connect_types_do_not_touch_either_radio(self):
        original = self.fleet.resolve().session
        for target in (None, 42, [], {}):
            response = await self.client.post(
                "/api/v1/meshcore/connect", json={"kind": "ble", "target": target}
            )
            self.assertEqual(response.status, 400)
        self.assertIs(self.fleet.resolve().session, original)

    async def test_owner_routing_still_reads_saved_history_after_manual_disconnect(
        self,
    ):
        await self.fleet.resolve().disconnect()
        response = await self.client.get(
            "/api/v1/meshcore/ui", params={"owner": "a1" * 32}
        )
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["result"]["owner"], "a1" * 32)
