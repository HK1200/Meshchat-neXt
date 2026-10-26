# SPDX-License-Identifier: MIT
import copy
import hashlib
import unittest

from Crypto.PublicKey import ECC

from meshchatnext.src.backend.meshcore_identity import (
    decrypt_backup,
    derive_public,
    encrypt_backup,
)


def keypair(seed=None):
    seed = bytes(range(32)) if seed is None else seed
    expanded = bytearray(hashlib.sha512(seed).digest())
    expanded[0] &= 248
    expanded[31] &= 63
    expanded[31] |= 64
    return bytes(expanded), ECC.construct(
        curve="Ed25519", seed=seed
    ).public_key().export_key(format="raw").hex()


class BackupTests(unittest.TestCase):
    def test_expanded_key_matches_standard_seed_derivation(self):
        key, owner = keypair()
        self.assertEqual(derive_public(key), owner)

    def test_backup_roundtrip_randomized_and_contains_no_plaintext_secret(self):
        key, owner = keypair()
        first = encrypt_backup(key, owner, "a sufficiently long password")
        second = encrypt_backup(key, owner, "a sufficiently long password")
        self.assertNotEqual(first["ciphertext"], second["ciphertext"])
        self.assertNotIn(key.hex(), str(first))
        self.assertEqual(
            decrypt_backup(first, "a sufficiently long password"), (owner, key)
        )

    def test_imports_authenticated_backups_from_the_earlier_integration(self):
        from unittest.mock import patch

        from Crypto.Protocol.KDF import scrypt

        from meshchatnext.src.backend import meshcore_identity

        key, owner = keypair()
        with patch.object(meshcore_identity, "FORMAT", meshcore_identity.LEGACY_FORMAT):
            # Explicit format argument is needed because default parameters bind at definition time.
            with patch.object(
                meshcore_identity,
                "_aad",
                lambda value: (meshcore_identity.LEGACY_FORMAT + ":" + value).encode(),
            ):
                with patch.object(
                    meshcore_identity,
                    "_backup_key",
                    lambda password, salt: scrypt(
                        password, salt, 32, N=16384, r=8, p=1
                    ),
                ):
                    backup = encrypt_backup(key, owner, "legacy backup password")
        self.assertEqual(decrypt_backup(backup, "legacy backup password"), (owner, key))

    def test_wrong_password_and_tampering_fail_closed(self):
        key, owner = keypair()
        backup = encrypt_backup(key, owner, "correct-password")
        with self.assertRaises(ValueError):
            decrypt_backup(backup, "incorrect-password")
        for field in ("public_key", "salt", "nonce", "ciphertext", "tag"):
            bad = copy.deepcopy(backup)
            bad[field] = ("00" if bad[field][:2] != "00" else "01") + bad[field][2:]
            with self.assertRaises(ValueError):
                decrypt_backup(bad, "correct-password")

    def test_reject_invalid_keys_and_owner_mismatch(self):
        key, owner = keypair()
        for bad in (key[:32], bytes(64), b"\xff" * 64):
            with self.assertRaises(ValueError):
                encrypt_backup(bad, owner, "correct-password")
        with self.assertRaises(ValueError):
            encrypt_backup(key, "aa" * 32, "correct-password")
        with self.assertRaises(ValueError):
            encrypt_backup(key, owner, "short")


class IdentitySessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import sys
        from enum import Enum, auto
        from types import SimpleNamespace

        from meshchatnext.src.backend.meshcore_session import MeshCoreSession
        from tests.backend.test_meshcore_session import FakeClient, FakeConnection

        class Events(Enum):
            OK = auto()
            ERROR = auto()
            DISABLED = auto()
            PRIVATE_KEY = auto()

        self.types = Events
        self._previous_meshcore = sys.modules.get("meshcore")
        sys.modules["meshcore"] = SimpleNamespace(EventType=Events)
        private, owner = keypair()

        class Client(FakeClient):
            secret = private
            key = owner
            name = "original"
            disabled = False
            imports = 0

            async def send_appstart(client):
                return client.event(
                    {
                        "public_key": client.key,
                        "name": client.name,
                        "private_key": "excluded",
                    }
                )

            async def set_name(client, name):
                client.name = name
                return client.event({})

            async def export_private_key(client):
                return SimpleNamespace(
                    type=Events.DISABLED if client.disabled else Events.PRIVATE_KEY,
                    payload={"private_key": client.secret},
                    is_error=lambda: False,
                )

            async def send(client, frame, expected):
                client.imports += 1
                if client.disabled:
                    return SimpleNamespace(
                        type=Events.DISABLED, payload={}, is_error=lambda: False
                    )
                client.secret = frame[1:]
                client.key = derive_public(client.secret)
                return SimpleNamespace(
                    type=Events.OK, payload={}, is_error=lambda: False
                )

        self.session = MeshCoreSession(
            connection_factory=FakeConnection, client_factory=Client
        )
        await self.session.connect("ble", "selected")
        self.client = self.session._client

    async def asyncTearDown(self):
        await self.session.disconnect()
        import sys

        if self._previous_meshcore is None:
            sys.modules.pop("meshcore", None)
        else:
            sys.modules["meshcore"] = self._previous_meshcore

    async def test_identity_is_secret_free_and_name_round_trips(self):
        self.assertNotIn("private_key", str(await self.session.read_identity()))
        self.assertEqual((await self.session.set_name("New name"))["name"], "New name")
        for name in ("", "\x00name", "é" * 16):
            with self.assertRaises(ValueError):
                await self.session.set_name(name)

    async def test_disabled_export_and_import_are_explicit_and_never_retried(self):
        self.client.disabled = True
        with self.assertRaises(PermissionError):
            await self.session.backup_identity(
                "correct-password", expected_public_key=self.client.key
            )
        private, owner = keypair(b"x" * 32)
        backup = encrypt_backup(private, owner, "correct-password")
        with self.assertRaises(PermissionError):
            await self.session.restore_identity(
                backup, "correct-password", expected_current_public_key=self.client.key
            )
        self.assertEqual(self.client.imports, 1)

    async def test_restore_authenticates_and_checks_selected_radio_before_write(self):
        private, owner = keypair(b"x" * 32)
        backup = encrypt_backup(private, owner, "correct-password")
        with self.assertRaises(ValueError):
            await self.session.restore_identity(
                backup,
                "incorrect-password",
                expected_current_public_key=self.client.key,
            )
        with self.assertRaises(ValueError):
            await self.session.restore_identity(
                backup, "correct-password", expected_current_public_key="aa" * 32
            )
        self.assertEqual(self.client.imports, 0)
        result = await self.session.restore_identity(
            backup, "correct-password", expected_current_public_key=self.client.key
        )
        self.assertEqual(result["public_key"], owner)
        self.assertEqual(self.client.imports, 1)

    async def test_backup_then_restore_same_identity_does_not_write(self):
        backup = await self.session.backup_identity(
            "correct-password", expected_public_key=self.client.key
        )
        await self.session.restore_identity(
            backup, "correct-password", expected_current_public_key=self.client.key
        )
        self.assertEqual(self.client.imports, 0)
