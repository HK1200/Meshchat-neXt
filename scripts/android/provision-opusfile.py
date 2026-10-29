#!/usr/bin/env python3
"""Provision missing offline Android Opus-file decoders from verified Xiph sources."""

import argparse
import hashlib
import importlib.util
import os
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.12"
SOURCE_SHA256 = "118d8601c12dd6a44f52423e68ca9083cc9f2bfe72da7a8c1acb22a80ae3550b"
SOURCE_URL = f"https://github.com/xiph/opusfile/releases/download/v{VERSION}/opusfile-{VERSION}.tar.gz"
NDK_VERSION = "27.3.13750724"
_spec = importlib.util.spec_from_file_location(
    "android_native_helpers", Path(__file__).with_name("provision-opus.py")
)
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
ABIS = _helpers.ABIS
verify_elf = _helpers.verify_elf
publish_missing = _helpers.publish_missing
TRIPLES = {
    "arm64-v8a": "aarch64-linux-android",
    "x86_64": "x86_64-linux-android",
    "armeabi-v7a": "armv7a-linux-androideabi",
}


def verify_source(path, expected=SOURCE_SHA256):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Source checksum mismatch: {path}")


def extract_source(archive, destination, prefix=f"opusfile-{VERSION}"):
    with tarfile.open(archive, "r:*") as source:
        members = source.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if (
                not parts
                or parts[0] != prefix
                or ".." in parts
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError(f"Unsafe source archive entry: {member.name}")
        source.extractall(destination, members=members, filter="data")
    return destination / prefix


def obtain(supplied, cache, url, checksum):
    archive = supplied or cache
    if not archive.exists():
        if supplied:
            raise ValueError(f"Source archive does not exist: {archive}")
        with tempfile.NamedTemporaryFile(dir=cache.parent) as download:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - pinned HTTPS source, verified by SHA-256 before use.
                import shutil

                shutil.copyfileobj(response, download)
            download.flush()
            verify_source(Path(download.name), checksum)
            try:
                os.link(download.name, cache)
            except FileExistsError:
                pass
    verify_source(archive, checksum)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--abis", default=os.environ.get("MESHCHATNEXT_ABIS", ",".join(ABIS))
    )
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--opus-source-archive", type=Path)
    parser.add_argument("--ogg-source-archive", type=Path)
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
        target = jni / abi / "libopusfile.so"
        if os.path.lexists(target):
            verify_elf(target, abi)
        else:
            missing.append(abi)
    if args.verify_only:
        if missing:
            raise ValueError(
                f"Missing OpusFile for {', '.join(missing)}. Run scripts/android/provision-opusfile.py first."
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
    work = ROOT / f".local/opusfile-{VERSION}-android"
    work.mkdir(parents=True, exist_ok=True)
    archive = obtain(
        args.source_archive,
        work / f"opusfile-{VERSION}.tar.gz",
        SOURCE_URL,
        SOURCE_SHA256,
    )
    opus_archive = obtain(
        args.opus_source_archive,
        work / "opus-1.5.2.tar.gz",
        _helpers.SOURCE_URL,
        _helpers.SOURCE_SHA256,
    )
    ogg_archive = obtain(
        args.ogg_source_archive,
        work / "libogg-1.3.6.tar.xz",
        "https://downloads.xiph.org/releases/ogg/libogg-1.3.6.tar.xz",
        "5c8253428e181840cd20d41f3ca16557a9cc04bad4a3d04cce84808677fa1061",
    )
    with tempfile.TemporaryDirectory(dir=work, prefix="provision-") as temporary:
        temp = Path(temporary)
        source = extract_source(archive, temp)
        opus = extract_source(opus_archive, temp, "opus-1.5.2")
        ogg = extract_source(ogg_archive, temp, "libogg-1.3.6")
        include = temp / "include/ogg"
        include.mkdir(parents=True)
        config = (ogg / "include/ogg/config_types.h.in").read_text()
        replacements = {
            "INCLUDE_INTTYPES_H": "1",
            "INCLUDE_STDINT_H": "1",
            "INCLUDE_SYS_TYPES_H": "1",
            "SIZE16": "int16_t",
            "USIZE16": "uint16_t",
            "SIZE32": "int32_t",
            "USIZE32": "uint32_t",
            "SIZE64": "int64_t",
            "USIZE64": "uint64_t",
        }
        for key, value in replacements.items():
            config = config.replace(f"@{key}@", value)
        (include / "config_types.h").write_text(config)
        for abi in missing:
            for library in ["libogg.so", "libopus.so"]:
                verify_elf(jni / abi / library, abi)
            built = temp / f"{abi}-libopusfile.so"
            compiler = (
                ndk
                / "toolchains/llvm/prebuilt/linux-x86_64/bin"
                / f"{TRIPLES[abi]}24-clang"
            )
            command = [
                str(compiler),
                "-shared",
                "-fPIC",
                "-O2",
                "-D_POSIX_C_SOURCE=200809L",
                "-DOP_HAVE_LRINTF",
                "-Wl,--no-undefined",
                "-Wl,-soname,libopusfile.so",
                "-Wl,-z,max-page-size=16384",
                "-Wl,-z,common-page-size=16384",
                "-I" + str(source / "include"),
                "-I" + str(opus / "include"),
                "-I" + str(ogg / "include"),
                "-I" + str(temp / "include"),
            ]
            command += [
                str(source / "src" / name)
                for name in ["info.c", "internal.c", "opusfile.c", "stream.c"]
            ]
            command += [
                str(jni / abi / "libogg.so"),
                str(jni / abi / "libopus.so"),
                "-lm",
                "-o",
                str(built),
            ]
            _helpers.run_quiet(command, work / f"provision-{abi}.log")
            publish_missing(built, jni / abi / "libopusfile.so", abi)
            print(f"OpusFile {abi}: provisioned and verified", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, tarfile.TarError) as error:
        raise SystemExit(f"OpusFile: {error}") from error
