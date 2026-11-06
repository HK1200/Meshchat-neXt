# SPDX-License-Identifier: MIT
"""Synthetic private location consent, wire compatibility and no-retry checks."""

import asyncio
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
from meshchatnext.src.backend.meshcore_private_location import (
    WRITE_GUARD,
    LocationPermissionChanged,
    check_write_permission,
    decode,
    encode,
)
from meshchatnext.src.backend.meshcore_store import MeshCoreStore

OWNER, PEER, OTHER = "a1" * 32, "b2" * 32, "c3" * 32
STAMP = 1793957816
VECTOR = "!NFLOC1:geo:48.7500000,-122.4800000,0.00;u=10.00;t=1793957816;s=0.00;b=0.00"


def fix(stamp=None):
    return {
        "latitude": 48.75,
        "longitude": -122.48,
        "altitude": 0,
        "accuracy": 10,
        "last_update": int(time.time()) if stamp is None else stamp,
        "speed": 0,
        "bearing": 0,
    }


@pytest.fixture
def store(tmp_path):
    value = MeshCoreStore(tmp_path / "meshcore.sqlite")
    value.bind(OWNER, "Synthetic")
    value.replace_contacts(
        OWNER, {PEER: {"public_key": PEER, "adv_name": "Test", "type": 1}}
    )
    return value


def payload(text, peer=PEER):
    return {
        "pubkey_prefix": peer[:12],
        "txt_type": 0,
        "text": text,
        "sender_timestamp": int(time.time()),
    }


def test_exact_family_wire_vector_and_strict_roundtrip():
    assert encode(fix(STAMP), now=STAMP) == VECTOR
    assert decode(VECTOR, now=STAMP) == fix(STAMP)


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", True),
        ("longitude", float("nan")),
        ("latitude", 91),
        ("longitude", -181),
        ("altitude", -12001),
        ("accuracy", 655.36),
        ("speed", -1),
        ("bearing", 361),
        ("last_update", STAMP - 86401),
        ("last_update", STAMP + 301),
    ],
)
def test_invalid_measurements_never_encode(field, value):
    with pytest.raises(ValueError):
        encode({**fix(STAMP), field: value}, now=STAMP)


@pytest.mark.parametrize(
    "text",
    [
        VECTOR + " ",
        "prefix" + VECTOR,
        VECTOR.replace("NFLOC1", "NFLOC2"),
        VECTOR.replace("48.7500000", "48.75"),
        VECTOR.replace("u=10.00", "u=nan"),
        "!NFLOC" + "x" * 160,
    ],
)
def test_strict_decoder_rejects_malformed_frames(text):
    with pytest.raises(ValueError):
        decode(text, now=STAMP)


def test_no_consent_no_private_position_and_no_chat_bubble(store):
    assert store.private_location_policy(OWNER, PEER) == {
        "receive": False,
        "share": False,
        "generation": None,
    }
    assert store.receive(OWNER, "direct", payload(encode(fix()))) is None
    assert store.private_locations(OWNER) == []
    assert store.history(OWNER, PEER) == []


def test_receive_replay_revoke_and_persistence(store):
    store.configure_private_location(OWNER, PEER, True, False)
    first = fix(int(time.time()) - 2)
    assert store.receive(OWNER, "direct", payload(encode(first))) is None
    assert store.private_locations(OWNER)[0]["latitude"] == first["latitude"]
    newer = {**fix(), "latitude": 49.25}
    store.receive(OWNER, "direct", payload(encode(newer)))
    store.receive(OWNER, "direct", payload(encode(first)))
    assert store.private_locations(OWNER)[0]["latitude"] == 49.25
    store.configure_private_location(OWNER, PEER, False, False)
    assert store.private_locations(OWNER) == []
    store.configure_private_location(OWNER, PEER, True, False)
    store.receive(OWNER, "direct", payload(encode(first)))
    assert store.private_locations(OWNER) == []  # replay tombstone survives revocation
    restored = MeshCoreStore(store.path)
    assert restored.private_location_policy(OWNER, PEER)["receive"] is True
    assert restored.history(OWNER, PEER) == []


@pytest.mark.parametrize(
    "text", ["!NFLOCgarbage", "!NFLOC2:geo:1,2", "!NFLOC1:" + "x" * 200]
)
def test_reserved_invalid_frames_are_consumed_without_history(store, text):
    store.configure_private_location(OWNER, PEER, True, False)
    assert store.receive(OWNER, "direct", payload(text)) is None
    assert store.private_locations(OWNER) == []
    assert store.history(OWNER, PEER) == []


