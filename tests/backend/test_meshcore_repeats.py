# SPDX-License-Identifier: MIT
import hashlib
import tempfile
import unittest
from pathlib import Path

from meshchatnext.src.backend.meshcore_identity import derive_public
from meshchatnext.src.backend.meshcore_repeats import (
    RepeatTracker,
    channel_packet,
    direct_packet,
    fingerprint,
    observed_fingerprint,
)
from meshchatnext.src.backend.meshcore_store import MeshCoreStore


def identity(seed):
    private = bytearray(hashlib.sha512(seed).digest())
    private[0] &= 248
    private[31] &= 63
    private[31] |= 64
    private = bytes(private)
    return private, derive_public(private)


class RepeatTests(unittest.TestCase):
    def test_matches_channel_packet_across_paths_and_transport_headers(self):
        packet = channel_packet(bytes(range(16)), "TestClient 🇺🇲", 1234, "hello")
        tracker = RepeatTracker()
        tracker.register("channel", "send-1", packet)
        for width in (1, 2, 3):
            raw = (
                bytes(((5 << 2) | 1, ((width - 1) << 6) | 2))
                + bytes(width * 2)
                + packet[1]
            )
            self.assertEqual(tracker.observe(raw), ("channel", "send-1"))
        transport = bytes(((5 << 2) | 3,)) + b"abcd" + b"\0" + packet[1]
        self.assertEqual(tracker.observe(transport), ("channel", "send-1"))
        altered = packet[1][:-1] + bytes((packet[1][-1] ^ 1,))
        self.assertIsNone(tracker.observe(bytes(((5 << 2) | 1, 0)) + altered))

    def test_dm_cipher_matches_exchange_on_recipient_side_and_is_not_an_ack(self):
        import hmac

        from Crypto.Cipher import AES
        from Crypto.Protocol.DH import key_agreement
        from Crypto.PublicKey import ECC

        sender_private, sender = identity(b"public test sender")
        recipient_private, recipient = identity(b"public test recipient")
        packet = direct_packet(sender_private, sender, recipient, 1234, "hello")
        p = (1 << 255) - 19
        y = int.from_bytes(bytes.fromhex(sender), "little") & ((1 << 255) - 1)
        secret = key_agreement(
            static_priv=ECC.construct(curve="Curve25519", seed=recipient_private[:32]),
            static_pub=ECC.construct(
                curve="Curve25519", point_x=(1 + y) * pow(1 - y, -1, p) % p
            ),
            kdf=lambda x: x,
        )
        self.assertEqual(
            hmac.digest(secret, packet[1][4:], "sha256")[:2], packet[1][2:4]
        )
        plain = AES.new(secret[:16], AES.MODE_ECB).decrypt(packet[1][4:]).rstrip(b"\0")
        self.assertEqual(plain, (1234).to_bytes(4, "little") + b"\0hello")
        tracker = RepeatTracker()
        tracker.register("direct", "dm-1", packet)
        self.assertEqual(
            tracker.observe(bytes(((2 << 2) | 1, 0)) + packet[1]), ("direct", "dm-1")
        )
        self.assertIsNone(tracker.observe(bytes(((3 << 2) | 1, 0)) + packet[1]))

    def test_rejects_malformed_frames_and_bounds_cache_by_size_and_time(self):
        now = [0]
        tracker = RepeatTracker(maximum=1, lifetime=10, clock=lambda: now[0])
        first = channel_packet(bytes(16), "A", 1, "one")
        second = channel_packet(bytes(16), "A", 2, "two")
        tracker.register("channel", "one", first)
        tracker.register("channel", "two", second)
        self.assertEqual(len(tracker.entries), 1)
        self.assertNotIn(fingerprint(*first), tracker.entries)
        now[0] = 11
        self.assertIsNone(tracker.observe(bytes((21, 0)) + second[1]))
        for raw in (
            b"",
            b"\x15",
            b"\x15\xff" + bytes(20),
            bytes((0xD5, 0)) + bytes(20),
            bytes((21, 63)) + bytes(20),
        ):
            self.assertIsNone(observed_fingerprint(raw))

    def test_counts_are_owner_scoped_persistent_and_do_not_change_delivery_state(self):
        with tempfile.TemporaryDirectory() as folder:
            store = MeshCoreStore(Path(folder) / "history.sqlite")
            owner, peer = "a1" * 32, "b2" * 32
            store.bind(owner, "test")
            store.replace_contacts(
                owner, {peer: {"public_key": peer, "type": 1, "adv_name": "peer"}}
            )
            row, _ = store.prepare_send(owner, peer, "test", "dm")
            store.result(owner, "dm", "accepted", "01020304", 5)
            store.repeat_observation(owner, "direct", "dm")
            store.repeat_observation(owner, "direct", "dm", 3)
            store.repeat_observation("c3" * 32, "direct", "dm", 9)
            row = store.history(owner, peer)[0]
            self.assertEqual(row["state"], "accepted")
            self.assertEqual(row["heard_repeats"], 3)
            self.assertEqual(
                MeshCoreStore(Path(folder) / "history.sqlite").history(owner, peer)[0][
                    "heard_repeats"
                ],
                3,
            )
