"""Open TAK golden vectors and identity-scoped map history boundaries."""

import math

import pytest

from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from meshchatnext.src.backend.meshcore_tactical_wire import decode, encode

# Upstream test/team/team_wire_golden_test.dart; shared with native Wadamesh TAK.
P1 = "5001020304071c60218fb7159b54003803c0084d2501084a61646520e29ca8"
P2 = "500102030418ebd0073b5a20b51b0000000000ff8b0507416c7068612d31"
P3 = "5001020304201b224618b6e10d380000000000fff300064b392d52657814"
A1 = "53aabbccddbeef131c4fecc0b72221600c05427261766f174e65656420776174657220617420746865207269646765"
A2 = "53aabbccdd0001000000000000000000000000"
M1 = "4d0a0b0c0d1234567800041bed17f8b76cda4868eb2c5008526f636b66616c6c1d547261696c20626c6f636b65642070617374207468652062726964676500"
M2 = "4d0a0b0c0d000000ff0109000000000000000000000001204142434445464748494a4b4c4d4e4f505152535455565758595a3031323334350028deadbeef0c0102"


def test_published_position_encoder_vectors():
    assert (
        encode(
            {
                "kind": "position",
                "alias": "01020304",
                "latitude": 47.6062095,
                "longitude": -122.3320748,
                "altitude": 56,
                "speed": 1.4,
                "heading": 270.5,
                "accuracy": 8,
                "battery": 77,
                "role": 2,
                "color": 5,
                "status": 1,
                "callsign": "Jade ✨",
                "from_radio": True,
            }
        ).hex()
        == P1
    )
    assert (
        encode(
            {
                "kind": "position",
                "alias": "01020304",
                "latitude": -33.8688197,
                "longitude": 151.2092955,
                "role": 8,
                "color": 11,
                "status": 5,
                "callsign": "  Alpha-1  ",
                "sos": True,
                "relayed": True,
            }
        ).hex()
        == P2
    )
    assert (
        encode(
            {
                "kind": "position",
                "alias": "01020304",
                "latitude": 45.5231,
                "longitude": -122.6765,
                "role": 20,
                "color": 3,
                "callsign": "K9-Rex",
            }
        ).hex()
        == P3
    )
    result = decode(bytes.fromhex(P1))
    assert result["callsign"] == "Jade ✨"
    assert result["from_radio"] and result["identity_verified"] is False
    assert result["latitude"] == 47.6062095
    assert decode(bytes.fromhex(P3))["role"] == 20


def test_published_pin_alert_vectors():
    assert (
        encode(
            {
                "kind": "alert",
                "alias": "aabbccdd",
                "id": 0xBEEF,
                "active": True,
                "alert_kind": 1,
                "latitude": 47.5,
                "longitude": -122.25,
                "accuracy": 12,
                "callsign": "Bravo",
                "note": "Need water at the ridge",
            }
        ).hex()
        == A1
    )
    assert (
        encode({"kind": "alert", "alias": "aabbccdd", "id": 1, "active": False}).hex()
        == A2
    )
    assert (
        encode(
            {
                "kind": "pin",
                "alias": "0a0b0c0d",
                "id": 0x12345678,
                "pin_kind": 4,
                "latitude": 46.8523,
                "longitude": -121.7603,
                "timestamp": 1760242768,
                "label": "Rockfall",
                "note": "Trail blocked past the bridge",
            }
        ).hex()
        == M1
    )
    assert decode(bytes.fromhex(M1))["note"] == "Trail blocked past the bridge"
    result = decode(bytes.fromhex(M2))
    assert result["deleted"] and result["attachment"] == {
        "mode": 40,
        "sid": "deadbeef",
        "packets": 12,
        "extra": 258,
    }


@pytest.mark.parametrize("wire", [P1, P2, P3, A1])
def test_truncation_never_becomes_partial_position_or_alert(wire):
    raw = bytes.fromhex(wire)
    for size in range(len(raw)):
        with pytest.raises((ValueError, UnicodeError)):
            decode(raw[:size])


@pytest.mark.parametrize("value", [math.nan, math.inf, -91, 91, True, "47"])
def test_outgoing_coordinate_validation(value):
    with pytest.raises(ValueError):
        encode(
            {"kind": "position", "alias": "01020304", "latitude": value, "longitude": 0}
        )


