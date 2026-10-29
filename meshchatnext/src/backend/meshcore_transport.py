# SPDX-License-Identifier: MIT
"""Opt-in Android MeshCore transports; independent of RNS and its radio interfaces.

Implements meshcore_py's transport contract (connect/send/disconnect/set_reader/
set_disconnect_callback). Java is loaded lazily, so importing this module does
not start a connection or require Android or the upstream MeshCore package.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import sys

from meshchatnext.src.env_utils import env_str

MAX_FRAME = 300


def transport_platform():
    if env_str("ANDROID_ROOT"):
        return "android"
    if sys.platform == "win32":
        return "windows"
    return "linux" if sys.platform.startswith("linux") else "unsupported"


def create_connection(kind, target, *, context=None, **options):
    if context is not None or transport_platform() == "android":
        return AndroidConnection(kind, target, context=context, **options)
    if transport_platform() in ("linux", "windows"):
        from meshchatnext.src.backend.meshcore_desktop_transport import (
            DesktopConnection,
        )

        return DesktopConnection(kind, target, **options)
    raise ConnectionError("MeshCore radios are not yet supported on this platform")


class SerialFrames:
    """Incremental companion USB deframer, including console junk and split headers."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames = []
        while self.buffer:
            marker = self.buffer.find(b">")
            if marker < 0:
                self.buffer.clear()
                break
            del self.buffer[:marker]
            if len(self.buffer) < 3:
                break
            size = int.from_bytes(self.buffer[1:3], "little")
            if not 1 <= size <= MAX_FRAME:
                del self.buffer[0]
                continue
            if len(self.buffer) < size + 3:
                break
            frames.append(bytes(self.buffer[3 : size + 3]))
            del self.buffer[: size + 3]
        return frames


def _native_factory(
    kind, target, *, context=None, port_index=0, baud=115200, dtr=True, rts=False
):
    from java import jclass

    if context is None:
        from usb4a.usb import get_context

        context = get_context()
    context = context.getApplicationContext()
    if kind == "usb":
        return jclass("com.meshchatnext.meshcore.UsbSession")(
            context,
            target,
            port_index,
            baud,
            dtr,
            rts,
        )
    return jclass("com.meshchatnext.meshcore.BleSession")(context, target)


