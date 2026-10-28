# SPDX-License-Identifier: MIT
import asyncio

import pytest

from meshchatnext.src.backend.meshcore_service import MeshCoreService
from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from meshchatnext.src.backend.meshcore_topology import cached_route, topology_nodes

OWNER = "a1" * 32
PEER = "b2" * 32
OTHER = "c3" * 32


@pytest.mark.parametrize(
    "contact",
    [
        {},
        {"out_path_len": True},
        {"out_path_len": 64},
        {"out_path_len": 2, "out_path_hash_mode": 0, "out_path": "ab"},
        {"out_path_len": 1, "out_path_hash_mode": 3, "out_path": "abcd"},
        {"out_path_len": 1, "out_path_hash_mode": 0, "out_path": "zz"},
        {"out_path_len": 22, "out_path_hash_mode": 2, "out_path": "ab" * 66},
    ],
)
def test_invalid_routes_do_not_create_links(contact):
    assert cached_route(contact) is None


@pytest.mark.parametrize("width", [1, 2, 3])
def test_width_and_zero_hashes_preserved(width):
    raw = "a1" * width + "00" * width
    assert cached_route(
        {"out_path_len": 2, "out_path_hash_mode": width - 1, "out_path": raw}
    ) == {"hops": 2, "hash_bytes": width, "hashes": ["a1" * width, "00" * width]}


def test_saved_route_changes_not_polling_time_and_offline_roundtrip(tmp_path):
    path = tmp_path / "history.sqlite"
    store = MeshCoreStore(path)
    contact = {
        "public_key": PEER,
        "adv_name": "Repeater",
        "type": 2,
        "last_advert": 10,
        "out_path_len": 1,
        "out_path_hash_mode": 0,
        "out_path": "00",
    }
    store.save_announce(OWNER, contact, heard=12)
    first = store.topology_routes(OWNER)[PEER]
    snapshot = topology_nodes(store, OWNER, {PEER: contact})
    assert snapshot[0]["route"] == first
    assert store.announces(OWNER)[0]["heard"] == 12
    assert MeshCoreStore(path).topology_routes(OWNER)[PEER] == first
    assert store.topology_routes(OTHER) == {}
    contact.update(out_path_len=-1, out_path="")
    updated = topology_nodes(store, OWNER, {PEER: contact})[0]["route"]
    assert updated["hops"] == -1 and updated["hashes"] == []
    assert updated["stored_at"] >= first["stored_at"]
    contact.update(out_path_len=2, out_path="bad")
    assert topology_nodes(store, OWNER, {PEER: contact})[0]["route"] == updated


def test_old_announce_does_not_replace_new_route(tmp_path):
    store = MeshCoreStore(tmp_path / "history.sqlite")
    contact = {"public_key": PEER, "type": 2, "last_advert": 20, "out_path_len": 0}
    store.save_announce(OWNER, contact)
    store.save_announce(OWNER, {**contact, "last_advert": 10, "out_path_len": -1})
    assert store.topology_routes(OWNER)[PEER]["hops"] == 0


@pytest.mark.asyncio
async def test_snapshot_does_not_wait_for_connection_lock_or_dial(tmp_path):
    service = MeshCoreService(tmp_path)
    service._known_owner = OWNER
    service._store = MeshCoreStore(tmp_path / "history.sqlite")
    service._store.save_announce(OWNER, {"public_key": PEER, "type": 2})
    async with service._lock:
        result = await asyncio.wait_for(service.topology_snapshot("account"), 1)
    assert result["owner"] == OWNER and result["nodes"][0]["peer"] == PEER
    assert not result["connected"]


@pytest.mark.asyncio
async def test_owner_change_during_snapshot_rejected(tmp_path, monkeypatch):
    import meshchatnext.src.backend.meshcore_topology as topology

    service = MeshCoreService(tmp_path)
    service._known_owner = OWNER
    service._store = MeshCoreStore(tmp_path / "history.sqlite")

    def change(*args):
        service._known_owner = OTHER
        return []

    monkeypatch.setattr(topology, "topology_nodes", change)
    with pytest.raises(ValueError, match="identity changed"):
        await service.topology_snapshot("account")
