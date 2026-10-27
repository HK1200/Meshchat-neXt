# SPDX-License-Identifier: MIT
import stat

import pytest

from meshchatnext.src.backend.sip_desktop_store import SipAccounts


class Vault:
    def __init__(self):
        self.values = {}

    def save(self, key, value):
        self.values[key] = value

    def load(self, key, **options):
        return self.values[key]

    def remove(self, key):
        self.values.pop(key, None)


def test_saved_password_never_appears_in_metadata_or_public_account(tmp_path):
    vault = Vault()
    store = SipAccounts(tmp_path / "sip.json", vault)
    row = store.save(
        {"extension": "1234", "password": "should-be-discarded"}, "test-secret"
    )
    assert store.password(row["id"]) == "test-secret"
    assert "test-secret" not in store.path.read_text() and "password" not in row
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    restored = SipAccounts(store.path, vault)
    assert (
        restored.selected == row["id"] and restored.password(row["id"]) == "test-secret"
    )
    restored.remove(row["id"])
    assert not restored.accounts and not vault.values


def test_session_only_password_does_not_survive_restart(tmp_path):
    vault = Vault()
    store = SipAccounts(tmp_path / "sip.json", vault)
    row = store.save({"extension": "1234", "save_password": False}, "session-secret")
    assert not vault.values
    assert store.password(row["id"]) == "session-secret"
    with pytest.raises(ValueError, match="Enter"):
        SipAccounts(store.path, vault).password(row["id"])


def test_vault_failure_does_not_commit_account_or_plaintext(tmp_path):
    class Failed(Vault):
        def save(self, key, value):
            raise ValueError("locked")

    store = SipAccounts(tmp_path / "sip.json", Failed())
    with pytest.raises(ValueError):
        store.save({"extension": "1234"}, "secret")
    assert store.accounts == [] and not store.path.exists()


def test_edit_can_keep_password_or_stop_saving_it(tmp_path):
    vault = Vault()
    store = SipAccounts(tmp_path / "sip.json", vault)
    row = store.save({"extension": "1234"}, "saved")
    row = store.save({**row, "label": "Edited"}, "")
    assert store.password(row["id"]) == "saved"
    store.save({**row, "save_password": False}, None)
    assert not vault.values and store.password(row["id"]) == "saved"


@pytest.mark.parametrize(
    "fields",
    [
        {"host": "host;injection"},
        {"port": True},
        {"allowed_networks": []},
        {"allowed_networks": ["i2p"]},
        {"save_password": "yes"},
        {"label": "x\npassword"},
    ],
)
def test_invalid_account_never_reaches_vault(tmp_path, fields):
    vault = Vault()
    store = SipAccounts(tmp_path / "sip.json", vault)
    with pytest.raises(ValueError):
        store.save({"extension": "1234", **fields}, "secret")
    assert not vault.values and not store.path.exists()
