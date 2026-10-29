# SPDX-License-Identifier: MIT
"""Windows Credential Manager slots; no plaintext file or roaming fallback.

Generic credentials use the current Windows user's local-machine persistence.
https://learn.microsoft.com/windows/win32/api/wincred/ns-wincred-credentialw
"""

import ctypes as ct
import sys

from meshchatnext.src.backend.meshcore_store import public_key


class _FileTime(ct.Structure):
    _fields_ = [("low", ct.c_uint32), ("high", ct.c_uint32)]


class _Credential(ct.Structure):
    _fields_ = [
        ("flags", ct.c_uint32),
        ("type", ct.c_uint32),
        ("target", ct.c_wchar_p),
        ("comment", ct.c_wchar_p),
        ("written", _FileTime),
        ("size", ct.c_uint32),
        ("blob", ct.POINTER(ct.c_ubyte)),
        ("persist", ct.c_uint32),
        ("attribute_count", ct.c_uint32),
        ("attributes", ct.c_void_p),
        ("alias", ct.c_wchar_p),
        ("username", ct.c_wchar_p),
    ]


class _CredentialManager:
    def __init__(self):
        if sys.platform != "win32":
            raise ValueError("Windows Credential Manager is unavailable")
        self.api = ct.WinDLL("Advapi32.dll", use_last_error=True)
        self.api.CredReadW.argtypes = [
            ct.c_wchar_p,
            ct.c_uint32,
            ct.c_uint32,
            ct.POINTER(ct.POINTER(_Credential)),
        ]
        self.api.CredReadW.restype = ct.c_int
        self.api.CredWriteW.argtypes = [ct.POINTER(_Credential), ct.c_uint32]
        self.api.CredWriteW.restype = ct.c_int
        self.api.CredDeleteW.argtypes = [ct.c_wchar_p, ct.c_uint32, ct.c_uint32]
        self.api.CredDeleteW.restype = ct.c_int
        self.api.CredFree.argtypes = [ct.c_void_p]
        self.api.CredFree.restype = None

    @staticmethod
    def _error():
        if (
            ct.get_last_error() == 1168
        ):  # ERROR_NOT_FOUND only; access denied is not absence.
            raise FileNotFoundError("Saved password slot is missing")
        raise ValueError("Windows Credential Manager could not complete this request")

    def read(self, target, *, presence_only=False, max_size=64):
        credential = ct.POINTER(_Credential)()
        if not self.api.CredReadW(target, 1, 0, ct.byref(credential)):
            self._error()
        try:
            value = credential.contents
            if value.type != 1 or value.target != target or value.size > max_size:
                raise ValueError("Invalid saved password slot")
            if presence_only:
                return True
            return ct.string_at(value.blob, value.size)
        finally:
            self.api.CredFree(credential)

    def write(self, target, secret):
        buffer = (ct.c_ubyte * len(secret)).from_buffer_copy(secret)
        value = _Credential(
            type=1,
            target=target,
            size=len(secret),
            blob=buffer,
            persist=2,
            username="Meshchat neXt",
        )
        try:
            if not self.api.CredWriteW(ct.byref(value), 0):
                self._error()
        finally:
            ct.memset(buffer, 0, len(secret))

    def delete(self, target):
        if not self.api.CredDeleteW(target, 1, 0) and ct.get_last_error() != 1168:
            self._error()


class WindowsNodePasswords:
    def __init__(self, api=None):
        self._api = api if api is not None else _CredentialManager()

    @staticmethod
    def slot(owner, peer, role):
        if role not in ("member", "admin"):
            raise ValueError("Invalid password role")
        return f"org.meshchatnext.node-passwords/v1/{public_key(owner)}/{public_key(peer)}/{role}"

    def has(self, owner, peer, role):
        try:
            return (
                self._api.read(self.slot(owner, peer, role), presence_only=True) is True
            )
        except FileNotFoundError:
            return False

    def save(self, owner, peer, role, password):
        target = self.slot(owner, peer, role)
        if (
            not isinstance(password, str)
            or "\0" in password
            or len(password.encode("utf-8")) > 64
        ):
            raise ValueError("Password must contain at most 64 UTF-8 bytes without NUL")
        self._api.write(target, password.encode("utf-8"))

    def load(self, owner, peer, role):
        return self._api.read(self.slot(owner, peer, role)).decode("utf-8")

    def forget(self, owner, peer, role):
        self._api.delete(self.slot(owner, peer, role))
