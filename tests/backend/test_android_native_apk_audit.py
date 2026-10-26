import importlib.util
import io
import struct
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "next_native_apk_audit",
    Path(__file__).parents[2] / "scripts/android/verify-native-apk.py",
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def elf(bits=32, machine=40, alignment=4096):
    start, size = (52, 32) if bits == 32 else (64, 56)
    data = bytearray(start + size)
    data[:7] = b"\x7fELF" + bytes([1 if bits == 32 else 2, 1, 1])
    struct.pack_into("<H", data, 18, machine)
    if bits == 32:
        struct.pack_into("<I", data, 28, start)
        struct.pack_into("<HH", data, 42, size, 1)
        struct.pack_into(
            "<IIIIIIII", data, start, 1, 0, 0, 0, len(data), len(data), 5, alignment
        )
    else:
        struct.pack_into("<Q", data, 32, start)
        struct.pack_into("<HH", data, 54, size, 1)
        struct.pack_into(
            "<IIQQQQQQ", data, start, 1, 5, 0, 0, 0, len(data), len(data), alignment
        )
    return bytes(data)


def test_accepts_real_armv7_header_layout():
    assert audit.inspect("arm.so", elf())["abi"] == "armeabi-v7a"


@pytest.mark.parametrize("machine,abi", [(62, "x86_64"), (183, "arm64-v8a")])
def test_keeps_64_bit_alignment_requirement(machine, abi):
    assert audit.inspect("64.so", elf(64, machine, 16384))["abi"] == abi
    with pytest.raises(ValueError, match="16 KB LOAD"):
        audit.inspect("bad.so", elf(64, machine, 4096))


@pytest.mark.parametrize(
    "data", [b"\x7fELF", elf()[:60], elf(32, 183), elf(64, 40, 16384)]
)
def test_rejects_truncated_or_mismatched_architectures(data):
    with pytest.raises(ValueError):
        audit.inspect("bad.so", data)


def test_rejects_under_aligned_32_bit_library():
    with pytest.raises(ValueError, match="4 KB LOAD"):
        audit.inspect("bad.so", elf(alignment=1024))


@pytest.mark.parametrize(
    "bits,machine,alignment,allowed", [(32, 40, 4096, True), (64, 62, 16384, False)]
)
def test_gnu_fortran_is_only_allowed_for_armv7(bits, machine, alignment, allowed):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("lib/libgfortran.so", elf(bits, machine, alignment))
    with zipfile.ZipFile(stream) as z:
        if allowed:
            assert len(audit.collect(z)) == 1
        else:
            with pytest.raises(ValueError, match="legacy/desktop"):
                audit.collect(z)
