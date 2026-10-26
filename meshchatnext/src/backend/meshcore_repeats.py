# SPDX-License-Identifier: MIT
"""Match overheard RF packets to outgoing messages, independently of delivery ACKs.

Only SHA-256 packet fingerprints are retained. Route/path changes are excluded;
packet type and complete encrypted payload must match. Counts are observations,
not a count of unique repeaters and not proof of delivery.
"""

import hashlib
import hmac
import time
from collections import OrderedDict


def encrypted(secret, plaintext):
    from Crypto.Cipher import AES

    padded = plaintext + bytes((-len(plaintext)) % 16)
    ciphertext = AES.new(secret[:16], AES.MODE_ECB).encrypt(padded)
    return hmac.digest(secret, ciphertext, "sha256")[:2] + ciphertext


def channel_packet(key, name, timestamp, text):
    plaintext = timestamp.to_bytes(4, "little") + b"\0" + (name + ": " + text).encode()
    return 5, hashlib.sha256(key).digest()[:1] + encrypted(key, plaintext)


def direct_packet(private, owner, peer, timestamp, text, *, incoming=False):
    from Crypto.Protocol.DH import key_agreement
    from Crypto.PublicKey import ECC

    # MeshCore uses an expanded Ed25519 scalar, not an Ed25519 seed. Convert
    # the peer's Edwards y coordinate to Montgomery u for X25519 exchange.
    y = int.from_bytes(bytes.fromhex(peer), "little") & ((1 << 255) - 1)
    p = (1 << 255) - 19
    if y >= p or y == 1:
        raise ValueError("Invalid peer public key")
    u = (1 + y) * pow(1 - y, -1, p) % p
    secret = key_agreement(
        static_priv=ECC.construct(curve="Curve25519", seed=private[:32]),
        static_pub=ECC.construct(curve="Curve25519", point_x=u),
        kdf=lambda value: value,
    )
    plaintext = timestamp.to_bytes(4, "little") + b"\0" + text.encode()
    return 2, (
        bytes.fromhex(owner if incoming else peer)[:1]
        + bytes.fromhex(peer if incoming else owner)[:1]
    ) + encrypted(secret, plaintext)


def fingerprint(kind, payload):
    return hashlib.sha256(bytes((kind,)) + payload).digest()


def observed_fingerprint(raw):
    if not isinstance(raw, bytes) or not 3 <= len(raw) <= 300:
        return None
    header = raw[0]
    if header >> 6:  # Unknown payload versions are never guessed.
        return None
    kind = (header >> 2) & 15
    if kind not in (2, 5):
        return None
    offset = 5 if header & 3 in (0, 3) else 1
    if offset >= len(raw):
        return None
    path = raw[offset]
    width = (path >> 6) + 1
    if width > 3:
        return None
    offset += 1 + (path & 63) * width
    if len(raw) - offset < (20 if kind == 2 else 19):
        return None
    return fingerprint(kind, raw[offset:])


class RepeatTracker:
    def __init__(self, *, maximum=512, lifetime=600, clock=time.monotonic):
        self.entries = OrderedDict()
        self.maximum = maximum
        self.lifetime = lifetime
        self.clock = clock

    def register(self, message_kind, message_id, packet):
        self._expire()
        key = fingerprint(*packet)
        self.entries[key] = (message_kind, message_id, self.clock())
        self.entries.move_to_end(key)
        while len(self.entries) > self.maximum:
            self.entries.popitem(last=False)

    def _expire(self):
        while self.entries:
            _, _, created = next(iter(self.entries.values()))
            if self.clock() - created <= self.lifetime:
                break
            self.entries.popitem(last=False)

    def observe(self, raw):
        self._expire()
        entry = self.entries.get(observed_fingerprint(raw))
        return entry[:2] if entry else None


def packet_path(raw, *, received, rssi=None, snr=None):
    """Observed wire path, not proof that every listed node received a message."""
    import math

    if observed_fingerprint(raw) is None:
        return None
    offset = 5 if raw[0] & 3 in (0, 3) else 1
    encoded = raw[offset]
    width, count = (encoded >> 6) + 1, encoded & 63
    if count * width > 64:
        return None
    path = raw[offset + 1 : offset + 1 + count * width]
    result = {
        "route": "flood" if raw[0] & 3 in (0, 1) else "direct",
        "hash_bytes": width,
        "hashes": [path[i : i + width].hex() for i in range(0, len(path), width)],
        "received": received,
    }
    result.update(
        {
            key: value
            for key, value in (("rssi", rssi), ("snr", snr))
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and -200 <= value <= 200
        }
    )
    return result
