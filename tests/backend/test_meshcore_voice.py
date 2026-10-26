import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend.meshcore_voice import (
    MeshCoreVoice,
    b36,
    decode,
    encode,
    envelope,
)

OWNER, PEER, OTHER = "a1" * 32, "b2" * 32, "c3" * 32


def test_codec_and_envelope_bounds():
    for count in (1600, 16000, 320000):
        encoded, seconds = encode(bytes(count))
        audio = base64.b64decode(decode(encoded, 1))
        assert audio[:4] == b"RIFF"
        assert len(audio) <= 326444
        assert seconds <= 20
    assert envelope("VE3:" + b36(0xFFFFFFFF) + ":1:2:k")["sid"] == "ffffffff"
    for text in (
        "VE3:0:1:1:1",
        "VE3:1:7:1:1",
        "VE3:1:1:zz:1",
        "VE3:1:1:1:l",
        "VE3:../../:1:1:1",
    ):
        with pytest.raises(ValueError):
            envelope(text)
    for pcm in (b"", bytes(1601), bytes(320002)):
        with pytest.raises(ValueError):
            encode(pcm)


@pytest.fixture
async def voice(tmp_path):
    listeners = {}

    def subscribe(kind, handler):
        listeners[kind] = handler
        return SimpleNamespace(unsubscribe=lambda: listeners.pop(kind, None))

    client = SimpleNamespace(
        contacts={PEER: {"out_path_len": 0, "out_path": "", "out_path_hash_mode": 0}},
        subscribe=subscribe,
        commands=SimpleNamespace(
            send_raw_data=AsyncMock(
                return_value=SimpleNamespace(payload={}, is_error=lambda: False)
            )
        ),
    )
    session = SimpleNamespace(
        _lock=asyncio.Lock(), _client=client, _payload=lambda x: x.payload
    )
    messages = SimpleNamespace(
        owner=OWNER,
        session=session,
        _client=client,
        _types=SimpleNamespace(RAW_DATA="raw"),
        _check=lambda: None,
        send_direct=AsyncMock(return_value={"state": "submitted"}),
        store=SimpleNamespace(history=lambda *args: []),
    )
    instance = MeshCoreVoice(messages, tmp_path)
    instance.gate = AsyncMock()
    yield instance
    await instance.close()
    assert not listeners


@pytest.mark.asyncio
async def test_draft_not_served_until_send_and_owner_peer_cache_isolation(voice):
    draft = await voice.prepare(
        PEER, base64.b64encode(bytes(16000)).decode(), "recording-request-1"
    )
    assert draft["total"] == 1
    assert voice.clip(PEER, draft["sid"], "out")["announced"] == 0
    with pytest.raises(ValueError):
        voice.clip(OTHER, draft["sid"], "out")
    voice.enqueue(PEER, draft["sid"], None, True)
    await asyncio.sleep(0.01)
    voice.messages._client.commands.send_raw_data.assert_not_awaited()
    await voice.send(PEER, draft["sid"], "send-request")
    args = voice.messages.send_direct.await_args
    assert envelope(args.args[1])["sid"] == draft["sid"]
    voice.enqueue(PEER, draft["sid"], None, True)
    await asyncio.sleep(0.01)
    packet = voice.messages._client.commands.send_raw_data.await_args.args[0]
    assert packet[0] == 0x57 and packet[1:5].hex() == draft["sid"]
    assert len(packet) == 157
    assert (await voice.play(PEER, draft["sid"], "out"))["wav_base64"]
    await voice.discard(PEER, draft["sid"])
    assert voice.clip(
        PEER, draft["sid"], "out"
    )  # Announced clips cannot accidentally be discarded.


@pytest.mark.asyncio
async def test_raw_reception_rejects_unrequested_wrong_sid_and_bad_frames(voice):
    frames = {}
    voice.active = ("12345678", {"mode": 1, "total": 2}, frames)

    def rx(data):
        voice.received(SimpleNamespace(payload={"payload": data.hex()}))

    rx(bytes.fromhex("561234567900") + bytes(6))
    assert not frames
    rx(bytes.fromhex("561234567800") + bytes(5))
    assert not frames
    rx(bytes.fromhex("561234567803") + bytes(6))
    assert not frames
    rx(bytes.fromhex("571234567800") + bytes(6) + b"x")
    assert frames == {0: bytes(6)}
    rx(bytes.fromhex("561234567800") + b"abcdef")
    assert frames[0] == bytes(6)


