#!/usr/bin/env python3
"""Provision missing Android Ogg libraries; existing files are never replaced."""

import argparse
import hashlib
import os
import struct
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "1.3.6"
SOURCE_SHA256 = "5c8253428e181840cd20d41f3ca16557a9cc04bad4a3d04cce84808677fa1061"
SOURCE_URL = f"https://downloads.xiph.org/releases/ogg/libogg-{VERSION}.tar.xz"
NDK_VERSION = "27.3.13750724"
ABIS = {"arm64-v8a": (2, 183), "x86_64": (2, 62), "armeabi-v7a": (1, 40)}
ROOT = Path(__file__).resolve().parents[2]


def verify_elf(path, abi):
    with path.open("rb") as stream:
        header = stream.read(64)
    elf_class, machine = ABIS[abi]
    if (
        len(header) < 52
        or header[:4] != b"\x7fELF"
        or header[4] != elf_class
        or header[5:7] != b"\x01\x01"
        or struct.unpack_from("<HH", header, 16) != (3, machine)
    ):
        raise ValueError(f"{path}: expected little-endian {abi} ELF shared library")


def verify_source(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"Source checksum mismatch: {path} ({digest})")


def extract_source(archive, destination):
    # Extract only regular files/directories beneath the expected root. No links.
    with tarfile.open(archive, "r:xz") as source:
        members = source.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if (
                not parts
                or parts[0] != f"libogg-{VERSION}"
                or ".." in parts
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"Unsafe source archive entry: {member.name}")
        source.extractall(destination, members=members, filter="data")
    return destination / f"libogg-{VERSION}"


def run_quiet(command, log):
    with log.open("ab") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def publish_missing(built, target, abi):
    verify_elf(built, abi)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Hard-link a completed, same-filesystem temporary copy atomically, without
    # replacing even a dangling symlink or a file created by another process.
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".ogg-") as staged:
        staged.write(built.read_bytes())
        staged.flush()
        os.chmod(staged.name, 0o644)
        try:
            os.link(staged.name, target)
        except FileExistsError:
            verify_elf(target, abi)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--abis", default=os.environ.get("MESHCHATNEXT_ABIS", ",".join(ABIS))
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="No downloads or writes; fail on missing/invalid libraries",
    )
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--ndk", type=Path)
    args = parser.parse_args()
    abis = list(
        dict.fromkeys(abi.strip() for abi in args.abis.split(",") if abi.strip())
    )
    if not abis or set(abis) - ABIS.keys():
        parser.error(f"Select ABIs from {', '.join(ABIS)}")
    jni = ROOT / "android/app/src/main/jniLibs"
    missing = []
    for abi in abis:
        target = jni / abi / "libogg.so"
        if os.path.lexists(target):
            verify_elf(target, abi)
            print(f"Ogg {abi}: verified existing library", flush=True)
        else:
            missing.append(abi)
    if args.verify_only:
        if missing:
            raise ValueError(
                f"Missing Ogg for {', '.join(missing)}. Run: python3 scripts/android/provision-ogg.py --abis {args.abis}"
            )
        return
    if not missing:
        return
    sdk = Path(
        os.environ.get("ANDROID_SDK_ROOT")
        or os.environ.get("ANDROID_HOME")
        or Path.home() / "Android/Sdk"
    )
    ndk = args.ndk or sdk / "ndk" / NDK_VERSION
    properties = ndk / "source.properties"
    if not properties.is_file() or not any(
        line.strip() == f"Pkg.Revision = {NDK_VERSION}"
        for line in properties.read_text().splitlines()
    ):
        raise ValueError(f"Expected NDK {NDK_VERSION} at {ndk}")
    work = ROOT / f".local/ogg-{VERSION}-android"
    work.mkdir(parents=True, exist_ok=True)
    archive = args.source_archive or work / f"libogg-{VERSION}.tar.xz"
    if not archive.exists():
        if args.source_archive:
            raise ValueError(f"Source archive does not exist: {archive}")
        with tempfile.NamedTemporaryFile(dir=work, suffix=".tar.xz") as download:
            with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:  # noqa: S310 - pinned HTTPS source, verified by SHA-256 before use.
                import shutil

                shutil.copyfileobj(response, download)
            download.flush()
            verify_source(Path(download.name))
            # Also avoid replacing a concurrently supplied source archive.
            try:
                os.link(download.name, archive)
            except FileExistsError:
                pass
    verify_source(archive)
    # A fresh extraction/build avoids trusting stale local sources or CMake caches.
    with tempfile.TemporaryDirectory(dir=work, prefix="provision-") as temporary:
        source = extract_source(archive, Path(temporary))
        for abi in missing:
            build = Path(temporary) / f"build-{abi}"
            log = work / f"provision-{abi}.log"
            print(f"Ogg {abi}: building {VERSION} (log: {log})", flush=True)
            run_quiet(
                [
                    "cmake",
                    "-S",
                    str(source),
                    "-B",
                    str(build),
                    f"-DCMAKE_TOOLCHAIN_FILE={ndk}/build/cmake/android.toolchain.cmake",
                    f"-DANDROID_ABI={abi}",
                    "-DANDROID_PLATFORM=android-24",
                    "-DCMAKE_BUILD_TYPE=Release",
                    "-DBUILD_SHARED_LIBS=ON",
                    "-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON",
                    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384",
                    "-DOPUS_BUILD_SHARED_LIBRARY=ON",
                    "-DOPUS_BUILD_TESTING=OFF",
                    "-DOPUS_BUILD_PROGRAMS=OFF",
                    "-DOPUS_CUSTOM_MODES=OFF",
                ],
                log,
            )
            run_quiet(["cmake", "--build", str(build), "--parallel", "2"], log)
            publish_missing(build / "libogg.so", jni / abi / "libogg.so", abi)
            print(f"Ogg {abi}: provisioned and verified", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, tarfile.TarError) as error:
        raise SystemExit(f"Ogg: {error}") from error
