#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Restore reviewed native inputs without silently replacing them with vendor fallbacks."""

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_EXPANDED = 384 * 1024 * 1024


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install_archive(archive, destination, metadata):
    if archive.stat().st_size != metadata["size"] or sha(archive) != metadata["sha256"]:
        raise ValueError("Qualified native archive checksum or size mismatch")
    expected = metadata["files"]
    if not expected or any(
        not (
            n.startswith("android/vendor/")
            or n.startswith("android/app/src/main/jniLibs/")
            or n.startswith("notices/")
        )
        or Path(n).is_absolute()
        or ".." in Path(n).parts
        for n in expected
    ):
        raise ValueError("Unsafe qualified input inventory")
    destination = destination.resolve()
    # Validate every archive member and existing destination before writing any input.
    with tarfile.open(archive, "r:xz") as source:
        members = source.getmembers()
        if {m.name for m in members} != set(expected) or len(members) != len(expected):
            raise ValueError("Qualified archive inventory mismatch")
        if (
            any(not m.isfile() or m.size < 0 for m in members)
            or sum(m.size for m in members) > MAX_EXPANDED
        ):
            raise ValueError("Unsafe or oversized qualified archive")
        for member in members:
            data = source.extractfile(member)
            if (
                data is None
                or hashlib.file_digest(data, "sha256").hexdigest()
                != expected[member.name]
            ):
                raise ValueError("Qualified archive member checksum mismatch")
            target = destination / member.name
            if not target.resolve().is_relative_to(destination) or any(
                p.is_symlink()
                for p in (target, *target.parents)
                if p != destination.parent
            ):
                raise ValueError("Unsafe existing destination")
            if target.exists() and (
                not target.is_file() or sha(target) != expected[member.name]
            ):
                raise ValueError("Existing input differs; use a fresh build tree")
        for member in members:
            target = destination / member.name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged:
                try:
                    shutil.copyfileobj(source.extractfile(member), staged)
                    staged.flush()
                    os.chmod(staged.name, 0o644)
                    os.replace(staged.name, target)
                finally:
                    Path(staged.name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--destination", type=Path, default=ROOT)
    args = parser.parse_args()
    metadata = json.loads((ROOT / "android/release/qualified-inputs.json").read_text())
    if metadata["format"] != 1 or metadata["repository"] != "HK1200/Meshchat-neXt":
        raise ValueError("Unexpected qualified input publisher")
    for name, expected in metadata["source_guards"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(
                "Native wrapper source changed; rebuild and qualify its native inputs"
            )
    if args.archive:
        install_archive(args.archive, args.destination, metadata)
    else:
        url = f"https://github.com/{metadata['repository']}/releases/download/{metadata['tag']}/{metadata['asset']}"
        with tempfile.TemporaryDirectory(prefix="qualified-android-") as temporary:
            archive = Path(temporary) / "inputs.tar.xz"
            with (
                urllib.request.urlopen(url, timeout=60) as response,  # noqa: S310 - fixed publisher and pinned archive digest
                archive.open("wb") as output,
            ):
                count = 0
                while data := response.read(1024 * 1024):
                    count += len(data)
                    if count > MAX_ARCHIVE:
                        raise ValueError("Oversized qualified archive download")
                    output.write(data)
            install_archive(archive, args.destination, metadata)
    print(
        f"Restored {len(metadata['files'])} exact qualified inputs/notices; rebuild SIP and Expat from current pinned sources."
    )


if __name__ == "__main__":
    main()