@pytest.mark.asyncio
async def test_voice_route_does_not_change_multibyte_hash_settings(voice):
    voice.messages._client.contacts[PEER].update(
        out_path_len=1, out_path="aaaa", out_path_hash_mode=1
    )
    with pytest.raises(ValueError, match="one-byte"):
        voice.route(PEER)
    assert voice.messages._client.contacts[PEER]["out_path_hash_mode"] == 1
    with pytest.raises(ValueError):
        await voice.fetch(PEER, "nonexistent")


@pytest.mark.asyncio
async def test_hidden_request_requires_matching_known_sender(voice):
    good = {"text": "VR3:1:a:" + PEER[:12], "pubkey_prefix": PEER[:12]}
    assert voice.hidden_request(good)
    assert not voice.hidden_request({**good, "pubkey_prefix": OTHER[:12]})
    assert not voice.hidden_request({**good, "text": "VR3:1:m0-zzz:" + PEER[:12]})


@pytest.mark.asyncio
async def test_two_clients_fetch_codec2_clip_with_raw_packet_loss_retry(
    voice, tmp_path
):
    from meshchatnext.src.backend.meshcore_voice import MeshCoreVoice

    sender = voice
    listeners = {}

    def subscribe(kind, callback):
        listeners[kind] = callback
        return SimpleNamespace(unsubscribe=lambda: listeners.pop(kind, None))

    client = SimpleNamespace(
        contacts={OWNER: {"out_path_len": 0, "out_path": "", "out_path_hash_mode": 0}},
        subscribe=subscribe,
        commands=SimpleNamespace(),
    )
    session = SimpleNamespace(
        _lock=asyncio.Lock(), _client=client, _payload=lambda event: event.payload
    )
    messages = SimpleNamespace(
        owner=PEER,
        session=session,
        _client=client,
        _types=SimpleNamespace(RAW_DATA="raw"),
        _check=lambda: None,
        store=SimpleNamespace(),
    )
    # Each client has its own database, identity and independent session lock.
    folder = tmp_path / "receiver"
    folder.mkdir()
    receiver = MeshCoreVoice(messages, folder)
    receiver.gate = AsyncMock()
    dropped = False
    packets = []

    async def to_receiver(packet, path):
        nonlocal dropped
        packets.append(packet)
        if packet[5] == 1 and not dropped:
            dropped = True
        else:
            receiver.received(SimpleNamespace(payload={"payload": packet.hex()}))
        return SimpleNamespace(payload={}, is_error=lambda: False)

    async def to_sender(packet, path):
        sender.received(SimpleNamespace(payload={"payload": packet.hex()}))
        return SimpleNamespace(payload={}, is_error=lambda: False)

    sender.messages._client.commands.send_raw_data = AsyncMock(side_effect=to_receiver)
    client.commands.send_raw_data = AsyncMock(side_effect=to_sender)
    try:
        draft = await sender.prepare(
            PEER, base64.b64encode(bytes(48000)).decode(), "roundtrip-recording"
        )
        await sender.send(PEER, draft["sid"], "roundtrip-send")
        text = sender.messages.send_direct.await_args.args[1]
        messages.store.history = lambda *args: [
            {"id": "incoming-clip", "text": text, "direction": "in"}
        ]
        assert (await receiver.fetch(OWNER, "incoming-clip"))["state"] == "downloading"
        await asyncio.wait_for(receiver.fetch_task, 12)
        assert receiver.jobs[OWNER + ":" + draft["sid"]]["state"] == "complete"
        assert dropped and client.commands.send_raw_data.await_count == 2
        assert (
            receiver.clip(OWNER, draft["sid"], "in")["data"]
            == sender.clip(PEER, draft["sid"], "out")["data"]
        )
        audio = base64.b64decode(
            (await receiver.play(OWNER, draft["sid"], "in"))["wav_base64"]
        )
        assert audio[:4] == b"RIFF" and len(audio) == len(
            base64.b64decode(draft["wav_base64"])
        )
        assert packets[0][0] == 0x57
    finally:
        await receiver.close()


