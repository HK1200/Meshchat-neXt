# SPDX-License-Identifier: MIT
"""Public hashtag and shared-key channels on an explicitly connected companion.

Secrets stay on the companion and in transient command buffers. Metadata and
history use SHA-256 of the full secret, never the firmware's one-byte hash.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets

PUBLIC_GROUP_KEY = base64.b64decode("izOH6cXN6mrJ5e26oRXNcg==")


def channel_name(name):
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("A channel name is required")
    if not name.startswith("#"):
        name = "#" + name
    if (
        len(name) < 2
        or any(char.isspace() for char in name)
        or len(name.encode("utf-8")) > 31
    ):
        raise ValueError(
            "Use a hashtag name of at most 31 UTF-8 bytes without whitespace"
        )
    return name


def channel_id(key):
    return hashlib.sha256(key).hexdigest()


def metadata(slot, name, key):
    empty = name == "" and key == bytes(16)
    return {
        "slot": slot,
        "name": name,
        "channel_id": None if empty else channel_id(key),
        "kind": "empty"
        if empty
        else "public"
        if key == PUBLIC_GROUP_KEY
        or (name.startswith("#") and key == hashlib.sha256(name.encode()).digest()[:16])
        else "private",
    }


class ChannelUpdateError(ConnectionError):
    """A write may have applied; inspect live state before attempting another edit."""

    def __init__(self, slot):
        super().__init__(
            "Channel update could not be verified; refresh before editing again"
        )
        self.slot = slot


class MeshCoreChannels:
    def __init__(self, messenger):
        self.messages = messenger
        self.session = messenger.session
        self.store = messenger.store

    def _check(self):
        self.messages._check()

    async def _read(self, slot):
        payload = self.session._payload(
            await self.session._client.commands.get_channel(slot)
        )
        if payload.get("channel_idx") != slot or not isinstance(
            payload.get("channel_name"), str
        ):
            raise ConnectionError("Invalid channel response")
        key = payload.get("channel_secret")
        if not isinstance(key, bytes) or len(key) != 16:
            raise ConnectionError("Unsupported channel key format")
        if hasattr(self.messages, "_channel_keys"):
            self.messages._channel_keys[slot] = key
        return metadata(slot, payload["channel_name"], key), key

    async def _refresh(self):
        self._check()
        await asyncio.to_thread(self.store.invalidate_channels, self.messages.owner)
        info = self.session._payload(
            await self.session._client.commands.send_device_query()
        )
        count = info.get("max_channels")
        if type(count) is not int or not 1 <= count <= 256:
            raise ConnectionError("Firmware does not expose a valid channel capacity")
        rows = []
        for slot in range(count):
            row, _ = await self._read(slot)
            rows.append(row)
        await asyncio.to_thread(self.store.replace_channels, self.messages.owner, rows)
        return rows

    async def refresh(self):
        async with self.session._lock:
            return await self._refresh()

    async def _write(self, slot, name, key):
        types = self.messages._types
        await asyncio.to_thread(
            self.store.invalidate_channel, self.messages.owner, slot
        )
        try:
            # Send exact bytes: upstream set_channel overrides explicit keys on
            # hashtag names, which would silently turn a private channel public.
            frame = b"\x20" + bytes((slot,)) + name.encode().ljust(32, b"\x00") + key
            self.session._payload(
                await self.session._client.commands.send(frame, [types.OK, types.ERROR])
            )
            row, actual = await self._read(slot)
            if row["name"] != name or actual != key:
                raise ConnectionError("Channel readback mismatch")
            # Packets arriving while the slot changes have no wire epoch.
            # Preserve them unbound rather than guessing which key they used.
            await self.messages._drain_pending()
            await self._refresh()
            return row
        except Exception:
            raise ChannelUpdateError(slot) from None

    async def _add(self, name, key):
        async with self.session._lock:
            rows = await self._refresh()
            identity = channel_id(key)
            matches = [row for row in rows if row["channel_id"] == identity]
            if matches:
                if len(matches) == 1 and matches[0]["name"] == name:
                    return matches[0]
                raise ValueError(
                    "This key is already configured under another name or slot"
                )
            free = next(
                (row for row in rows if row["slot"] != 0 and row["kind"] == "empty"),
                None,
            )
            if free is None:
                raise ValueError("No empty non-default channel slot is available")
            # Pop/persist existing packets while their current slot bindings are
            # still valid. This shares the same lock as the normal receiver.
            await self.messages._drain_pending()
            return await self._write(free["slot"], name, key)

    async def add_public(self, name):
        # Hashtag PSKs are case-sensitive. Canonicalize new public joins to the
        # lowercase names used by companion clients; never rewrite saved keys.
        name = channel_name(channel_name(name).lower())
        return await self._add(name, hashlib.sha256(name.encode()).digest()[:16])

    async def add_private(self, name, *, key=None):
        # Open TAK and other clients classify a leading '#' as a public hashtag
        # even if its key is random. New private channels use a plain label.
        # Imported/saved channels keep their exact existing names and keys.
        name = channel_name(name)[1:]
        key = secrets.token_bytes(16) if key is None else key
        if not isinstance(key, bytes) or len(key) != 16 or key == bytes(16):
            raise ValueError(
                "Private channel key must be exactly 16 bytes and must not be all zero"
            )
        if key in (
            PUBLIC_GROUP_KEY,
            hashlib.sha256(name.encode()).digest()[:16],
            hashlib.sha256(("#" + name).encode()).digest()[:16],
        ):
            raise ValueError(
                "A private channel requires a key distinct from its public hashtag key"
            )
        return await self._add(name, key)

    async def import_channel(self, name, key):
        """Preserve backup names/keys; keep existing channels and protected slot zero."""
        if (
            not isinstance(name, str)
            or not name.strip()
            or "\x00" in name
            or len(name.encode()) > 31
        ):
            raise ValueError("Invalid imported channel name")
        if not isinstance(key, bytes) or len(key) != 16 or key == bytes(16):
            raise ValueError("Invalid imported channel key")
        async with self.session._lock:
            rows = await self._refresh()
            identity = channel_id(key)
            existing = next(
                (row for row in rows if row["channel_id"] == identity), None
            )
            if existing:
                return False
            free = next(
                (row for row in rows if row["slot"] != 0 and row["kind"] == "empty"),
                None,
            )
            if free is None:
                raise ValueError("No empty non-default channel slot is available")
            await self.messages._drain_pending()
            await self._write(free["slot"], name, key)
            return True

    async def remove(self, slot, *, expected_channel_id):
        self._validate_slot(slot)
        if slot == 0:
            raise ValueError("The default channel slot is protected")
        async with self.session._lock:
            self._check()
            row, _ = await self._read(slot)
            if row["channel_id"] is None or row["channel_id"] != expected_channel_id:
                raise ValueError("Channel changed; refresh before removing it")
            await self.messages._drain_pending()
            return await self._write(slot, "", bytes(16))

    @staticmethod
    def _validate_slot(slot):
        if type(slot) is not int or not 0 <= slot <= 255:
            raise ValueError("Channel slot must be an integer from 0-255")

    async def export_key(self, slot, *, expected_channel_id):
        """Explicit sharing operation. Never included in metadata, history or logs."""
        self._validate_slot(slot)
        async with self.session._lock:
            self._check()
            row, key = await self._read(slot)
            if row["channel_id"] is None or row["channel_id"] != expected_channel_id:
                raise ValueError("Channel changed; refresh before sharing it")
            return key

    async def send(self, slot, text, *, expected_channel_id, request_id):
        self._validate_slot(slot)
        async with self.session._lock:
            self._check()
            row, key = await self._read(slot)
            if row["channel_id"] is None or row["channel_id"] != expected_channel_id:
                raise ValueError("Channel changed; refresh before sending")
            info = self.session._payload(
                await self.session._client.commands.send_appstart()
            )
            # Firmware prepends '<name>: ' and silently truncates to 160 bytes.
            maximum = 160 - len(info["name"].encode("utf-8")) - 2
            if (
                not isinstance(text, str)
                or not text
                or "\x00" in text
                or len(text.encode("utf-8")) > maximum
            ):
                raise ValueError(
                    f"Channel message must contain 1-{maximum} UTF-8 bytes without NUL"
                )
            saved, fresh = await asyncio.to_thread(
                self.store.prepare_channel_send,
                self.messages.owner,
                row,
                text,
                request_id,
            )
            if not fresh:
                return saved
            from meshchatnext.src.backend.meshcore_tools import channel_scope

            scope = await asyncio.to_thread(
                self.store.channel_scope, self.messages.owner, expected_channel_id
            )
            send_started = False
            try:
                async with channel_scope(self.session, scope):
                    try:
                        track = getattr(self.messages, "track_channel_repeat", None)
                        if track is not None:
                            await track(saved, key, info["name"])
                        send_started = True
                        event = await self.session._client.commands.send_chan_msg(
                            slot, text, timestamp=saved["timestamp"]
                        )
                        state = (
                            "submitted"
                            if event is not None
                            and event.type == self.messages._types.OK
                            else "rejected"
                            if event is not None
                            and event.is_error()
                            and isinstance(event.payload.get("error_code"), int)
                            else "unknown"
                        )
                        return await asyncio.to_thread(
                            self.store.channel_result,
                            self.messages.owner,
                            request_id,
                            state,
                        )
                    except BaseException:
                        await asyncio.shield(
                            asyncio.to_thread(
                                self.store.channel_result,
                                self.messages.owner,
                                request_id,
                                "unknown",
                            )
                        )
                        raise
            except BaseException:
                if not send_started:
                    await asyncio.shield(
                        asyncio.to_thread(
                            self.store.channel_result,
                            self.messages.owner,
                            request_id,
                            "rejected",
                        )
                    )
                raise

    async def history(self, identity, *, limit=100):
        self._check()
        return await asyncio.to_thread(
            self.store.channel_history, self.messages.owner, identity, limit
        )
