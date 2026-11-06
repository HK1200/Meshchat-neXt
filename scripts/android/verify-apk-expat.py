#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Reject APKs whose actual Chaquopy parser bytes differ from the fixed build."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path


def verify(apk: Path, provenance: dict, expected_abis: set[str]) -> dict:
    if (
        provenance.get("python_kernel") != "3.11.17"
        or provenance.get("expat") != "2.10.0"
        or provenance.get("cpython_source")
        != "e6392eb68a39cef49c9fe6431253050caa17a426"
        or provenance.get("inputs", {}).get("expat-2.10.0.tar.xz")
        != "c624ba2998fc65df1163a49641ff3f9ab73138b11641d92c86bee0fb01b1bc7f"
    ):
        raise ValueError("Parser build provenance is not the pinned security backport")
    records = provenance["abis"]
    hashes = {r["abi"]: r["module_sha256"] for r in records}
    if len(hashes) != len(records) or set(hashes) != expected_abis:
        raise ValueError("Parser build ABI inventory mismatch")
    found = {}
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate APK entries")
        for abi in expected_abis:
            name = f"assets/chaquopy/stdlib-{abi}.imy"
            if name not in names:
                continue
            if archive.getinfo(name).file_size > 128 * 1024 * 1024:
                raise ValueError("Oversized packaged standard library")
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as stdlib:
                member = "pyexpat.cpython-311.so"
                if stdlib.namelist().count(member) != 1:
                    raise ValueError("Missing or duplicate packaged parser")
                if stdlib.getinfo(member).file_size > 32 * 1024 * 1024:
                    raise ValueError("Oversized packaged parser")
                digest = hashlib.sha256(stdlib.read(member)).hexdigest()
            if digest != hashes[abi]:
                raise ValueError(f"Stale or altered packaged parser for {abi}")
            found[abi] = digest
        actual = {
            name.removeprefix("assets/chaquopy/stdlib-").removesuffix(".imy")
            for name in names
            if name.startswith("assets/chaquopy/stdlib-")
            and name.endswith(".imy")
            and name != "assets/chaquopy/stdlib-common.imy"
        }
        if not found or actual != set(found):
            raise ValueError("APK contains unqualified or missing parser ABIs")
    with apk.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"apk": apk.name, "apk_sha256": digest, "parser_sha256": found}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--abis", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("apks", type=Path, nargs="+")
    args = parser.parse_args()
    expected = set(args.abis.split(","))
    if not expected or not expected <= {"arm64-v8a", "x86_64", "armeabi-v7a"}:
        raise ValueError("Unexpected Android ABI selection")
    provenance = json.loads(args.provenance.read_text())
    reports = [verify(apk, provenance, expected) for apk in args.apks]
    if set().union(*(set(r["parser_sha256"]) for r in reports)) != expected:
        raise ValueError("Complete APK ABI coverage is missing")
    result = {
        "passed": True,
        "scope": "Exact packaged parser bytes, not native runtime execution",
        "apks": reports,
    }
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
