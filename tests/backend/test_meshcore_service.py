# SPDX-License-Identifier: MIT
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

from meshchatnext.src.backend.meshcore_service import MeshCoreService

OWNER = "a1" * 32


class Session:
    identity = OWNER
    failures = 0
    instances: ClassVar[list] = []

    def __init__(self):
        self.is_connected = False
        self.closed = False
        self._lock = asyncio.Lock()
        self.__class__.instances.append(self)

    async def connect(self, kind, target):
        if self.__class__.failures:
            self.__class__.failures -= 1
            raise ConnectionError("offline")
        self.is_connected = True

    async def read_identity(self):
        return {"public_key": self.identity, "name": "test"}

    async def disconnect(self):
        self.is_connected = False
        self.closed = True

    async def restore_identity(self, backup, password, *, expected_current_public_key):
        from meshchatnext.src.backend.meshcore_identity import decrypt_backup

        if expected_current_public_key != self.identity:
            raise ValueError("Wrong selected identity")
        owner, _ = decrypt_backup(backup, password)
        self.__class__.identity = owner
        return await self.read_identity()


class Messages:
    def __init__(self, session, store):
        self.session = session
        self.owner = session.identity
        self.receiving = False
        self.failed = False
        self.closed = False

    async def open(self):
        pass

    async def start_receiving(self):
        self.receiving = True

    def status(self):
        return {"processing_failed": self.failed}

    async def close(self):
        self.closed = True
        await self.session.disconnect()

    async def _drain_pending(self):
        self.drained = True

    async def _stop(self):
        self.paused = True


class Channels:
    def __init__(self, messages):
        pass

    async def refresh(self):
        return []


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Session.identity = OWNER
        Session.failures = 0
        Session.instances = []
        self.folder = tempfile.TemporaryDirectory()
        self.service = self.make()
        await self.service.start()

    def make(self):
        return MeshCoreService(
            self.folder.name,
            session_factory=Session,
            messenger_factory=Messages,
            channel_factory=Channels,
            store_factory=lambda path: SimpleNamespace(
                region_automation=lambda owner: {"enabled": False, "last_scan": 0}
            ),
            poll_interval=0.01,
            retry_max=0.04,
        )

    async def asyncTearDown(self):
        await self.service.close()
        self.folder.cleanup()

    async def wait(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.01)
        self.fail("Recovery did not reach expected state")

    async def test_retains_usb_failure_after_closing_and_clears_on_verified_connection(
        self,
    ):
        await self.service.connect("usb", "selected-device", auto_reconnect=False)
        self.service.session.connection_issue = "usb_detached"
        self.service.session.is_connected = False
        self.assertEqual(self.service.status()["connection_issue"], "usb_detached")
        await self.service.disconnect()
        self.assertEqual(self.service.status()["connection_issue"], "usb_detached")
        await self.service.connect("usb", "new-path", auto_reconnect=False)
        self.assertTrue(self.service.status()["connected"])
        self.assertIsNone(self.service.status()["connection_issue"])

    async def test_connection_identifier_changes_on_reconnect(self):
        await self.service.connect("ble", "chosen", receive=True)
        first = self.service.status()["connection_id"]
        self.assertIsInstance(first, str)
        await self.service.connect("ble", "chosen", receive=True)
        self.assertNotEqual(first, self.service.status()["connection_id"])
        await self.service.disconnect()
        self.assertIsNone(self.service.status()["connection_id"])

    async def test_opt_in_no_radio_until_selected(self):
        await asyncio.sleep(0.03)
        self.assertEqual(Session.instances, [])
        self.assertFalse(self.service.status()["selected"])

    async def test_loss_reconnects_fresh_and_restores_receiving_without_sending(self):
        await self.service.connect("ble", "chosen", receive=True)
        original = self.service.session
        original.is_connected = False
        await self.wait(
            lambda: (
                self.service.session is not original
                and self.service.status()["connected"]
            )
        )
        self.assertTrue(original.closed)
        self.assertTrue(self.service.messages.receiving)
        self.assertEqual(len(Session.instances), 2)

    async def test_processing_failure_rebuilds_workers(self):
        await self.service.connect("ble", "chosen")
        old = self.service.messages
        old.failed = True
        await self.wait(
            lambda: (
                self.service.messages is not old and self.service.status()["connected"]
            )
        )
        self.assertTrue(old.closed)

    async def test_identity_change_blocks_reconnect_before_opening_history(self):
        await self.service.connect("usb", "selected-device")
        Session.identity = "b2" * 32
        self.service.session.is_connected = False
        await self.wait(lambda: self.service.status()["state"] == "identity_changed")
        count = len(Session.instances)
        await asyncio.sleep(0.05)
        self.assertEqual(len(Session.instances), count)
        self.assertIsNone(self.service.messages)
        with self.assertRaises(ConnectionError):
            await self.service.call("session", "read_identity")

    async def test_disconnect_clears_selection_and_stops_recovery(self):
        await self.service.connect("ble", "chosen")
        await self.service.disconnect()
        count = len(Session.instances)
        await asyncio.sleep(0.05)
        self.assertEqual(len(Session.instances), count)
        self.assertIsNone(
            json.loads((Path(self.folder.name) / "connection.json").read_text())
        )

    async def test_restart_recovers_only_pinned_selected_identity(self):
        await self.service.connect("ble", "chosen", receive=True)
        await self.service.close()
        self.service = self.make()
        await self.service.start()
        await self.wait(lambda: self.service.status()["connected"])
        self.assertTrue(self.service.messages.receiving)
        saved = json.loads((Path(self.folder.name) / "connection.json").read_text())
        self.assertEqual(saved["owner"], OWNER)
        self.assertNotIn("key", saved)

    async def test_reconnect_retries_with_bounds_but_manual_disconnect_cancels(self):
        await self.service.connect("ble", "chosen")
        Session.failures = 2
        self.service.session.is_connected = False
        await self.wait(
            lambda: self.service.status()["connected"] and Session.failures == 0
        )
        self.assertEqual(len(Session.instances), 4)

    async def test_manual_mode_does_not_reconnect(self):
        await self.service.connect("ble", "chosen", auto_reconnect=False)
        self.service.session.is_connected = False
        await asyncio.sleep(0.06)
        self.assertEqual(len(Session.instances), 1)
        self.assertFalse(self.service.status()["connected"])

    async def test_invalid_persisted_selection_does_not_connect(self):
        await self.service.close()
        (Path(self.folder.name) / "connection.json").write_text('{"kind":"ble"}')
        self.service = self.make()
        await self.service.start()
        self.assertEqual(self.service.status()["state"], "invalid_selection")
        self.assertEqual(Session.instances, [])

    async def test_restore_pauses_old_workers_and_rebinds_verified_identity(self):
        from meshchatnext.src.backend.meshcore_identity import encrypt_backup
        from tests.backend.test_meshcore_identity import keypair

        await self.service.connect("ble", "chosen", receive=True)
        old = self.service.messages
        key, owner = keypair(b"x" * 32)
        backup = encrypt_backup(key, owner, "correct-password")
        result = await self.service.restore(
            backup, "correct-password", expected_current_public_key=OWNER
        )
        self.assertEqual(result["public_key"], owner)
        self.assertTrue(old.drained and old.paused and old.closed)
        self.assertIsNot(old, self.service.messages)
        self.assertTrue(self.service.messages.receiving)
        self.assertEqual(
            json.loads((Path(self.folder.name) / "connection.json").read_text())[
                "owner"
            ],
            owner,
        )
