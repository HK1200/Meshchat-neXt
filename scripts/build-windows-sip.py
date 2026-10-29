#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Build the local Windows SIP helper from checksum-pinned sources; no registration."""

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "re-4.12.0.tar.gz": "707b6194dd3b8d3fb1641ca08a0999aaac1d38d36b5c45514777a13ded311923",
    "baresip-4.12.0.tar.gz": "710d79d60c15c09f0aeb93e5d2f219e7f12ab93f62cab826e4280592a1ea155f",
    "opus-1.5.2.tar.gz": "65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1",
    "mbedtls-3.6.7.tar.bz2": "a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6",
}


def verify_sources(cache):
    for name, digest in SOURCES.items():
        if hashlib.sha256((cache / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Source checksum mismatch: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cache", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    verify_sources(args.source_cache)
    if args.verify_only:
        print("All four pinned SIP source archives verified")
        return
    if sys.platform != "win32" or not shutil.which("cl") or not shutil.which("ninja"):
        parser.error("Use a native x64 MSVC development shell with CMake and Ninja")
    if (
        struct.calcsize("P") != 8
        or os.environ.get("VSCMD_ARG_TGT_ARCH", "").casefold() != "x64"
    ):
        parser.error("Use 64-bit Python from the x64 MSVC Native Tools shell")
    cmake = shutil.which("cmake")
    if not cmake:
        parser.error("CMake is required")
    work = ROOT / ".local/windows-sip"
    work.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        with tarfile.open(args.source_cache / name) as archive:
            top = archive.getmembers()[0].name.split("/")[0]
            if not (work / top).exists():
                archive.extractall(work, filter="data")
    include = work / "include/opus"
    shutil.copytree(work / "opus-1.5.2/include", include, dirs_exist_ok=True)
    # Recorded local build patch: all libre socket calls inherit our adapter policy.
    re_cmake = work / "re-4.12.0/CMakeLists.txt"
    marker = "# Meshchat neXt Windows socket policy"
    text = re_cmake.read_text()
    if marker not in text:
        header = (ROOT / "native/sip/windows/socket_policy.h").as_posix()
        re_cmake.write_text(
            text
            + f'\n{marker}\ntarget_compile_options(re-objs PRIVATE "/FI{header}")\n'
        )
    common = [
        "-G",
        "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DBUILD_TESTING=OFF",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DCMAKE_DISABLE_FIND_PACKAGE_ZLIB=ON",
    ]

    def build(source, output, options=(), target=None):
        subprocess.run(
            [cmake, "-S", str(source), "-B", str(work / output), *common, *options],
            check=True,
        )
        command = [cmake, "--build", str(work / output), "--parallel", "2"]
        if target:
            command += ["--target", target]
        subprocess.run(command, check=True)

    build(
        work / "mbedtls-3.6.7",
        "tls-build",
        ["-DENABLE_TESTING=OFF", "-DENABLE_PROGRAMS=OFF"],
    )
    build(
        work / "opus-1.5.2",
        "opus-build",
        ["-DOPUS_BUILD_TESTING=OFF", "-DOPUS_BUILD_PROGRAMS=OFF"],
    )
    tls_libs = ";".join(
        str(work / f"tls-build/library/{name}.lib")
        for name in ("mbedtls", "mbedx509", "mbedcrypto")
    )
    tls = [
        "-DUSE_OPENSSL=OFF",
        "-DUSE_MBEDTLS=ON",
        f"-DMBEDTLS_INCLUDE_DIR={work / 'mbedtls-3.6.7/include'}",
        f"-DMBEDTLS_LIBRARY={tls_libs}",
        f'-DCMAKE_C_FLAGS=/I"{work / "mbedtls-3.6.7/include"}"',
    ]
    build(
        work / "re-4.12.0",
        "re-build",
        [
            *tls,
            "-DLIBRE_BUILD_SHARED=OFF",
            "-DLIBRE_BUILD_STATIC=ON",
            "-DUSE_PCP=OFF",
            "-DUSE_BFCP=OFF",
            "-DUSE_RTMP=OFF",
        ],
        "re",
    )
    build(
        work / "baresip-4.12.0",
        "baresip-build",
        [
            *tls,
            "-DSTATIC=ON",
            "-DMODULES=g711;opus;ausine;aufile;wasapi",
            f"-DRE_INCLUDE_DIR={work / 're-4.12.0/include'}",
            f"-DRE_LIBRARY={work / 're-build/re-static.lib'};{tls_libs}",
            f"-Dre_DIR={work / 're-4.12.0/cmake'}",
            f"-DOPUS_INCLUDE_DIR={work / 'include'}",
            f"-DOPUS_LIBRARY={work / 'opus-build/opus.lib'}",
        ],
        "baresip",
    )
    build(
        ROOT / "native/sip/windows",
        "helper-build",
        [f"-DSOURCE_ROOT={work}"],
        "meshchatnext-sip",
    )
    shutil.copy2(
        work / "helper-build/meshchatnext-sip.exe", work / "meshchatnext-sip.exe"
    )
    licenses = work / "licenses"
    licenses.mkdir(exist_ok=True)
    for source, label in (
        ("re-4.12.0/LICENSE", "libre-LICENSE.txt"),
        ("baresip-4.12.0/LICENSE", "baresip-LICENSE.txt"),
        ("opus-1.5.2/COPYING", "opus-COPYING.txt"),
        ("mbedtls-3.6.7/LICENSE", "mbedtls-LICENSE.txt"),
    ):
        shutil.copy2(work / source, licenses / label)
    (work / "build-provenance.json").write_text(
        json.dumps(
            {
                "sources": SOURCES,
                "modules": ["g711", "opus", "ausine", "aufile", "wasapi"],
                "patch": marker,
                "status": "built locally; native tests still required",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
