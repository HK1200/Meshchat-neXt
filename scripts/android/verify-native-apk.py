#!/usr/bin/env python3
"""Audit every native payload, including nested Chaquopy archives and versioned .so files."""

import argparse
import hashlib
import io
import json
import struct
import zipfile
from collections import Counter
from pathlib import Path


def inspect(name, data):
    if len(data) < 52 or data[:4] != b"\x7fELF" or data[5] != 1:
        raise ValueError(f"Expected little-endian ELF: {name}")
    elf_class = data[4]
    machine = struct.unpack_from("<H", data, 18)[0]
    abi = {(2, 183): "arm64-v8a", (2, 62): "x86_64", (1, 40): "armeabi-v7a"}.get(
        (elf_class, machine)
    )
    if abi is None:
        raise ValueError(f"Unsupported ELF architecture: {name}")
    if elf_class == 2:
        if len(data) < 64:
            raise ValueError(f"Truncated ELF header: {name}")
        start = struct.unpack_from("<Q", data, 32)[0]
        size, count = struct.unpack_from("<HH", data, 54)
        minimum = 56
    else:
        start = struct.unpack_from("<I", data, 28)[0]
        size, count = struct.unpack_from("<HH", data, 42)
        minimum = 32
    if size < minimum or start + size * count > len(data):
        raise ValueError(f"Truncated ELF program headers: {name}")
    headers = []
    for i in range(count):
        if elf_class == 2:
            headers.append(struct.unpack_from("<IIQQQQQQ", data, start + i * size))
        else:
            kind, offset, address, physical, files, memory, flags, alignment = (
                struct.unpack_from("<IIIIIIII", data, start + i * size)
            )
            headers.append(
                (kind, flags, offset, address, physical, files, memory, alignment)
            )
    # 64-bit releases retain the 16 KB requirement. ARMv7 uses 4 KB pages.
    page_size = 16384 if elf_class == 2 else 4096
    loads = [p for p in headers if p[0] == 1]
    if not loads or any(p[7] < page_size or (p[2] - p[3]) % page_size for p in loads):
        raise ValueError(f"{page_size // 1024} KB LOAD alignment failed: {name}")
    for p in (p for p in headers if p[0] == 0x6474E552):
        end = p[3] + p[6]
        boundary = (end + page_size - 1) // page_size * page_size
        if end < boundary and any(
            q[1] & 2 and max(end, q[3]) < min(boundary, q[3] + q[6]) for q in loads
        ):
            raise ValueError(f"{page_size // 1024} KB RELRO layout failed: {name}")
    return {"path": name, "abi": abi, "sha256": hashlib.sha256(data).hexdigest()}


def collect(archive, prefix=""):
    rows = []
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        if ".so" in Path(name).name:
            row = inspect(prefix + name, archive.read(name))
            # Only ARMv7 uses the official Chaquopy GNU Fortran runtime.
            if (
                "libgfortran" in name and row["abi"] != "armeabi-v7a"
            ) or "filterlib.cpython-" in name:
                raise ValueError(
                    f"Unexpected legacy/desktop native payload: {prefix + name}"
                )
            rows.append(row)
        elif name.endswith(".imy"):
            data = io.BytesIO(archive.read(name))
            if zipfile.is_zipfile(data):
                with zipfile.ZipFile(data) as nested:
                    rows.extend(collect(nested, prefix + name + "!"))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--abis", required=True)
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        help="Previously validated native APK inventory JSON",
    )
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    abis = set(args.abis.split(","))
    reference = json.loads(args.reference.read_text())["libraries"]
    expected = Counter((r["abi"], r["sha256"]) for r in reference if r["abi"] in abis)
    with zipfile.ZipFile(args.apk) as archive:
        rows = collect(archive)
    actual = Counter((r["abi"], r["sha256"]) for r in rows)
    if not expected or actual != expected or {r["abi"] for r in rows} != abis:
        raise ValueError(
            "Packaged native library inventory differs from the validated reference"
        )
    args.report.write_text(
        json.dumps(
            {
                "apk_sha256": hashlib.sha256(args.apk.read_bytes()).hexdigest(),
                "libraries": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"PASS: {len(rows)} native ELF payloads match the validated reference and pass the ABI-specific page layout checks"
    )


if __name__ == "__main__":
    main()
