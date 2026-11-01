# SPDX-License-Identifier: 0BSD
"""Preserve private mkdir(0700) semantics for the current Windows container.

CPython issue134587: its Windows private-directory ACL omits the container SID.
Use an explicit private ACL at creation, never a permissive inheritance fallback.
"""

import ctypes
import os
import sys

from meshchatnext.src.backend.appcontainer_security import token_sid


def install_private_directory_compat():
    if os.name != "nt":
        return False
    try:
        package_sid = token_sid(31)
        user_sid = token_sid(1)
    except OSError:
        return False
    if not package_sid.startswith("S-1-15-2-"):
        return False
    if getattr(os.mkdir, "_meshchat_container_private", False):
        return True
    original = os.mkdir
    sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{user_sid})(A;OICI;FA;;;{package_sid})"

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("descriptor", ctypes.c_void_p),
            ("inherit", ctypes.c_int),
        ]

    def mkdir(path, mode=0o777, *, dir_fd=None):
        if mode != 0o700 or dir_fd is not None:
            return original(path, mode, dir_fd=dir_fd)
        sys.audit("os.mkdir", path, mode, -1)
        native_path = os.fsdecode(os.fspath(path))
        if "\0" in native_path:
            raise ValueError("embedded null character")
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        convert = adv.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
        ]
        descriptor = ctypes.c_void_p()
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateDirectoryW
        create.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(SecurityAttributes)]
        create.restype = ctypes.c_int
        try:
            attributes = SecurityAttributes(
                ctypes.sizeof(SecurityAttributes), descriptor, False
            )
            if not create(native_path, ctypes.byref(attributes)):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree(descriptor)

    mkdir._meshchat_container_private = True
    os.mkdir = mkdir
    return True