def test_map_nodes_never_link_contacts_or_mix_identity_history(tmp_path):
    store = MeshCoreStore(tmp_path / "history.sqlite")
    owner, other, peer = "a1" * 32, "b2" * 32, "c3" * 32
    record = {
        "public_key": peer,
        "adv_name": "Hill",
        "type": 2,
        "last_advert": 100,
        "adv_lat": 48.95,
        "adv_lon": -122.45,
    }
    store.save_announce(owner, record)
    assert store.map_nodes(other) == []
    assert store.contacts(owner) == []
    assert store.map_nodes(owner)[0]["saved"] == 0
    assert store.map_nodes(owner)[0]["latitude"] == 48.95
    store.save_announce(owner, {**record, "last_advert": 90, "adv_lat": 1}, heard=101)
    assert store.map_nodes(owner)[0]["latitude"] == 48.95
    store.save_announce(
        owner, {**record, "last_advert": 110, "adv_lat": 0, "adv_lon": 0}
    )
    assert (
        store.map_nodes(owner)[0]["updated"] == 100
    )  # Keep last known, never invent 0,0.
    store.save_announce(other, {**record, "adv_lat": 40})
    assert store.map_nodes(other)[0]["latitude"] == 40


def test_malformed_positions_do_not_break_announce_storage(tmp_path):
    store = MeshCoreStore(tmp_path / "history.sqlite")
    for index, value in enumerate([None, math.nan, math.inf, True, 91, "49"]):
        store.save_announce(
            "a1" * 32,
            {
                "public_key": f"{index:064x}",
                "adv_name": "Unknown",
                "type": 1,
                "last_advert": 100,
                "adv_lat": value,
                "adv_lon": 1,
            },
        )
    assert store.map_nodes("a1" * 32) == []
    assert len(store.announces("a1" * 32)) == 6


