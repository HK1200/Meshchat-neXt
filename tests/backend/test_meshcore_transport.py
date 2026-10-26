# SPDX-License-Identifier: MIT
"""Transport failure/concurrency tests without Android, radios, or Reticulum."""

import asyncio
import importlib.util
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from meshchatnext.src.backend.meshcore_transport import (
    AndroidConnection,
    SerialFrames,
    attached_usb_devices,
    paired_ble_devices,
    permit_usb_device,
)


class UsbSelectionTests(unittest.TestCase):
    def test_lists_candidates_without_opening_or_requesting_permission(self):
        device = SimpleNamespace(
            getProductName=lambda: "T1000-E",
            getVendorId=lambda: 0x239A,
            getProductId=lambda: 0x8029,
        )
        context = Mock()
        context.getSystemService.return_value.getDeviceList.return_value = {
            "/usb/2": device
        }
        with (
            patch(
                "meshchatnext.src.backend.meshcore_transport.list_usb_devices",
                return_value=["/usb/2"],
            ),
            patch(
                "meshchatnext.src.backend.meshcore_transport.usb_has_permission",
                return_value=False,
            ),
            patch(
                "meshchatnext.src.backend.meshcore_transport.request_usb_permission"
            ) as request,
        ):
            self.assertEqual(
                attached_usb_devices(context),
                [
                    {
                        "path": "/usb/2",
                        "name": "T1000-E",
                        "vendor_id": 0x239A,
                        "product_id": 0x8029,
                        "permission": False,
                    }
                ],
            )
            request.assert_not_called()
        context.getSystemService.return_value.openDevice.assert_not_called()

    def test_requests_only_selected_device_and_rejects_detached_path(self):
        context = Mock()
        with (
            patch(
                "meshchatnext.src.backend.meshcore_transport.list_usb_devices",
                return_value=["/usb/2"],
            ),
            patch(
                "meshchatnext.src.backend.meshcore_transport.usb_has_permission",
                return_value=False,
            ),
            patch(
                "meshchatnext.src.backend.meshcore_transport.request_usb_permission"
            ) as request,
        ):
            self.assertEqual(
                permit_usb_device("/usb/2", context),
                {"granted": False, "requested": True},
            )
            request.assert_called_once_with(context, "/usb/2")
            with self.assertRaises(ValueError):
                permit_usb_device("/usb/1", context)
            request.assert_called_once()
        with (
            patch(
                "meshchatnext.src.backend.meshcore_transport.list_usb_devices",
                return_value=["/usb/2"],
            ),
            patch(
                "meshchatnext.src.backend.meshcore_transport.usb_has_permission",
                return_value=True,
            ),
            patch(
                "meshchatnext.src.backend.meshcore_transport.request_usb_permission"
            ) as request,
        ):
            self.assertEqual(
                permit_usb_device("/usb/2", context),
                {"granted": True, "requested": False},
            )
            request.assert_not_called()


class PairedBluetoothTests(unittest.TestCase):
    def test_lists_named_ble_candidates_without_connecting_and_excludes_classic(self):
        devices = [
            SimpleNamespace(
                getType=lambda: 2,
                getAddress=lambda: "AA:BB:CC:DD:EE:FF",
                getName=lambda: "MeshCore",
            ),
            SimpleNamespace(
                getType=lambda: 3,
                getAddress=lambda: "11:22:33:44:55:66",
                getName=lambda: "RNode",
            ),
            SimpleNamespace(getType=lambda: 1),
        ]
        adapter = SimpleNamespace(
            isEnabled=lambda: True,
            getBondedDevices=lambda: SimpleNamespace(toArray=lambda: devices),
        )
        context = Mock()
        context.getApplicationContext.return_value.getSystemService.return_value.getAdapter.return_value = adapter
        result = paired_ble_devices(context)
        self.assertEqual([row["name"] for row in result], ["RNode", "MeshCore"])
        context.getApplicationContext.return_value.getSystemService.assert_called_once_with(
            "bluetooth"
        )

    def test_bluetooth_disabled_is_reported_without_changing_adapter_state(self):
        context = Mock()
        context.getApplicationContext.return_value.getSystemService.return_value.getAdapter.return_value.isEnabled.return_value = False
        with self.assertRaises(ConnectionError):
            paired_ble_devices(context)