def test_ambiguous_prefix_or_wrong_companion_never_updates_location(store):
    collision = PEER[:12] + "dd" * 26
    store.replace_contacts(
        OWNER, {p: {"public_key": p, "type": 1} for p in (PEER, collision)}
    )
    with pytest.raises(ValueError, match="Ambiguous"):
        store.configure_private_location(OWNER, PEER, True, False)
    store.receive(OWNER, "direct", payload(encode(fix())))
    assert store.private_locations(OWNER) == []
    store.receive(OTHER, "direct", payload(encode(fix())))
    assert store.private_locations(OTHER) == []


def test_receive_never_promotes_channel_or_admin_frames(store):
    store.configure_private_location(OWNER, PEER, True, False)
    assert (
        store.receive_private_location(OWNER, "channel", payload(encode(fix())))
        is False
    )
    assert (
        store.receive_private_location(
            OWNER, "direct", {**payload(encode(fix())), "txt_type": 1}
        )
        is True
    )
    assert store.private_locations(OWNER) == []


def test_contact_removal_clears_permissions_and_positions(store):
    policy = store.configure_private_location(OWNER, PEER, True, True)
    store.receive(OWNER, "direct", payload(encode(fix())))
    store.replace_contacts(OWNER, {})
    assert store.private_locations(OWNER) == []
    store.replace_contacts(OWNER, {PEER: {"public_key": PEER, "type": 1}})
    assert store.private_location_policy(OWNER, PEER)["generation"] is None
    with pytest.raises(LocationPermissionChanged):
        store.check_private_location_send(OWNER, PEER, policy["generation"])


@pytest.mark.parametrize("kind", [2, 3, 4])
def test_no_repeater_room_or_sensor_consent(store, kind):
    store.replace_contacts(OWNER, {PEER: {"public_key": PEER, "type": kind}})
    with pytest.raises(ValueError):
        store.configure_private_location(OWNER, PEER, True, True)


def test_send_rate_limit_and_idempotent_request(store):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    rid = str(uuid.uuid4())
    f = fix()
    row, fresh = store.reserve_private_location(
        OWNER, PEER, f, rid, policy["generation"]
    )
    assert fresh and row["frame"].startswith("!NFLOC1:geo:")
    assert (
        store.reserve_private_location(OWNER, PEER, f, rid, policy["generation"])[1]
        is False
    )
    with pytest.raises(ValueError):
        store.reserve_private_location(
            OWNER, PEER, f, str(uuid.uuid4()), policy["generation"]
        )
    with pytest.raises(ValueError):
        store.reserve_private_location(
            OWNER, PEER, {**f, "latitude": 50}, rid, policy["generation"]
        )
    assert store.history(OWNER, PEER) == []


def test_send_requires_fresh_fix_current_generation_and_saved_full_key(store):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    store.configure_private_location(OWNER, PEER, False, False)
    with pytest.raises(LocationPermissionChanged):
        store.reserve_private_location(
            OWNER, PEER, fix(), str(uuid.uuid4()), policy["generation"]
        )
    policy = store.configure_private_location(OWNER, PEER, False, True)
    with pytest.raises(ValueError):
        store.reserve_private_location(
            OWNER,
            PEER,
            fix(int(time.time()) - 121),
            str(uuid.uuid4()),
            policy["generation"],
        )
    with pytest.raises(ValueError):
        store.reserve_private_location(
            OWNER, PEER[:12], fix(), str(uuid.uuid4()), policy["generation"]
        )
    with pytest.raises(ValueError):
        store.reserve_private_location(
            OWNER, PEER, fix(), "not-a-uuid", policy["generation"]
        )


@pytest.mark.asyncio
async def test_private_submission_is_once_and_never_enters_chat(store):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    sent = []

    async def send(peer, text, **options):
        check_write_permission()
        sent.append((peer, text, options))
        return SimpleNamespace(type="sent", is_error=lambda: False)

    client = SimpleNamespace(commands=SimpleNamespace(send_msg=send))
    session = SimpleNamespace(_lock=asyncio.Lock(), _client=client, is_connected=True)
    messenger = MeshCoreMessaging(
        session, store, event_types=SimpleNamespace(MSG_SENT="sent")
    )
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    args = {
        "peer": PEER,
        "fix": fix(),
        "request_id": str(uuid.uuid4()),
        "generation": policy["generation"],
    }
    result = await messenger.send_private_location(**args)
    assert result["state"] == "accepted"
    assert await messenger.send_private_location(**args) == result
    assert len(sent) == 1 and sent[0][2]["attempt"] == 0
    assert store.history(OWNER, PEER) == []
    assert WRITE_GUARD.get() is None


