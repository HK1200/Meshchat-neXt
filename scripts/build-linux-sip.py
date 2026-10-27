#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Build pinned Linux SIP core locally; no accounts, registration or system install.

The core includes file/sine test audio. Supply explicit PulseAudio headers and
library paths to include desktop microphone/playback support.
Pass a cache of the same verified upstream archives used by the Android build.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "re-4.12.0.tar.gz": "707b6194dd3b8d3fb1641ca08a0999aaac1d38d36b5c45514777a13ded311923",
    "baresip-4.12.0.tar.gz": "710d79d60c15c09f0aeb93e5d2f219e7f12ab93f62cab826e4280592a1ea155f",
    "opus-1.5.2.tar.gz": "65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1",
    "mbedtls-3.6.7.tar.bz2": "a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6",
}


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cache", required=True, type=Path)
    parser.add_argument("--pulse-include", type=Path)
    parser.add_argument("--pulse-library", type=Path)
    args = parser.parse_args()
    if bool(args.pulse_include) != bool(args.pulse_library):
        parser.error("Supply both PulseAudio include and library paths")
    if args.pulse_include and (
        not (args.pulse_include / "pulse/pulseaudio.h").is_file()
        or not args.pulse_library.is_file()
    ):
        parser.error("PulseAudio headers or library missing")
    work = ROOT / ".local/linux-sip"
    work.mkdir(parents=True, exist_ok=True)
    for name, digest in SOURCES.items():
        source = args.source_cache / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Source checksum mismatch: {name}")
        archive = work / name
        if not archive.exists():
            shutil.copy2(source, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Cached source checksum mismatch: {name}")
        with tarfile.open(archive) as tar:
            top = tar.getmembers()[0].name.split("/")[0]
            if not (work / top).exists():
                tar.extractall(work, filter="data")
    common = [
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        "-DBUILD_TESTING=OFF",
    ]

    def build(source, output, options, target=None):
        run(["cmake", "-S", work / source, "-B", work / output, *common, *options])
        command = ["cmake", "--build", work / output, "-j2"]
        if target:
            command += ["--target", target]
        run(command)

    build(
        "mbedtls-3.6.7", "tls-build", ["-DENABLE_TESTING=OFF", "-DENABLE_PROGRAMS=OFF"]
    )
    build(
        "opus-1.5.2",
        "opus-build",
        [
            "-DOPUS_BUILD_TESTING=OFF",
            "-DOPUS_BUILD_PROGRAMS=OFF",
            "-DBUILD_SHARED_LIBS=OFF",
        ],
    )
    tls = [
        "-DCMAKE_C_FLAGS=-I" + str(work / "mbedtls-3.6.7/include"),
        "-DUSE_OPENSSL=OFF",
        "-DUSE_MBEDTLS=ON",
        "-DMBEDTLS_INCLUDE_DIR=" + str(work / "mbedtls-3.6.7/include"),
        "-DMBEDTLS_LIBRARY="
        + ";".join(
            str(work / f"tls-build/library/lib{x}.a")
            for x in ("mbedtls", "mbedx509", "mbedcrypto")
        ),
    ]
    build(
        "re-4.12.0",
        "re-build",
        [
            *tls,
            "-DLIBRE_BUILD_SHARED=OFF",
            "-DLIBRE_BUILD_STATIC=ON",
            "-DUSE_PCP=OFF",
            "-DUSE_BFCP=OFF",
            "-DUSE_RTMP=OFF",
        ],
    )
    include = work / "include"
    include.mkdir(exist_ok=True)
    if not (include / "opus").exists():
        (include / "opus").symlink_to(
            work / "opus-1.5.2/include", target_is_directory=True
        )
    audio_options = []
    modules = "g711;opus;ausine;aufile;menu"
    if args.pulse_include:
        modules += ";pulse"
        audio_options = [
            "-DPULSE_INCLUDE_DIR=" + str(args.pulse_include.resolve()),
            "-DPULSE_LIBRARY=" + str(args.pulse_library.resolve()),
        ]
    build(
        "baresip-4.12.0",
        "baresip-build",
        [
            *tls,
            "-DSTATIC=ON",
            "-DMODULES=" + modules,
            *audio_options,
            "-DRE_INCLUDE_DIR=" + str(work / "re-4.12.0/include"),
            "-DRE_LIBRARY="
            + ";".join(
                [
                    str(work / "re-build/libre.a"),
                    *(
                        str(work / f"tls-build/library/lib{x}.a")
                        for x in ("mbedtls", "mbedx509", "mbedcrypto")
                    ),
                ]
            ),
            "-Dre_DIR=" + str(work / "re-4.12.0/cmake"),
            "-DOPUS_INCLUDE_DIR=" + str(include),
            "-DOPUS_LIBRARY=" + str(work / "opus-build/libopus.a"),
        ],
        "baresip_exe",
    )
    # Use the same native link dependencies CMake selected for the core.
    import shlex

    link = shlex.split(
        (work / "baresip-build/CMakeFiles/baresip_exe.dir/link.txt").read_text()
    )
    dependencies = link[link.index("libbaresip.a") :]
    dependencies[0] = str(work / "baresip-build/libbaresip.a")
    run(
        [
            "cc",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wl,--wrap=socket",
            "-I" + str(work / "re-4.12.0/include"),
            "-I" + str(work / "baresip-4.12.0/include"),
            ROOT / "native/sip/desktop_sip.c",
            "-o",
            work / "meshchatnext-sip",
            *dependencies,
        ]
    )
    license_dir = work / "licenses"
    license_dir.mkdir(exist_ok=True)
    for source, label in (
        ("re-4.12.0/LICENSE", "libre-LICENSE.txt"),
        ("baresip-4.12.0/LICENSE", "baresip-LICENSE.txt"),
        ("opus-1.5.2/COPYING", "opus-COPYING.txt"),
        ("mbedtls-3.6.7/LICENSE", "mbedtls-LICENSE.txt"),
    ):
        shutil.copy2(work / source, license_dir / label)
    pulse_copyright = work / "sysdeps/root/usr/share/doc/libpulse-dev/copyright"
    if args.pulse_include and pulse_copyright.is_file():
        shutil.copy2(pulse_copyright, license_dir / "PulseAudio-COPYRIGHT.txt")
    (work / "build-provenance.json").write_text(
        json.dumps(
            {
                "sources": SOURCES,
                "status": "Native core built; application IPC/controller integration pending",
                "audio_modules": modules.split(";"),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
