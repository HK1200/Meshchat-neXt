# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from meshchatnext.src.backend import meshcore_desktop_transport as desktop
from meshchatnext.src.backend import meshcore_transport as transport
from meshchatnext.src.backend.meshcore_windows_credentials import WindowsNodePasswords

OWNER, PEER, OTHER = "a1" * 32, "b2" * 32, "c3" * 32


def test_windows_platform_and_constructor_do_not_connect(monkeypatch):
    monkeypatch.setattr(transport.sys, "platform", "win32")
    monkeypatch.delenv("ANDROID_ROOT", raising=False)
    assert transport.transport_platform() == "windows"
    factory = Mock()
    connection = transport.create_connection("usb", "com12", native_factory=factory)
    assert connection.target == "COM12"
    factory.assert_not_called()


@pytest.mark.parametrize(
    "target",
    [
        "COM0",
        "COM65536",
        "COM1/file",
        "C:/private",
        r"\\.\C:",
        "/dev/ttyUSB0",
        "COM1:secret",
        "COM1\0",
    ],
)
def test_windows_only_allows_canonical_com_devices(monkeypatch, target):
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    with pytest.raises(ValueError):
        desktop.DesktopConnection("usb", target)


def test_linux_still_rejects_windows_devices(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    with pytest.raises(ValueError, match="under /dev"):
        desktop.DesktopConnection("usb", "COM12")


@pytest.mark.asyncio
async def test_two_windows_connections_remain_independent(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    natives = [
        SimpleNamespace(
            connect=AsyncMock(return_value=True),
            disconnect=AsyncMock(),
            send=AsyncMock(),
            set_reader=Mock(),
            set_disconnect_callback=Mock(),
        )
        for _ in range(2)
    ]
    first = desktop.DesktopConnection(
        "usb", "COM12", native_factory=lambda *a, **k: natives[0]
    )
    second = desktop.DesktopConnection(
        "ble", "AA:BB:CC:DD:EE:FF", native_factory=lambda *a, **k: natives[1]
    )
    await first.connect()
    await second.connect()
    await first.disconnect()
    await second.send(b"hello")
    natives[1].disconnect.assert_not_awaited()
    await second.disconnect()


class Credentials:
    def __init__(self):
        self.values = {}
        self.read_secret = 0

    def read(self, target, *, presence_only=False):
        if target not in self.values:
            raise FileNotFoundError()
        if presence_only:
            return True
        self.read_secret += 1
        return self.values[target]

    def write(self, target, secret):
        self.values[target] = secret

    def delete(self, target):
        self.values.pop(target, None)


def test_credentials_isolate_owner_peer_and_role_and_status_does_not_read_secret():
    api = Credentials()
    provider = WindowsNodePasswords(api)
    provider.save(OWNER, PEER, "admin", "é-secret")
    assert provider.has(OWNER, PEER, "admin")
    assert not provider.has(OTHER, PEER, "admin")
    assert not provider.has(OWNER, OTHER, "admin")
    assert not provider.has(OWNER, PEER, "member")
    assert api.read_secret == 0
    assert provider.load(OWNER, PEER, "admin") == "é-secret"
    provider.forget(OWNER, PEER, "admin")
    assert not provider.has(OWNER, PEER, "admin")


@pytest.mark.parametrize("secret", ["x" * 65, "é" * 33, "bad\0secret", None])
def test_credential_validation_does_not_call_native_store(secret):
    api = Mock()
    with pytest.raises(ValueError):
        WindowsNodePasswords(api).save(OWNER, PEER, "member", secret)
    api.write.assert_not_called()


def test_credential_failure_is_not_missing_and_has_no_fallback():
    api = Mock()
    api.read.side_effect = PermissionError("denied")
    with pytest.raises(PermissionError):
        WindowsNodePasswords(api).has(OWNER, PEER, "admin")


def test_windows_provider_is_selected_lazily(monkeypatch):
    from meshchatnext.src.backend import meshcore_credentials as credentials
    from meshchatnext.src.backend import meshcore_windows_credentials as windows

    provider = Mock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(credentials, "transport_platform", lambda: "windows")
    monkeypatch.setattr(windows, "WindowsNodePasswords", factory)
    passwords = credentials.NodePasswords()
    factory.assert_not_called()
    assert passwords.provider() is provider
    factory.assert_called_once()


def test_windows_com_endpoint_case_does_not_allow_duplicate_device(monkeypatch):
    from meshchatnext.src.backend import meshcore_fleet as fleet

    monkeypatch.setattr(fleet, "transport_platform", lambda: "windows")
    assert fleet.MeshCoreFleet._endpoint(
        "usb", "com12"
    ) == fleet.MeshCoreFleet._endpoint("usb", "COM12")


def test_native_credential_binding_releases_reads_and_clears_write_buffer(monkeypatch):
    import ctypes as ct

    from meshchatnext.src.backend import meshcore_windows_credentials as windows

    secret = (ct.c_ubyte * 6).from_buffer_copy(b"secret")
    target = WindowsNodePasswords.slot(OWNER, PEER, "member")
    value = windows._Credential(type=1, target=target, size=6, blob=secret, persist=2)

    def read(name, kind, flags, destination):
        ct.cast(destination, ct.POINTER(ct.POINTER(windows._Credential)))[0] = (
            ct.pointer(value)
        )
        return 1

    buffers = []

    def write(pointer, flags):
        credential = ct.cast(pointer, ct.POINTER(windows._Credential)).contents
        assert credential.persist == 2
        assert credential.target == target
        assert ct.string_at(credential.blob, credential.size) == b"secret"
        buffers.append((credential.blob, credential.size))
        return 1

    api = SimpleNamespace(
        CredReadW=Mock(side_effect=read),
        CredWriteW=Mock(side_effect=write),
        CredDeleteW=Mock(return_value=1),
        CredFree=Mock(),
    )
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows.ct, "WinDLL", Mock(return_value=api), raising=False)
    manager = windows._CredentialManager()
    assert manager.read(target) == b"secret"
    assert manager.read(target, presence_only=True) is True
    assert api.CredFree.call_count == 2
    manager.write(target, b"secret")
    # Keep the original ctypes argument alive through Mock's call record.
    assert ct.string_at(*buffers[0]) == bytes(6)