@pytest.mark.asyncio
async def test_revoke_at_native_handoff_blocks_send_without_reconnect(store):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    sent = []

    async def send(*args, **kwargs):
        store.configure_private_location(OWNER, PEER, False, False)
        check_write_permission()
        sent.append(args)

    client = SimpleNamespace(commands=SimpleNamespace(send_msg=send))
    session = SimpleNamespace(_lock=asyncio.Lock(), _client=client, is_connected=True)
    messenger = MeshCoreMessaging(
        session, store, event_types=SimpleNamespace(MSG_SENT="sent")
    )
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    with pytest.raises(LocationPermissionChanged):
        await messenger.send_private_location(
            PEER, fix(), str(uuid.uuid4()), policy["generation"]
        )
    assert not sent and session.is_connected and WRITE_GUARD.get() is None


@pytest.mark.asyncio
async def test_android_worker_rechecks_consent_without_disconnect():
    from meshchatnext.src.backend.meshcore_transport import AndroidConnection

    connection = AndroidConnection("usb", "/dev/synthetic")
    connection._connected = True
    sent = []
    connection._native = SimpleNamespace(send=sent.append)
    connection.disconnect = AsyncMock()
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise LocationPermissionChanged("revoked")

    token = WRITE_GUARD.set(guard)
    try:
        with pytest.raises(LocationPermissionChanged):
            await connection.send(b"synthetic")
    finally:
        WRITE_GUARD.reset(token)
    assert calls == 2 and not sent
    connection.disconnect.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_result_is_persisted_and_not_retransmitted(store):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    send = AsyncMock(side_effect=TimeoutError("synthetic"))
    client = SimpleNamespace(commands=SimpleNamespace(send_msg=send))
    session = SimpleNamespace(_lock=asyncio.Lock(), _client=client, is_connected=True)
    messenger = MeshCoreMessaging(
        session, store, event_types=SimpleNamespace(MSG_SENT="sent")
    )
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    args = {
        "peer": PEER,
        "fix": fix(),
        "request_id": str(uuid.uuid4()),
        "generation": policy["generation"],
    }
    with pytest.raises(TimeoutError):
        await messenger.send_private_location(**args)
    assert (await messenger.send_private_location(**args))["state"] == "unknown"
    assert send.await_count == 1
    assert WRITE_GUARD.get() is None


@pytest.mark.asyncio
async def test_receive_queue_consumes_private_frame_without_notification(store):
    store.configure_private_location(OWNER, PEER, True, False)
    event = SimpleNamespace(type="direct", payload=payload(encode(fix())))
    client = SimpleNamespace(
        commands=SimpleNamespace(get_msg=AsyncMock(return_value=event))
    )
    session = SimpleNamespace(
        _lock=asyncio.Lock(),
        _client=client,
        is_connected=True,
        _payload=lambda e: e.payload,
    )
    types = SimpleNamespace(
        NO_MORE_MSGS="empty",
        CONTACT_MSG_RECV="direct",
        CHANNEL_MSG_RECV="channel",
        CHANNEL_DATA_RECV="data",
    )
    messenger = MeshCoreMessaging(session, store, event_types=types)
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    notify = AsyncMock()
    messenger.on_message = notify
    assert await messenger._fetch_message() is True
    assert len(store.private_locations(OWNER)) == 1
    assert store.history(OWNER, PEER) == []
    notify.assert_not_called()


@pytest.mark.asyncio
async def test_desktop_transport_rechecks_revoked_consent_before_native_send():
    from meshchatnext.src.backend.meshcore_desktop_transport import DesktopConnection

    connection = DesktopConnection("usb", "/dev/synthetic")
    native = SimpleNamespace(send=AsyncMock())
    connection._native = native
    connection._connected = True

    def guard():
        raise LocationPermissionChanged("revoked")

    token = WRITE_GUARD.set(guard)
    try:
        with pytest.raises(LocationPermissionChanged):
            await connection.send(b"synthetic")
    finally:
        WRITE_GUARD.reset(token)
    native.send.assert_not_called()
    assert connection.is_connected


