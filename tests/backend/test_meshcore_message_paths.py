import time
from types import SimpleNamespace

import pytest

from meshchatnext.src.backend.meshcore_message_paths import describe_paths
from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
from meshchatnext.src.backend.meshcore_repeats import (
    RepeatTracker,
    channel_packet,
    direct_packet,
    fingerprint,
    packet_path,
)
from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from tests.backend.test_meshcore_repeats import identity

OWNER, PEER = "a1" * 32, "b2" * 32


@pytest.fixture
def store(tmp_path):
    value = MeshCoreStore(tmp_path / "history.sqlite")
    value.bind(OWNER, "Local")
    value.replace_contacts(
        OWNER, {PEER: {"public_key": PEER, "type": 1, "adv_name": "Peer"}}
    )
    return value


def observation(hashes=None, route="flood"):
    return {
        "route": route,
        "hash_bytes": 1,
        "hashes": hashes or ["c3"],
        "received": time.time(),
        "snr": 5,
        "rssi": -70,
    }


@pytest.mark.parametrize("width", [1, 2, 3])
def test_wire_paths_preserve_width_and_transport_offset(width):
    packet = channel_packet(bytes(16), "Test", 123, "hello")
    raw = (
        bytes([(5 << 2) | 0])
        + b"abcd"
        + bytes([((width - 1) << 6) | 2])
        + bytes.fromhex("c3" * width + "d4" * width)
        + packet[1]
    )
    result = packet_path(raw, received=10, rssi=-90, snr=2.5)
    assert result["hashes"] == ["c3" * width, "d4" * width]
    assert result["route"] == "flood"
    assert packet_path(bytes([0xFF]) + raw, received=10) is None


def test_dm_incoming_fingerprint_matches_sender_without_changing_crypto():
    a, ap = identity(b"sender fixture")
    b, bp = identity(b"receiver fixture")
    assert direct_packet(a, ap, bp, 123, "test") == direct_packet(
        b, bp, ap, 123, "test", incoming=True
    )


def test_persistent_paths_are_message_owner_and_target_scoped_and_bounded(store):
    row, _ = store.prepare_send(OWNER, PEER, "one", "send-one")
    store.save_message_paths(OWNER, "direct", row["id"], [observation()] * 40)
    details = MeshCoreStore(store.path).message_details(
        OWNER, "direct", PEER, row["id"]
    )
    assert len(details["routes"]) == 32
    assert details["state"] == "submitting"
    with pytest.raises(ValueError):
        store.message_details("d4" * 32, "direct", PEER, row["id"])
    with pytest.raises(ValueError):
        store.message_details(OWNER, "direct", "e5" * 32, row["id"])


def test_short_hash_collisions_never_choose_a_convenient_location():
    known = [
        {"peer": "c3" + "11" * 31, "name": "A"},
        {"peer": "c3" + "22" * 31, "name": "B"},
    ]
    positions = [dict(known[0], latitude=1, longitude=2, updated=1)]
    result = describe_paths(
        {"id": "one", "direction": "out", "state": "accepted"},
        [observation()],
        known,
        positions,
        owner=OWNER,
        kind="direct",
        target=PEER,
    )
    assert result["routes"][0]["hops"][0]["candidate_count"] == 2
    assert result["routes"][0]["points"] == []


def test_direct_route_hashes_are_not_drawn_as_observed_traversal():
    known = [{"peer": "c3" * 32, "name": "Repeater"}]
    result = describe_paths(
        {"id": "one", "direction": "out", "state": "accepted"},
        [observation(route="direct")],
        known,
        [dict(known[0], latitude=1, longitude=2, updated=1)],
        owner=OWNER,
        kind="direct",
        target=PEER,
    )
    assert result["routes"][0]["points"] == []


def test_old_incoming_metadata_does_not_invent_the_saved_contact_route(store):
    store.receive(
        OWNER,
        "direct",
        {
            "pubkey_prefix": PEER[:12],
            "sender_timestamp": 12,
            "text": "hello",
            "path_len": 2,
            "SNR": 4,
        },
    )
    row = store.history(OWNER, PEER)[0]
    result = store.message_details(OWNER, "direct", PEER, row["id"])
    assert result["reported_hops"] == 2 and not result["routes"]


@pytest.mark.asyncio
async def test_incoming_channel_correlation_requires_the_exact_encrypted_payload():
    m = MeshCoreMessaging(None, None)
    m.owner = OWNER
    m._channel_keys[1] = bytes(16)
    payload = {
        "channel_idx": 1,
        "sender_timestamp": 123,
        "text": "Test: hello",
        "txt_type": 0,
    }
    packet = channel_packet(bytes(16), "Test", 123, "hello")
    m._rx_paths.append((fingerprint(*packet), observation()))
    assert (await m._incoming_path("channel", payload))["observed_paths"]
    assert "observed_paths" not in await m._incoming_path(
        "channel", dict(payload, text="Test: different")
    )
    assert (
        await m._incoming_path("direct", payload) == payload
    )  # no additional identity-key export


@pytest.mark.asyncio
async def test_repeat_evidence_persists_without_changing_delivery_semantics(store):
    row, _ = store.prepare_send(OWNER, PEER, "one", "observed")
    m = MeshCoreMessaging(None, store)
    m.owner = OWNER
    m._repeat_tracker = RepeatTracker()
    packet = channel_packet(bytes(16), "Test", 123, "one")
    m._repeat_tracker.register("direct", row["id"], packet)
    raw = bytes([(5 << 2) | 1, 1]) + bytes.fromhex("c3") + packet[1]
    for _ in range(40):
        m._on_repeat(
            SimpleNamespace(payload={"payload": raw.hex(), "rssi": -80, "snr": 3})
        )
    await m._flush_repeats()
    result = store.message_details(OWNER, "direct", PEER, row["id"])
    assert result["heard_repeats"] == 40 and len(result["routes"]) == 32
    assert result["state"] == "submitting"
