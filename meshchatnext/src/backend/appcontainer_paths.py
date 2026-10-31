# SPDX-License-Identifier: 0BSD
"""Preserve handle-based canonicalization when AppContainer denies DOS mapping.

The container cannot query the volume mount manager. Resolve using the NT
volume name from the same read-attributes handle, never a lexical path fallback.
"""

from __future__ import annotations

import ctypes
import ntpath
import os

from meshchatnext.src.backend.appcontainer_security import is_appcontainer_process


def _final_nt_path(path):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    create.restype = ctypes.c_void_p
    # Read attributes only; sharing and directory support mirror realpath.
    handle = create(os.fsdecode(path), 0x80, 7, None, 3, 0x02000000, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        final = kernel.GetFinalPathNameByHandleW
        final.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        final.restype = ctypes.c_ulong
        size = 512
        while size <= 32768:
            buffer = ctypes.create_unicode_buffer(size)
            length = final(handle, buffer, size, 2)  # VOLUME_NAME_NT, normalized.
            if not length:
                raise ctypes.WinError(ctypes.get_last_error())
            if length < size:
                value = buffer.value
                if not value.startswith("\\Device\\"):
                    raise OSError("Unexpected canonical NT volume name")
                canonical = "\\\\?\\GLOBALROOT" + value
                return os.fsencode(canonical) if isinstance(path, bytes) else canonical
            size = length + 1
        raise OSError("Canonical NT path exceeds supported length")
    finally:
        close = kernel.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        close(handle)


def install_private_path_compat():
    if os.name != "nt" or not is_appcontainer_process():
        return False
    original = getattr(ntpath, "_getfinalpathname", None)
    if original is None:
        raise RuntimeError("Windows canonical path resolver is unavailable")
    if getattr(original, "_meshchat_container_canonical", False):
        return True

    def resolve(path):
        try:
            return original(path)
        except OSError as error:
            if getattr(error, "winerror", None) != 5:
                raise
            return _final_nt_path(path)

    resolve._meshchat_container_canonical = True
    ntpath._getfinalpathname = resolve
    return True
