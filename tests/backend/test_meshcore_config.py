# SPDX-License-Identifier: MIT
import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from meshchatnext.src.backend.meshcore_config import (
    apply_config,
    live_review,
    parse_config,
)
from meshchatnext.src.backend.meshcore_identity import (
    decrypt_backup,
    derive_public,
    encrypt_backup,
)
from meshchatnext.src.backend.meshcore_store import MeshCoreStore

PRIVATE = bytearray(range(64))
PRIVATE[0] &= 248
PRIVATE[31] = (PRIVATE[31] & 63) | 64
PRIVATE = bytes(PRIVATE)
OWNER = derive_public(PRIVATE)


def fixture():
    return {
        "name": "Field radio",
        "public_key": OWNER,
        "private_key": PRIVATE.hex(),
        "radio_settings": {
            "frequency": 910525,
            "bandwidth": 62500,
            "spreading_factor": 7,
            "coding_rate": 8,
            "tx_power": 22,
        },
        "position_settings": {"latitude": "0", "longitude": "0"},
        "contacts": [
            {
                "name": "Peer",
                "public_key": "b2" * 32,
                "type": 2,
                "flags": 1,
                "latitude": "1.25",
                "longitude": "-2.5",
                "last_advert": 123,
                "out_path_list": "abcd",
            }
        ],
        "channels": [
            {
                "name": "Private team",
                "secret": "c3" * 16,
                "region_scope_name": None,
                "region_scope_key": None,
            }
        ],
    }


