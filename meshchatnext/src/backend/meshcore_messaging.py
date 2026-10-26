# SPDX-License-Identifier: MIT
"""Opt-in MeshCore messaging controller. No UI or Reticulum dependencies.

Own the session until close(); callers must not reconnect it behind this
controller. All wire commands share the session lock with radio settings.
Receiving is explicit because fetching pops the companion's message queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import Counter, defaultdict, deque

from meshchatnext.src.backend.meshcore_store import public_key


class MeshCoreMessaging:
    def __init__(self, session, store, *, event_types=None):
        self.session = session
        self.store = store
        self._types = event_types
        self.owner = None
        self._client = None
        self._subscriptions = []
        self._acks = asyncio.Queue(maxsize=256)
        self._announces = {}
        self._announce_waiting = asyncio.Event()
        self._waiting = asyncio.Event()
        self._tasks = []
        self._failure = None
        self._receiving = False
        self._opened = False
        self.on_message = None
        self._repeat_tracker = None
        self._repeat_counts = Counter()
        self._repeat_waiting = asyncio.Event()
        self._repeat_lock = asyncio.Lock()
        self.rx_log = deque(maxlen=256)
        self._rx_paths = deque(maxlen=256)
        self._repeat_paths = defaultdict(list)
        self._channel_keys = {}
        self._repeat_private = None
        self._repeat_export_disabled = False

    def _check(self):
        if self._failure is not None:
            raise RuntimeError(
                "MeshCore message processing stopped; close and reconnect"
            ) from self._failure
        if (
            self.owner is None
            or self._client is not self.session._client
            or not self.session.is_connected
        ):
            raise ConnectionError("MeshCore messaging is disconnected")

    async def open(self):
        """Read identity and contacts; do not consume messages until start_receiving."""
        if self._opened:
            raise RuntimeError("Create a new controller for each connection")
        self._opened = True
        if self._types is None:
            from meshcore import EventType

            self._types = EventType
        async with self.session._lock:
            if not self.session.is_connected:
                raise ConnectionError("MeshCore is disconnected")
            self._client = self.session._client
            try:
                info = self.session._payload(
                    await self._client.commands.send_appstart()
                )
                self.owner = await asyncio.to_thread(
                    self.store.bind,
                    public_key(info["public_key"]),
                    str(info.get("name", "")),
                )
                self._subscriptions = [
                    self._client.subscribe(self._types.ACK, self._on_ack),
                    self._client.subscribe(
                        self._types.MESSAGES_WAITING, self._on_waiting
                    ),
                ]
                log_type = getattr(self._types, "RX_LOG_DATA", None)
                if log_type is not None:
                    from meshchatnext.src.backend.meshcore_repeats import RepeatTracker

                    self._repeat_tracker = RepeatTracker()
                    self._subscriptions.append(
                        self._client.subscribe(log_type, self._on_repeat)
                    )
                    self._tasks.append(asyncio.create_task(self._repeat_loop()))
                for name in ("ADVERTISEMENT", "NEW_CONTACT"):
                    kind = getattr(self._types, name, None)
                    if kind is not None:
                        self._subscriptions.append(
                            self._client.subscribe(kind, self._on_announce)
                        )
                self._tasks.append(
                    asyncio.create_task(self._guard(self._announce_loop()))
                )
                self._tasks.append(
                    asyncio.create_task(self._guard(self._receipt_loop()))
                )
                await self._sync_contacts()
            except BaseException:
                await self._stop()
                raise
        return {"public_key": self.owner, "name": str(info.get("name", ""))}

    def _on_repeat(self, event):
        payload = event.payload
        if isinstance(payload, dict):
            raw = payload.get("payload", "")
            if isinstance(raw, str) and len(raw) <= 600:
                self.rx_log.append(
                    {
                        "received": time.time(),
                        **{
                            k: payload.get(k)
                            for k in (
                                "snr",
                                "rssi",
                                "payload_type",
                                "route_type",
                                "path_len",
                                "payload_length",
                            )
                        },
                        "raw": raw,
                    }
                )
        if not isinstance(payload, dict):
            return
        raw = payload.get("payload")
        if not isinstance(raw, str) or len(raw) > 600:
            return
        try:
            from meshchatnext.src.backend.meshcore_repeats import (
                observed_fingerprint,
                packet_path,
            )

            packet = bytes.fromhex(raw)
            observation = packet_path(
                packet,
                received=time.time(),
                rssi=payload.get("rssi"),
                snr=payload.get("snr"),
            )
            if observation:
                self._rx_paths.append((observed_fingerprint(packet), observation))
            match = (
                self._repeat_tracker.observe(packet) if self._repeat_tracker else None
            )
        except (ValueError, TypeError):
            return
        if match is not None:
            if observation and len(self._repeat_paths[match]) < 32:
                self._repeat_paths[match].append(observation)
            self._repeat_counts[match] += 1
            self._repeat_waiting.set()

    async def _repeat_loop(self):
        try:
            while True:
                await self._repeat_waiting.wait()
                await asyncio.sleep(0.2)
                await self._flush_repeats()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Optional metrics must never stop message/ACK processing.
            self._repeat_tracker = None
            self._repeat_private = None
            self._repeat_counts.clear()

    async def _flush_repeats(self):
        async with self._repeat_lock:
            pending, self._repeat_counts = self._repeat_counts, Counter()
            self._repeat_waiting.clear()
            paths, self._repeat_paths = self._repeat_paths, defaultdict(list)
            for (kind, message_id), count in pending.items():
                await asyncio.to_thread(
                    self.store.repeat_observation,
                    self.owner,
                    kind,
                    message_id,
                    min(count, 10000),
                )
                if paths.get((kind, message_id)):
                    await asyncio.to_thread(
                        self.store.save_message_paths,
                        self.owner,
                        kind,
                        message_id,
                        paths[(kind, message_id)],
                    )

    async def track_channel_repeat(self, row, key, name):
        if self._repeat_tracker is None:
            return
        from meshchatnext.src.backend.meshcore_repeats import channel_packet

        await self._track_repeat(
            "channel",
            row["id"],
            channel_packet(key, name, row["timestamp"], row["text"]),
        )

    async def _track_repeat(self, kind, message_id, packet):
        try:
            await asyncio.to_thread(
                self.store.repeat_observation, self.owner, kind, message_id
            )
            self._repeat_tracker.register(kind, message_id, packet)
        except Exception:
            self._repeat_tracker = None
            self._repeat_private = None

    async def _track_direct_repeat(self, row):
        if self._repeat_tracker is None or self._repeat_export_disabled:
            return
        try:
            from meshchatnext.src.backend.meshcore_identity import derive_public
            from meshchatnext.src.backend.meshcore_repeats import direct_packet

            if self._repeat_private is None:
                event = await self._client.commands.export_private_key()
                private = (
                    event.payload.get("private_key") if event is not None else None
                )
                if not isinstance(private, bytes) or len(private) != 64:
                    self._repeat_export_disabled = True
                    return
                if derive_public(private) != self.owner:
                    self._repeat_export_disabled = True
                    return
                self._repeat_private = private
            packet = await asyncio.to_thread(
                direct_packet,
                self._repeat_private,
                self.owner,
                row["peer"],
                row["timestamp"],
                row["text"],
            )
            await self._track_repeat("direct", row["id"], packet)
        except Exception:
            self._repeat_export_disabled = True
            self._repeat_private = None

    def _on_announce(self, event):
        if self._failure is not None:
            return
        try:
            peer = public_key(event.payload.get("public_key"))
        except ValueError:
            return
        # Discovery bursts coalesce by key; message and ACK queues are independent.
        if len(self._announces) >= 4096 and peer not in self._announces:
            self._announces.pop(next(iter(self._announces)))
        self._announces[peer] = (dict(event.payload), time.time())
        self._announce_waiting.set()

    async def _announce_loop(self):
        while True:
            await self._announce_waiting.wait()
            await asyncio.sleep(0.2)
            async with self.session._lock:
                self._check()
                pending, self._announces = self._announces, {}
                self._announce_waiting.clear()
                contacts = None
                for peer, (payload, heard) in pending.items():
                    if "type" not in payload:
                        if contacts is None:
                            await self._sync_contacts()
                            contacts = self._client.contacts
                        payload = contacts.get(peer)
                    if payload is not None:
                        await asyncio.to_thread(
                            self.store.save_announce, self.owner, payload, heard
                        )
                    else:
                        await asyncio.to_thread(
                            self.store.touch_announce, self.owner, peer, heard
                        )

    def _on_ack(self, event):
        if self._failure is not None:
            return
        code = event.payload.get("code") or event.attributes.get("code")
        try:
            self._acks.put_nowait((code, time.time()))
        except asyncio.QueueFull:
            self._failure = RuntimeError("Receipt queue overflow")

    def _on_waiting(self, event):
        self._waiting.set()

    async def _guard(self, operation):
        try:
            await operation
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Do not log payloads, message text, or upstream exceptions.
            self._failure = error
            # Release close() if the receipt writer has failed. Once failed,
            # callbacks cannot enqueue further work or drain another message.
            while not self._acks.empty():
                self._acks.get_nowait()
                self._acks.task_done()

    async def _receipt_loop(self):
        while True:
            code, received = await self._acks.get()
            try:
                await asyncio.to_thread(self.store.receipt, self.owner, code, received)
            finally:
                self._acks.task_done()

    async def _sync_contacts(self):
        # Subscribe-before-write via send(), avoiding get_contacts()'s multi-event race.
        event = await self._client.commands.send(
            b"\x04", [self._types.CONTACTS, self._types.ERROR]
        )
        payload = self.session._payload(event)
        await asyncio.to_thread(self.store.replace_contacts, self.owner, payload)
        for contact in payload.values():
            if contact.get("last_advert", 0):
                await asyncio.to_thread(self.store.save_announce, self.owner, contact)
        return await asyncio.to_thread(self.store.contacts, self.owner)

    async def sync_contacts(self):
        async with self.session._lock:
            self._check()
            return await self._sync_contacts()

    async def add_contact(self, peer, name):
        peer = public_key(peer)
        if (
            not isinstance(name, str)
            or not name.strip()
            or "\x00" in name
            or len(name.encode()) > 31
        ):
            raise ValueError("Contact name must contain 1-31 UTF-8 bytes")
        async with self.session._lock:
            self._check()
            existing = await self._sync_contacts()
            if any(row["peer"] == peer for row in existing):
                return existing
            self.session._payload(
                await self._client.commands.add_contact(
                    {
                        "public_key": peer,
                        "type": 1,
                        "flags": 0,
                        "out_path": "",
                        "out_path_len": -1,
                        "out_path_hash_mode": -1,
                        "adv_name": name,
                        "last_advert": 0,
                        "adv_lat": 0,
                        "adv_lon": 0,
                    }
                )
            )
            contacts = await self._sync_contacts()
            if not any(row["peer"] == peer for row in contacts):
                raise ConnectionError("Contact addition could not be verified")
            return contacts

    async def import_contact(self, contact):
        """Merge a validated backup contact without replacing an existing entry."""
        async with self.session._lock:
            self._check()
            rows = await self._sync_contacts()
            peer = contact["public_key"]
            if any(row["peer"] == peer and row.get("active", True) for row in rows):
                return False
            self.session._payload(
                await self._client.commands.add_contact(dict(contact))
            )
            await self._sync_contacts()
            actual = self._client.contacts.get(peer)
            if not actual or any(
                actual.get(key) != contact[key]
                for key in ("public_key", "type", "flags", "adv_name", "last_advert")
            ):
                raise ConnectionError("Imported contact could not be verified")
            if any(
                type(actual.get(key)) not in (int, float)
                or abs(actual[key] - int(contact[key] * 1e6) / 1e6) > 0.000001
                for key in ("adv_lat", "adv_lon")
            ):
                raise ConnectionError("Imported contact position could not be verified")
            return True

    async def send_direct(self, peer, text, *, request_id, room=False):
        """Submit once. Reusing a request ID reads its result; it never resends."""
        async with self.session._lock:
            self._check()
            timestamp_floor = 0
            if room:
                clock = self.session._payload(
                    await self._client.commands.get_time()
                ).get("time")
                if type(clock) is not int or not 0 <= clock < 0xFFFFFFFF:
                    raise ConnectionError("Invalid companion clock for room post")
                timestamp_floor = clock + 1
            row, fresh = await asyncio.to_thread(
                self.store.prepare_send,
                self.owner,
                peer,
                text,
                request_id,
                room=room,
                timestamp_floor=timestamp_floor,
            )
            if not fresh:
                return row
            try:
                if not room:
                    await self._track_direct_repeat(row)
                event = await self._client.commands.send_msg(
                    peer, text, timestamp=row["timestamp"], attempt=0
                )
                if event is not None and event.type == self._types.MSG_SENT:
                    ack = event.payload["expected_ack"]
                    if not isinstance(ack, bytes) or len(ack) != 4:
                        raise ValueError("Invalid companion receipt token")
                    timeout = float(event.payload["suggested_timeout"]) / 1000
                    if not 0 <= timeout <= 86400:
                        raise ValueError("Invalid companion receipt timeout")
                    return await asyncio.to_thread(
                        self.store.result,
                        self.owner,
                        request_id,
                        "accepted",
                        ack.hex(),
                        max(5, timeout * 1.2),
                    )
                # Firmware numeric rejection proves no packet was accepted. A timeout
                # or local transport error cannot establish whether it transmitted.
                rejected = (
                    event is not None
                    and event.is_error()
                    and isinstance(event.payload.get("error_code"), int)
                )
                return await asyncio.to_thread(
                    self.store.result,
                    self.owner,
                    request_id,
                    "rejected" if rejected else "unknown",
                )
            except BaseException:
                await asyncio.shield(
                    asyncio.to_thread(
                        self.store.result, self.owner, request_id, "unknown"
                    )
                )
                raise

    async def start_receiving(self):
        self._check()
        if not self._receiving:
            self._receiving = True
            self._tasks.append(asyncio.create_task(self._guard(self._receive_loop())))
            self._waiting.set()

    async def _fetch_message(self):
        """Fetch and commit one packet while caller holds the shared session lock."""
        self._check()
        event = await self._client.commands.get_msg()
        payload = self.session._payload(event)
        if event.type == self._types.NO_MORE_MSGS:
            return False
        kinds = {
            self._types.CONTACT_MSG_RECV: "direct",
            self._types.CHANNEL_MSG_RECV: "channel",
            self._types.CHANNEL_DATA_RECV: "channel_data",
        }
        if event.type not in kinds:
            raise ConnectionError("Unexpected message queue response")
        # CLI responses belong to explicit administrator requests, not chat history or alerts.
        if event.type == self._types.CONTACT_MSG_RECV and payload.get("txt_type") == 1:
            return True
        voice = getattr(self, "voice", None)
        if (
            event.type == self._types.CHANNEL_DATA_RECV
            and voice
            and await voice.receive_channel(payload)
        ):
            return True
        tactical = getattr(self, "tactical", None)
        if (
            event.type == self._types.CHANNEL_DATA_RECV
            and tactical
            and await tactical.receive(payload)
        ):
            return True
        voice = getattr(self, "voice", None)
        if (
            event.type == self._types.CONTACT_MSG_RECV
            and voice
            and voice.hidden_request(payload)
        ):
            return True
        try:
            payload = await self._incoming_path(kinds[event.type], payload)
        except Exception:
            pass  # Optional route observations cannot interrupt queue delivery.
        try:
            notification = await asyncio.to_thread(
                self.store.receive, self.owner, kinds[event.type], payload
            )
        except Exception as error:
            # Manual pre-edit drains must stop after storage failures too.
            self._failure = error
            raise
        if notification is not None and self.on_message is not None:
            try:
                self.on_message(notification)
            except Exception:
                pass  # Alert failures must never interrupt durable message reception.
        return True

    async def _incoming_path(self, kind, payload):
        import hashlib

        from meshchatnext.src.backend.meshcore_repeats import (
            direct_packet,
            encrypted,
            fingerprint,
        )

        if payload.get("txt_type", 0) != 0 or not isinstance(payload.get("text"), str):
            return payload
        timestamp = payload.get("sender_timestamp")
        if type(timestamp) is not int or not 0 <= timestamp < 2**32:
            return payload
        packet = None
        if kind == "channel":
            slot = payload.get("channel_idx")
            key = self._channel_keys.get(slot)
            if key is None and getattr(self, "channels", None):
                _, key = await self.channels._read(slot)
            if key:
                packet = (
                    5,
                    hashlib.sha256(key).digest()[:1]
                    + encrypted(
                        key,
                        timestamp.to_bytes(4, "little")
                        + b"\0"
                        + payload["text"].encode(),
                    ),
                )
        elif kind == "direct" and self._repeat_private:
            prefix = payload.get("pubkey_prefix", "")
            peers = [
                p
                for p in self._client.contacts
                if len(prefix) == 12 and p.startswith(prefix)
            ]
            if len(peers) == 1:
                packet = direct_packet(
                    self._repeat_private,
                    self.owner,
                    peers[0],
                    timestamp,
                    payload["text"],
                    incoming=True,
                )
        if packet:
            key = fingerprint(*packet)
            paths = [
                entry
                for digest, entry in self._rx_paths
                if digest == key and time.time() - entry["received"] <= 120
            ][-32:]
            if paths:
                return {**payload, "observed_paths": paths}
        return payload

    async def _drain_pending(self):
        # Bounded pre-edit drain prevents old packets being assigned to a reused
        # slot. If traffic never stops, refuse the edit without changing the radio.
        for _ in range(256):
            if not await self._fetch_message():
                return
        raise RuntimeError("Message queue remains busy; channel edit was not applied")

    async def _receive_loop(self):
        while True:
            await self._waiting.wait()
            self._waiting.clear()
            for _ in range(32):
                async with self.session._lock:
                    if not await self._fetch_message():
                        break
                await asyncio.sleep(0)
            else:
                self._waiting.set()

    async def history(self, peer=None, *, limit=100):
        self._check()
        return await asyncio.to_thread(self.store.history, self.owner, peer, limit)

    def status(self):
        return {
            "connected": self.owner is not None
            and self._client is self.session._client
            and self.session.is_connected,
            "receiving": self._receiving and self._failure is None,
            "processing_failed": self._failure is not None,
        }

    async def _stop(self):
        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions.clear()
        with contextlib.suppress(Exception):
            await self._flush_repeats()
        if self._failure is None:
            await self._acks.join()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._repeat_tracker = None
        self._repeat_private = None
        self._repeat_counts.clear()
        self._rx_paths.clear()
        self._repeat_paths.clear()
        self._channel_keys.clear()
        self.owner = self._client = None
        self._receiving = False

    async def close(self):
        # Serialize with a pending send/drain so cancellation cannot pop a message
        # between its response and local commit. Drain receipt work before teardown.
        async with self.session._lock:
            await self._stop()
            await self.session._close()
