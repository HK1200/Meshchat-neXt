import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from meshchatnext.src.backend import meshcore_transport as platform
from meshchatnext.src.backend.meshcore_desktop_transport import (
    UART_SERVICE,
    DesktopConnection,
    attached_devices,
    discover_devices,
    permit_device,
)


class Native:
    def __init__(self):
        self.reader = self.callback = None
        self.connect = AsyncMock(return_value="ready")
        self.disconnect = AsyncMock()
        self.send = AsyncMock()

    def set_reader(self, reader):
        self.reader = reader

    def set_disconnect_callback(self, callback):
        self.callback = callback


def make(native=None, **options):
    native = native or Native()
    return DesktopConnection(
        "usb", "/dev/ttyUSB-test", native_factory=lambda *a, **k: native, **options
    ), native


@pytest.mark.asyncio
async def test_explicit_open_and_independent_lifetimes():
    first, one = make()
    second, two = make()
    one.connect.assert_not_called()
    await first.connect()
    await second.connect()
    await first.disconnect()
    await second.send(b"\x01hello")
    assert second.is_connected
    two.disconnect.assert_not_called()
    await second.disconnect()


@pytest.mark.asyncio
async def test_cancelled_connect_closes_partial_native_session():
    connection, native = make()
    started = asyncio.Event()

    async def wait():
        started.set()
        await asyncio.Event().wait()

    native.connect.side_effect = wait
    task = asyncio.create_task(connection.connect())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    native.disconnect.assert_awaited_once()
    assert not connection.is_connected


@pytest.mark.asyncio
async def test_timeout_closes_session_and_redacts_native_error():
    connection, native = make(timeout=0.01)
    native.connect.side_effect = lambda: None
    native.connect.side_effect = TimeoutError("private packet contents")
    with pytest.raises(ConnectionError, match="check device access") as error:
        await connection.connect()
    assert "private" not in str(error.value)
    native.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_late_callbacks_and_frames_cannot_close_a_replacement_connection():
    one, two = Native(), Native()
    factory = Mock(side_effect=[one, two])
    connection = DesktopConnection("ble", "AA:BB:CC:DD:EE:FF", native_factory=factory)
    reader = SimpleNamespace(handle_rx=AsyncMock())
    callback = AsyncMock()
    connection.set_reader(reader)
    connection.set_disconnect_callback(callback)
    await connection.connect()
    await connection.disconnect()
    await connection.connect()
    await one.callback("old connection")
    await one.reader.handle_rx(b"stale")
    assert connection.is_connected
    callback.assert_not_called()
    reader.handle_rx.assert_not_called()
    await two.reader.handle_rx(b"current")
    reader.handle_rx.assert_awaited_once_with(b"current")
    await connection.disconnect()


@pytest.mark.asyncio
async def test_failed_write_closes_even_when_callback_raises():
    connection, native = make()
    connection.set_disconnect_callback(
        AsyncMock(side_effect=RuntimeError("callback failed"))
    )
    await connection.connect()
    native.send.return_value = False
    with pytest.raises(ConnectionError, match="not confirmed"):
        await connection.send(b"\x02")
    native.disconnect.assert_awaited_once()
    assert not connection.is_connected


@pytest.mark.asyncio
async def test_writes_are_serialized_and_never_replayed():
    connection, native = make()
    active = peak = 0

    async def send(data):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

    native.send.side_effect = send
    await connection.connect()
    await asyncio.gather(connection.send(b"\x01"), connection.send(b"\x02"))
    assert peak == 1 and native.send.await_count == 2
    await connection.disconnect()


@pytest.mark.parametrize(
    "kind,target",
    [("usb", "/tmp/credentials"), ("ble", ""), ("ble", "radio-name"), ("tcp", "host")],
)
def test_invalid_or_implicit_targets_are_rejected(kind, target):
    with pytest.raises(ValueError):
        DesktopConnection(kind, target)


def test_enumeration_and_permission_checks_do_not_open_or_modify_devices(monkeypatch):
    import serial.tools.list_ports

    import meshchatnext.src.backend.meshcore_desktop_transport as desktop

    monkeypatch.setattr(
        serial.tools.list_ports,
        "comports",
        lambda: [
            SimpleNamespace(
                device="/dev/ttyUSB-test", description="Test radio", vid=1, pid=2
            )
        ],
    )
    monkeypatch.setattr(desktop.os, "access", lambda *args: False)
    assert attached_devices()[0]["permission"] is False
    with pytest.raises(ConnectionError, match="access denied"):
        permit_device("/dev/ttyUSB-test")
    with pytest.raises(ValueError):
        permit_device("/tmp/credentials")