class AndroidConnection:
    """One selected radio transport. Reconnect creates a fresh native session.

    Automatic retries/handshake are the protocol client's responsibility. No
    global adapter resets, RNS imports, background auto-connect, or radio writes
    happen at construction. Callers must explicitly choose their device.
    """

    def __init__(
        self,
        kind,
        target,
        *,
        context=None,
        port_index=0,
        baud=115200,
        dtr=True,
        rts=False,
        timeout=20.0,
        native_factory=None,
    ):
        if kind not in ("usb", "ble"):
            raise ValueError("Transport must be usb or ble")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("An explicit device path or BLE address is required")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        if baud <= 0 or port_index < 0:
            raise ValueError("Invalid serial parameters")
        self.kind = kind
        self.target = target
        self.timeout = timeout
        self._options = {
            "context": context,
            "port_index": port_index,
            "baud": baud,
            "dtr": dtr,
            "rts": rts,
        }
        self._factory = native_factory or _native_factory
        self.reader = None
        self._disconnect_callback = None
        self._lifecycle = asyncio.Lock()
        self._write = asyncio.Lock()
        self._native = None
        self._pump = None
        self._ready = None
        self._written = None
        self._stopping = False
        self._connected = False
        self._notifications = set()
        self._loss_notified = False
        self.failure_reason = None

    @property
    def is_connected(self):
        return self._connected

    def set_reader(self, reader):
        self.reader = reader

    def set_disconnect_callback(self, callback):
        self._disconnect_callback = callback

    async def connect(self):
        async with self._lifecycle:
            if self._connected:
                return self.target
            await self._stop()
            self._stopping = False
            self._loss_notified = False
            self.failure_reason = None
            self._ready = asyncio.get_running_loop().create_future()
            self._native = self._factory(self.kind, self.target, **self._options)
            self._pump = asyncio.create_task(
                self._receive(), name="meshcore-android-rx"
            )
            try:
                await asyncio.to_thread(self._native.start)
                await asyncio.wait_for(asyncio.shield(self._ready), self.timeout)
            except BaseException:
                self.failure_reason = self.failure_reason or "transport_setup_failed"
                await self._stop()
                raise
            if not self._connected:
                await self._stop()
                raise ConnectionError("MeshCore disconnected during setup")
            return self.target

    async def send(self, data):
        payload = bytes(data)
        if not 1 <= len(payload) <= MAX_FRAME:
            raise ValueError("Companion payload must contain 1-300 bytes")
        async with self._write:
            if not self._connected or self._native is None:
                raise ConnectionError("MeshCore transport is disconnected")
            self._written = asyncio.get_running_loop().create_future()
            packet = (
                b"<" + len(payload).to_bytes(2, "little") + payload
                if self.kind == "usb"
                else payload
            )
            try:
                await asyncio.to_thread(self._native.send, packet)
                await asyncio.wait_for(asyncio.shield(self._written), self.timeout)
            except BaseException as error:
                # The command may already be on air. Never automatically replay a write.
                session = self._native
                self.failure_reason = self.failure_reason or "transport_write_failed"
                await self.disconnect()
                if not isinstance(error, asyncio.CancelledError):
                    self._schedule_disconnect(
                        "meshcore_write_failed", session, require_current=False
                    )
                raise
            finally:
                if self._written is not None and not self._written.done():
                    self._written.cancel()
                elif self._written is not None and not self._written.cancelled():
                    self._written.exception()
                self._written = None
        return True

    def _fail_waiters(self, reason):
        for waiter in (self._ready, self._written):
            if waiter is not None and not waiter.done():
                waiter.set_exception(ConnectionError(reason))

    async def _receive(self):
        frames = SerialFrames()
        failure = None
        try:
            while True:
                event = await asyncio.to_thread(self._native.poll, 200)
                if event is None:
                    continue
                kind = str(event.kind)
                if kind == "ready":
                    if not self._ready.done():
                        self._connected = True
                        self._ready.set_result(True)
                elif kind == "written":
                    if self._written is not None and not self._written.done():
                        self._written.set_result(True)
                elif kind == "data" and failure is None and not self._stopping:
                    # Java byte[] contains signed values through some bridge versions.
                    data = bytes(int(value) & 255 for value in event.data)
                    packets = frames.feed(data) if self.kind == "usb" else [data]
                    for packet in packets:
                        if self.reader is not None:
                            await self.reader.handle_rx(packet)
                elif kind == "error":
                    detail = str(event.detail)
                    failure = (
                        detail
                        if detail
                        in {
                            "usb_detached",
                            "usb_permission_required",
                            "device_missing",
                            "device_busy_or_unavailable",
                            "serial_port_missing",
                            "usb_open_failed",
                            "usb_read_failed",
                            "usb_write_failed",
                        }
                        else "transport_failed"
                    )
                    self.failure_reason = failure
                    self._connected = False
                    self._fail_waiters(failure)
                    await asyncio.to_thread(self._native.close)
                elif kind == "closed":
                    failure = failure or "meshcore_disconnected"
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            failure = "meshcore_receive_failed"
            await asyncio.to_thread(self._native.close)
        finally:
            if failure and not self._stopping:
                self.failure_reason = self.failure_reason or failure
            self._connected = False
            self._fail_waiters(failure or "meshcore_disconnected")
            if failure and not self._stopping and self._disconnect_callback is not None:
                self._schedule_disconnect(failure, self._native)

    def _schedule_disconnect(self, reason, session, *, require_current=True):
        if self._disconnect_callback is None:
            return
        task = asyncio.create_task(
            self._notify_disconnect(reason, session, require_current)
        )
        self._notifications.add(task)
        task.add_done_callback(self._notifications.discard)

    async def _notify_disconnect(self, reason, session, require_current):
        # Callback may reconnect; don't hold the receive task or lifecycle lock.
        if require_current and (self._stopping or self._native is not session):
            return
        if not require_current and self._native is not None:
            return
        if self._loss_notified:
            return
        self._loss_notified = True
        callback = self._disconnect_callback
        if callback is not None:
            with contextlib.suppress(Exception):
                await callback(reason)

    async def _stop(self):
        self._stopping = True
        self._connected = False
        if self._native is not None:
            await asyncio.to_thread(self._native.close)
        if self._pump is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._pump), 3)
            except TimeoutError:
                self._pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._pump
            self._pump = None
        self._native = None
        # Retrieve exceptions after teardown, including early-open failure and timeout.
        for waiter in (self._ready, self._written):
            if waiter is not None and not waiter.done():
                waiter.cancel()
            elif waiter is not None and not waiter.cancelled():
                waiter.exception()

    async def disconnect(self):
        async with self._lifecycle:
            for task in list(self._notifications):
                if task is not asyncio.current_task():
                    task.cancel()
            await self._stop()


def list_usb_devices(context):
    from java import jclass

    return [
        str(path)
        for path in jclass("com.meshchatnext.meshcore.UsbDevices").list(context)
    ]


def usb_has_permission(context, path):
    from java import jclass

    return bool(
        jclass("com.meshchatnext.meshcore.UsbDevices").hasPermission(context, path)
    )


def request_usb_permission(context, path):
    from java import jclass

    jclass("com.meshchatnext.meshcore.UsbDevices").requestPermission(context, path)


def attached_usb_devices(context=None):
    """List serial candidates without opening, probing or selecting a device."""
    if context is None and transport_platform() in ("linux", "windows"):
        from meshchatnext.src.backend.meshcore_desktop_transport import attached_devices

        return attached_devices()
    try:
        if context is None:
            from usb4a.usb import get_context

            context = get_context()
        manager = context.getSystemService("usb")
        if manager is None:
            raise ConnectionError("USB is unavailable")
        devices = manager.getDeviceList()
        result = []
        for path in sorted(list_usb_devices(context)):
            device = devices.get(path)
            if device is None:
                continue
            name = device.getProductName()
            result.append(
                {
                    "path": path,
                    "name": str(name) if name else "USB serial radio",
                    "vendor_id": int(device.getVendorId()),
                    "product_id": int(device.getProductId()),
                    "permission": usb_has_permission(context, path),
                }
            )
        return result
    except ConnectionError:
        raise
    except Exception as error:
        raise ConnectionError("USB devices unavailable") from error


