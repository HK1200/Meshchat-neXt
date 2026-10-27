#!/usr/bin/env python3
"""Build the pinned Open TAK image wrapper; run after tools/media-env.sh.

Outputs ignored libraries; sources and provenance remain reviewable. No installs.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = "76558ad5918820d66fa78460d9957e5bbf7cf9eef1a5421b5ba5e616f200d76e"
URL = "https://raw.githubusercontent.com/jade-on-mesh/meshcore-open-tak/deps-cache/aom-v3.12.1.tar.gz"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--android-abi", choices=["arm64-v8a", "armeabi-v7a", "x86_64"])
    parser.add_argument("--ndk")
    parser.add_argument(
        "--work-dir", type=Path, help="Persistent native build/cache folder"
    )
    args = parser.parse_args()
    cache = (
        args.work_dir.resolve() if args.work_dir else ROOT / "temp-tests" / "av1-build"
    )
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "aom.tgz"
    if not archive.exists():
        with (
            urllib.request.urlopen(URL, timeout=60) as response,  # noqa: S310 -- Fixed HTTPS source; SHA-256 checked before extraction.
            archive.open("wb") as target,
        ):
            shutil.copyfileobj(response, target)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA:
        raise RuntimeError("AV1 source checksum mismatch")
    if not (cache / "aom").exists():
        with tarfile.open(archive) as source:
            source.extractall(cache, filter="data")
    cmake = shutil.which("cmake")
    if not cmake:
        raise RuntimeError("CMake is required")
    label = args.android_abi or "host"
    build = cache / label
    options = [
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        "-DENABLE_DOCS=0",
        "-DENABLE_EXAMPLES=0",
        "-DENABLE_TESTS=0",
        "-DENABLE_TESTDATA=0",
        "-DENABLE_TOOLS=0",
        "-DCONFIG_AV1_HIGHBITDEPTH=0",
        "-DCONFIG_WEBM_IO=0",
    ]
    if args.android_abi:
        ndk = Path(args.ndk or os.environ["ANDROID_NDK_HOME"])
        options += [
            "-DCMAKE_TOOLCHAIN_FILE="
            + str(ndk / "build/cmake/android.toolchain.cmake"),
            "-DANDROID_ABI=" + label,
            "-DANDROID_PLATFORM=android-24",
        ]
        target = {
            "arm64-v8a": "aarch64-linux-android24",
            "armeabi-v7a": "armv7a-linux-androideabi24",
            "x86_64": "x86_64-linux-android24",
        }[label]
        compiler = str(
            ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin" / (target + "-clang")
        )
        output = ROOT / "android/app/src/main/jniLibs" / label / "libvox_av1.so"
    else:
        options += ["-DAOM_TARGET_CPU=generic"]
        compiler = shutil.which("cc")
        if not compiler:
            raise RuntimeError("A C compiler is required")
        output = cache / "libvox_av1.so"
    subprocess.run(
        [cmake, "-S", str(cache / "aom"), "-B", str(build), *options], check=True
    )
    subprocess.run([cmake, "--build", str(build), "--target", "aom", "-j4"], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            compiler,
            "-shared",
            "-fPIC",
            "-O2",
            "-std=gnu11",
            "-Wl,-z,max-page-size=16384",
            "-Wl,--exclude-libs,ALL",
            "-I" + str(cache / "aom"),
            str(ROOT / "native/av1/vox_av1.c"),
            str(build / "libaom.a"),
            "-lm",
            "-o",
            str(output),
        ],
        check=True,
    )
    print("AV1 library ready:", output)


if __name__ == "__main__":
    main()