@pytest.mark.asyncio
async def test_scan_filters_uart_advertisements_without_connecting():
    scanner = SimpleNamespace(
        discover=AsyncMock(
            return_value={
                "one": (
                    SimpleNamespace(address="AA", name="Test"),
                    SimpleNamespace(
                        local_name=None, service_uuids=[UART_SERVICE.upper()]
                    ),
                ),
                "two": (
                    SimpleNamespace(address="BB", name="Other"),
                    SimpleNamespace(local_name=None, service_uuids=[]),
                ),
            }
        )
    )
    assert await discover_devices(scanner=scanner) == [
        {"address": "AA", "name": "Test"}
    ]
    scanner.discover.assert_awaited_once_with(timeout=5.0, return_adv=True)


def test_android_factory_is_preserved_and_desktop_factory_is_lazy(monkeypatch):
    monkeypatch.setattr(platform, "transport_platform", lambda: "android")
    android = Mock(return_value="android connection")
    monkeypatch.setattr(platform, "AndroidConnection", android)
    assert platform.create_connection("usb", "/android/device") == "android connection"
    monkeypatch.setattr(platform, "transport_platform", lambda: "linux")
    native = Mock()
    connection = platform.create_connection(
        "usb", "/dev/ttyUSB-test", native_factory=native
    )
    assert isinstance(connection, DesktopConnection)
    native.assert_not_called()


@pytest.mark.asyncio
async def test_stalled_write_is_bounded_and_not_replayed():
    connection, native = make(timeout=0.02)

    async def stall(data):
        await asyncio.Event().wait()

    native.send.side_effect = stall
    await connection.connect()
    with pytest.raises(ConnectionError, match="not confirmed"):
        await asyncio.wait_for(connection.send(b"\x01"), timeout=1)
    native.send.assert_awaited_once()
    native.disconnect.assert_awaited_once()
    assert not connection.is_connected


@pytest.mark.asyncio
async def test_linux_discovery_uses_the_existing_event_loop(monkeypatch):
    import meshchatnext.src.backend.meshcore_desktop_transport as desktop

    loop = asyncio.get_running_loop()
    seen = []

    async def scan():
        seen.append(asyncio.get_running_loop())
        return [{"address": "AA:BB:CC:DD:EE:FF", "name": "Candidate"}]

    monkeypatch.setattr(platform, "transport_platform", lambda: "linux")
    monkeypatch.setattr(desktop, "discover_devices", scan)
    for _ in range(3):
        assert await platform.available_ble_devices()
    assert seen == [loop, loop, loop]


@pytest.mark.asyncio
async def test_real_sdk_serial_framing_over_a_virtual_linux_tty(monkeypatch):
    import os

    import serial

    # PTYs have no modem-control pins; only those pin ioctls are replaced.
    # Opening, async reads/writes, and framing use the real SDK/pyserial stack.
    class PtySerial(serial.Serial):
        def _update_dtr_state(self):
            pass

        def _update_rts_state(self):
            pass

    monkeypatch.setattr(serial, "Serial", PtySerial)
    master, slave = os.openpty()
    os.set_blocking(master, False)
    connection = DesktopConnection("usb", os.ttyname(slave), timeout=2)
    received = asyncio.Queue()
    connection.set_reader(SimpleNamespace(handle_rx=received.put))
    try:
        await connection.connect()
        await connection.send(b"\x01hello")
        wire = bytearray()
        async with asyncio.timeout(2):
            while len(wire) < 9:
                try:
                    wire.extend(os.read(master, 1024))
                except BlockingIOError:
                    await asyncio.sleep(0.005)
        assert bytes(wire) == b"<\x06\x00\x01hello"
        os.write(master, b"console junk>")
        await asyncio.sleep(0)
        os.write(master, b"\x03\x00\x05ab")
        assert await asyncio.wait_for(received.get(), 2) == b"\x05ab"
        await connection.disconnect()
        assert not connection.is_connected
    finally:
        await connection.disconnect()
        os.close(master)
        os.close(slave)
