# SPDX-License-Identifier: MIT
"""Desktop SIP account metadata with passwords kept exclusively in Secret Service."""

import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from contextlib import closing
from pathlib import Path


class SipPasswords:
    def __init__(self, profile, service=None):
        self.profile = hashlib.sha256(str(Path(profile).resolve()).encode()).hexdigest()
        self.service = service
        self._windows = None

    def _call(self, account_id, action, *, interactive=True):
        account_id = str(uuid.UUID(account_id))
        api = self.service
        if api is None:
            import secretstorage

            api = secretstorage
        attrs = {
            "application": "org.meshchatnext.sip",
            "profile": self.profile,
            "account": account_id,
        }
        try:
            with closing(api.dbus_init()) as connection:
                if not api.check_service_availability(connection):
                    raise ValueError("unavailable")
                collection = api.get_collection_by_alias(connection, "default")
                if collection.is_locked():
                    if not interactive:
                        raise ValueError("locked")
                    collection.unlock(timeout=30)
                    if collection.is_locked():
                        raise ValueError("locked")
                return action(collection, attrs)
        except Exception:
            raise ValueError(
                "Secure SIP password storage could not complete this request"
            ) from None

    def _windows_call(self, action):
        try:
            return action()
        except Exception:
            raise ValueError(
                "Secure SIP password storage could not complete this request"
            ) from None

    def _windows_slot(self, account_id):
        from meshchatnext.src.backend.meshcore_windows_credentials import (
            _CredentialManager,
        )

        if self._windows is None:
            self._windows = _CredentialManager()
        return f"org.meshchatnext.sip/v1/{self.profile}/{uuid.UUID(account_id)!s}"

    def save(self, account_id, password):
        if sys.platform == "win32" and self.service is None:
            target = self._windows_slot(account_id)
            if (
                not isinstance(password, str)
                or "\0" in password
                or len(password.encode()) > 256
            ):
                raise ValueError("Invalid SIP password")
            return self._windows_call(
                lambda: self._windows.write(target, password.encode())
            )
        return self._call(
            account_id,
            lambda c, a: c.create_item(
                "Meshchat neXt · SIP password", a, password.encode(), replace=True
            ),
        )

    def load(self, account_id, *, interactive=True):
        if sys.platform == "win32" and self.service is None:
            target = self._windows_slot(account_id)
            return self._windows_call(
                lambda: self._windows.read(target, max_size=256).decode()
            )

        def read(collection, attrs):
            items = list(collection.search_items(attrs))
            if len(items) != 1:
                raise ValueError("Missing or ambiguous saved password")
            return items[0].get_secret().decode()

        return self._call(account_id, read, interactive=interactive)

    def remove(self, account_id):
        if sys.platform == "win32" and self.service is None:
            target = self._windows_slot(account_id)
            return self._windows_call(lambda: self._windows.delete(target))

        def remove(collection, attrs):
            for item in collection.search_items(attrs):
                item.delete()

        return self._call(account_id, remove)


class SipAccounts:
    def __init__(self, path, vault=None):
        self.path = Path(path)
        self.vault = vault if vault is not None else SipPasswords(self.path.parent)
        self.session_passwords = {}
        self.accounts = []
        self.selected = ""
        self.enabled = False
        self.feature_enabled = True
        if self.path.exists():
            if self.path.stat().st_size > 128 * 1024:
                raise ValueError("SIP account file is too large")
            data = json.loads(self.path.read_text())
            self.accounts = [
                self.validate(row, existing=True) for row in data.get("accounts", [])
            ]
            if len(self.accounts) > 32 or len({r["id"] for r in self.accounts}) != len(
                self.accounts
            ):
                raise ValueError("Invalid SIP account collection")
            self.selected = data.get("selected", "")
            if self.selected and not any(
                row["id"] == self.selected for row in self.accounts
            ):
                raise ValueError("Invalid selected SIP account")
            self.enabled = data.get("enabled") is True
            self.feature_enabled = data.get("feature_enabled", True) is not False

    @staticmethod
    def validate(row, existing=False):
        if not isinstance(row, dict):
            raise ValueError("Invalid SIP account")
        account_id = str(uuid.UUID(row["id"])) if row.get("id") else str(uuid.uuid4())
        user, host = row.get("extension", ""), row.get("host", "premium.hamsoverip.com")
        if not isinstance(user, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", user):
            raise ValueError("Check the SIP extension")
        if (
            not isinstance(host, str)
            or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host)
            or ".." in host
        ):
            raise ValueError("Check the SIP server")
        port = row.get("port", 5160)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Check the SIP server port")
        allowed = row.get("allowed_networks", ["wifi", "ethernet", "mobile"])
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(n not in ("wifi", "ethernet", "mobile") for n in allowed)
        ):
            raise ValueError("Select supported SIP connections")
        save = row.get("save_password", True)
        if type(save) is not bool:
            raise ValueError("Invalid saved-password option")
        label = row.get("label", user)
        if (
            not isinstance(label, str)
            or len(label) > 80
            or any(ord(c) < 32 for c in label)
        ):
            raise ValueError("Invalid SIP account label")
        # Rebuild from a whitelist, so neither imports nor API requests can put
        # password fields into the metadata file or public status.
        return {
            "id": account_id,
            "label": label,
            "extension": user,
            "host": host,
            "port": port,
            "allowed_networks": list(dict.fromkeys(allowed)),
            "network": "selected",
            "save_password": save,
        }

    def persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".sip-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(
                    {
                        "accounts": self.accounts,
                        "selected": self.selected,
                        "enabled": self.enabled,
                        "feature_enabled": self.feature_enabled,
                    },
                    file,
                )
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def find(self, account_id):
        for row in self.accounts:
            if row["id"] == account_id:
                return dict(row)
        raise ValueError("SIP account not found")

    def password(self, account_id, *, interactive=True):
        row = self.find(account_id)
        if account_id in self.session_passwords:
            return self.session_passwords[account_id]
        if row["save_password"]:
            return self.vault.load(account_id, interactive=interactive)
        raise ValueError("Enter the SIP account password")

    def save(self, row, password=None):
        account = self.validate(row)
        if row.get("id"):
            self.find(account["id"])
        elif len(self.accounts) >= 32:
            raise ValueError("Too many SIP accounts")
        if password == "" or password is None:
            password = self.password(account["id"]) if row.get("id") else None
        if (
            not isinstance(password, str)
            or not password
            or "\0" in password
            or len(password.encode()) > 256
        ):
            raise ValueError("Enter a SIP password of at most 256 UTF-8 bytes")
        if account["save_password"]:
            self.vault.save(account["id"], password)
        elif row.get("id") and self.find(account["id"])["save_password"]:
            self.vault.remove(account["id"])
        self.session_passwords[account["id"]] = password
        self.accounts = [r for r in self.accounts if r["id"] != account["id"]] + [
            account
        ]
        if not self.selected:
            self.selected = account["id"]
        self.persist()
        return dict(account)

    def remove(self, account_id):
        row = self.find(account_id)
        if row["save_password"]:
            self.vault.remove(account_id)
        self.accounts = [r for r in self.accounts if r["id"] != account_id]
        self.session_passwords.pop(account_id, None)
        if self.selected == account_id:
            self.selected = self.accounts[0]["id"] if self.accounts else ""
            self.enabled = False
        self.persist()
