# SPDX-License-Identifier: MIT
"""Managed, opt-in MeshCore companion session, independent of Reticulum lifecycle.

The companion transport is selected explicitly. Importing
this module opens no radios and does not import RNS or the MeshCore dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, cast

from meshchatnext.src.backend.meshcore_settings import (
    RADIO_FIELDS,
    WRITABLE_FIELDS,
    SettingsApplyError,
    decode_settings,
    radio_frame,
    validate_changes,
)
from meshchatnext.src.backend.meshcore_transport import AndroidConnection


class MeshCoreSession:
    """Own a companion client and transport, serializing setup and read requests.

    Initial setup reads identity/radio information and firmware capabilities.
    It does not set time, advertise, fetch queued messages, or export secrets.
    Identity and radio settings remain on the companion until explicitly edited.
    """

    def __init__(self, *, connection_factory=AndroidConnection, client_factory=None):
        self._connection_factory = connection_factory
        self._client_factory = client_factory
        self._lock = asyncio.Lock()
        self._connection = None
        self._client = None
        self._device_info = None
        self._self_info = None
        self._last_connection_issue = None

    @property
    def is_connected(self):
        return bool(self._connection and self._connection.is_connected)

    @property
    def connection_issue(self):
        return (
            getattr(self._connection, "failure_reason", None)
            or self._last_connection_issue
        )

    async def connect(self, kind, target, *, context=None, **transport_options):
        async with self._lock:
            await self._close()
            self._last_connection_issue = None
            factory = self._client_factory
            if factory is None:
                from meshcore import MeshCore

                factory = MeshCore
            self._connection = self._connection_factory(
                kind,
                target,
                context=context,
                **transport_options,
            )
            try:
                # Reconnect is explicit for now: no invisible retries or command replays.
                self._client = factory(
                    # The SDK annotates only its built-in transports; this adapter
                    # implements the same tested reader/write/lifecycle contract.
                    cast(Any, self._connection),
                    default_timeout=8.0,
                    auto_reconnect=False,
                )
                # SDK debug/error paths can include raw packets (including keys).
                # Expose only our redacted status/diagnostic stages to app logs.
                logging.getLogger("meshcore").disabled = True
                async with asyncio.timeout(35):
                    self._self_info = self._payload(await self._client.connect())
                    self._device_info = self._payload(
                        await self._client.commands.send_device_query()
                    )
                return self.status()
            except BaseException:
                await self._close()
                raise

    @staticmethod
    def _payload(event):
        if event is None or event.is_error():
            raise ConnectionError("MeshCore companion request failed")
        if not isinstance(event.payload, dict):
            raise ConnectionError("Invalid companion response")
        return dict(event.payload)

    def status(self):
        """Small, secret-free status suitable for diagnostics and later UI use."""
        return {
            "connected": self.is_connected,
            "transport": self._connection.kind if self._connection else None,
            "device_queried": self._device_info is not None,
            "identity_read": self._self_info is not None,
        }

    async def query_device(self):
        async with self._lock:
            if not self.is_connected or self._client is None:
                raise ConnectionError("MeshCore is disconnected")
            self._device_info = self._payload(
                await self._client.commands.send_device_query()
            )
            return self.status()

    async def _read_identity(self):
        from meshchatnext.src.backend.meshcore_store import public_key

        if not self.is_connected or self._client is None:
            raise ConnectionError("MeshCore is disconnected")
        info = self._payload(await self._client.commands.send_appstart())
        self._self_info = info
        return {
            "public_key": public_key(info["public_key"]),
            "name": str(info.get("name", "")),
        }

    async def read_battery(self):
        import time

        async with self._lock:
            if not self.is_connected:
                raise ConnectionError("MeshCore is disconnected")
            payload = self._payload(await self._client.commands.get_bat())
            millivolts = payload.get("level")
            if type(millivolts) is not int or not 2500 <= millivolts <= 4500:
                return {"percent": None, "voltage_mv": None, "estimated": False}
            return {
                "percent": None,
                "voltage_mv": millivolts,
                "estimated": False,
                "read_at": time.time(),
            }

    async def read_clock(self):
        import time

        async with self._lock:
            payload = self._payload(await self._client.commands.get_time())
            value = payload.get("time")
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ConnectionError("Invalid companion clock response")
            return {
                "radio_time": value,
                "phone_time": int(time.time()),
                "offset_seconds": value - int(time.time()),
            }

    async def read_identity(self):
        async with self._lock:
            return await self._read_identity()

    async def set_name(self, name):
        if (
            not isinstance(name, str)
            or not name.strip()
            or "\x00" in name
            or len(name.encode("utf-8")) > 31
        ):
            raise ValueError("Radio name must contain 1-31 UTF-8 bytes without NUL")
        async with self._lock:
            before = await self._read_identity()
            if before["name"] == name:
                return before
            self._payload(await self._client.commands.set_name(name))
            after = await self._read_identity()
            if after != {**before, "name": name}:
                raise ConnectionError("Identity name update could not be verified")
            return after

    async def backup_identity(self, password, *, expected_public_key):
        from meshcore import EventType

        from meshchatnext.src.backend.meshcore_identity import _password, encrypt_backup

        _password(password)
        async with self._lock:
            before = await self._read_identity()
            if before["public_key"] != expected_public_key:
                raise ValueError("Selected identity changed; refresh before backup")
            event = await self._client.commands.export_private_key()
            if event is not None and event.type == EventType.DISABLED:
                raise PermissionError("This firmware disables private-key export")
            private = self._payload(event).get("private_key")
            backup = await asyncio.to_thread(
                encrypt_backup, private, before["public_key"], password
            )
            if await self._read_identity() != before:
                raise ConnectionError("Selected identity changed during backup")
            return backup

    async def restore_identity(self, backup, password, *, expected_current_public_key):
        from meshcore import EventType

        from meshchatnext.src.backend.meshcore_identity import decrypt_backup

        owner, private = await asyncio.to_thread(decrypt_backup, backup, password)
        async with self._lock:
            before = await self._read_identity()
            if before["public_key"] != expected_current_public_key:
                raise ValueError("Selected identity changed; refresh before restoring")
            if before["public_key"] == owner:
                return before
            event = await self._client.commands.send(
                b"\x18" + private, [EventType.OK, EventType.ERROR, EventType.DISABLED]
            )
            if event is not None and event.type == EventType.DISABLED:
                raise PermissionError("This firmware disables private-key import")
            self._payload(event)
            after = await self._read_identity()
            if after["public_key"] != owner:
                raise ConnectionError(
                    "Identity restore could not be verified; reconnect and inspect identity"
                )
            return after

    async def _read_settings(self):
        if not self.is_connected or self._client is None:
            raise ConnectionError("MeshCore is disconnected")
        self._self_info = self._payload(await self._client.commands.send_appstart())
        self._device_info = self._payload(
            await self._client.commands.send_device_query()
        )
        return decode_settings(self._self_info, self._device_info)

    async def read_settings(self):
        """Read current settings and capabilities directly from the selected radio."""
        async with self._lock:
            return await self._read_settings()

    async def read_radio2(self):
        from meshchatnext.src.backend.meshcore_radio2 import read_radio2

        async with self._lock:
            return await read_radio2(self)

    async def apply_radio2(self, **changes):
        from meshchatnext.src.backend.meshcore_radio2 import apply_radio2

        async with self._lock:
            return await apply_radio2(self, **changes)

    async def apply_settings(self, **changes):
        """Validate all fields first, preserve unrelated radio fields, then verify each write.

        Updates span multiple firmware commands and are not atomic. On failure,
        SettingsApplyError reports verified fields and best-effort live readback;
        writes are neither retried nor silently rolled back.
        """
        async with self._lock:
            current = await self._read_settings()
            requested = validate_changes(changes, current["max_tx_power_dbm"])
            if "path_hash_bytes" in requested and not current["path_hash_supported"]:
                raise ValueError(
                    "This firmware does not expose the default path hash size"
                )
            target = {**current, **requested}
            operations = []
            if any(
                name in requested and requested[name] != current[name]
                for name in RADIO_FIELDS
            ):
                # Construct in preflight, before any write, including repeat preservation.
                operations.append(
                    (radio_frame(target), (*RADIO_FIELDS, "client_repeat"))
                )
            if (
                "tx_power_dbm" in requested
                and requested["tx_power_dbm"] != current["tx_power_dbm"]
            ):
                operations.append(
                    (
                        b"\x0c"
                        + requested["tx_power_dbm"].to_bytes(4, "little", signed=True),
                        ("tx_power_dbm",),
                    )
                )
            if (
                "path_hash_bytes" in requested
                and requested["path_hash_bytes"] != current["path_hash_bytes"]
            ):
                operations.append(
                    (
                        bytes((0x3D, 0, requested["path_hash_bytes"] - 1)),
                        ("path_hash_bytes",),
                    )
                )
            verified = []
            for frame, fields in operations:
                try:
                    from meshcore import EventType

                    self._payload(
                        await self._client.commands.send(
                            frame, [EventType.OK, EventType.ERROR]
                        )
                    )
                    current = await self._read_settings()
                    if any(current[name] != target[name] for name in fields):
                        raise ConnectionError("Settings readback mismatch")
                    verified.extend(fields)
                except BaseException as error:
                    self._self_info = self._device_info = None
                    if not isinstance(error, Exception):
                        raise
                    readback = None
                    with contextlib.suppress(Exception):
                        readback = await self._read_settings()
                    raise SettingsApplyError(fields, verified, readback) from error
            return current

    async def _close(self):
        self._last_connection_issue = self.connection_issue
        client, connection = self._client, self._connection
        self._client = None
        self._connection = None
        self._device_info = None
        self._self_info = None
        try:
            if client is not None:
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(10):
                        await client.disconnect()
        finally:
            # Upstream manager may already mark itself disconnected after link loss;
            # close our native transport regardless, so no GATT/USB resource survives.
            if connection is not None:
                await connection.disconnect()

    async def disconnect(self):
        async with self._lock:
            await self._close()


async def probe_managed_session(kind, target, *, context=None):
    """Read-only integration check using the real optional protocol library.

    Repeats setup/query/close through a new client and GATT/USB session, including
    an unexpected transport closure between them. Never fetches private keys or
    messages and never changes companion settings or transmits LoRa packets.
    """
    session = MeshCoreSession()
    try:
        first = await session.connect(kind, target, context=context)
        if not first["connected"] or not first["device_queried"]:
            raise ConnectionError("Initial MeshCore protocol setup failed")
        await session.query_device()
        # Simulate transport loss without resetting the shared Bluetooth adapter.
        await session._connection.disconnect()
        if session.is_connected:
            raise ConnectionError("Transport loss did not update connection state")
        try:
            await session.query_device()
        except ConnectionError:
            pass
        else:
            raise ConnectionError("Disconnected session accepted a device query")
        await session.disconnect()
        second = await session.connect(kind, target, context=context)
        if not second["connected"] or not second["identity_read"]:
            raise ConnectionError("MeshCore protocol reconnect failed")
        await session.query_device()
    finally:
        await session.disconnect()
    if session.is_connected:
        raise ConnectionError("MeshCore session leaked its connection")
    return {"protocol": "ok", "reconnect": "ok", "cleanup": "ok"}


async def probe_radio_settings(kind, target, *, context):
    """Opt-in hardware write test. Persist baseline first and restore it in finally.

    A recovery snapshot remains in the test app's private files if restoration
    cannot be verified. It contains only radio settings, not identity secrets.
    """
    import json
    from pathlib import Path

    session = MeshCoreSession()
    baseline = None
    recovery = Path(str(context.getFilesDir())) / "meshcore-settings-restore.json"
    # Never overwrite an unresolved recovery snapshot from an earlier failed test.
    if await asyncio.to_thread(recovery.exists):
        raise RuntimeError("An unresolved radio settings recovery snapshot exists")
    try:
        await session.connect(kind, target, context=context)
        baseline = await session.read_settings()
        await asyncio.to_thread(recovery.write_text, json.dumps(baseline, indent=2))
        changes = {
            "frequency_mhz": round(
                baseline["frequency_mhz"]
                + (0.025 if baseline["frequency_mhz"] < 2499 else -0.025),
                3,
            ),
            "bandwidth_khz": 125 if baseline["bandwidth_khz"] != 125 else 250,
            "sf": baseline["sf"] - 1 if baseline["sf"] > 5 else 6,
            "cr": 6 if baseline["cr"] == 5 else 5,
            "tx_power_dbm": baseline["tx_power_dbm"] - 1
            if baseline["tx_power_dbm"] > -9
            else -8,
        }
        await session.apply_settings(**changes)
        if baseline["path_hash_supported"]:
            for size in (1, 2, 3):
                await session.apply_settings(path_hash_bytes=size)
    finally:
        try:
            if baseline is not None and await asyncio.to_thread(recovery.exists):
                original = {
                    name: baseline[name]
                    for name in WRITABLE_FIELDS
                    if baseline.get(name) is not None
                }
                await session.apply_settings(**original)
                final = await session.read_settings()
                if final != baseline:
                    raise ConnectionError(
                        "Original radio settings could not be verified; recovery snapshot retained"
                    )
                await asyncio.to_thread(recovery.unlink)
        finally:
            await session.disconnect()
    return {
        "settings": "ok",
        "restored": "ok",
        "path_hash_supported": baseline["path_hash_supported"],
    }