def permit_usb_device(path, context=None):
    """Request permission only for the explicitly selected serial candidate."""
    if not isinstance(path, str) or not path:
        raise ValueError("Select a USB radio")
    if context is None and transport_platform() in ("linux", "windows"):
        from meshchatnext.src.backend.meshcore_desktop_transport import permit_device

        return permit_device(path)
    if context is None:
        try:
            from usb4a.usb import get_context

            context = get_context()
        except Exception as error:
            raise ConnectionError("Android USB is unavailable") from error
    if path not in list_usb_devices(context):
        raise ValueError("Selected USB radio is no longer attached")
    granted = usb_has_permission(context, path)
    if not granted:
        request_usb_permission(context, path)
    return {"granted": granted, "requested": not granted}


async def scan_ble(context, duration=5.0):
    """Discover Nordic UART candidates, which may include RNodes; never auto-connect.

    Returns addresses and advertised names. Only a successful MeshCore handshake
    identifies a compatible companion; the UART service UUID alone cannot.
    """
    from java import jclass

    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("Scan duration must be between 0 and 30 seconds")
    session = jclass("com.meshchatnext.meshcore.BleDiscovery")(context)
    found = {}
    try:
        await asyncio.to_thread(session.start)
        end = asyncio.get_running_loop().time() + duration
        while asyncio.get_running_loop().time() < end:
            event = await asyncio.to_thread(session.poll, 200)
            if event is None:
                continue
            if str(event.kind) == "error":
                raise ConnectionError(str(event.detail))
            if str(event.kind) == "found":
                name = bytes(int(value) & 255 for value in event.data).decode(
                    "utf-8", "replace"
                )
                found[str(event.detail)] = name
            if str(event.kind) == "closed":
                break
    finally:
        await asyncio.to_thread(session.close)
    return [{"address": address, "name": found[address]} for address in sorted(found)]


async def probe_radio(kind, target, *, context=None, **options):
    """Hardware smoke test: companion handshake/query only, no settings or LoRa sends.

    Pass the actual Android Application context when running without MainActivity.
    Returns counts rather than identity/key data. USB permission must be granted;
    BLE pairing, where required, is handled by Android's system dialog.
    """
    connection = AndroidConnection(kind, target, context=context, **options)
    incoming = asyncio.Queue(maxsize=32)

    class Reader:
        async def handle_rx(self, packet):
            incoming.put_nowait(packet)

    connection.set_reader(Reader())

    async def response(expected):
        async with asyncio.timeout(connection.timeout):
            while True:
                packet = await incoming.get()
                if packet[0] == 0x01:
                    raise ConnectionError("Companion rejected probe command")
                if packet[0] == expected:
                    return packet

    try:
        await connection.connect()
        await connection.send(b"\x01\x03      Meshchat neXt")
        own_info = await response(0x05)
        await connection.send(b"\x16\x03")
        device_info = await response(0x0D)
        if len(own_info) < 2 or len(device_info) < 4:
            raise ConnectionError("Truncated companion response")
        return {
            "transport": kind,
            "handshake": "ok",
            "query": "ok",
            "self_info_bytes": len(own_info),
            "device_info_bytes": len(device_info),
        }
    finally:
        await connection.disconnect()


def paired_ble_devices(context=None):
    """Read Android paired devices or Linux UART advertisements without connecting."""
    try:
        if context is None:
            from usb4a.usb import get_context

            context = get_context()
        manager = context.getApplicationContext().getSystemService("bluetooth")
        adapter = manager.getAdapter() if manager is not None else None
        if adapter is None or not adapter.isEnabled():
            raise ConnectionError("Bluetooth is unavailable or disabled")
        found = {}
        for device in adapter.getBondedDevices().toArray():
            if int(device.getType()) == 1:  # Classic-only devices cannot use BLE UART.
                continue
            address = str(device.getAddress())
            name = device.getName()
            found[address] = str(name) if name is not None else "Unnamed paired device"
        return [
            {"address": address, "name": found[address]} for address in sorted(found)
        ]
    except ConnectionError:
        raise
    except Exception as error:
        raise ConnectionError(
            "Paired Bluetooth devices unavailable; check permission"
        ) from error


async def available_ble_devices(context=None):
    """Keep Linux BlueZ discovery on the application's existing asyncio loop."""
    if context is not None or transport_platform() == "android":
        return await asyncio.to_thread(paired_ble_devices, context)
    if transport_platform() in ("linux", "windows"):
        from meshchatnext.src.backend.meshcore_desktop_transport import discover_devices

        return await discover_devices()
    raise ConnectionError("Bluetooth discovery is unavailable on this platform")