@pytest.mark.asyncio
async def test_cached_audio_plays_offline_and_stays_owner_scoped(voice):
    from meshchatnext.src.backend.meshcore_service import MeshCoreService
    from meshchatnext.src.backend.meshcore_voice import play_cached

    draft = await voice.prepare(
        PEER, base64.b64encode(bytes(16000)).decode(), "offline-recording"
    )
    cached = play_cached(voice.path.parent, OWNER, PEER, draft["sid"], "out")
    assert base64.b64decode(cached["wav_base64"])[:4] == b"RIFF"
    with pytest.raises(ValueError):
        play_cached(voice.path.parent, OTHER, PEER, draft["sid"], "out")
    with pytest.raises(ValueError):
        play_cached(voice.path.parent, OWNER, PEER, draft["sid"], "invalid")
    with pytest.raises(ValueError):
        play_cached(voice.path.parent / "missing", OWNER, PEER, draft["sid"], "out")
    service = MeshCoreService(voice.path.parent)
    service._selection = {
        "owner": OWNER,
        "kind": "ble",
        "target": "test",
        "auto_reconnect": False,
    }
    assert not service.status()["connected"]
    assert (await service.cached_voice(PEER, draft["sid"], "out", OWNER))["wav_base64"]
    with pytest.raises(ValueError):
        await service.cached_voice(PEER, draft["sid"], "out", OTHER)
    service._selection = None
    (voice.path.parent / "ui-owner.json").write_text('"' + OWNER + '"')
    assert (await service.cached_voice(PEER, draft["sid"], "out", OWNER))["wav_base64"]


@pytest.mark.asyncio
async def test_connection_close_cancels_download_without_caching_partial_audio(voice):
    requested = asyncio.Event()

    async def request(packet, path):
        requested.set()
        return SimpleNamespace(payload={}, is_error=lambda: False)

    voice.messages._client.commands.send_raw_data = AsyncMock(side_effect=request)
    voice.messages.store.history = lambda *args: [
        {"id": "interrupted", "direction": "in", "text": "VE3:1:1:2:2"}
    ]
    await voice.fetch(PEER, "interrupted")
    await asyncio.wait_for(requested.wait(), 1)
    voice.received(
        SimpleNamespace(
            payload={
                "payload": (
                    b"V" + bytes.fromhex("00000001") + b"\x00" + bytes(156)
                ).hex()
            }
        )
    )
    await voice.close()
    assert voice.fetch_task.done()
    assert voice.jobs[PEER + ":00000001"]["state"] == "cancelled"
    assert voice.active is None
    with pytest.raises(ValueError):
        voice.clip(PEER, "00000001", "in")
    # A late fragment from the old connection cannot complete a cancelled clip.
    voice.received(
        SimpleNamespace(
            payload={
                "payload": (
                    b"V" + bytes.fromhex("00000001") + b"\x01" + bytes(144)
                ).hex()
            }
        )
    )
    assert voice.active is None


@pytest.mark.asyncio
async def test_tactical_draft_only_served_after_explicit_attachment_share(voice):
    draft = await voice.prepare(
        OWNER, base64.b64encode(bytes(16000)).decode(), "tactical-draft-1234"
    )
    voice.enqueue(PEER, draft["sid"], None, False)
    await asyncio.sleep(0.02)
    voice.messages._client.commands.send_raw_data.assert_not_awaited()
    with voice.db() as db:
        db.execute(
            "UPDATE clips SET announced=2 WHERE owner=? AND peer=? AND sid=?",
            (OWNER, OWNER, draft["sid"]),
        )
    voice.enqueue(PEER, draft["sid"], None, False)
    await asyncio.sleep(0.02)
    voice.messages._client.commands.send_raw_data.assert_awaited_once()
    voice.messages.send_direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_tactical_fetch_refuses_unsupported_media_without_rf(voice):
    with pytest.raises(ValueError, match="not supported"):
        await voice.fetch_reference(
            PEER, {"sid": "1234abcd", "mode": 32, "total": 1, "seconds": 100}
        )
    voice.messages._client.commands.send_raw_data.assert_not_awaited()


@pytest.mark.parametrize("text", ["VI1:1:14:1:2s", "VI1:1:14:1:2s photo caption"])
def test_image_envelope_is_distinct_from_audio(text):
    assert envelope(text) == {"sid": "00000001", "mode": 40, "total": 1, "seconds": 100}
    for bad in ("VI1:1:1:1:1", "VE3:1:14:1:1", "VI1:1:14:zz:1", "VI1:0:14:1:1"):
        with pytest.raises(ValueError):
            envelope(bad)


