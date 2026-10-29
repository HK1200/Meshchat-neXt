# SPDX-License-Identifier: MIT
import struct

import pytest

from meshchatnext.src.backend.meshcore_peer_radio2 import decode_discovery_radio2


def profile(flags=5):
    return bytes([1, flags]) + struct.pack("<IIBB", 911150, 250000, 7, 5)


def test_profile_preserves_rx_and_temporary_settings():
    result = decode_discovery_radio2(profile(11))
    assert result == {
        "state": "enabled",
        "source": "nearby_discovery",
        "mode": "rx",
        "temporary": True,
        "frequency_mhz": 911.15,
        "bandwidth_khz": 250.0,
        "sf": 7,
        "cr": 5,
    }
    assert decode_discovery_radio2(profile())["mode"] == "rxtx"


def test_unavailable_is_not_claimed_to_mean_disabled_or_unsupported():
    assert decode_discovery_radio2(bytes([1, 0]))["state"] == "unavailable"


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        None,
        "Radio2 enabled",
        bytes([2, 0]),
        bytes([1]),
        profile()[:-1],
        profile() + b"x",
        profile(0),
        profile(7),
        profile(21),
        bytes([1, 0]) + bytes(10),
        bytes([1, 5]) + struct.pack("<IIBB", 0, 250000, 7, 5),
    ],
)
def test_legacy_unknown_and_malformed_are_never_confirmed(payload):
    assert decode_discovery_radio2(payload)["state"] == "unknown"


def test_cached_reports_are_owner_scoped_persistent_and_do_not_touch_heard(tmp_path):
    from meshchatnext.src.backend.meshcore_store import MeshCoreStore
    from meshchatnext.src.backend.meshcore_topology import topology_nodes

    owner, other, peer = "a1" * 32, "c3" * 32, "b2" * 32
    store = MeshCoreStore(tmp_path / "history.sqlite")
    store.record_node_discovery(owner, peer, 2, 100)
    store.record_node_discovery(other, peer, 2, 101)
    store.save_announce(
        owner,
        {
            "public_key": peer,
            "type": 2,
            "adv_name": "Hill",
            "last_advert": 90,
            "adv_lat": 49,
            "adv_lon": -122,
        },
    )
    store.node_preference(owner, peer, True)
    store.record_peer_radio2(owner, peer, decode_discovery_radio2(profile()), 200)
    store.record_peer_radio2(owner, peer, {"state": "unavailable"}, 199)
    reopened = MeshCoreStore(store.path)
    assert reopened.nodes(owner)[0]["radio2"]["state"] == "enabled"
    assert reopened.map_nodes(owner)[0]["radio2"]["state"] == "enabled"
    assert reopened.announces(owner)[0]["heard"] == 100
    assert reopened.announces(other)[0]["radio2"] == {"state": "unknown"}
    assert topology_nodes(reopened, owner, {})[0]["radio2"]["observed"] == 200
