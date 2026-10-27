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
    if not manifest.get("tag", "").startswith("linux-v") or (
        tag != "linux-stable" and manifest["tag"] != tag
    ):
        raise ValueError("Wrong Linux release tag")
    if not re.fullmatch(r"linux-v[0-9]+\.[0-9]+\.[0-9]+", manifest["tag"]) or manifest[
        "tag"
    ] != "linux-v" + manifest.get("version", ""):
        raise ValueError("Invalid Linux version tag")
    artifacts = manifest.get("artifacts", [])
    if len(artifacts) != 2 or {a.get("kind") for a in artifacts} != {"deb", "appimage"}:
        raise ValueError("Expected exactly the Linux deb and AppImage")
    for artifact in artifacts:
        name = artifact["file"]
        if (
            Path(name).name != name
            or artifact.get("platform") != "linux"
            or artifact.get("arch") != "x86_64"
        ):
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