class RNodeUsbGuardTests(unittest.TestCase):
    def test_usbserial4a_uses_guard_and_returns_real_connection(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "android/app/src/main/python/usb4a/usb.py"
        )
        access = Mock()
        connection = object()
        access.openUsb.return_value = connection
        manager = Mock()
        manager.hasPermission.return_value = True
        context = Mock()
        context.getSystemService.return_value = manager
        device = object()

        def autoclass(name):
            return access if name == "com.meshchatnext.radio.DeviceAccess" else Mock()

        spec = importlib.util.spec_from_file_location("guarded_usb_test", source)
        module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"jnius": SimpleNamespace(autoclass=autoclass)}):
            spec.loader.exec_module(module)
            module.set_context(context)
            bridge = module.get_usb_manager()
            self.assertIs(bridge.openDevice(device), connection)
            self.assertTrue(bridge.hasPermission(device))
        access.openUsb.assert_called_once_with(context, device)
        manager.openDevice.assert_not_called()


class FakeNative:
    def __init__(self, *, ready=True, acknowledge=True):
        self.events = queue.Queue()
        self.ready = ready
        self.acknowledge = acknowledge
        self.closed = False
        self.sent = []

    def event(self, kind, data=None, detail="fake"):
        self.events.put(SimpleNamespace(kind=kind, data=data, detail=detail))

    def poll(self, timeout):
        try:
            return self.events.get(timeout=timeout / 1000)
        except queue.Empty:
            return None

    def start(self):
        if self.ready:
            self.event("ready")

    def send(self, data):
        if self.closed:
            raise ConnectionError("closed")
        self.sent.append(data)
        if self.acknowledge:
            self.event("written")

    def close(self):
        if not self.closed:
            self.closed = True
            self.event("closed")