def test_room_text_is_not_private_location_protocol(store):
    store.replace_contacts(OWNER, {PEER: {"public_key": PEER, "type": 3}})
    assert (
        store.receive_private_location(OWNER, "direct", payload(encode(fix()))) is False
    )
    assert (
        store.receive_private_location(OWNER, "direct", payload("!NFLOCgarbage"))
        is False
    )
    assert store.private_locations(OWNER) == []


@pytest.mark.asyncio
async def test_plain_chat_cannot_bypass_private_location_consent(store):
    client = SimpleNamespace(commands=SimpleNamespace(send_msg=AsyncMock()))
    session = SimpleNamespace(_lock=asyncio.Lock(), _client=client, is_connected=True)
    messenger = MeshCoreMessaging(session, store)
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    with pytest.raises(ValueError, match="private location controls"):
        await messenger.send_direct(PEER, encode(fix()), request_id=str(uuid.uuid4()))
    client.commands.send_msg.assert_not_called()


@pytest.mark.parametrize("receive,share", [(1, False), (False, "true"), (None, True)])
def test_consent_is_explicit_boolean_only(store, receive, share):
    with pytest.raises(ValueError):
        store.configure_private_location(OWNER, PEER, receive, share)
    assert store.private_location_policy(OWNER, PEER)["generation"] is None


@pytest.mark.asyncio
async def test_private_positions_are_map_only_not_advertisements_or_team_broadcasts(
    store, tmp_path
):
    from meshchatnext.src.backend.meshcore_service import MeshCoreService

    store.configure_private_location(OWNER, PEER, True, False)
    store.receive(OWNER, "direct", payload(encode(fix())))
    service = MeshCoreService(tmp_path / "service")
    service._store = store
    service.folder.mkdir(parents=True)
    service.ui = AsyncMock(
        return_value={
            "owner": OWNER,
            "connected": False,
            "contacts": store.contacts(OWNER),
        }
    )
    result = await service.map_snapshot("synthetic-account")
    assert result["nodes"][0]["private_location"] is True
    assert result["nodes"][0]["peer"] == PEER
    assert store.map_nodes(OWNER) == []
    assert not result["tactical"].get("records")
    assert store.history(OWNER, PEER) == []
    store.configure_private_location(OWNER, PEER, False, False)
    assert (await service.map_snapshot("synthetic-account"))["nodes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,fields,method",
    [
        ("status", {}, "private_location_status"),
        (
            "configure",
            {"receive": True, "share": False, "generation": None},
            "configure_private_location",
        ),
        (
            "send",
            {
                "fix": fix(STAMP),
                "request_id": str(uuid.uuid4()),
                "generation": "synthetic",
            },
            "send_private_location",
        ),
    ],
)
async def test_http_requires_exact_owner_and_forbids_room_channel_fields(
    action, fields, method
):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from meshchatnext.src.backend.meshcore_http import register_meshcore_routes

    call = AsyncMock(return_value={"ok": True})
    service = SimpleNamespace(call=call)
    routes = web.RouteTableDef()
    register_meshcore_routes(routes, SimpleNamespace(meshcore_service=service))
    app = web.Application()
    app.add_routes(routes)
    async with TestClient(TestServer(app)) as client:
        base = {"peer": PEER, **fields}
        for body in (
            base,
            {**base, "expected_owner": OWNER[:12]},
            {**base, "expected_owner": OWNER, "room": True},
            {**base, "expected_owner": OWNER, "channel_id": "public"},
        ):
            response = await client.post(
                "/api/v1/meshcore/private-location-" + action, json=body
            )
            assert response.status == 400
        call.assert_not_called()
        response = await client.post(
            "/api/v1/meshcore/private-location-" + action,
            json={**base, "expected_owner": OWNER},
        )
        assert response.status == 200
        assert call.call_args.args == ("messages", method)
        assert call.call_args.kwargs["expected_owner"] == OWNER
        assert call.call_args.kwargs["peer"] == PEER


def test_sent_location_log_keeps_only_digest_and_rate_limit_survives_contact_readd(
    store,
):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    rid = str(uuid.uuid4())
    f = fix()
    store.reserve_private_location(OWNER, PEER, f, rid, policy["generation"])
    with store._connect() as db:
        saved = db.execute("SELECT frame FROM private_location_sends").fetchone()[0]
    assert len(saved) == 64 and "geo:" not in saved
    store.replace_contacts(OWNER, {})
    store.replace_contacts(OWNER, {PEER: {"public_key": PEER, "type": 1}})
    policy = store.configure_private_location(OWNER, PEER, False, True)
    with pytest.raises(ValueError, match="one minute"):
        store.reserve_private_location(
            OWNER, PEER, f, str(uuid.uuid4()), policy["generation"]
        )


