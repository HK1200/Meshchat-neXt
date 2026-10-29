# SPDX-License-Identifier: MIT
"""Explicit Linux and Windows companion connections. No radio is opened by importing this module."""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import re
import stat
import sys

UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"


def _factory(kind, target, *, baud, dtr, rts):
    if kind == "usb":
        if sys.platform == "win32":
            if target not in {row["path"] for row in attached_devices()}:
                raise ValueError("Selected serial device is no longer attached")
        elif not stat.S_ISCHR(os.stat(target).st_mode):
            raise ValueError("Select a serial device")
        from meshcore.serial_cx import SerialConnection

        return SerialConnection(target, baud, dtr=dtr, rts=rts)
    from meshcore.ble_cx import BLEConnection

    return BLEConnection(address=target)


class DesktopConnection:
    """Own one selected USB/BLE connection; never reset an adapter or replay writes."""

    def __init__(
        self,
        kind,
        target,
        *,
        timeout=20.0,
        baud=115200,
        dtr=True,
        rts=False,
        port_index=0,
        context=None,
        native_factory=None,
    ):
        if kind not in ("usb", "ble"):
            raise ValueError("Transport must be usb or ble")
        if (
            not isinstance(target, str)
            or not target.strip()
            or "\0" in target
            or len(target) > 256
        ):
            raise ValueError("Select an explicit serial device or Bluetooth address")
        target = target.strip()
        if kind == "usb":
            if sys.platform == "win32":
                if (
                    not re.fullmatch(r"COM[1-9][0-9]{0,4}", target, re.IGNORECASE)
                    or int(target[3:]) > 65535
                ):
                    raise ValueError("Select a Windows COM serial device")
                target = target.upper()
            elif not target.startswith("/dev/") or not os.path.isabs(target):
                raise ValueError("Select a Linux serial device under /dev")
        if kind == "ble" and not re.fullmatch(
            r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", target
        ):
            raise ValueError("Select a Bluetooth device address")
        if not math.isfinite(timeout) or timeout <= 0 or baud <= 0 or port_index != 0:
            raise ValueError("Invalid connection parameters")
        self.kind, self.target, self.timeout = kind, target, timeout
        self._options = {"baud": baud, "dtr": dtr, "rts": rts}
        self._factory = native_factory or _factory
        self._native = None
        self._reader = None
        self._callback = None
        self._connected = False
        self._failed = None
        self._lifecycle = asyncio.Lock()
        self._write = asyncio.Lock()
        self.failure_reason = None

    @property
    def is_connected(self):
        return self._connected

    def set_reader(self, reader):
        self._reader = reader

    def set_disconnect_callback(self, callback):
        self._callback = callback

    def _reader_for(self, native):
        connection = self

        class Reader:
            async def handle_rx(self, data):
                if connection._native is native and connection._reader is not None:
                    await connection._reader.handle_rx(data)

        return Reader()

    async def _lost(self, native):
        if self._native is not native or self._failed is native:
            return
        self._failed = native
        self._connected = False
        self.failure_reason = "MeshCore radio connection lost"
        if self._callback is not None:
            with contextlib.suppress(Exception):
                await self._callback(self.failure_reason)

    async def _close(self):
        native, self._native = self._native, None
        self._connected = False
        if native is not None:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(3):
                    await native.disconnect()

    async def connect(self):
        async with self._lifecycle:
            if self._connected:
                return self.target
            await self._close()
            self.failure_reason = None
            try:
                native = self._factory(self.kind, self.target, **self._options)
                self._native = native
                self._failed = None
                native.set_reader(self._reader_for(native))

                async def disconnected(*_args):
                    await self._lost(native)

                native.set_disconnect_callback(disconnected)
                async with asyncio.timeout(self.timeout):
                    result = await native.connect()
                if not result or self._failed is native:
                    raise ConnectionError("Companion connection did not open")
                self._connected = True
                return self.target
            except asyncio.CancelledError:
                await self._close()
                raise
            except Exception:
                await self._close()
                self.failure_reason = "Could not open MeshCore radio; check device access and Bluetooth settings"
                raise ConnectionError(self.failure_reason) from None

    async def send(self, data):
        data = bytes(data)
        if not 1 <= len(data) <= 300:
            raise ValueError("Invalid companion frame size")
        async with self._write:
            native = self._native
            if not self._connected or native is None:
                raise ConnectionError("MeshCore is disconnected")
            try:
                async with asyncio.timeout(self.timeout):
                    result = await native.send(data)
                if result is False or not self._connected:
                    raise ConnectionError("Companion write failed")
            except asyncio.CancelledError:
                async with self._lifecycle:
                    if self._native is native:
                        await self._close()
                raise
            except Exception:
                await self._lost(native)
                async with self._lifecycle:
                    if self._native is native:
                        await self._close()
                raise ConnectionError(
                    "MeshCore write failed; delivery is not confirmed"
                ) from None

    async def disconnect(self):
        async with self._lifecycle:
            await self._close()


def attached_devices():
    """Enumerate candidates without opening serial ports or probing radios."""
    from serial.tools.list_ports import comports

    return [
        {
            "path": p.device,
            "name": p.description or "USB serial radio",
            "vendor_id": p.vid,
            "product_id": p.pid,
            "permission": sys.platform == "win32"
            or os.access(p.device, os.R_OK | os.W_OK),
        }
        for p in sorted(comports(), key=lambda p: p.device)
    ]


def permit_device(path):
    if path not in {p["path"] for p in attached_devices()}:
        raise ValueError("Selected serial device is no longer attached")
    if sys.platform != "win32" and not os.access(path, os.R_OK | os.W_OK):
        raise ConnectionError(
            "Serial access denied; grant your Linux user access to this device and sign in again"
        )
    return {"granted": True, "requested": False}


async def discover_devices(duration=5.0, scanner=None):
    """Read advertisements only. A companion handshake is still required."""
    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("Scan duration must be between 0 and 30 seconds")
    if scanner is None:
        from bleak import BleakScanner

        scanner = BleakScanner
    try:
        async with asyncio.timeout(duration + 5):
            found = await scanner.discover(timeout=duration, return_adv=True)
    except Exception:
        raise ConnectionError(
            "Bluetooth discovery is unavailable; check the Bluetooth adapter and permissions"
        ) from None
    return [
        {
            "address": device.address,
            "name": advert.local_name or device.name or "Bluetooth device",
        }
        for device, advert in sorted(found.values(), key=lambda value: value[0].address)
        if UART_SERVICE in {u.lower() for u in (advert.service_uuids or [])}
    ]