class SerialFrameTests(unittest.TestCase):
    def test_every_split_and_coalesced_frames(self):
        stream = b"console junk>\x03\x00\x05\x80\xff>\x02\x00\x0d\x03"
        for split in range(len(stream) + 1):
            parser = SerialFrames()
            self.assertEqual(
                parser.feed(stream[:split]) + parser.feed(stream[split:]),
                [b"\x05\x80\xff", b"\x0d\x03"],
            )

    def test_invalid_lengths_resynchronize_and_buffer_is_bounded(self):
        parser = SerialFrames()
        self.assertEqual(parser.feed(b">\xff\xff>\0\0>\x01\0\x05"), [b"\x05"])
        parser.feed(b"x" * 10000)
        self.assertEqual(parser.buffer, b"")
        parser.feed(b">\x2c\x01" + b"x" * 299)
        self.assertEqual(len(parser.buffer), 302)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connections = []

    async def asyncTearDown(self):
        for connection in self.connections:
            await connection.disconnect()

    def make(self, kind="usb", native=None, **options):
        native = native or FakeNative()
        connection = AndroidConnection(
            kind, "selected-radio", native_factory=lambda *a, **k: native, **options
        )
        self.connections.append(connection)
        return connection, native

    async def test_usb_and_ble_have_distinct_framing_and_lifecycles(self):
        usb, un = self.make()
        ble, bn = self.make("ble")
        await asyncio.gather(usb.connect(), ble.connect())
        await asyncio.gather(usb.send(b"\x16\x03"), ble.send(b"\x16\x03"))
        self.assertEqual(un.sent, [b"<\x02\0\x16\x03"])
        self.assertEqual(bn.sent, [b"\x16\x03"])
        await usb.disconnect()
        self.assertTrue(ble.is_connected)
        await ble.send(b"\x01")
        self.assertFalse(bn.closed)

    async def test_signed_java_bytes_and_split_serial_notifications(self):
        connection, native = self.make()
        received = asyncio.Queue()
        connection.set_reader(SimpleNamespace(handle_rx=received.put))
        await connection.connect()
        native.event("data", [62, 2])
        native.event("data", [0, -128, -1])
        self.assertEqual(await asyncio.wait_for(received.get(), 1), b"\x80\xff")

    async def test_write_waits_for_native_ack_and_serializes_commands(self):
        connection, native = self.make(native=FakeNative(acknowledge=False))
        await connection.connect()
        first = asyncio.create_task(connection.send(b"a"))
        second = asyncio.create_task(connection.send(b"b"))
        while not native.sent:
            await asyncio.sleep(0.001)
        self.assertEqual(len(native.sent), 1)
        self.assertFalse(first.done())
        native.event("written")
        await first
        while len(native.sent) < 2:
            await asyncio.sleep(0.001)
        native.event("written")
        await second

    async def test_open_timeout_cleans_up_only_its_own_session(self):
        connection, native = self.make(native=FakeNative(ready=False), timeout=0.03)
        other, other_native = self.make("ble")
        await other.connect()
        with self.assertRaises(asyncio.TimeoutError):
            await connection.connect()
        self.assertTrue(native.closed)
        self.assertTrue(other.is_connected)
        self.assertFalse(other_native.closed)

    async def test_remote_loss_notifies_once_and_fails_pending_send(self):
        connection, native = self.make(native=FakeNative(acknowledge=False))
        reasons = []
        called = asyncio.Event()

        async def lost(reason):
            reasons.append(reason)
            called.set()

        connection.set_disconnect_callback(lost)
        await connection.connect()
        sending = asyncio.create_task(connection.send(b"a"))
        while not native.sent:
            await asyncio.sleep(0.001)
        native.event("error", detail="usb_read_failed")
        with self.assertRaises(ConnectionError):
            await sending
        await asyncio.wait_for(called.wait(), 1)
        self.assertEqual(len(reasons), 1)
        self.assertFalse(connection.is_connected)

    async def test_fixed_usb_failure_reason_survives_close_and_untrusted_details_are_hidden(
        self,
    ):
        connection, native = self.make()
        await connection.connect()
        native.event("error", detail="usb_detached")
        for _ in range(100):
            if not connection.is_connected:
                break
            await asyncio.sleep(0.001)
        await connection.disconnect()
        self.assertEqual(connection.failure_reason, "usb_detached")
        other, other_native = self.make()
        await other.connect()
        other_native.event("error", detail="unexpected private device details")
        for _ in range(100):
            if not other.is_connected:
                break
            await asyncio.sleep(0.001)
        await other.disconnect()
        self.assertEqual(other.failure_reason, "transport_failed")

    async def test_explicit_disconnect_does_not_request_reconnect(self):
        connection, _native = self.make()
        reasons = []

        async def lost(reason):
            reasons.append(reason)

        connection.set_disconnect_callback(lost)
        await connection.connect()
        await connection.disconnect()
        await asyncio.sleep(0)
        self.assertEqual(reasons, [])

    async def test_reconnect_uses_new_native_session_and_no_stale_serial_buffer(self):
        first, second = FakeNative(), FakeNative()
        sessions = iter([first, second])
        connection = AndroidConnection(
            "usb", "radio", native_factory=lambda *a, **k: next(sessions)
        )
        self.connections.append(connection)
        received = asyncio.Queue()
        connection.set_reader(SimpleNamespace(handle_rx=received.put))
        await connection.connect()
        first.event("data", b">\x02")
        await connection.disconnect()
        await connection.connect()
        second.event("data", b">\x01\0\x0d")
        self.assertEqual(await asyncio.wait_for(received.get(), 1), b"\x0d")

    async def test_cancelling_inflight_send_closes_session_without_replay(self):
        connection, native = self.make(native=FakeNative(acknowledge=False))
        await connection.connect()
        sending = asyncio.create_task(connection.send(b"a"))
        while not native.sent:
            await asyncio.sleep(0.001)
        sending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await sending
        self.assertTrue(native.closed)
        self.assertEqual(len(native.sent), 1)

    async def test_write_timeout_closes_and_notifies(self):
        connection, native = self.make(
            native=FakeNative(acknowledge=False), timeout=0.03
        )
        lost = asyncio.Event()

        async def callback(reason):
            lost.set()

        connection.set_disconnect_callback(callback)
        await connection.connect()
        with self.assertRaises(asyncio.TimeoutError):
            await connection.send(b"a")
        await asyncio.wait_for(lost.wait(), 1)
        self.assertTrue(native.closed)


if __name__ == "__main__":
    unittest.main()
