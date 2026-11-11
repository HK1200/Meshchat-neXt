#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Verify the pinned signed Linux update manifest and hosted package bytes."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from meshchatnext.src.update_rsm import APP_ID, SCHEMA, verify_rsm


def verify(folder, signer, tag, *, manifest_only=False):
    manifest = verify_rsm(
        (folder / "latest.rsm").read_bytes(), required_signer_hash=bytes.fromhex(signer)
    )
    if json.loads((folder / "latest.json").read_text()) != manifest:
        raise ValueError("Readable and signed manifests differ")
    if (
        manifest.get("app") != APP_ID
        or manifest.get("schema") != SCHEMA
        or manifest.get("track") != "release"
    ):
        raise ValueError("Unexpected Linux application, schema or track")
    package_tag = manifest.get("tag", "")
    version = manifest.get("version", "")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or package_tag not in {
        "v" + version,
        "linux-v" + version,
    }:
        raise ValueError("Invalid Linux version tag")
    if tag != "linux-stable" and package_tag != tag:
        raise ValueError("Wrong Linux release tag")
    artifacts = manifest.get("artifacts", [])
    expected = {("x86_64", "deb"), ("x86_64", "appimage")}
    if package_tag.startswith("v"):
        expected |= {("aarch64", "deb"), ("aarch64", "appimage")}
    if (
        len(artifacts) != len(expected)
        or {(a.get("arch"), a.get("kind")) for a in artifacts} != expected
    ):
        raise ValueError("Expected Linux deb and AppImage pairs for the release")
    for artifact in artifacts:
        name = artifact["file"]
        if Path(name).name != name or artifact.get("platform") != "linux":
            raise ValueError("Unexpected artifact path or platform")
        if manifest_only:
            continue
        payload = folder / name
        if (
            payload.stat().st_size != artifact["size"]
            or hashlib.sha256(payload.read_bytes()).hexdigest() != artifact["sha256"]
        ):
            raise ValueError("Package size or checksum mismatch")
    return {
        "passed": True,
        "tag": manifest["tag"],
        "version": manifest["version"],
        "artifacts": len(artifacts),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--signer", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    result = verify(
        args.folder, args.signer, args.tag, manifest_only=args.manifest_only
    )
    print(result["tag"] if args.manifest_only else json.dumps(result))
