# SPDX-License-Identifier: 0BSD
"""Read actual Windows token identity, independent of environment markers."""

from __future__ import annotations

import ctypes
import os


def _kernel():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _close(handle):
    fn = _kernel().CloseHandle
    fn.argtypes = [ctypes.c_void_p]
    fn(handle)


def token_sid(info_class):
    kernel = _kernel()
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.OpenProcessToken.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    token = ctypes.c_void_p()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    output = ctypes.c_wchar_p()
    try:
        query = advapi.GetTokenInformation
        query.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        size = ctypes.c_ulong()
        query(token, info_class, None, 0, ctypes.byref(size))
        if not size.value:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(size.value)
        if not query(token, info_class, buffer, len(buffer), ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.c_void_p.from_buffer(buffer)
        advapi.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(output)):
            raise ctypes.WinError(ctypes.get_last_error())
        return output.value
    finally:
        if output:
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree(ctypes.cast(output, ctypes.c_void_p))
        _close(token)


def is_appcontainer_process():
    if os.name != "nt":
        return False
    try:
        sid = token_sid(31)
        return bool(sid and sid.startswith("S-1-15-2-"))
    except OSError:
        return False
