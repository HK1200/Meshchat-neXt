#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Verify an embedded source signature without a local identity cache or radio."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from RNS.Utilities.rnid import extract_signed_rsg_data, validate_rsg

KINDS = {
    "next": (
        "meshchatnext.rsm",
        "87b2973e252645589a1543010e9fcda1",
        "# meshchatnext tree manifest v1",
    ),
    "hk": (
        "meshchatx.rsm",
        "4d3aaedcc9aab76c61353deed5adfb8c",
        "# meshchatx tree manifest v1",
    ),
}


def verify(root: Path, manifest: str, signer: str, header: str) -> dict[str, object]:
    raw = (root / manifest).read_bytes()
    envelope = extract_signed_rsg_data(raw)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("message"), bytes):
        raise ValueError("Missing signed source inventory")
    body = envelope["message"]
    valid, _, identity = validate_rsg(
        raw, message=body, required_signer=bytes.fromhex(signer)
    )
    if not valid or identity is None:
        raise ValueError("Pinned source signature verification failed")
    lines = body.decode("utf-8").splitlines()
    if not lines or lines[0] != header:
        raise ValueError("Unexpected source inventory format")
    inventory = {}
    for line in lines[1:]:
        if not line:
            continue
        digest, name = line.split("  ", 1)
        if (
            name in inventory
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Invalid or duplicate source inventory entry")
        inventory[name] = digest
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required for the full tracked inventory")
    tracked = (
        subprocess.check_output([git, "ls-files", "-z"], cwd=root)
        .decode("utf-8")
        .split("\0")
    )
    expected = {
        name
        for name in tracked
        if name
        and name != manifest
        and not (
            name.startswith("vendor/") or "/vendor/" in name or name.endswith("/vendor")
        )
    }
    if set(inventory) != expected:
        raise ValueError(
            "Signed source does not cover the exact full tracked inventory"
        )
    for name, digest in inventory.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Signed source file hash mismatch: {name}")
    return {
        "passed": True,
        "signer": identity.hash.hex(),
        "tracked_files": len(expected),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(Path(__file__).resolve().parents[2], *KINDS[args.kind])))


if __name__ == "__main__":
    main()