class ConfigParsingTests(unittest.TestCase):
    def test_official_shape_converts_units_and_retains_types_without_exposing_secrets(
        self,
    ):
        plan = parse_config(json.dumps(fixture()))
        self.assertEqual(plan["radio"]["frequency_mhz"], 910.525)
        self.assertEqual(plan["radio"]["bandwidth_khz"], 62.5)
        self.assertEqual(plan["contacts"][0]["type"], 2)
        self.assertEqual(plan["channels"][0]["name"], "Private team")
        self.assertIn("contacts.out_path_list", plan["unsupported"])
        self.assertIn("position_settings", plan["unsupported"])

    def test_identity_keys_must_match_and_encrypted_backups_are_supported(self):
        raw = fixture()
        raw["public_key"] = "b2" * 32
        with self.assertRaises(ValueError):
            parse_config(json.dumps(raw))
        backup = encrypt_backup(PRIVATE, OWNER, "sufficiently-long-password")
        plan = parse_config(json.dumps(backup), "sufficiently-long-password")
        self.assertEqual(plan["private"], PRIVATE)
        self.assertEqual(plan["present"], ["identity"])
        with self.assertRaises(ValueError):
            parse_config(json.dumps(backup), "incorrect-password")

    def test_scoped_channels_are_never_silently_downgraded(self):
        raw = fixture()
        raw["channels"][0]["region_scope_name"] = "private scope"
        plan = parse_config(json.dumps(raw))
        self.assertEqual(plan["channels"], [])
        self.assertTrue(
            any("Scoped channel skipped" in item for item in plan["unsupported"])
        )

    def test_duplicate_fields_and_nonfinite_or_ambiguous_keys_are_rejected(self):
        for text in (
            '{"name":"First","name":"Second"}',
            '{"radio_settings":{"frequency":NaN}}',
            "[]",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_config(text)
        raw = fixture()
        raw["channels"][0]["secret"] = "ab cd" * 8
        with self.assertRaises(ValueError):
            parse_config(json.dumps(raw))


class ConfigImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = MeshCoreStore(Path(self.folder.name) / "history.sqlite")
        self.plan = parse_config(json.dumps(fixture()))
        self.identity = {"name": "Old name", "public_key": OWNER}
        self.settings = {
            "frequency_mhz": 910.525,
            "bandwidth_khz": 62.5,
            "sf": 7,
            "cr": 8,
            "tx_power_dbm": 22,
            "max_tx_power_dbm": 22,
        }
        self.contacts = []
        self.channels = [
            {"slot": 0, "kind": "public", "name": "Public", "channel_id": "default"},
            {"slot": 1, "kind": "empty", "name": "", "channel_id": None},
        ]
        session = SimpleNamespace(
            read_identity=AsyncMock(side_effect=lambda: dict(self.identity)),
            read_settings=AsyncMock(side_effect=lambda: dict(self.settings)),
            set_name=AsyncMock(return_value={"public_key": OWNER, "name": "Imported"}),
            apply_settings=AsyncMock(),
            _device_info={"max_contacts": 10},
        )
        messages = SimpleNamespace(
            owner=OWNER,
            sync_contacts=AsyncMock(side_effect=lambda: copy.deepcopy(self.contacts)),
            import_contact=AsyncMock(return_value=True),
        )
        channels = SimpleNamespace(
            refresh=AsyncMock(side_effect=lambda: copy.deepcopy(self.channels)),
            import_channel=AsyncMock(return_value=True),
        )
        self.service = SimpleNamespace(
            status=lambda: {"connected": True},
            session=session,
            messages=messages,
            channels=channels,
            _store=self.store,
            _restore_locked=AsyncMock(),
        )
        self.review = await live_review(self.service, self.plan)
        self.request = str(uuid.uuid4())

    async def asyncTearDown(self):
        self.folder.cleanup()

    async def apply(self, sections, **kwargs):
        return await apply_config(
            self.service,
            self.plan,
            sections,
            OWNER,
            self.review["preview_id"],
            self.request,
            kwargs.get("replace_identity", False),
        )

    async def test_preview_is_read_only_and_does_not_return_private_or_channel_keys(
        self,
    ):
        serialized = json.dumps(self.review)
        self.assertNotIn(PRIVATE.hex(), serialized)
        self.assertNotIn("c3" * 16, serialized)
        self.service.messages.import_contact.assert_not_awaited()
        self.service.channels.import_channel.assert_not_awaited()

    async def test_selected_sections_only_and_repeated_requests_never_replay(self):
        first = await self.apply(["contacts", "channels"])
        self.assertEqual(first["state"], "complete")
        self.assertEqual(first["contacts_added"], 1)
        self.service.session.set_name.assert_not_awaited()
        second = await self.apply(["contacts", "channels"])
        self.assertEqual(second, first)
        self.service.messages.import_contact.assert_awaited_once()
        self.service.channels.import_channel.assert_awaited_once()

    async def test_conflicts_capacity_and_stale_radio_preflight_cause_no_writes(self):
        self.channels[1] = {
            "slot": 1,
            "kind": "private",
            "name": "Other",
            "channel_id": "occupied",
        }
        with self.assertRaises(ValueError):
            await self.apply(["channels"])
        self.service.channels.import_channel.assert_not_awaited()
        self.channels[1] = {"slot": 1, "kind": "empty", "name": "", "channel_id": None}
        self.settings["sf"] = 8
        with self.assertRaises(ValueError):
            await self.apply(["radio"])
        self.service.session.apply_settings.assert_not_awaited()

    async def test_partial_failure_is_recorded_and_never_automatically_retried(self):
        self.service.channels.import_channel.side_effect = ConnectionError("uncertain")
        first = await self.apply(["contacts", "channels"])
        self.assertEqual(first["state"], "uncertain")
        self.assertEqual(first["completed"], ["contacts"])
        self.assertEqual(first["stopped_at"], "channels")
        second = await self.apply(["contacts", "channels"])
        self.assertEqual(first, second)
        self.service.channels.import_channel.assert_awaited_once()
        self.assertEqual(self.store.config_import_result(OWNER, self.request), first)

    async def test_different_identity_requires_explicit_confirmation_before_any_write(
        self,
    ):
        self.identity["public_key"] = "d4" * 32
        self.service.messages.owner = "d4" * 32
        review = await live_review(self.service, self.plan)
        with self.assertRaises(ValueError):
            await apply_config(
                self.service,
                self.plan,
                ["name", "identity"],
                "d4" * 32,
                review["preview_id"],
                self.request,
                False,
            )
        self.service.session.set_name.assert_not_awaited()
        self.service._restore_locked.assert_not_awaited()

    async def test_confirmed_identity_replacement_uses_verified_encrypted_restore_and_is_not_repeated(
        self,
    ):
        self.identity["public_key"] = "d4" * 32
        self.service.messages.owner = "d4" * 32
        review = await live_review(self.service, self.plan)
        result = await apply_config(
            self.service,
            self.plan,
            ["identity"],
            "d4" * 32,
            review["preview_id"],
            self.request,
            True,
        )
        self.assertTrue(result["identity_replaced"])
        args, kwargs = self.service._restore_locked.call_args
        self.assertEqual(decrypt_backup(args[0], args[1]), (OWNER, PRIVATE))
        self.assertEqual(kwargs["expected_current_public_key"], "d4" * 32)
        again = await apply_config(
            self.service,
            self.plan,
            ["identity"],
            "d4" * 32,
            review["preview_id"],
            self.request,
            True,
        )
        self.assertEqual(again, result)
        self.service._restore_locked.assert_awaited_once()

    async def test_removed_cached_contacts_are_counted_as_new_and_do_not_consume_capacity(
        self,
    ):
        self.contacts = [{"peer": "b2" * 32, "active": 0}]
        review = await live_review(self.service, self.plan)
        self.assertEqual(review["contacts"]["new"], 1)
        self.assertEqual(review["contacts"]["existing"], 0)

    async def test_durable_started_receipt_never_replays_after_an_interruption(self):
        import hashlib

        sections = ["name"]
        digest = hashlib.sha256(
            (
                self.plan["source_digest"]
                + json.dumps(sorted(sections))
                + self.review["preview_id"]
                + str(False)
            ).encode()
        ).hexdigest()
        self.store.config_import_run(OWNER, self.request, digest, claim=True)
        result = await self.apply(sections)
        self.assertEqual(result["state"], "uncertain")
        self.service.session.set_name.assert_not_awaited()

    async def test_channel_name_conflict_and_unknown_contact_capacity_are_reported(
        self,
    ):
        self.channels[0]["name"] = "Private team"
        self.service.session._device_info = {}
        review = await live_review(self.service, self.plan)
        self.assertIn("channels", review["errors"])
        self.assertIn("contacts", review["errors"])


if __name__ == "__main__":
    unittest.main()
