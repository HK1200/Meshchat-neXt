# SPDX-License-Identifier: MIT
"""Linux Secret Service storage for explicitly saved MeshCore node passwords.

No file fallback, temporary collection, or passive unlock prompts. Each operation
owns and closes its D-Bus connection; attributes identify only this application's
owner/peer/role slot, never the password itself.
"""

from contextlib import closing

from meshchatnext.src.backend.meshcore_store import public_key


class DesktopNodePasswords:
    def __init__(self, service=None):
        # Import is lazy: polling the page must not start a keyring or a prompt.
        self._service = service

    def _api(self):
        if self._service is None:
            import secretstorage

            self._service = secretstorage
        return self._service

    @staticmethod
    def _attributes(owner, peer, role):
        if role not in ("member", "admin"):
            raise ValueError("Invalid password role")
        return {
            "application": "org.meshchatnext.node-passwords",
            "schema": "1",
            "owner": public_key(owner),
            "peer": public_key(peer),
            "role": role,
        }

    def _operate(self, owner, peer, role, action, *, unlock=False):
        attributes = self._attributes(owner, peer, role)
        api = self._api()
        with closing(api.dbus_init()) as connection:
            if not api.check_service_availability(connection):
                raise ValueError("Secure password storage is unavailable")
            # Unlike get_default_collection, this never creates a collection or
            # silently selects an ephemeral session collection.
            collection = api.get_collection_by_alias(connection, "default")
            if collection.is_locked():
                if not unlock:
                    return False
                collection.unlock(timeout=30)
                if collection.is_locked():
                    raise ValueError("Secure password storage remains locked")
            return action(collection, attributes)

    def has(self, owner, peer, role):
        return self._operate(
            owner,
            peer,
            role,
            lambda collection, attrs: any(collection.search_items(attrs)),
        )

    def save(self, owner, peer, role, password):
        if (
            not isinstance(password, str)
            or "\0" in password
            or len(password.encode()) > 64
        ):
            raise ValueError("Invalid password")

        def store(collection, attrs):
            collection.create_item(
                "Meshchat neXt · MeshCore node password",
                attrs,
                password.encode("utf-8"),
                replace=True,
            )

        self._operate(owner, peer, role, store, unlock=True)

    def load(self, owner, peer, role):
        def read(collection, attrs):
            items = list(collection.search_items(attrs))
            if len(items) != 1:
                raise ValueError("Saved password slot is missing or ambiguous")
            return items[0].get_secret().decode("utf-8")

        return self._operate(owner, peer, role, read, unlock=True)

    def forget(self, owner, peer, role):
        def remove(collection, attrs):
            for item in collection.search_items(attrs):
                item.delete()

        self._operate(owner, peer, role, remove, unlock=True)
