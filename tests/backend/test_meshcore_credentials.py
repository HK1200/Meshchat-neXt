from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend.meshcore_credentials import NodePasswords
from meshchatnext.src.backend.meshcore_nodes import MeshCoreNodes

OWNER, PEER = "a1" * 32, "b2" * 32


class Provider:
    def __init__(self):
        self.data = {}

    def has(self, *slot):
        return slot in self.data

    def save(self, *args):
        self.data[args[:3]] = args[3]

    def load(self, *slot):
        return self.data[slot]

    def forget(self, *slot):
        self.data.pop(slot, None)


def test_password_roles_and_identity_isolation_without_plaintext_fallback():
    provider = Provider()
    vault = NodePasswords(provider)
    vault.save(OWNER, PEER, "admin", "test-only-secret")
    assert vault.status(OWNER, PEER) == {"available": True, "saved_roles": ["admin"]}
    assert vault.status(PEER, OWNER)["saved_roles"] == []
    assert vault.load(OWNER, PEER, "admin") == "test-only-secret"
    vault.forget(OWNER, PEER, "admin")
    assert not vault.status(OWNER, PEER)["saved_roles"]
    for value in ("x" * 65, "\0", True):
        with pytest.raises(ValueError):
            vault.save(OWNER, PEER, "member", value)
    unsupported = NodePasswords()
    unsupported._attempted = True
    assert not unsupported.status(OWNER, PEER)["available"]
    with pytest.raises(ValueError):
        unsupported.save(OWNER, PEER, "member", "secret")


@pytest.mark.asyncio
async def test_only_verified_login_saved_and_storage_failure_preserves_login():
    vault = NodePasswords(Provider())
    messages = SimpleNamespace(owner=OWNER, session=object())
    nodes = MeshCoreNodes(messages, vault)
    nodes._exchange = AsyncMock(return_value={"state": "denied"})
    await nodes.login(PEER, "secret", remember=True)
    assert vault.status(OWNER, PEER)["saved_roles"] == []
    nodes._exchange.return_value = {"state": "verified", "is_admin": True}
    result = await nodes.login(PEER, "secret", remember=True)
    assert result["password_saved"] is True
    await nodes.login(PEER, use_saved_role="admin")
    nodes._exchange.assert_awaited_with(PEER, "login", "secret")
    vault.save = lambda *args: (_ for _ in ()).throw(RuntimeError("do not disclose"))
    result = await nodes.login(PEER, "secret", remember=True)
    assert result["state"] == "verified" and result["password_saved"] is False


def test_native_provider_is_lazy_and_storage_errors_do_not_disclose_credentials(
    monkeypatch,
):
    import sys

    monkeypatch.setattr(
        "meshchatnext.src.backend.meshcore_credentials.transport_platform",
        lambda: "android",
    )
    provider = Provider()
    context = SimpleNamespace(getApplicationContext=lambda: "application-context")
    monkeypatch.setitem(
        sys.modules, "java", SimpleNamespace(jclass=lambda name: lambda ctx: provider)
    )
    monkeypatch.setitem(
        sys.modules, "usb4a.usb", SimpleNamespace(get_context=lambda: context)
    )
    vault = NodePasswords()
    assert vault.status(OWNER, PEER)["available"]
    assert vault.provider() is provider
    provider.save = lambda *args: (_ for _ in ()).throw(
        RuntimeError("sensitive-test-only")
    )
    with pytest.raises(ValueError) as error:
        vault.save(OWNER, PEER, "admin", "secret")
    assert "sensitive-test-only" not in str(error.value)
    provider.has = lambda *args: (_ for _ in ()).throw(RuntimeError("secret"))
    assert vault.status(OWNER, PEER) == {"available": False, "saved_roles": []}
    for role in ("invalid", None):
        with pytest.raises(ValueError):
            vault.load(OWNER, PEER, role)

    def failed(name):
        raise RuntimeError("unavailable")

    monkeypatch.setitem(sys.modules, "java", SimpleNamespace(jclass=failed))
    assert not NodePasswords().status(OWNER, PEER)["available"]


@pytest.mark.asyncio
async def test_radio_battery_preserves_measured_voltage_and_rejects_unknown_values():
    from meshchatnext.src.backend.meshcore_session import MeshCoreSession

    session = MeshCoreSession()
    session._connection = SimpleNamespace(is_connected=True)
    session._client = SimpleNamespace(
        commands=SimpleNamespace(
            get_bat=AsyncMock(
                return_value=SimpleNamespace(
                    payload={"level": 4186}, is_error=lambda: False
                )
            )
        )
    )
    battery = await session.read_battery()
    assert (
        battery["voltage_mv"] == 4186
        and battery["percent"] is None
        and not battery["estimated"]
    )
    session._client.commands.get_bat.return_value.payload = {"level": 0}
    assert (await session.read_battery())["voltage_mv"] is None
    session._connection = None
    with pytest.raises(ConnectionError):
        await session.read_battery()


def test_linux_provider_selected_without_opening_keyring(monkeypatch):
    from meshchatnext.src.backend.meshcore_desktop_credentials import (
        DesktopNodePasswords,
    )

    monkeypatch.setattr(
        "meshchatnext.src.backend.meshcore_credentials.transport_platform",
        lambda: "linux",
    )
    vault = NodePasswords()
    assert isinstance(vault.provider(), DesktopNodePasswords)
    assert vault.provider()._service is None


def test_unsupported_platform_has_no_plaintext_fallback(monkeypatch):
    monkeypatch.setattr(
        "meshchatnext.src.backend.meshcore_credentials.transport_platform",
        lambda: "unsupported",
    )
    assert NodePasswords().provider() is None
