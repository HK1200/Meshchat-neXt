from meshchatnext.src.backend.meshcore_map_traffic import describe_traffic
from meshchatnext.src.backend.meshcore_repeats import channel_packet


def entry(path, *, route=1, received=100):
    raw = (
        bytes([(5 << 2) | route, len(path) // 2])
        + bytes.fromhex(path)
        + channel_packet(bytes(16), "Test", 1, "hello")[1]
    )
    return {"received": received, "raw": raw.hex()}


def test_collision_without_a_position_still_breaks_the_route():
    known = [
        {"peer": "a1" * 32},
        {"peer": "b2" * 32},
        {"peer": "b2" + "00" * 31},
        {"peer": "c3" * 32},
    ]
    positions = [
        dict(n, latitude=1, longitude=2) for n in (known[0], known[1], known[3])
    ]
    result = describe_traffic([entry("a1b2c3")], known, positions, now=101)[0]
    assert result["points"] == [[2, 1], None, [2, 1]]
    assert result["incomplete"] is True
    assert result["missing_hops"] == 1
    assert "raw" not in result


def test_direct_paths_are_not_traversals_and_stale_packets_are_omitted():
    known = [{"peer": "a1" * 32}]
    positions = [dict(known[0], latitude=1, longitude=2)]
    result = describe_traffic(
        [
            entry("a1", route=2),
            entry("a1", received=1),
            entry("a1", received=200),
            {"raw": "invalid", "received": 100},
        ],
        known,
        positions,
        now=101,
    )
    assert len(result) == 1
    assert result[0]["route"] == "direct"
    assert result[0]["points"] == []


def test_unknown_and_unlocated_hops_and_invalid_coordinates_remain_gaps():
    known = [{"peer": "a1" * 32}, {"peer": "b2" * 32}]
    result = describe_traffic(
        [entry("a1b2c3")], known, [dict(known[0], latitude=91, longitude=2)], now=101
    )
    assert result[0]["points"] == [None, None, None]


def test_traffic_is_bounded_and_ids_are_stable():
    log = [entry("a1", received=100 + n / 100) for n in range(100)]
    result = describe_traffic(log, [], [], now=101)
    assert len(result) == 32
    assert result == describe_traffic(log, [], [], now=101)


async def test_service_snapshot_is_read_only_and_discards_a_radio_switch():
    import asyncio
    from types import SimpleNamespace

    from meshchatnext.src.backend.meshcore_service import MeshCoreService

    owner = "a1" * 32
    messages = SimpleNamespace(
        owner=owner, rx_log=[entry("a1", received=__import__("time").time())]
    )
    service = SimpleNamespace(
        _lock=asyncio.Lock(),
        _selection={"owner": owner},
        messages=messages,
        status=lambda: {"connected": True},
    )

    def announces(selected):
        assert selected == owner
        service._selection = {"owner": "b2" * 32}
        return [{"peer": owner}]

    service._store = SimpleNamespace(announces=announces, map_nodes=lambda selected: [])
    result = await MeshCoreService.map_traffic(service)
    assert result == {"owner": "b2" * 32, "connected": False, "packets": []}


async def test_service_disconnected_never_reads_the_store_or_radio():
    import asyncio
    from types import SimpleNamespace

    from meshchatnext.src.backend.meshcore_service import MeshCoreService

    service = SimpleNamespace(
        _lock=asyncio.Lock(),
        _selection={"owner": "a1" * 32},
        messages=None,
        status=lambda: {"connected": False},
    )
    assert (await MeshCoreService.map_traffic(service))["packets"] == []


async def test_map_traffic_api_resolves_and_guards_the_explicit_radio():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    import pytest

    from meshchatnext.src.backend.meshcore_fleet import MeshCoreFleet
    from meshchatnext.src.backend.meshcore_http import _read

    radio = SimpleNamespace(
        map_traffic=AsyncMock(
            return_value={"owner": "a1" * 32, "connected": True, "packets": []}
        )
    )
    fleet = Mock(spec=MeshCoreFleet)
    fleet.resolve.return_value = radio
    fleet._id.return_value = "radio-a"
    request = SimpleNamespace(query={"radio": "radio-a", "owner": "a1" * 32})
    result = await _read(fleet, SimpleNamespace(), request, "map-traffic")
    fleet.resolve.assert_called_once_with("radio-a", "a1" * 32)
    assert result["radio_id"] == "radio-a"
    radio.map_traffic.assert_awaited_once_with()
    fleet.resolve.side_effect = ValueError("MeshCore identity changed")
    with pytest.raises(ValueError):
        await _read(fleet, SimpleNamespace(), request, "map-traffic")
    radio.map_traffic.assert_awaited_once()
