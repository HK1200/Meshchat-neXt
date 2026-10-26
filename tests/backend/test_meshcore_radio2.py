# SPDX-License-Identifier: MIT
import unittest
from types import SimpleNamespace

from meshchatnext.src.backend.meshcore_radio2 import (
    MEDIAMESH_DEFAULTS,
    apply_radio2,
    decode_profile,
    read_radio2,
)


class Session:
    def __init__(self):
        self.is_connected = True
        self._client = SimpleNamespace(commands=self)
        self.version = 14
        self.profile = "> off (automatic allowed)"
        self.cross = "> off"
        self.policy = "> tx.media auto; active=channel/global"
        self.commands = []
        self.fail_write = False
        self.closed = False
        self.primary = {
            "frequency_mhz": 910.525,
            "bandwidth_khz": 62.5,
            "sf": 7,
            "cr": 8,
            "tx_power_dbm": 22,
            "path_hash_bytes": 1,
        }

    @staticmethod
    def _payload(event):
        return event.payload

    async def send_device_query(self):
        return SimpleNamespace(payload={"fw ver": self.version})

    async def _read_settings(self):
        return dict(self.primary)

    async def _close(self):
        self.closed = True

    async def run_cli_command(self, command):
        self.commands.append(command)
        if command.startswith("set radio2 "):
            if self.fail_write:
                return None
            value = command.removeprefix("set radio2 ")
            self.profile = (
                "> off"
                if value == "off"
                else "> " + value.removesuffix(",auto") + ",40 (auto)"
            )
        elif command == "set radio2.cross off":
            self.cross = "> off"
        elif command == "set tx.media radio2":
            self.policy = "> tx.media radio2; active=radio2"
        text = {
            "get radio2": self.profile,
            "get radio2.cross": self.cross,
            "get tx.media": self.policy,
        }.get(command, "OK")
        return SimpleNamespace(payload={"text": text}, is_error=lambda: False)


class Radio2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_stock_older_firmware_does_not_receive_cli_commands(self):
        session = Session()
        session.version = 13
        result = await read_radio2(session)
        self.assertFalse(result["supported"])
        self.assertEqual(session.commands, [])

    async def test_defaults_enable_mediamesh_and_verify_primary_unchanged(self):
        session = Session()
        before = dict(session.primary)
        result = await apply_radio2(session, enabled=True)
        self.assertEqual(result["profile"], MEDIAMESH_DEFAULTS)
        self.assertEqual(result["mode"], "rxtx")
        self.assertFalse(result["crossing"])
        self.assertEqual(result["media_policy"], "radio2")
        self.assertEqual(session.primary, before)
        self.assertIn("set radio2 911.150,250.000,7,5,rxtx,auto", session.commands)

    async def test_saved_custom_profile_takes_precedence_over_defaults(self):
        session = Session()
        session.profile = "> 912.000,125.000,8,6,rx,48 (auto)"
        result = await apply_radio2(session, enabled=True)
        self.assertEqual(
            result["profile"],
            {"frequency_mhz": 912.0, "bandwidth_khz": 125.0, "sf": 8, "cr": 6},
        )

    async def test_invalid_changes_and_same_primary_frequency_write_nothing(self):
        for changes in (
            {"enabled": 1},
            {"enabled": True, "sf": 99},
            {"enabled": False, "frequency_mhz": 911.15},
            {"enabled": True, "frequency_mhz": 910.525},
        ):
            session = Session()
            with self.assertRaises(ValueError):
                await apply_radio2(session, **changes)
            self.assertFalse(any(c.startswith("set ") for c in session.commands))

    async def test_uncertain_write_closes_connection_and_never_replays(self):
        session = Session()
        session.fail_write = True
        with self.assertRaises(ConnectionError):
            await apply_radio2(session, enabled=True)
        self.assertTrue(session.closed)
        self.assertEqual(sum(c.startswith("set radio2 ") for c in session.commands), 1)

    async def test_disabled_and_timing_warning_profile_formats(self):
        self.assertFalse(decode_profile("> off (automatic allowed)")["enabled"])
        result = decode_profile(
            "> 911.150,250.000,7,5,rxtx,40 (auto); timing self-test pending; wait=119s"
        )
        self.assertTrue(result["automatic_preamble"])
        with self.assertRaises(ConnectionError):
            decode_profile("> unexpected response")
