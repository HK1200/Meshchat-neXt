# SPDX-License-Identifier: MIT
"""MeshCore expanded Ed25519 key backups. Secrets never enter normal status/history."""

from __future__ import annotations

import secrets

from meshchatnext.src.backend.meshcore_store import public_key

FORMAT = "meshchatnext-meshcore-identity-v1"
LEGACY_FORMAT = "meshchatx-meshcore-identity-v1"  # Authenticated backups from the earlier integration.


def derive_public(private):
    """Derive from MeshCore's expanded scalar, not from an Ed25519 seed."""
    from Crypto.PublicKey import ECC
    from Crypto.Signature.eddsa import import_public_key

    if not isinstance(private, bytes) or len(private) != 64:
        raise ValueError("A 64-byte MeshCore expanded private key is required")
    if private[0] & 7 or private[31] & 0xC0 != 0x40:
        raise ValueError("Invalid expanded private key scalar")
    generator = import_public_key(bytes.fromhex("58" + "66" * 31)).pointQ
    point = generator * int.from_bytes(private[:32], "little")
    result = (
        ECC.construct(curve="Ed25519", point_x=point.x, point_y=point.y)
        .export_key(format="raw")
        .hex()
    )
    if result[:2] in ("00", "ff"):
        raise ValueError("Unsupported MeshCore public key prefix")
    return result


def _password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError("Backup password must contain 12-1024 characters")
    return password.encode("utf-8")


def _aad(owner, backup_format=FORMAT):
    return (backup_format + ":" + public_key(owner)).encode()


def _backup_key(password: bytes, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=32, n=16384, r=8, p=1).derive(password)


def encrypt_backup(private, owner, password):
    from Crypto.Cipher import AES

    password = _password(password)
    owner = public_key(owner)
    if derive_public(private) != owner:
        raise ValueError("Exported key does not match the selected identity")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    cipher = AES.new(_backup_key(password, salt), AES.MODE_GCM, nonce=nonce)
    cipher.update(_aad(owner))
    ciphertext, tag = cipher.encrypt_and_digest(private)
    return {
        "format": FORMAT,
        "public_key": owner,
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
        "tag": tag.hex(),
    }


def decrypt_backup(backup, password):
    from Crypto.Cipher import AES

    password = _password(password)
    try:
        if (
            not isinstance(backup, dict)
            or set(backup)
            != {"format", "public_key", "salt", "nonce", "ciphertext", "tag"}
            or backup["format"] not in (FORMAT, LEGACY_FORMAT)
        ):
            raise ValueError
        owner = public_key(backup["public_key"])
        values = [
            bytes.fromhex(backup[key]) for key in ("salt", "nonce", "ciphertext", "tag")
        ]
        if [len(value) for value in values] != [16, 12, 64, 16]:
            raise ValueError
        salt, nonce, ciphertext, tag = values
        cipher = AES.new(_backup_key(password, salt), AES.MODE_GCM, nonce=nonce)
        cipher.update(_aad(owner, backup["format"]))
        private = cipher.decrypt_and_verify(ciphertext, tag)
        if derive_public(private) != owner:
            raise ValueError
        return owner, private
    except (ValueError, KeyError, TypeError):
        raise ValueError("Backup could not be authenticated or is invalid") from None
