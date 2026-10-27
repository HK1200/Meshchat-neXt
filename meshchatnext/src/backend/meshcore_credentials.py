# SPDX-License-Identifier: MIT
"""Platform secure credentials; no plaintext or temporary-storage fallback."""

from meshchatnext.src.backend.meshcore_store import public_key
from meshchatnext.src.backend.meshcore_transport import transport_platform


class NodePasswords:
    def __init__(self, provider=None):
        self._provider = provider
        self._attempted = provider is not None

    def provider(self):
        if not self._attempted:
            self._attempted = True
            try:
                if transport_platform() == "linux":
                    from meshchatnext.src.backend.meshcore_desktop_credentials import (
                        DesktopNodePasswords,
                    )

                    self._provider = DesktopNodePasswords()
                elif transport_platform() == "android":
                    from java import jclass
                    from usb4a.usb import get_context

                    self._provider = jclass(
                        "com.meshchatnext.meshcore.SecureNodePasswords"
                    )(get_context().getApplicationContext())
            except Exception:
                self._provider = None
        return self._provider

    @staticmethod
    def slot(owner, peer, role):
        if role not in ("member", "admin"):
            raise ValueError("Invalid password role")
        return public_key(owner), public_key(peer), role

    def status(self, owner, peer):
        owner, peer, _ = self.slot(owner, peer, "member")
        provider = self.provider()
        try:
            roles = [
                r
                for r in ("member", "admin")
                if provider and provider.has(owner, peer, r)
            ]
            return {"available": provider is not None, "saved_roles": roles}
        except Exception:
            return {"available": False, "saved_roles": []}

    def save(self, owner, peer, role, password):
        slot = self.slot(owner, peer, role)
        if (
            not isinstance(password, str)
            or "\0" in password
            or len(password.encode()) > 64
        ):
            raise ValueError("Password must contain at most 64 UTF-8 bytes without NUL")
        self._call("save", *slot, password)

    def load(self, owner, peer, role):
        return str(self._call("load", *self.slot(owner, peer, role)))

    def forget(self, owner, peer, role):
        self._call("forget", *self.slot(owner, peer, role))

    def _call(self, method, *args):
        provider = self.provider()
        if provider is None:
            raise ValueError("Secure password storage is unavailable on this device")
        try:
            return getattr(provider, method)(*args)
        except Exception:
            raise ValueError(
                "Secure password storage could not complete this request"
            ) from None
