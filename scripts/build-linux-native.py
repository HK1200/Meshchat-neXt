#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Reproducible native Linux inputs for desktop SIP and MediaMesh photos.

Requires CMake, a C compiler and PulseAudio development headers (libpulse-dev on
Mint/Ubuntu). Never installs packages or flashes devices. Use --offline to forbid
source downloads; all archives are checked against the Android release pins.
"""

import argparse
import hashlib
import importlib.util
import platform
import shutil
import subprocess
import sys
import sysconfig
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verified_archive(target, url, digest, *, offline):
    if not url.startswith("https://"):
        raise ValueError("Native sources require HTTPS")
    target = Path(target)
    if target.is_file():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Source checksum mismatch: {target.name}")
        return
    if offline:
        raise ValueError(f"Offline source archive missing: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with (
            urllib.request.urlopen(url, timeout=60) as response,  # noqa: S310 -- Fixed HTTPS archive URLs, SHA-256 verified before use.
            partial.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Downloaded source checksum mismatch: {target.name}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--arch", choices=("x64", "arm64"))
    parser.add_argument("--pulse-include", type=Path, default=Path("/usr/include"))
    parser.add_argument("--pulse-library", type=Path)
    args = parser.parse_args()
    arch = {"x86_64": "x64", "aarch64": "arm64"}.get(platform.machine())
    if (
        not sys.platform.startswith("linux")
        or not arch
        or (args.arch and args.arch != arch)
    ):
        parser.error(
            "Native Linux builds require a matching host architecture; cross-compilation is not configured"
        )
    if not (args.pulse_include / "pulse/pulseaudio.h").is_file():
        parser.error(
            "PulseAudio headers missing; install libpulse-dev or provide --pulse-include"
        )
    multiarch = sysconfig.get_config_var("MULTIARCH")
    library = args.pulse_library or Path(f"/usr/lib/{multiarch}/libpulse.so")
    if not library.is_file():
        parser.error("PulseAudio development library missing; provide --pulse-library")
    spec = importlib.util.spec_from_file_location(
        "linux_sip_build", ROOT / "scripts/build-linux-sip.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    cache = ROOT / ".local/linux-sip"
    urls = {
        "re-4.12.0.tar.gz": "https://codeload.github.com/baresip/re/tar.gz/refs/tags/v4.12.0",
        "baresip-4.12.0.tar.gz": "https://codeload.github.com/baresip/baresip/tar.gz/refs/tags/v4.12.0",
        "opus-1.5.2.tar.gz": "https://downloads.xiph.org/releases/opus/opus-1.5.2.tar.gz",
        "mbedtls-3.6.7.tar.bz2": "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2",
    }
    for name, digest in builder.SOURCES.items():
        verified_archive(cache / name, urls[name], digest, offline=args.offline)
    av1_spec = importlib.util.spec_from_file_location(
        "linux_av1_build", ROOT / "scripts/build-meshcore-av1.py"
    )
    av1 = importlib.util.module_from_spec(av1_spec)
    av1_spec.loader.exec_module(av1)
    verified_archive(
        ROOT / ".local/av1/aom.tgz", av1.URL, av1.SHA, offline=args.offline
    )
    subprocess.run(
        [
            sys.executable,
            ROOT / "scripts/build-linux-sip.py",
            "--source-cache",
            cache,
            "--pulse-include",
            args.pulse_include,
            "--pulse-library",
            library,
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            ROOT / "scripts/build-meshcore-av1.py",
            "--work-dir",
            ROOT / ".local/av1",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
