# SPDX-License-Identifier: MIT
"""Bounded MediaMesh VE3 Codec2 clips. Raw radio audio is unencrypted.

Wire interoperability follows jade-on-mesh/meshcore-open-tak docs/vox-voice.md.
No live telephone calls, automatic downloads, or primary-radio fallback.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import math
import re
import secrets
import sqlite3
import time
import wave
from pathlib import Path

from meshchatnext.src.backend.meshcore_store import public_key

MODES = {
    0: (700, 4, 320),
    1: (1200, 6, 320),
    2: (2400, 6, 160),
    3: (1300, 7, 320),
    4: (1400, 7, 320),
    5: (1600, 8, 320),
    6: (3200, 8, 160),
}


class VoiceCapabilityError(ValueError):
    """Only fixed, non-sensitive guidance may be placed in this exception."""


def play_cached(folder, owner, peer, sid, direction):
    owner, peer = public_key(owner), public_key(peer)
    if direction not in ("in", "out"):
        raise ValueError("Invalid clip direction")
    path = Path(folder) / "voice.sqlite"
    if not path.exists():
        raise ValueError("Voice clip is not cached")
    db = sqlite3.connect(path)
    try:
        row = db.execute(
            "SELECT data,mode FROM clips WHERE owner=? AND peer=? AND sid=? AND direction=?",
            (owner, peer, sid, direction),
        ).fetchone()
        if row is None:
            raise ValueError("Voice clip is not cached")
        return media_preview(row[0], row[1])
    finally:
        db.close()


def b36(n):
    result = ""
    while n:
        n, digit = divmod(n, 36)
        result = "0123456789abcdefghijklmnopqrstuvwxyz"[digit] + result
    return result or "0"


def envelope(text):
    if not isinstance(text, str) or len(text) > 160:
        raise ValueError("Unsupported media envelope")
    fields = text.split(" ", 1)[0]
    if not re.fullmatch(
        r"(?:VE3|VI1):[0-9a-z]{1,7}:[0-9a-z]{1,2}:[0-9a-z]{1,2}:[0-9a-z]{1,2}", fields
    ):
        raise ValueError("Unsupported media envelope")
    sid, mode, total, seconds = [int(x, 36) for x in fields.split(":")[1:]]
    image = fields.startswith("VI1:")
    if (
        not 0 < sid <= 0xFFFFFFFF
        or not 1 <= total <= 64
        or (image and (mode != 40 or not 1 <= seconds <= 600))
        or (not image and (mode not in MODES or not 1 <= seconds <= 20))
    ):
        raise ValueError("Unsupported media clip")
    return {"sid": f"{sid:08x}", "mode": mode, "total": total, "seconds": seconds}


def media_preview(data, mode):
    if mode == 40:
        from meshchatnext.src.backend.meshcore_images import decode_image

        return decode_image(data)
    return {"wav_base64": decode(data, mode)}


def frame_size(mode):
    return 1 if mode == 40 else MODES[mode][1]


def encode(pcm):
    import numpy as np
    import pycodec2

    if not isinstance(pcm, bytes) or not 1600 <= len(pcm) <= 320000 or len(pcm) % 2:
        raise ValueError("Record between 0.1 and 20 seconds of 8 kHz mono PCM")
    codec = pycodec2.Codec2(1200)
    samples = np.frombuffer(pcm, dtype="<i2")
    step = codec.samples_per_frame()
    blocks = [
        codec.encode(
            np.pad(
                samples[i : i + step], (0, max(0, step - len(samples[i : i + step])))
            )
        )
        for i in range(0, len(samples), step)
    ]
    return b"".join(blocks), max(1, math.ceil(len(samples) / 8000))


def decode(data, mode):
    import pycodec2

    rate, size, _ = MODES[mode]
    if not data or len(data) % size or len(data) > 16000:
        raise ValueError("Invalid encoded voice data")
    codec = pycodec2.Codec2(rate)
    pcm = b"".join(
        codec.decode(data[i : i + size]).astype("<i2").tobytes()
        for i in range(0, len(data), size)
    )
    if len(pcm) > 326400:
        raise ValueError("Voice clip exceeds 20 seconds")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(pcm)
    return base64.b64encode(output.getvalue()).decode()


class MeshCoreVoice:
    def __init__(self, messages, folder):
        self.messages = messages
        self.session = messages.session
        self.owner = messages.owner
        self.path = Path(folder) / "voice.sqlite"
        self.queue = asyncio.Queue(maxsize=8)
        self.jobs = {}
        self.channel_scopes = {}
        self.active = None
        self.active_channel = None
        self.last_served = {}
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS clips(owner TEXT,peer TEXT,sid TEXT,mode INTEGER,total INTEGER,seconds INTEGER,direction TEXT,data BLOB,announced INTEGER DEFAULT 0,created REAL,request_id TEXT,PRIMARY KEY(owner,peer,sid,direction),UNIQUE(owner,request_id))"
            )
            db.execute(
                "DELETE FROM clips WHERE created < ?", (time.time() - 7 * 86400,)
            )
            db.execute(
                "DELETE FROM clips WHERE rowid NOT IN (SELECT rowid FROM clips WHERE owner=? ORDER BY created DESC LIMIT 100) AND owner=?",
                (self.owner, self.owner),
            )
        self.subscription = messages._client.subscribe(
            messages._types.RAW_DATA, self.received
        )
        self.worker = asyncio.create_task(self.serve_loop())
        self.fetch_task = None

    def db(self):
        # Context manager closes connections as well as committing transactions.
        @contextlib.contextmanager
        def connection():
            db = sqlite3.connect(self.path)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

        return connection()

    def clip(self, peer, sid, direction):
        peer = public_key(peer)
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM clips WHERE owner=? AND peer=? AND sid=? AND direction=?",
                (self.owner, peer, sid, direction),
            ).fetchone()
        if row is None:
            raise ValueError("Voice clip is not cached on this device")
        return dict(row)

    async def prepare(self, peer, pcm_base64, request_id):
        peer = public_key(peer)
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9-]{16,64}", request_id
        ):
            raise ValueError("Invalid recording request")
        if not isinstance(pcm_base64, str) or len(pcm_base64) > 426668:
            raise ValueError("Recording is too large")
        try:
            pcm = base64.b64decode(pcm_base64, validate=True)
        except Exception:
            raise ValueError("Invalid recording") from None
        with self.db() as db:
            previous = db.execute(
                "SELECT * FROM clips WHERE owner=? AND request_id=?",
                (self.owner, request_id),
            ).fetchone()
            if previous:
                if previous["peer"] != peer:
                    raise ValueError("Recording belongs to another contact")
                return {
                    **{k: previous[k] for k in ("sid", "seconds", "total")},
                    "wav_base64": await asyncio.to_thread(
                        decode, previous["data"], previous["mode"]
                    ),
                }
        data, seconds = await asyncio.to_thread(encode, pcm)
        sid = f"{secrets.randbelow(0xFFFFFFFF) + 1:08x}"
        total = math.ceil(len(data) / 156)
        with self.db() as db:
            count = db.execute(
                "SELECT count(*) FROM clips WHERE owner=?", (self.owner,)
            ).fetchone()[0]
            if count >= 100:
                db.execute(
                    "DELETE FROM clips WHERE rowid IN (SELECT rowid FROM clips WHERE owner=? ORDER BY created ASC LIMIT ?)",
                    (self.owner, count - 99),
                )
            db.execute(
                "INSERT INTO clips VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self.owner,
                    peer,
                    sid,
                    1,
                    total,
                    seconds,
                    "out",
                    data,
                    0,
                    time.time(),
                    request_id,
                ),
            )
        return {
            "sid": sid,
            "seconds": seconds,
            "total": total,
            "wav_base64": await asyncio.to_thread(decode, data, 1),
        }

    async def prepare_image(self, peer, rgb_base64, width, height, request_id):
        from meshchatnext.src.backend.meshcore_images import encode_image

        peer = public_key(peer)
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9-]{16,64}", request_id
        ):
            raise ValueError("Invalid photo request")
        with self.db() as db:
            old = db.execute(
                "SELECT * FROM clips WHERE owner=? AND request_id=?",
                (self.owner, request_id),
            ).fetchone()
        if old:
            if old["peer"] != peer or old["mode"] != 40:
                raise ValueError("Photo request belongs to another destination")
            return {
                "sid": old["sid"],
                "total": old["total"],
                "seconds": old["seconds"],
                **await asyncio.to_thread(media_preview, old["data"], 40),
            }
        data, aspect, preview = await asyncio.to_thread(
            encode_image, rgb_base64, width, height
        )
        sid = f"{secrets.randbelow(0xFFFFFFFF) + 1:08x}"
        total = math.ceil(len(data) / 156)
        with self.db() as db:
            db.execute(
                "INSERT INTO clips VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self.owner,
                    peer,
                    sid,
                    40,
                    total,
                    aspect,
                    "out",
                    data,
                    0,
                    time.time(),
                    request_id,
                ),
            )
            db.execute(
                "DELETE FROM clips WHERE owner=? AND rowid NOT IN (SELECT rowid FROM clips WHERE owner=? ORDER BY created DESC LIMIT 100)",
                (self.owner, self.owner),
            )
        return {"sid": sid, "total": total, "seconds": aspect, **preview}

    async def gate(self):
        from meshchatnext.src.backend.meshcore_radio2 import read_radio2

        info = await read_radio2(self.session)
        if (
            not info.get("supported")
            or not info.get("enabled")
            or info.get("mode") != "rxtx"
            or info.get("crossing") is not False
            or info.get("media_policy") != "radio2"
            or info.get("timing_pending")
        ):
            raise VoiceCapabilityError(
                "Enable Radio2 with the MediaMesh preset and crossing off before using voice clips"
            )

    async def send(self, peer, sid, request_id):
        row = self.clip(peer, sid, "out")
        async with self.session._lock:
            self.messages._check()
            await self.gate()
        text = ("VI1:" if row["mode"] == 40 else "VE3:") + ":".join(
            b36(n) for n in (int(sid, 16), row["mode"], row["total"], row["seconds"])
        )
        with self.db() as db:
            db.execute(
                "UPDATE clips SET announced=1 WHERE owner=? AND peer=? AND sid=? AND direction='out'",
                (self.owner, peer, sid),
            )
        return await self.messages.send_direct(peer, text, request_id=request_id)

    async def play(self, peer, sid, direction):
        if direction not in ("in", "out"):
            raise ValueError("Invalid clip direction")
        row = self.clip(peer, sid, direction)
        return await asyncio.to_thread(media_preview, row["data"], row["mode"])

    async def discard(self, peer, sid):
        public_key(peer)
        with self.db() as db:
            db.execute(
                "DELETE FROM clips WHERE owner=? AND peer=? AND sid=? AND direction='out' AND announced=0",
                (self.owner, peer, sid),
            )
        return {"state": "removed"}

    def route(self, peer):
        contact = self.messages._client.contacts.get(peer, {})
        hops = contact.get("out_path_len", -1)
        if type(hops) is not int or hops < 0:
            raise VoiceCapabilityError(
                "Voice clips need a known direct route; exchange a text message first"
            )
        if hops and contact.get("out_path_hash_mode", 0) != 0:
            raise VoiceCapabilityError(
                "This MediaMesh raw transport supports one-byte route hashes; the radio settings have not been changed"
            )
        path = bytes.fromhex(contact.get("out_path") or "")
        if hops > 8 or len(path) != hops:
            raise VoiceCapabilityError("Unsupported MediaMesh voice route")
        return path

    async def fetch(self, peer, message_id):
        peer = public_key(peer)
        history = await asyncio.to_thread(
            self.messages.store.history, self.owner, peer, 1000
        )
        row = next(
            (
                r
                for r in history
                if str(r["id"]) == str(message_id) and r["direction"] == "in"
            ),
            None,
        )
        if row is None:
            raise ValueError("Incoming voice message not found")
        meta = envelope(row["text"])
        return await self.fetch_reference(peer, meta)

    async def fetch_reference(self, peer, meta):
        """Fetch only after the caller validates a stored DM or tactical reference."""
        peer = public_key(peer)
        if (
            meta.get("mode") != 40 and meta.get("mode") not in MODES
        ) or not 1 <= meta.get("seconds", 0) <= (600 if meta.get("mode") == 40 else 20):
            raise ValueError("This attachment format is not supported")
        try:
            self.clip(peer, meta["sid"], "in")
            return {"state": "complete"}
        except ValueError:
            pass
        if self.fetch_task and not self.fetch_task.done():
            raise ValueError("Wait for the current voice download")
        async with self.session._lock:
            self.messages._check()
            await self.gate()
            self.route(peer)
        self.fetch_task = asyncio.create_task(self.download(peer, meta))
        return {"state": "downloading"}

    async def download(self, peer, meta, channel=None):
        sid = meta["sid"]
        frames = {}
        key = ("channel:" if channel else "") + peer + ":" + sid
        state = {"state": "downloading", "received": 0, "total": meta["total"]}
        self.jobs[key] = state
        if len(self.jobs) > 100:
            self.jobs.pop(next(iter(self.jobs)))
        self.active = (sid, meta, frames)
        self.active_channel = channel
        try:
            for attempt in range(4):
                missing = [i for i in range(meta["total"]) if i not in frames]
                if not missing:
                    break
                # Duplicate an index to vary retried requests and avoid seen-hash suppression.
                indices = missing + ([missing[0]] * attempt)
                payload = (
                    b"r"
                    + bytes.fromhex(sid)
                    + bytes([2 | (1 if attempt else 0)])
                    + bytes.fromhex(self.owner[:12])
                    + bytes([len(indices)])
                    + bytes(indices)
                )
                async with self.session._lock:
                    self.messages._check()
                    await self.gate()
                    if channel:
                        await self.channel_packet(channel, payload)
                    else:
                        self.session._payload(
                            await self.messages._client.commands.send_raw_data(
                                payload, path=self.route(peer)
                            )
                        )
                deadline = time.monotonic() + max(5, len(missing) * 0.5 + 3)
                while time.monotonic() < deadline and len(frames) < meta["total"]:
                    await asyncio.sleep(0.2)
                    state["received"] = len(frames)
            if len(frames) != meta["total"]:
                raise ConnectionError(
                    "Voice download incomplete; retry to request this clip again"
                )
            data = b"".join(frames[i] for i in range(meta["total"]))
            await asyncio.to_thread(media_preview, data, meta["mode"])
            with self.db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO clips VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                    (
                        self.owner,
                        peer,
                        sid,
                        meta["mode"],
                        meta["total"],
                        meta["seconds"],
                        "in",
                        data,
                        1,
                        time.time(),
                    ),
                )
                db.execute(
                    "DELETE FROM clips WHERE owner=? AND rowid NOT IN (SELECT rowid FROM clips WHERE owner=? ORDER BY created DESC LIMIT 100)",
                    (self.owner, self.owner),
                )
            state["state"] = "complete"
        except asyncio.CancelledError:
            state["state"] = "cancelled"
            raise
        except Exception:
            state.update(
                state="failed",
                error="Voice clip was not fully received. Check Radio2 and the route, then retry.",
            )
        finally:
            self.active = None
            self.active_channel = None

    def received(self, event, channel=None):
        raw = event.payload.get("payload") if isinstance(event.payload, dict) else None
        if not isinstance(raw, str) or len(raw) > 512:
            return
        try:
            data = bytes.fromhex(raw)
        except ValueError:
            return
        if len(data) < 6 or (
            channel != self.active_channel and data[0] in (0x56, 0x57)
        ):
            return
        sid = data[1:5].hex()
        if data[0] in (0x56, 0x57) and self.active and self.active[0] == sid:
            _, meta, frames = self.active
            index = data[5]
            block = data[6:-1] if data[0] == 0x57 else data[6:]
            size = frame_size(meta["mode"])
            if (
                index < meta["total"]
                and block
                and len(block) <= 156
                and len(block) % size == 0
            ):
                frames.setdefault(index, block)
        elif data[0] == 0x72 and len(data) >= 13:
            count = data[12]
            if count > 80 or len(data) < 13 + count or data[5] & ~7:
                return
            if channel:
                if data[6:12].hex() != self.owner[:12]:
                    indices = list(dict.fromkeys(data[13 : 13 + count]))
                    self.enqueue(
                        "channel:" + channel,
                        sid,
                        indices if data[5] & 1 else None,
                        bool(data[5] & 2),
                    )
                return
            prefix = data[6:12].hex()
            peers = [k for k in self.messages._client.contacts if k.startswith(prefix)]
            if len(peers) != 1:
                return
            indices = list(dict.fromkeys(data[13 : 13 + count]))
            self.enqueue(
                peers[0], sid, indices if data[5] & 1 else None, bool(data[5] & 2)
            )

    def hidden_request(self, payload):
        text = payload.get("text", "")
        match = (
            re.fullmatch(
                r"VR3:([0-9a-z]{1,7}):(a|m[0-9a-z.\-]{1,180}):([0-9a-f]{12})", text
            )
            if isinstance(text, str)
            else None
        )
        if not match:
            return False
        prefix = payload.get("pubkey_prefix", "")
        if not isinstance(prefix, str) or prefix.lower() != match[3]:
            return False
        peers = [
            k for k in self.messages._client.contacts if k.startswith(prefix.lower())
        ]
        if len(peers) != 1:
            return False
        sid = f"{int(match[1], 36):08x}"
        # All-frame requests are enough for initial interoperability; raw retry
        # requests provide the bounded missing-index mechanism.
        indices = None
        if match[2] != "a":
            indices = []
            for segment in match[2][1:].split("."):
                bounds = segment.split("-")
                if len(bounds) > 2 or not all(bounds):
                    return False
                start, end = int(bounds[0], 36), int(bounds[-1], 36)
                if not 0 <= start <= end < 64:
                    return False
                indices.extend(range(start, end + 1))
                if len(indices) > 64:
                    return False
        self.enqueue(peers[0], sid, indices, False)
        return True

    def enqueue(self, peer, sid, indices, salted):
        try:
            self.queue.put_nowait((peer, sid, indices, salted))
        except asyncio.QueueFull:
            pass

    async def serve_loop(self):
        while True:
            peer, sid, indices, salted = await self.queue.get()
            try:
                channel = peer[8:] if peer.startswith("channel:") else None
                try:
                    row = self.clip(channel or peer, sid, "out")
                    if channel and row["announced"] != 3:
                        continue
                except ValueError:
                    if channel:
                        continue
                    row = self.clip(self.owner, sid, "out")
                    if row["announced"] != 2:
                        continue
                if not row["announced"]:
                    continue
                key = (peer, sid)
                now = time.monotonic()
                if now - self.last_served.get(key, -100) < 2:
                    continue
                self.last_served[key] = now
                if len(self.last_served) > 100:
                    self.last_served.pop(next(iter(self.last_served)))
                size = frame_size(row["mode"])
                chunk = 156 // size * size
                blocks = [
                    row["data"][i : i + chunk]
                    for i in range(0, len(row["data"]), chunk)
                ]
                indices = range(len(blocks)) if indices is None else indices
                async with self.session._lock:
                    self.messages._check()
                    await self.gate()
                    path = None if channel else self.route(peer)
                    for index in indices:
                        if index >= len(blocks):
                            continue
                        packet = (
                            bytes([0x57 if salted else 0x56])
                            + bytes.fromhex(sid)
                            + bytes([index])
                            + blocks[index]
                        )
                        if salted:
                            packet += secrets.token_bytes(1)
                        if channel:
                            await self.channel_packet(channel, packet)
                        else:
                            self.session._payload(
                                await self.messages._client.commands.send_raw_data(
                                    packet, path=path
                                )
                            )
                        await asyncio.sleep(0.4)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # Never expose packet contents, audio, or secrets in logs.

    async def channel_packet(self, channel, payload):
        # Caller holds the shared session lock. Every packet revalidates its slot/key.
        from meshchatnext.src.backend.meshcore_tools import channel_scope

        channels = self.messages.channels
        rows = await asyncio.to_thread(self.messages.store.channel_ui, self.owner)
        row = next((r for r in rows if r["channel_id"] == channel), None)
        if not row:
            raise ValueError("Media channel changed")
        live, _ = await channels._read(row["slot"])
        if live["channel_id"] != channel:
            raise ValueError("Media channel changed")
        scope = await asyncio.to_thread(
            self.messages.store.channel_scope, self.owner, channel
        )
        expected = self.channel_scopes.get(channel, scope)
        if scope != expected:
            raise ValueError("Channel scope changed; restart the attachment transfer")
        async with channel_scope(self.session, scope):
            self.session._payload(
                await self.messages._client.commands.send_channel_data(
                    row["slot"], 0x5643, payload
                )
            )

    async def send_channel(self, channel_id, sid, request_id, expected_scope):
        channel_id = public_key(channel_id)
        row = self.clip(channel_id, sid, "out")
        async with self.session._lock:
            self.messages._check()
            await self.gate()
            scope = await asyncio.to_thread(
                self.messages.store.channel_scope, self.owner, channel_id
            )
            if scope != expected_scope:
                raise ValueError("Channel scope changed; review before sending")
        rows = await asyncio.to_thread(self.messages.store.channel_ui, self.owner)
        channel = next((r for r in rows if r["channel_id"] == channel_id), None)
        if not channel:
            raise ValueError("Media channel changed")
        text = ("VI1:" if row["mode"] == 40 else "VE3:") + ":".join(
            b36(n) for n in (int(sid, 16), row["mode"], row["total"], row["seconds"])
        )
        self.channel_scopes[channel_id] = scope
        with self.db() as db:
            db.execute(
                "UPDATE clips SET announced=3 WHERE owner=? AND peer=? AND sid=? AND direction='out'",
                (self.owner, channel_id, sid),
            )
        return await self.messages.channels.send(
            channel["slot"], text, expected_channel_id=channel_id, request_id=request_id
        )

    async def fetch_channel(self, channel_id, message_id, expected_scope):
        channel_id = public_key(channel_id)
        rows = await asyncio.to_thread(
            self.messages.store.channel_history, self.owner, channel_id, 1000
        )
        row = next(
            (
                r
                for r in rows
                if str(r["id"]) == str(message_id) and r["direction"] == "in"
            ),
            None,
        )
        if not row:
            raise ValueError("Incoming channel attachment not found")
        text = row["text"].partition(": ")[2]
        meta = envelope(text)
        if self.fetch_task and not self.fetch_task.done():
            raise ValueError("Wait for the current attachment download")
        async with self.session._lock:
            self.messages._check()
            await self.gate()
            scope = await asyncio.to_thread(
                self.messages.store.channel_scope, self.owner, channel_id
            )
            if scope != expected_scope:
                raise ValueError("Channel scope changed; refresh before downloading")
            self.channel_scopes[channel_id] = scope
        self.fetch_task = asyncio.create_task(
            self.download(channel_id, meta, channel_id)
        )
        return {"state": "downloading"}

    async def receive_channel(self, payload):
        if payload.get("data_type") != 0x5643:
            return False
        rows = await asyncio.to_thread(self.messages.store.channel_ui, self.owner)
        row = next((r for r in rows if r["slot"] == payload.get("channel_idx")), None)
        if row:
            from types import SimpleNamespace

            self.received(SimpleNamespace(payload=payload), row["channel_id"])
        return True  # Control packets never become chat, unread counts or alerts.

    async def close(self):
        self.subscription.unsubscribe()
        tasks = [self.worker] + ([self.fetch_task] if self.fetch_task else [])
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