@pytest.mark.asyncio
async def test_channel_frames_are_bound_to_the_requested_channel_and_never_raw(voice):
    frames = {}
    voice.active = ("12345678", {"mode": 40, "total": 1}, frames)
    voice.active_channel = OTHER
    event = SimpleNamespace(payload={"payload": "561234567800010203"})
    voice.received(event)
    voice.received(event, OWNER)
    assert not frames
    voice.received(event, OTHER)
    assert frames == {0: b"\x01\x02\x03"}
    voice.messages._client.commands.send_raw_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_media_control_is_consumed_without_ordinary_chat(voice):
    voice.messages.store.channel_ui = lambda *_: [{"slot": 2, "channel_id": OTHER}]
    assert (
        await voice.receive_channel(
            {"data_type": 0x5643, "channel_idx": 2, "payload": "invalid"}
        )
        is True
    )
    assert await voice.receive_channel({"data_type": 1}) is False
    assert voice.queue.empty()


@pytest.mark.asyncio
async def test_channel_packet_revalidates_slot_and_scope_before_transmission(voice):
    voice.messages.store.channel_ui = lambda *_: [{"slot": 2, "channel_id": OTHER}]
    voice.messages.store.channel_scope = lambda *_: "new"
    voice.messages.channels = SimpleNamespace(
        _read=AsyncMock(return_value=({"channel_id": OTHER}, bytes(16)))
    )
    voice.messages._client.commands.send_channel_data = AsyncMock()
    voice.channel_scopes[OTHER] = "old"
    with pytest.raises(ValueError, match="scope changed"):
        await voice.channel_packet(OTHER, b"hello")
    voice.messages._client.commands.send_channel_data.assert_not_awaited()
    voice.channel_scopes[OTHER] = "new"
    voice.messages.channels._read.return_value = ({"channel_id": OWNER}, bytes(16))
    with pytest.raises(ValueError, match="channel changed"):
        await voice.channel_packet(OTHER, b"hello")
    voice.messages._client.commands.send_channel_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_frame_retry_changes_request_and_finishes_without_reannouncing(
    voice,
):
    data, _ = encode(bytes(32000))
    meta = {"sid": "76543210", "mode": 1, "total": 2, "seconds": 2}
    attempts = []

    async def reply(payload, **_):
        attempts.append(payload)
        index = 0 if len(attempts) == 1 else 1
        block = data[:156] if index == 0 else data[156:]
        packet = (
            bytes([0x57]) + bytes.fromhex(meta["sid"]) + bytes([index]) + block + b"x"
        )
        voice.received(SimpleNamespace(payload={"payload": packet.hex()}))
        return SimpleNamespace(payload={})

    voice.messages._client.commands.send_raw_data.side_effect = reply
    await voice.download(PEER, meta)
    assert len(attempts) == 2 and attempts[0] != attempts[1]
    assert attempts[0][5] == 2 and attempts[1][5] == 3
    assert voice.jobs[PEER + ":" + meta["sid"]]["state"] == "complete"
    assert voice.clip(PEER, meta["sid"], "in")["data"] == data
    voice.messages.send_direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_partial_download_is_not_saved_as_complete(voice):
    meta = {"sid": "76543211", "mode": 1, "total": 2, "seconds": 2}
    task = asyncio.create_task(voice.download(PEER, meta))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert voice.active is None
    assert voice.jobs[PEER + ":" + meta["sid"]]["state"] == "cancelled"
    with pytest.raises(ValueError):
        voice.clip(PEER, meta["sid"], "in")
    voice.messages.send_direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_cache_can_be_opened_without_radio_commands(voice):
    from meshchatnext.src.backend.meshcore_images import library
    from meshchatnext.src.backend.meshcore_voice import play_cached

    try:
        library()
    except ValueError:
        pytest.skip("Build optional AV1 codec for native photo checks")
    draft = await voice.prepare_image(
        PEER,
        base64.b64encode(bytes([80, 120, 200]) * 1024).decode(),
        32,
        32,
        "offline-photo-check-1",
    )
    result = play_cached(voice.path.parent, OWNER, PEER, draft["sid"], "out")
    assert result["png_base64"] == draft["png_base64"]
    voice.gate.assert_not_awaited()
    voice.messages._client.commands.send_raw_data.assert_not_awaited()