@pytest.mark.asyncio
async def test_fresh_firmware_contact_prefix_collision_prevents_private_send(store):
    policy = store.configure_private_location(OWNER, PEER, False, True)
    collision = PEER[:12] + "dd" * 26
    contacts = {p: {"public_key": p, "type": 1} for p in (PEER, collision)}
    read = AsyncMock(return_value=SimpleNamespace(payload=contacts))
    send = AsyncMock()
    client = SimpleNamespace(commands=SimpleNamespace(send=read, send_msg=send))
    session = SimpleNamespace(
        _lock=asyncio.Lock(),
        _client=client,
        is_connected=True,
        _payload=lambda e: e.payload,
    )
    types = SimpleNamespace(CONTACTS="contacts", ERROR="error", MSG_SENT="sent")
    messenger = MeshCoreMessaging(session, store, event_types=types)
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    with pytest.raises(ValueError, match="Ambiguous"):
        await messenger.send_private_location(
            PEER, fix(), str(uuid.uuid4()), policy["generation"]
        )
    read.assert_awaited_once_with(b"\x04", ["contacts", "error"])
    send.assert_not_called()


def test_private_and_normal_messages_share_monotonic_companion_clock(store):
    first, _ = store.prepare_send(OWNER, PEER, "synthetic normal", str(uuid.uuid4()))
    policy = store.configure_private_location(OWNER, PEER, False, True)
    private, _ = store.reserve_private_location(
        OWNER, PEER, fix(), str(uuid.uuid4()), policy["generation"]
    )
    last, _ = store.prepare_send(
        OWNER, PEER, "another synthetic normal", str(uuid.uuid4())
    )
    assert first["timestamp"] < private["timestamp"] < last["timestamp"]
    assert store.outgoing_clock(OWNER, PEER) == last["timestamp"]


