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
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError(f"Expected little-endian ELF64: {name}")
    machine = struct.unpack_from("<H", data, 18)[0]
    abi = {183: "arm64-v8a", 62: "x86_64"}.get(machine)
    if abi is None:
        raise ValueError(f"Unsupported ELF architecture: {name}")
    start = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    headers = [
        struct.unpack_from("<IIQQQQQQ", data, start + i * size) for i in range(count)
    ]
    loads = [p for p in headers if p[0] == 1]
    if not loads or any(p[7] < 16384 or (p[2] - p[3]) % 16384 for p in loads):
        raise ValueError(f"16 KB LOAD alignment failed: {name}")
    for p in (p for p in headers if p[0] == 0x6474E552):
        end = p[3] + p[6]
        boundary = (end + 16383) // 16384 * 16384
        if end < boundary and any(
            q[1] & 2 and max(end, q[3]) < min(boundary, q[3] + q[6]) for q in loads
        ):
            raise ValueError(f"16 KB RELRO layout failed: {name}")
    return {"path": name, "abi": abi, "sha256": hashlib.sha256(data).hexdigest()}


def collect(archive, prefix=""):
    rows = []
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        if ".so" in Path(name).name:
            if "libgfortran" in name or "filterlib.cpython-" in name:
                raise ValueError(
                    f"Unexpected legacy/desktop native payload: {prefix + name}"
                )
            rows.append(inspect(prefix + name, archive.read(name)))
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
        f"PASS: {len(rows)} native ELF payloads match the validated reference and pass 16 KB layout checks"
    )


if __name__ == "__main__":
    main()
