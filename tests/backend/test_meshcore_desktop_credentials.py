# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from meshchatnext.src.backend.meshcore_desktop_credentials import DesktopNodePasswords

OWNER, PEER = "a1" * 32, "b2" * 32


def fixture(locked=False):
    connection = Mock()
    collection = Mock()
    collection.is_locked.return_value = locked
    collection.search_items.return_value = []
    api = SimpleNamespace(
        dbus_init=Mock(return_value=connection),
        check_service_availability=Mock(return_value=True),
        get_collection_by_alias=Mock(return_value=collection),
    )
    return DesktopNodePasswords(api), api, connection, collection


def test_construction_is_passive():
    provider, api, _, _ = fixture()
    assert provider is not None
    api.dbus_init.assert_not_called()


def test_status_never_unlocks_or_reads_secrets():
    provider, _, conn, collection = fixture(locked=True)
    assert provider.has(OWNER, PEER, "admin") is False
    collection.unlock.assert_not_called()
    collection.search_items.assert_not_called()
    conn.close.assert_called_once()


def test_save_uses_exact_slot_and_replaces_without_plaintext_attributes():
    provider, api, conn, collection = fixture()
    provider.save(OWNER, PEER, "member", "example-secret")
    api.get_collection_by_alias.assert_called_once_with(conn, "default")
    args, kw = collection.create_item.call_args
    assert args[1] == {
        "application": "org.meshchatnext.node-passwords",
        "schema": "1",
        "owner": OWNER,
        "peer": PEER,
        "role": "member",
    }
    assert args[2] == b"example-secret"
    assert kw == {"replace": True}
    conn.close.assert_called_once()


def test_explicit_load_can_unlock_but_bounds_prompt():
    provider, _, conn, collection = fixture()
    collection.is_locked.side_effect = [True, False]
    item = Mock()
    item.get_secret.return_value = b"saved"
    collection.search_items.return_value = [item]
    assert provider.load(OWNER, PEER, "admin") == "saved"
    collection.unlock.assert_called_once_with(timeout=30)
    conn.close.assert_called_once()


def test_cancelled_unlock_fails_closed_and_closes_connection():
    provider, _, conn, collection = fixture(locked=True)
    with pytest.raises(ValueError, match="remains locked"):
        provider.load(OWNER, PEER, "admin")
    collection.search_items.assert_not_called()
    conn.close.assert_called_once()


def test_unavailable_service_does_not_select_collection():
    provider, api, conn, _ = fixture()
    api.check_service_availability.return_value = False
    with pytest.raises(ValueError, match="unavailable"):
        provider.save(OWNER, PEER, "member", "value")
    api.get_collection_by_alias.assert_not_called()
    conn.close.assert_called_once()


def test_exception_closes_connection():
    provider, _, conn, collection = fixture()
    collection.create_item.side_effect = RuntimeError("service failed")
    with pytest.raises(RuntimeError):
        provider.save(OWNER, PEER, "member", "value")
    conn.close.assert_called_once()


def test_ambiguous_slot_never_returns_an_arbitrary_secret():
    provider, _, conn, collection = fixture()
    first, second = Mock(), Mock()
    collection.search_items.return_value = [first, second]
    with pytest.raises(ValueError, match="ambiguous"):
        provider.load(OWNER, PEER, "member")
    first.get_secret.assert_not_called()
    second.get_secret.assert_not_called()
    conn.close.assert_called_once()


def test_forget_only_matching_application_slot():
    provider, _, conn, collection = fixture()
    item = Mock()
    collection.search_items.return_value = [item]
    provider.forget(OWNER, PEER, "admin")
    attrs = collection.search_items.call_args.args[0]
    assert attrs["application"] == "org.meshchatnext.node-passwords"
    assert (
        attrs["owner"] == OWNER and attrs["peer"] == PEER and attrs["role"] == "admin"
    )
    item.delete.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.parametrize("password", [None, "a" * 65, "x\0y"])
def test_invalid_secret_does_not_open_bus(password):
    provider, api, _, _ = fixture()
    with pytest.raises(ValueError):
        provider.save(OWNER, PEER, "member", password)
    api.dbus_init.assert_not_called()