@pytest.mark.asyncio
async def test_service_can_revoke_consent_while_private_send_waits_at_transport(
    store, tmp_path
):
    from meshchatnext.src.backend.meshcore_service import MeshCoreService

    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    async def send(*args, **kwargs):
        entered.set()
        await release.wait()
        check_write_permission()
        sent.append(args)

    client = SimpleNamespace(commands=SimpleNamespace(send_msg=send))
    session = SimpleNamespace(_lock=asyncio.Lock(), _client=client, is_connected=True)
    messenger = MeshCoreMessaging(
        session, store, event_types=SimpleNamespace(MSG_SENT="sent")
    )
    messenger.owner = OWNER
    messenger._client = client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    service = MeshCoreService(tmp_path / "service")
    service.session, service.messages = session, messenger
    service._state = "connected"
    policy = store.configure_private_location(OWNER, PEER, False, True)
    task = asyncio.create_task(
        service.call(
            "messages",
            "send_private_location",
            peer=PEER,
            fix=fix(),
            request_id=str(uuid.uuid4()),
            generation=policy["generation"],
            expected_owner=OWNER,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        revoked = await asyncio.wait_for(
            service.call(
                "messages",
                "configure_private_location",
                peer=PEER,
                receive=False,
                share=False,
                expected_owner=OWNER,
            ),
            5,
        )
        assert revoked["share"] is False
        release.set()
        with pytest.raises(LocationPermissionChanged):
            await task
        assert not sent and session.is_connected
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_permissions_can_be_revoked_offline_without_any_radio_or_location_access(
    store, tmp_path
):
    from meshchatnext.src.backend.meshcore_service import MeshCoreService

    store.configure_private_location(OWNER, PEER, True, True)
    store.receive(OWNER, "direct", payload(encode(fix())))
    service = MeshCoreService(tmp_path / "offline")
    service._store, service._known_owner = store, OWNER
    assert service.session is None
    assert (
        await service.call(
            "messages", "private_location_status", peer=PEER, expected_owner=OWNER
        )
    )["share"] is True
    result = await service.call(
        "messages",
        "configure_private_location",
        peer=PEER,
        receive=False,
        share=False,
        expected_owner=OWNER,
    )
    assert result["receive"] is False and result["share"] is False
    assert store.private_locations(OWNER) == []
    with pytest.raises(ValueError):
        await service.call(
            "messages",
            "configure_private_location",
            peer=PEER,
            receive=True,
            share=True,
            expected_owner=OTHER,
        )
    assert store.private_location_policy(OWNER, PEER)["share"] is False


@pytest.mark.asyncio
async def test_changed_hardware_identity_is_rejected_before_private_destination_or_send(
    store,
):
    client = SimpleNamespace(
        commands=SimpleNamespace(
            send_appstart=AsyncMock(
                return_value=SimpleNamespace(payload={"public_key": OTHER})
            ),
            send_msg=AsyncMock(),
        )
    )
    session = SimpleNamespace(
        _lock=asyncio.Lock(),
        _client=client,
        is_connected=True,
        _payload=lambda e: e.payload,
    )
    messenger = MeshCoreMessaging(session, store)
    messenger.owner, messenger._client = OWNER, client
    messenger._sync_contacts = AsyncMock()
    policy = store.configure_private_location(OWNER, PEER, False, True)
    with pytest.raises(LocationPermissionChanged, match="identity changed"):
        await messenger.send_private_location(
            PEER, fix(), str(uuid.uuid4()), policy["generation"]
        )
    messenger._sync_contacts.assert_not_called()
    client.commands.send_msg.assert_not_called()


@pytest.mark.asyncio
async def test_current_hardware_full_identity_preflight_succeeds_without_sending(store):
    client = SimpleNamespace(
        commands=SimpleNamespace(
            send_appstart=AsyncMock(
                return_value=SimpleNamespace(payload={"public_key": OWNER})
            ),
            send_msg=AsyncMock(),
        )
    )
    session = SimpleNamespace(
        _lock=asyncio.Lock(),
        _client=client,
        is_connected=True,
        _payload=lambda e: e.payload,
    )
    messenger = MeshCoreMessaging(session, store)
    messenger.owner, messenger._client = OWNER, client
    await messenger._verify_private_location_identity()
    client.commands.send_msg.assert_not_called()


@pytest.mark.asyncio
async def test_actual_pinned_sdk_preserves_no_send_outcome_when_guard_exception_becomes_event(
    store,
):
    from meshcore.commands.messaging import MessagingCommands
    from meshcore.events import EventDispatcher, EventType

    policy = store.configure_private_location(OWNER, PEER, False, True)
    frames = []

    async def native_send(data):
        store.configure_private_location(OWNER, PEER, False, False)
        check_write_permission()
        frames.append(data)

    commands = MessagingCommands(default_timeout=8.0)
    commands.set_dispatcher(EventDispatcher())
    commands.set_connection(SimpleNamespace(send=native_send))
    client = SimpleNamespace(commands=commands)
    session = SimpleNamespace(_lock=asyncio.Lock(), _client=client, is_connected=True)
    messenger = MeshCoreMessaging(session, store, event_types=EventType)
    messenger.owner, messenger._client = OWNER, client
    messenger._verify_private_location_identity = AsyncMock()
    messenger._sync_contacts = AsyncMock(return_value=store.contacts(OWNER))
    args = {
        "peer": PEER,
        "fix": fix(),
        "request_id": str(uuid.uuid4()),
        "generation": policy["generation"],
    }
    result = await messenger.send_private_location(**args)
    assert result["state"] == "rejected"
    assert not frames and session.is_connected
    assert await messenger.send_private_location(**args) == result


@pytest.mark.parametrize("field", ["accuracy", "speed", "bearing"])
def test_unsigned_zero_fields_remain_family_decoder_compatible(field):
    encoded = encode({**fix(STAMP), field: -0.0}, now=STAMP)
    assert decode(encoded, now=STAMP)[field] == 0
    assert ";u=-" not in encoded and ";s=-" not in encoded and ";b=-" not in encoded


def test_stale_settings_cannot_restore_a_revoked_permission(store):
    first = store.configure_private_location(OWNER, PEER, True, True, generation=None)
    revoked = store.configure_private_location(
        OWNER, PEER, False, False, generation=first["generation"]
    )
    with pytest.raises(LocationPermissionChanged, match="read them again"):
        store.configure_private_location(
            OWNER, PEER, True, True, generation=first["generation"]
        )
    assert store.private_location_policy(OWNER, PEER) == revoked
    assert not revoked["receive"] and not revoked["share"]
