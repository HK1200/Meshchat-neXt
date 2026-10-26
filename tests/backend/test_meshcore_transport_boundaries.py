# SPDX-License-Identifier: MIT
"""Discovery, read-only probes, and native-boundary failure recovery."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from meshchatnext.src.backend import meshcore_session
from meshchatnext.src.backend import meshcore_transport as transport
from tests.backend.test_meshcore_session import FakeClient, FakeConnection
from tests.backend.test_meshcore_transport import FakeNative


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["usb", "ble"])
@pytest.mark.parametrize("reply", ["ok", "rejected", "truncated", "silent"])
async def test_probe_only_queries_and_always_releases_selected_radio(kind, reply):
    class ProbeNative(FakeNative):
        def send(self, data):
            super().send(data)
            command = data[3:] if kind == "usb" else data
            if reply == "silent":
                return
            if reply == "rejected":
                packet = b"\x01"
            elif command[0] == 1:
                packet = b"\x05" if reply == "truncated" else b"\x05\x01"
            else:
                packet = b"\x0d\x01\x02\x03"
            framed = b">" + len(packet).to_bytes(2, "little") + packet
            self.event("data", list(framed if kind == "usb" else packet))

    native = ProbeNative()
    connection = transport.AndroidConnection(
        kind, "explicit-device", timeout=0.1, native_factory=lambda *a, **kw: native
    )
    with patch.object(transport, "AndroidConnection", return_value=connection):
        if reply == "ok":
            result = await transport.probe_radio(kind, "explicit-device")
            assert result == {
                "transport": kind,
                "handshake": "ok",
                "query": "ok",
                "self_info_bytes": 2,
                "device_info_bytes": 4,
            }
        else:
            with pytest.raises((ConnectionError, TimeoutError)):
                await transport.probe_radio(kind, "explicit-device")
    commands = [packet[3:] if kind == "usb" else packet for packet in native.sent]
    assert commands[0].startswith(b"\x01\x03")
    assert all(command[0] in (1, 0x16) for command in commands)
    assert len(commands) <= 2  # No retries or write commands on any failure.
    assert native.closed and not connection.is_connected


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "permission", "start"])
async def test_ble_discovery_deduplicates_without_connecting_and_closes_on_failure(
    failure,
):
    events = [
        SimpleNamespace(kind="found", detail="BB", data=list(b"old")),
        SimpleNamespace(kind="found", detail="AA", data=[-62, -75]),
        SimpleNamespace(kind="found", detail="BB", data=list(b"updated")),
        SimpleNamespace(kind="closed"),
    ]
    if failure == "permission":
        events = [SimpleNamespace(kind="error", detail="permission denied")]
    session = Mock()
    session.poll.side_effect = events
    if failure == "start":
        session.start.side_effect = PermissionError("denied")
    factory = Mock(return_value=session)
    with patch.dict("sys.modules", {"java": SimpleNamespace(jclass=lambda _: factory)}):
        if failure:
            with pytest.raises((ConnectionError, PermissionError)):
                await transport.scan_ble("context", duration=1)
        else:
            assert await transport.scan_ble("context", duration=1) == [
                {"address": "AA", "name": "µ"},
                {"address": "BB", "name": "updated"},
            ]
    session.close.assert_called_once()
    session.connect.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_discovery_duration_never_starts_scanner():
    factory = Mock()
    with patch.dict("sys.modules", {"java": SimpleNamespace(jclass=factory)}):
        for duration in (0, -1, 31, float("inf"), float("nan")):
            with pytest.raises(ValueError):
                await transport.scan_ble("context", duration=duration)
    factory.assert_not_called()


def test_native_factory_keeps_selected_context_and_serial_options():
    context = Mock()
    application = context.getApplicationContext.return_value
    classes = {}

    def jclass(name):
        return classes.setdefault(name, Mock())

    with patch.dict("sys.modules", {"java": SimpleNamespace(jclass=jclass)}):
        transport._native_factory(
            "usb", "/usb/2", context=context, baud=57600, port_index=1
        )
        transport._native_factory("ble", "AA", context=context)
    classes["com.meshchatnext.meshcore.UsbSession"].assert_called_once_with(
        application, "/usb/2", 1, 57600, True, False
    )
    classes["com.meshchatnext.meshcore.BleSession"].assert_called_once_with(
        application, "AA"
    )


def test_usb_bridge_requests_only_explicit_permission_and_preserves_granted_access():
    devices = Mock()
    devices.list.return_value = ["/usb/2"]
    devices.hasPermission.return_value = True
    context = object()
    with patch.dict("sys.modules", {"java": SimpleNamespace(jclass=lambda _: devices)}):
        assert transport.permit_usb_device("/usb/2", context) == {
            "granted": True,
            "requested": False,
        }
        devices.requestPermission.assert_not_called()
        devices.hasPermission.return_value = False
        assert transport.permit_usb_device("/usb/2", context) == {
            "granted": False,
            "requested": True,
        }
        devices.requestPermission.assert_called_once_with(context, "/usb/2")
        with pytest.raises(ValueError):
            transport.permit_usb_device("/usb/9", context)
        devices.requestPermission.assert_called_once()
    for invalid in (None, "", 3):
        with pytest.raises(ValueError):
            transport.permit_usb_device(invalid, context)


def test_discovery_reports_missing_platform_services_without_opening_devices():
    context = Mock()
    context.getSystemService.return_value = None
    with pytest.raises(ConnectionError, match="USB is unavailable"):
        transport.attached_usb_devices(context)
    context.getSystemService.side_effect = PermissionError("denied")
    with pytest.raises(ConnectionError, match="USB devices unavailable"):
        transport.attached_usb_devices(context)
    context.getApplicationContext.side_effect = PermissionError("denied")
    with pytest.raises(ConnectionError, match="check permission"):
        transport.paired_ble_devices(context)


@pytest.mark.asyncio
async def test_managed_read_only_probe_detects_loss_reconnects_and_closes():
    session = meshcore_session.MeshCoreSession(
        connection_factory=FakeConnection, client_factory=FakeClient
    )
    with patch.object(meshcore_session, "MeshCoreSession", return_value=session):
        assert await meshcore_session.probe_managed_session("ble", "selected") == {
            "protocol": "ok",
            "reconnect": "ok",
            "cleanup": "ok",
        }
    assert not session.is_connected
    assert session._connection is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "apply", "restore"])
async def test_settings_probe_restores_baseline_or_retains_recovery_snapshot(
    tmp_path, failure
):
    baseline = {
        "frequency_mhz": 910.525,
        "bandwidth_khz": 62.5,
        "sf": 7,
        "cr": 8,
        "tx_power_dbm": 22,
        "path_hash_bytes": 1,
        "path_hash_supported": True,
    }
    recovery = tmp_path / "meshcore-settings-restore.json"

    class SettingsSession:
        def __init__(self):
            self.current = dict(baseline)
            self.applied = []
            self.closed = False

        async def connect(self, *a, **kw):
            pass

        async def read_settings(self):
            return dict(self.current)

        async def apply_settings(self, **changes):
            assert recovery.is_file()  # Persist recovery before the first write.
            self.applied.append(changes)
            if failure == "apply" and len(self.applied) == 1:
                raise ConnectionError("write not confirmed")
            if (
                failure != "restore"
                or changes.get("frequency_mhz") != baseline["frequency_mhz"]
            ):
                self.current.update(changes)

        async def disconnect(self):
            self.closed = True

    session = SettingsSession()
    context = SimpleNamespace(getFilesDir=lambda: str(tmp_path))
    with patch.object(meshcore_session, "MeshCoreSession", return_value=session):
        if failure:
            with pytest.raises(ConnectionError):
                await meshcore_session.probe_radio_settings(
                    "ble", "selected", context=context
                )
        else:
            assert await meshcore_session.probe_radio_settings(
                "ble", "selected", context=context
            ) == {"settings": "ok", "restored": "ok", "path_hash_supported": True}
    assert session.closed
    assert session.applied[-1] == {
        k: baseline[k] for k in meshcore_session.WRITABLE_FIELDS
    }
    assert recovery.exists() == (failure == "restore")
    if failure != "restore":
        assert session.current == baseline
    if failure is None:
        assert [
            row["path_hash_bytes"]
            for row in session.applied
            if set(row) == {"path_hash_bytes"}
        ] == [1, 2, 3]


@pytest.mark.asyncio
async def test_unresolved_settings_recovery_prevents_new_radio_connection(tmp_path):
    recovery = tmp_path / "meshcore-settings-restore.json"
    recovery.write_text("preserve existing recovery")
    factory = Mock()
    with patch.object(meshcore_session, "MeshCoreSession", factory):
        with pytest.raises(RuntimeError, match="unresolved"):
            await meshcore_session.probe_radio_settings(
                "ble",
                "selected",
                context=SimpleNamespace(getFilesDir=lambda: str(tmp_path)),
            )
    factory.return_value.connect.assert_not_called()
    assert recovery.read_text() == "preserve existing recovery"
