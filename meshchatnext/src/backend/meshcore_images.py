# SPDX-License-Identifier: MIT
"""Bounded Open TAK AV1 still images, with pixel-only PNG previews."""

from __future__ import annotations

import base64
import ctypes
import struct
import sys
import threading
import zlib
from pathlib import Path

from meshchatnext.src.env_utils import env_str

_LOCK = threading.Lock()
MAX_BYTES = 64 * 156


def library():
    configured = env_str("MESHCHAT_AV1_LIBRARY")
    candidates = [configured] if configured else []
    if getattr(sys, "frozen", False):
        candidates.append(
            str(Path(sys.executable).resolve().parent / "lib/libvox_av1.so")
        )
    native = env_str("MESHCHAT_NATIVE_LIB_DIR")
    if native:
        candidates.append(str(Path(native) / "libvox_av1.so"))
    candidates += [
        str(Path(__file__).resolve().parents[3] / ".local/av1/libvox_av1.so"),
        str(Path(__file__).resolve().parents[3] / "temp-tests/av1-build/libvox_av1.so"),
        "libvox_av1.so",
    ]
    for path in candidates:
        try:
            lib = ctypes.CDLL(path)
            pointer = ctypes.POINTER(ctypes.c_uint8)
            lib.vox_av1_encode.argtypes = [
                pointer,
                *([ctypes.c_int] * 5),
                pointer,
                ctypes.c_int,
            ]
            lib.vox_av1_encode.restype = ctypes.c_int
            lib.vox_av1_decode.argtypes = [
                pointer,
                ctypes.c_int,
                pointer,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_int),
            ]
            lib.vox_av1_decode.restype = ctypes.c_int
            return lib
        except OSError:
            continue
    raise ValueError("Photo codec is unavailable in this build")


def png(rgb, width, height):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    scan = b"".join(
        b"\x00" + rgb[y * width * 3 : (y + 1) * width * 3] for y in range(height)
    )
    value = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scan))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(value).decode()


def _decode(lib, data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Invalid image length")
    source = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    output = (ctypes.c_uint8 * (1024 * 1024 * 3))()
    w, h = ctypes.c_int(), ctypes.c_int()
    if (
        lib.vox_av1_decode(
            source, len(data), output, 1024, 1024, ctypes.byref(w), ctypes.byref(h)
        )
        != 1
    ):
        raise ValueError("Image is invalid or exceeds 1024 pixels per side")
    return bytes(output[: w.value * h.value * 3]), w.value, h.value


def decode_image(data):
    if not isinstance(data, bytes) or not 2 <= len(data) <= MAX_BYTES:
        raise ValueError("Invalid image payload")
    if data[0] == 1:
        obus = data[1:]
    elif data[0] == 2 and len(data) > 2 + data[1]:
        obus = data[2 + data[1] :]
    else:
        raise ValueError("Unsupported image payload version")
    with _LOCK:
        rgb, w, h = _decode(library(), obus)
    return {"png_base64": png(rgb, w, h), "width": w, "height": h}


def encode_image(rgb_base64, width, height):
    import numpy as np

    if any(type(n) is not int or not 1 <= n <= 512 for n in (width, height)):
        raise ValueError("Photo preparation requires at most 512 pixels per side")
    if not isinstance(rgb_base64, str) or len(rgb_base64) > 1048576:
        raise ValueError("Photo pixel data exceeds limit")
    try:
        rgb = base64.b64decode(rgb_base64, validate=True)
    except Exception:
        raise ValueError("Invalid photo pixels") from None
    if len(rgb) != width * height * 3:
        raise ValueError("Invalid photo dimensions")
    if not 1 / 6 <= width / height <= 6:
        raise ValueError("Crop the photo to an aspect ratio between 1:6 and 6:1")
    original = np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)
    payload = None
    with _LOCK:
        lib = library()
        for side in (384, 256, 160, 96, 64):
            scale = min(1, side / max(width, height))
            w, h = max(1, round(width * scale)), max(1, round(height * scale))
            small = original[
                np.minimum((np.arange(h) * height / h).astype(int), height - 1)[
                    :, None
                ],
                np.minimum((np.arange(w) * width / w).astype(int), width - 1)[None, :],
            ].tobytes()
            source = (ctypes.c_uint8 * len(small)).from_buffer_copy(small)
            output = (ctypes.c_uint8 * 65536)()
            for q in (32, 44, 54, 63):
                count = lib.vox_av1_encode(source, w, h, q, 10, 2, output, 65536)
                if 0 < count <= 2749:
                    payload = b"\x01" + bytes(output[:count])
                    pixels, w, h = _decode(lib, payload[1:])
                    break
            if payload:
                break
    if payload is None:
        raise ValueError("Could not fit photo into the radio budget")
    return (
        payload,
        min(600, max(1, round(width * 100 / height))),
        {
            "png_base64": png(pixels, w, h),
            "width": w,
            "height": h,
            "bytes": len(payload),
        },
    )