@pytest.fixture
def controller(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from meshchatnext.src.backend.meshcore_tactical import MeshCoreTactical

    owner, channel = "a1" * 32, "c3" * 32
    store = MeshCoreStore(tmp_path / "history.sqlite")
    store.bind(owner, "owner")
    row = {"slot": 1, "channel_id": channel, "name": "Team", "kind": "private"}
    store.replace_channels(owner, [row])
    event = SimpleNamespace(type="OK", payload={}, is_error=lambda: False)
    commands = SimpleNamespace(
        send_channel_data=AsyncMock(return_value=event),
        set_flood_scope=AsyncMock(return_value=event),
    )
    session = SimpleNamespace(
        _lock=asyncio.Lock(),
        _client=SimpleNamespace(commands=commands),
        _device_info={"fw ver": 12},
        _payload=lambda e: e.payload,
        _close=AsyncMock(),
    )
    messages = SimpleNamespace(
        owner=owner,
        session=session,
        store=store,
        _check=Mock(),
        _drain_pending=AsyncMock(),
        _types=SimpleNamespace(OK="OK"),
    )
    channels = SimpleNamespace(_read=AsyncMock(return_value=(row, bytes(16))))
    return MeshCoreTactical(messages, channels, tmp_path)


@pytest.mark.asyncio
async def test_opt_in_private_channel_and_idempotent_send(controller):
    import uuid

    c = controller
    with pytest.raises(ValueError, match="Enable"):
        await c.send(
            {"kind": "position", "latitude": 1, "longitude": 2}, str(uuid.uuid4())
        )
    channel = "c3" * 32
    await c.configure(True, channel, "Alpha")
    assert c.session._client.commands.send_channel_data.await_count == 0
    item = {"kind": "position", "latitude": 1, "longitude": 2}
    request = str(uuid.uuid4())
    first = await c.send(item, request)
    assert first["state"] == "submitted"
    assert await c.send(item, request) == first
    assert c.session._client.commands.send_channel_data.await_count == 1
    with pytest.raises(ValueError, match="reused"):
        await c.send({**item, "latitude": 3}, request)
    from meshchatnext.src.backend.meshcore_tactical import snapshot

    own = snapshot(c.folder, c.owner)
    assert len(own["records"]) == 1 and own["records"][0]["alias"] == c.owner[:8]
    assert snapshot(c.folder, "b2" * 32)["records"] == []
    assert c.messages.store.contacts(c.owner) == []


@pytest.mark.asyncio
async def test_live_slot_key_revalidated_before_sending(controller):
    import uuid

    c = controller
    await c.configure(True, "c3" * 32)
    c.channels._read.return_value = (
        {"channel_id": "d4" * 32, "kind": "private"},
        bytes(16),
    )
    with pytest.raises(ValueError, match="channel changed"):
        await c.send({"kind": "alert", "active": True}, str(uuid.uuid4()))
    c.session._client.commands.send_channel_data.assert_not_awaited()
    c.channels._read.return_value = (
        {"channel_id": "c3" * 32, "kind": "public"},
        bytes(16),
    )
    with pytest.raises(ValueError, match="private"):
        await c.configure(True, "c3" * 32)


@pytest.mark.asyncio
async def test_uncertain_send_never_retransmits_and_scoping_resets(controller):
    import uuid

    c = controller
    await c.configure(True, "c3" * 32)
    c.messages.store.channel_scope(c.owner, "c3" * 32, "#test")
    c.session._client.commands.send_channel_data.side_effect = ConnectionError(
        "link lost"
    )
    request, item = str(uuid.uuid4()), {"kind": "alert", "active": True}
    with pytest.raises(ConnectionError):
        await c.send(item, request)
    assert (await c.send(item, request))["state"] == "unknown"
    c.session._client.commands.send_channel_data.assert_awaited_once()
    assert [
        call.args[0]
        for call in c.session._client.commands.set_flood_scope.await_args_list
    ] == ["#test", None]


@pytest.mark.asyncio
async def test_receive_disabled_malformed_other_channel_and_self_do_not_leak(
    controller,
):
    from meshchatnext.src.backend.meshcore_tactical import snapshot

    c = controller
    payload = {"data_type": 0x5654, "channel_idx": 1, "payload": P1}
    assert await c.receive(payload) is True
    assert await c.receive({**payload, "data_type": 123}) is False
    await c.configure(True, "c3" * 32)
    for bad in (
        {**payload, "payload": "zz"},
        {**payload, "channel_idx": 2},
        {**payload, "payload": P1[:2] + c.owner[:8] + P1[10:]},
    ):
        assert await c.receive(bad)
    assert snapshot(c.folder, c.owner)["records"] == []
    assert await c.receive(payload)
    result = snapshot(c.folder, c.owner)
    assert len(result["records"]) == 1
    assert result["records"][0]["identity_verified"] is False
    assert c.messages.store.contacts(c.owner) == []
    c.session._client.commands.send_channel_data.assert_not_awaited()


@pytest.mark.parametrize(
    "record",
    [
        {"kind": "pin", "alias": "01020304", "deleted": "false"},
        {"kind": "alert", "alias": "01020304", "active": 1},
        {"kind": "alert", "alias": "01020304", "latitude": 1},
    ],
)
def test_reject_ambiguous_flags_and_half_coordinates(record):
    with pytest.raises(ValueError):
        encode(record)


def test_salute_layout_and_withdrawal():
    # Fixed big-endian layout from upstream team_wire.dart, with ASCII fields
    # and UTC timestamp independent of Dart's local-time test fixture.
    raw = (
        bytes.fromhex("520a0b0c0d0000004d03011c328b28b72568b868eb2c500305")
        + b"\x04Camp\x00\x0aCheckpoint\x04Team\x06Radios\x00"
    )
    result = decode(raw)
    assert result["kind"] == "report" and result["id"] == 77
    assert result["vehicles"] == 3 and result["people"] == 5
    assert result["activity"] == "Checkpoint" and result["urgency"] == 3
    assert encode(result) == raw
    result["withdrawn"] = True
    assert decode(encode(result))["withdrawn"] is True
    for n in range(25):
        with pytest.raises(ValueError):
            decode(raw[:n])


def test_general_report_capacity_and_text_byte_limits():
    item = {
        "kind": "report",
        "alias": "01020304",
        "id": 1,
        "latitude": 0,
        "longitude": 0,
        "timestamp": 1,
        "report_kind": 1,
        "activity": "x" * 100,
        "place": "P" * 24,
    }
    raw = encode(item)
    assert len(raw) <= 163 and decode(raw)["activity"] == "x" * 100
    with pytest.raises(ValueError, match="UTF-8"):
        encode({**item, "activity": "é" * 51})
    with pytest.raises(ValueError, match="capacity"):
        encode({**item, "size": "s" * 12, "unit": "u" * 24, "equipment": "e" * 28})


@pytest.mark.asyncio
async def test_reject_stale_selected_channel_before_rf(controller):
    import uuid

    c = controller
    await c.configure(True, "c3" * 32)
    with pytest.raises(ValueError, match="channel changed"):
        await c.send(
            {"kind": "alert"}, str(uuid.uuid4()), expected_channel_id="d4" * 32
        )
    c.session._client.commands.send_channel_data.assert_not_awaited()


@pytest.mark.parametrize(
    "record",
    [
        None,
        {},
        {"kind": "position", "alias": "01020304"},
        {"kind": "alert", "alias": "01 02 03", "id": 1},
    ],
)
def test_incomplete_records_raise_validation_errors(record):
    with pytest.raises(ValueError):
        encode(record)


S1 = "44010203041234abcd00050368e778000a546f20416c7068612d310001030048a1c0ff4556d8008a17920e00"
S3 = "44010203040000000900000268e77800046c696e6500000200000064000000c864c701"


def test_upstream_route_golden_bytes_and_negative_deltas():
    route = {
        "kind": "shape",
        "alias": "01020304",
        "id": 0x1234ABCD,
        "shape_kind": 5,
        "color": 3,
        "timestamp": 1760000000,
        "label": "To Alpha-1",
        "route_method": 1,
        "points": [[47.6, -122.33], [47.6, -122.31523], [47.60905, -122.31523]],
    }
    assert encode(route).hex() == S1
    assert decode(bytes.fromhex(S1))["points"] == route["points"]
    line = decode(bytes.fromhex(S3))
    assert line["points"] == [[0.001, 0.002], [0.0015, 0.001]]
    assert encode(line).hex() == S3
    for size in range(len(bytes.fromhex(S1))):
        with pytest.raises(ValueError):
            decode(bytes.fromhex(S1)[:size])


def test_geofence_circle_polygon_and_empty_deletion():
    circle = {
        "kind": "shape",
        "alias": "01020304",
        "id": 1,
        "timestamp": 2,
        "shape_kind": 4,
        "points": [[1, 2]],
        "radius_m": 100,
        "geofence": 3,
    }
    back = decode(encode(circle))
    assert back["radius_m"] == 100 and back["geofence"] == 3
    assert decode(encode({**circle, "deleted": True, "points": []}))["deleted"]
    polygon = {
        **circle,
        "shape_kind": 2,
        "points": [[1, 2], [1.001, 2], [1.001, 2.001]],
    }
    assert decode(encode(polygon))["geofence"] == 3
    with pytest.raises(ValueError, match="closed"):
        encode({**polygon, "shape_kind": 5})
    with pytest.raises(ValueError):
        encode({**circle, "radius_m": 0})
    with pytest.raises(ValueError):
        encode({**circle, "points": [[100, 0]]})


def test_shapes_reject_pathological_varints_counts_and_oversized_geometry():
    from meshchatnext.src.backend.meshcore_tactical_wire import Reader

    for raw in (b"\x80" * 6, b"\xff\xff\xff\xff\x10", b"\x80"):
        with pytest.raises(ValueError):
            Reader(raw).varint()
    item = {
        **decode(bytes.fromhex(S1)),
        "points": [[i / 1000, i / 1000] for i in range(120)],
    }
    with pytest.raises(ValueError, match="capacity"):
        encode(item)
    with pytest.raises(ValueError, match="120"):
        encode({**item, "points": item["points"] + [[0, 0]]})


@pytest.mark.asyncio
async def test_shape_preview_is_read_only_and_shares_channel_scope(controller):
    import uuid

    c = controller
    item = {
        "kind": "shape",
        "shape_kind": 5,
        "points": [[0, 0], [0.001, 0.001]],
        "label": "Test route",
    }
    preview = await c.preview_shape(item)
    assert 0 < preview["bytes"] <= 163 and preview["vertices"] == 2
    c.session._client.commands.send_channel_data.assert_not_awaited()
    await c.configure(True, "c3" * 32)
    c.messages.store.channel_scope(c.owner, "c3" * 32, "#test")
    result = await c.send(item, str(uuid.uuid4()), expected_channel_id="c3" * 32)
    assert result["state"] == "submitted"
    assert [
        call.args[0]
        for call in c.session._client.commands.set_flood_scope.await_args_list
    ] == ["#test", None]
    from meshchatnext.src.backend.meshcore_tactical import snapshot

    assert snapshot(c.folder, c.owner)["records"][0]["kind"] == "shape"


@pytest.mark.asyncio
async def test_scope_changed_after_preview_never_transmits(controller):
    import uuid

    c = controller
    await c.configure(True, "c3" * 32)
    item = {"kind": "shape", "shape_kind": 5, "points": [[0, 0], [0.001, 0.001]]}
    await c.preview_shape(item)
    c.messages.store.channel_scope(c.owner, "c3" * 32, "#new-region")
    with pytest.raises(ValueError, match="scope changed"):
        await c.send(
            item, str(uuid.uuid4()), expected_channel_id="c3" * 32, expected_scope=None
        )
    c.session._client.commands.send_channel_data.assert_not_awaited()


# Monitoring is local and never infers a crossing from a first/old position.
def test_geofence_geometry_accuracy_dateline_and_polygon():
    from meshchatnext.src.backend.meshcore_geofences import side

    circle = {"shape_kind": 4, "points": [[0, 0]], "radius_m": 100}
    assert side(circle, {"latitude": 0, "longitude": 0}) is True
    assert side(circle, {"latitude": 0.002, "longitude": 0}) is False
    assert side(circle, {"latitude": 0.0009, "longitude": 0}) is None
    assert side(circle, {"latitude": 0, "longitude": 0, "accuracy": 120}) is None
    polygon = {
        "shape_kind": 2,
        "points": [[-0.01, -0.01], [-0.01, 0.01], [0.01, 0.01], [0.01, -0.01]],
    }
    assert side(polygon, {"latitude": 0, "longitude": 0}) is True
    assert side(polygon, {"latitude": 0.02, "longitude": 0}) is False
    assert side(polygon, {"latitude": 0.01, "longitude": 0}) is None
    polygon["points"] = [
        [-0.01, 179.99],
        [-0.01, -179.99],
        [0.01, -179.99],
        [0.01, 179.99],
    ]
    assert side(polygon, {"latitude": 0, "longitude": 180}) is True


def test_monitor_baselines_repeats_edit_gaps_and_entry_exit_rules():
    from meshchatnext.src.backend.meshcore_geofences import CrossingMonitor

    m = CrossingMonitor()
    shape = {
        "alias": "aabbccdd",
        "id": 1,
        "shape_kind": 4,
        "points": [[0, 0]],
        "radius_m": 100,
        "geofence": 3,
    }
    outside = {"alias": "01020304", "latitude": 0.002, "longitude": 0}
    inside = {**outside, "latitude": 0}
    assert m.update(outside, [shape], 1) == []
    assert m.update(inside, [shape], 2)[0][1] == "entered"
    assert m.update(inside, [shape], 3) == []
    assert m.update({**inside, "latitude": 0.0009}, [shape], 4) == []
    assert m.update(outside, [shape], 5)[0][1] == "left"
    assert m.update(inside, [{**shape, "label": "edited"}], 6) == []
    assert m.update(outside, [shape], 1000) == []
    m.reset()
    shape["geofence"] = 1
    assert m.update(inside, [shape], 1001) == []
    assert m.update(outside, [shape], 1002) == []
    assert m.update(inside, [shape], 1003)[0][1] == "entered"


@pytest.mark.asyncio
async def test_monitor_persisted_preference_notifications_and_cleanup(controller):
    import time
    from unittest.mock import Mock

    from meshchatnext.src.backend.meshcore_tactical import fence_notification, snapshot

    c = controller
    channel = "c3" * 32
    await c.configure(True, channel, monitor_geofences=True)
    assert snapshot(c.folder, c.owner)["monitor_geofences"] is True
    c.on_notification = Mock()
    shape = {
        "kind": "shape",
        "alias": "01020304",
        "id": 1,
        "timestamp": 10,
        "shape_kind": 4,
        "points": [[0, 0]],
        "radius_m": 100,
        "geofence": 3,
    }
    outside = {
        "kind": "position",
        "alias": "01020304",
        "latitude": 0.002,
        "longitude": 0,
        "callsign": "Tester",
    }

    def payload(item):
        return {"data_type": 0x5654, "channel_idx": 1, "payload": encode(item).hex()}

    await c.receive(payload(shape))
    await c.receive(payload(outside))
    assert not c.on_notification.called
    await c.receive(payload({**outside, "latitude": 0}))
    event = c.on_notification.call_args.args[0]
    assert event["kind"] == "tactical" and "entered" in event["text"]
    from unittest.mock import AsyncMock

    from meshchatnext.src.backend.meshcore_service import MeshCoreService

    service = MeshCoreService(c.folder)
    service._store = c.messages.store
    service.tactical = c
    service.ui = AsyncMock(return_value={"owner": c.owner})
    assert service._notification_allowed(event)
    target = await service.notification_target(None, event["notification_key"])
    assert target["kind"] == "tactical" and target["shape"] == "01020304:1"
    assert (
        fence_notification(c.folder, c.owner, event["notification_key"])["shape"]
        == "01020304:1"
    )
    assert fence_notification(c.folder, "b2" * 32, event["notification_key"]) is None
    await c.receive(payload({**outside, "latitude": 0}))
    assert c.on_notification.call_count == 1
    # Deletion invalidates both pending notifications and crossing baselines.
    await c.receive(payload({**shape, "timestamp": 11, "deleted": True, "points": []}))
    assert fence_notification(c.folder, c.owner, event["notification_key"]) is None
    await c.receive(payload({**shape, "timestamp": 12}))
    await c.receive(payload(outside))
    assert c.on_notification.call_count == 1
    await c.configure(True, channel, monitor_geofences=False)
    await c.receive(payload({**outside, "latitude": 0}))
    assert c.on_notification.call_count == 1
    assert c.session._client.commands.send_channel_data.await_count == 0
    assert not service._notification_allowed(event)
    assert time.time() > event["created"] - 1


@pytest.mark.asyncio
async def test_team_alert_opt_in_repeat_clear_and_notification_target(controller):
    from unittest.mock import Mock

    from meshchatnext.src.backend.meshcore_tactical import team_notification

    c = controller
    channel = "c3" * 32
    alert = {
        "kind": "alert",
        "alias": "01020304",
        "id": 42,
        "active": True,
        "alert_kind": 4,
        "callsign": "Test",
        "note": "Private test",
    }

    def payload(item):
        return {"data_type": 0x5654, "channel_idx": 1, "payload": encode(item).hex()}

    await c.configure(True, channel)
    c.on_notification = Mock()
    await c.receive(payload(alert))
    assert not c.on_notification.called
    await c.configure(True, channel, notify_team_alerts=True)
    # Existing repeated alerts do not become new merely because notifications were enabled.
    await c.receive(payload(alert))
    assert not c.on_notification.called
    alert["id"] = 43
    await c.receive(payload(alert))
    event = c.on_notification.call_args.args[0]
    assert (
        event["name"].startswith("Team alert") and event["item"] == "alert:01020304:43"
    )
    assert (
        team_notification(c.folder, c.owner, event["notification_key"])["id"]
        == event["id"]
    )
    await c.receive(payload(alert))
    assert c.on_notification.call_count == 1
    await c.receive(payload({**alert, "active": False}))
    assert team_notification(c.folder, c.owner, event["notification_key"]) is None
    await c.receive(payload(alert))
    assert c.on_notification.call_count == 1
    await c.configure(True, channel, notify_team_alerts=False)
    await c.receive(payload({**alert, "id": 44}))
    assert c.on_notification.call_count == 1
    assert c.session._client.commands.send_channel_data.await_count == 0


def test_casevac_documented_wire_layout_and_truncation():
    # Independently written from pinned team_casevac_wire.dart field order.
    expected = bytes.fromhex(
        "43 01020304 00000007 00 00000000 00000000 00000001 "
        "00 00 0000000000 00 00 00 00 03 00 000000000000 00 00 00 00"
    )
    record = {
        "kind": "casevac",
        "alias": "01020304",
        "id": 7,
        "timestamp": 1,
        "latitude": 0,
        "longitude": 0,
    }
    raw = encode(record)
    assert raw == expected and len(raw) == 45
    assert decode(raw)["marking"] == 3
    for size in range(len(raw)):
        with pytest.raises(ValueError):
            decode(raw[:size])
    malformed = bytearray(raw)
    malformed[9] = 2
    with pytest.raises(ValueError):
        decode(bytes(malformed))


def test_casevac_all_fields_and_capacity():
    from meshchatnext.src.backend.meshcore_tactical_wire import (
        CASEVAC_NUMBERS,
        CASEVAC_TEXT,
    )

    record = {
        "kind": "casevac",
        "alias": "01020304",
        "id": 7,
        "timestamp": 1,
        "latitude": 48,
        "longitude": -122,
        **{k: "x" * v for k, v in CASEVAC_TEXT.items()},
        **CASEVAC_NUMBERS,
    }
    raw = encode(record)
    assert len(raw) <= 163
    result = decode(raw)
    for key, value in record.items():
        assert result[key] == value
    for key, limit in CASEVAC_NUMBERS.items():
        with pytest.raises(ValueError):
            encode({**record, key: limit + 1})
    with pytest.raises(ValueError):
        encode({**record, "remarks": "🚑" * 11})


@pytest.mark.asyncio
async def test_casevac_send_and_withdrawal_owner_scoped(controller):
    import uuid

    c = controller
    await c.configure(True, "c3" * 32)
    result = await c.send(
        {"kind": "casevac", "latitude": 0, "longitude": 0, "urgent": 1},
        str(uuid.uuid4()),
    )
    assert result["state"] == "submitted"
    c.last_send.clear()
    await c.send(
        {
            "kind": "casevac",
            "latitude": 0,
            "longitude": 0,
            "id": result["id"],
            "deleted": True,
        },
        str(uuid.uuid4()),
    )
    from meshchatnext.src.backend.meshcore_tactical import snapshot

    assert snapshot(c.folder, c.owner)["records"][0]["deleted"] is True


@pytest.mark.parametrize("kind", ["pin", "report"])
def test_attachment_reference_roundtrip_and_wire_budget(kind):
    record = {
        "kind": kind,
        "alias": "aabbccdd",
        "id": 9,
        "latitude": 0,
        "longitude": 0,
        "timestamp": 1,
        "attachment": {"mode": 1, "sid": "1234abcd", "packets": 9, "extra": 9},
    }
    wire = encode(record)
    assert decode(wire)["attachment"] == record["attachment"]
    assert len(wire) == len(encode({**record, "attachment": None})) + 7
    if kind == "report":
        assert decode(encode({**record, "withdrawn": True}))["withdrawn"]


@pytest.mark.parametrize(
    "change",
    [
        {"mode": 0},
        {"sid": "../bad"},
        {"sid": "00000000"},
        {"packets": 65},
        {"packets": True},
        {"extra": -1},
        {"extra": 65536},
        {"surprise": 1},
    ],
)
def test_outgoing_attachment_rejects_invalid_metadata(change):
    meta = {"mode": 1, "sid": "1234abcd", "packets": 9, "extra": 9, **change}
    with pytest.raises(ValueError):
        encode(
            {
                "kind": "pin",
                "alias": "aabbccdd",
                "id": 1,
                "latitude": 0,
                "longitude": 0,
                "timestamp": 1,
                "attachment": meta,
            }
        )


@pytest.mark.asyncio
async def test_attachment_fetch_requires_current_stored_item_and_explicit_full_author(
    controller,
):
    import time
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    c = controller
    await c.configure(True, "c3" * 32)
    c.messages.voice = SimpleNamespace(
        fetch_reference=AsyncMock(return_value={"state": "downloading"})
    )
    record = {
        "kind": "pin",
        "alias": "b2b2b2b2",
        "id": 7,
        "timestamp": 1,
        "latitude": 0,
        "longitude": 0,
        "attachment": {"mode": 1, "sid": "1234abcd", "packets": 1, "extra": 1},
    }
    c._record(record, "c3" * 32, time.time())
    for peer, channel, item_id in [
        ("a1" * 32, "c3" * 32, 7),
        ("b2" * 32, "d4" * 32, 7),
        ("b2" * 32, "c3" * 32, 8),
    ]:
        with pytest.raises(ValueError):
            await c.fetch_attachment(peer, "pin", item_id, record["alias"], channel)
    c.messages.voice.fetch_reference.assert_not_awaited()
    assert await c.fetch_attachment(
        "b2" * 32, "pin", 7, record["alias"], "c3" * 32
    ) == {"state": "downloading"}
    c._record({**record, "deleted": True, "timestamp": 2}, "c3" * 32, time.time())
    with pytest.raises(ValueError):
        await c.fetch_attachment("b2" * 32, "pin", 7, record["alias"], "c3" * 32)
