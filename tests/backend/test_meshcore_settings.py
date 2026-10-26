# SPDX-License-Identifier: MIT
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_settings import (
    SettingsApplyError,
    validate_changes,
)


class Connection:
    def __init__(self, kind, target, **kwargs):
        self.kind = kind
        self.is_connected = False

    async def disconnect(self):
        self.is_connected = False


class Client:
    def __init__(self, connection, **kwargs):
        self.connection = connection
        self.commands = self
        self.sent = []
        self.own = {
            "radio_freq": 906.875,
            "radio_bw": 250.0,
            "radio_sf": 11,
            "radio_cr": 5,
            "tx_power": 22,
            "max_tx_power": 22,
            "public_key": "secret",
        }
        self.device = {
            "fw ver": 10,
            "path_hash_mode": 0,
            "repeat": True,
            "ble_pin": 123456,
        }
        self.reject_command = None
        self.ignore_command = None

    def event(self, payload=None, error=False):
        return SimpleNamespace(payload=dict(payload or {}), is_error=lambda: error)

    async def connect(self):
        self.connection.is_connected = True
        return self.event(self.own)

    async def disconnect(self):
        self.connection.is_connected = False

    async def send_appstart(self):
        return self.event(self.own)

    async def send_device_query(self):
        return self.event(self.device)

    async def send(self, frame, expected):
        self.sent.append(frame)
        command = frame[0]
        if command == self.reject_command:
            return self.event(error=True)
        if command != self.ignore_command:
            if command == 11:
                freq, bw, sf, cr = struct.unpack("<IIBB", frame[1:11])
                self.own.update(
                    radio_freq=freq / 1000, radio_bw=bw / 1000, radio_sf=sf, radio_cr=cr
                )
                if len(frame) > 11:
                    self.device["repeat"] = bool(frame[11])
            elif command == 12:
                self.own["tx_power"] = frame[1]
            elif command == 61:
                self.device["path_hash_mode"] = frame[2]
        return self.event()


class ValidationTests(unittest.TestCase):
    def test_invalid_values(self):
        invalid = {
            "frequency_mhz": [
                True,
                "906",
                float("nan"),
                float("inf"),
                149.999,
                2500.001,
                906.1234,
            ],
            "bandwidth_khz": [None, 6.999, 500.001, 62.5001],
            "sf": [True, 4, 13, 7.0],
            "cr": [4, 9, "4/5"],
            "tx_power_dbm": [-10, 23, 1.0, False],
            "path_hash_bytes": [0, 4, 1.0, True],
        }
        for field, values in invalid.items():
            for value in values:
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(ValueError),
                ):
                    validate_changes({field: value}, 22)
        with self.assertRaises(ValueError):
            validate_changes({"repeat": True}, 22)


class SettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stub = patch.dict(
            "sys.modules",
            {
                "meshcore": SimpleNamespace(
                    EventType=SimpleNamespace(OK="ok", ERROR="error")
                )
            },
        )
        self.stub.start()
        self.session = MeshCoreSession(
            connection_factory=Connection, client_factory=Client
        )
        await self.session.connect("ble", "selected")
        self.client = self.session._client

    async def asyncTearDown(self):
        await self.session.disconnect()
        self.stub.stop()

    async def test_readback_excludes_identity_and_pin_and_converts_hash_mode(self):
        result = await self.session.read_settings()
        self.assertEqual(result["path_hash_bytes"], 1)
        self.assertTrue(result["path_hash_supported"])
        self.assertTrue(result["client_repeat"])
        self.assertNotIn("public_key", result)
        self.assertNotIn("ble_pin", result)
        self.assertEqual(self.client.sent, [])

    async def test_radio_update_preserves_other_fields_and_repeat_and_uses_exact_ticks(
        self,
    ):
        result = await self.session.apply_settings(
            frequency_mhz=915.123, bandwidth_khz=62.5, sf=7, cr=8
        )
        self.assertEqual(
            self.client.sent, [b"\x0b" + struct.pack("<IIBBB", 915123, 62500, 7, 8, 1)]
        )
        self.assertEqual(result["frequency_mhz"], 915.123)
        self.assertEqual(result["tx_power_dbm"], 22)
        self.assertEqual(result["path_hash_bytes"], 1)
        result = await self.session.apply_settings(sf=8)
        self.assertEqual(result["frequency_mhz"], 915.123)
        self.assertEqual(result["bandwidth_khz"], 62.5)
        self.assertTrue(result["client_repeat"])

    async def test_negative_tx_power_has_signed_wire_encoding_and_readback(self):
        result = await self.session.apply_settings(tx_power_dbm=-9)
        self.assertEqual(self.client.sent, [b"\x0c\xf7\xff\xff\xff"])
        self.assertEqual(result["tx_power_dbm"], -9)

    async def test_hash_modes_one_to_three_bytes(self):
        for size in (2, 3, 1):
            result = await self.session.apply_settings(path_hash_bytes=size)
            self.assertEqual(self.client.sent[-1], bytes([61, 0, size - 1]))
            self.assertEqual(result["path_hash_bytes"], size)

    async def test_invalid_later_field_prevents_all_writes(self):
        with self.assertRaises(ValueError):
            await self.session.apply_settings(sf=7, path_hash_bytes=4)
        self.assertEqual(self.client.sent, [])

    async def test_unsupported_hash_has_no_default_and_blocks_entire_update(self):
        self.client.device = {"fw ver": 9, "repeat": False}
        current = await self.session.read_settings()
        self.assertIsNone(current["path_hash_bytes"])
        self.assertFalse(current["path_hash_supported"])
        with self.assertRaises(ValueError):
            await self.session.apply_settings(sf=7, path_hash_bytes=1)
        self.assertEqual(self.client.sent, [])

    async def test_missing_repeat_metadata_blocks_radio_write(self):
        del self.client.device["repeat"]
        with self.assertRaises(ValueError):
            await self.session.apply_settings(sf=7)
        self.assertEqual(self.client.sent, [])

    async def test_noop_does_not_write_flash(self):
        await self.session.apply_settings(
            frequency_mhz=906.875,
            bandwidth_khz=250,
            sf=11,
            cr=5,
            tx_power_dbm=22,
            path_hash_bytes=1,
        )
        self.assertEqual(self.client.sent, [])

    async def test_acknowledged_but_ignored_write_is_not_reported_successful(self):
        self.client.ignore_command = 61
        with self.assertRaises(SettingsApplyError) as caught:
            await self.session.apply_settings(path_hash_bytes=3)
        self.assertEqual(caught.exception.current_settings["path_hash_bytes"], 1)
        self.assertEqual(caught.exception.verified_fields, ())
        self.assertEqual(len(self.client.sent), 1)

    async def test_partial_failure_reports_actual_state_without_retry_or_rollback(self):
        self.client.reject_command = 12
        with self.assertRaises(SettingsApplyError) as caught:
            await self.session.apply_settings(sf=7, tx_power_dbm=20, path_hash_bytes=3)
        error = caught.exception
        self.assertEqual(error.attempted_fields, ("tx_power_dbm",))
        self.assertIn("sf", error.verified_fields)
        self.assertEqual(error.current_settings["sf"], 7)
        self.assertEqual(error.current_settings["tx_power_dbm"], 22)
        self.assertEqual([frame[0] for frame in self.client.sent], [11, 12])
