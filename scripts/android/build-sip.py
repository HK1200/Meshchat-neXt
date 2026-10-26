#!/usr/bin/env python3
"""Build the pinned BSD baresip/re Android SIP engine (no account data)."""

import argparse
import hashlib
import os
import pathlib
import struct
import subprocess
import sys
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCES = {
    "re": "707b6194dd3b8d3fb1641ca08a0999aaac1d38d36b5c45514777a13ded311923",
    "baresip": "710d79d60c15c09f0aeb93e5d2f219e7f12ab93f62cab826e4280592a1ea155f",
}


def run(args):
    subprocess.run(list(map(str, args)), check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--abi", default="arm64-v8a", choices=["arm64-v8a", "x86_64", "armeabi-v7a"]
    )
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--abis", default="")
    a = p.parse_args()
    if a.verify_only:
        for abi in a.abis.split(",") if a.abis else [a.abi]:
            target = ROOT / "android/app/src/main/jniLibs" / abi / "libnext_sip.so"
            data = target.read_bytes()
            expected = {
                "arm64-v8a": (2, 183),
                "x86_64": (2, 62),
                "armeabi-v7a": (1, 40),
            }[abi]
            if (
                data[:4] != b"\x7fELF"
                or data[4] != expected[0]
                or struct.unpack_from("<H", data, 18)[0] != expected[1]
            ):
                raise ValueError("Invalid SIP native library: " + abi)
            print("Verified SIP library:", abi)
        return
    work = ROOT / ".local/sip"
    work.mkdir(parents=True, exist_ok=True)
    ndk = (
        pathlib.Path(
            os.environ.get("ANDROID_HOME", str(pathlib.Path.home() / "Android/Sdk"))
        )
        / "ndk/27.3.13750724"
    )
    for name, digest in SOURCES.items():
        archive = work / (name + "-4.12.0.tar.gz")
        if not archive.exists():
            urllib.request.urlretrieve(
                f"https://codeload.github.com/baresip/{name}/tar.gz/refs/tags/v4.12.0",
                archive,
            )
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError("Source checksum mismatch")
        if not (work / (name + "-4.12.0")).exists():
            with tarfile.open(archive) as src:
                src.extractall(work, filter="data")
    common = [
        "-DCMAKE_TOOLCHAIN_FILE=" + str(ndk / "build/cmake/android.toolchain.cmake"),
        "-DANDROID_ABI=" + a.abi,
        "-DANDROID_PLATFORM=28",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384",
        "-DBUILD_TESTING=OFF",
    ]
    mb_archive = work / "mbedtls-3.6.7.tar.bz2"
    if not mb_archive.exists():
        urllib.request.urlretrieve(
            "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2",
            mb_archive,
        )
    if (
        hashlib.sha256(mb_archive.read_bytes()).hexdigest()
        != "a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6"
    ):
        raise ValueError("Mbed TLS source checksum mismatch")
    mb = work / "mbedtls-3.6.7"
    if not mb.exists():
        with tarfile.open(mb_archive) as src:
            src.extractall(work, filter="data")
    run([sys.executable, ROOT / "scripts/android/provision-opus.py", "--abis", a.abi])
    opus_source = work / "opus-1.5.2"
    if not opus_source.exists():
        archive = ROOT / ".local/opus-1.5.2-android/opus-1.5.2.tar.gz"
        if (
            hashlib.sha256(archive.read_bytes()).hexdigest()
            != "65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1"
        ):
            raise ValueError("Opus checksum mismatch")
        with tarfile.open(archive) as src:
            src.extractall(work, filter="data")
    mt = work / (a.abi + "-mbedtls")
    run(
        [
            "cmake",
            "-S",
            mb,
            "-B",
            mt,
            *common,
            "-DENABLE_TESTING=OFF",
            "-DENABLE_PROGRAMS=OFF",
        ]
    )
    run(["cmake", "--build", mt, "-j2"])
    tls = [
        "-DCMAKE_C_FLAGS=-I" + str(mb / "include"),
        "-DUSE_MBEDTLS=ON",
        "-DMBEDTLS_INCLUDE_DIR=" + str(mb / "include"),
        "-DMBEDTLS_LIBRARY="
        + str(mt / "library/libmbedtls.a")
        + ";"
        + str(mt / "library/libmbedx509.a")
        + ";"
        + str(mt / "library/libmbedcrypto.a"),
    ]
    re = work / "re-4.12.0"
    rb = work / (a.abi + "-re")
    run(
        [
            "cmake",
            "-S",
            re,
            "-B",
            rb,
            *common,
            "-DLIBRE_BUILD_SHARED=OFF",
            "-DLIBRE_BUILD_STATIC=ON",
            "-DUSE_OPENSSL=OFF",
            "-DOPENSSL_INCLUDE_DIR=",
            "-DOPENSSL_CRYPTO_LIBRARY=",
            "-DOPENSSL_SSL_LIBRARY=",
            *tls,
            "-DUSE_PCP=OFF",
            "-DUSE_BFCP=OFF",
            "-DUSE_RTMP=OFF",
        ]
    )
    run(["cmake", "--build", rb, "-j2"])
    recorder = work / "baresip-4.12.0/modules/aaudio/recorder.c"
    text = recorder.read_text()
    if "next_sip_audio_session" not in text:
        text = text.replace(
            '#include "aaudio.h"',
            '#include "aaudio.h"\nextern void next_sip_audio_session(int session);',
        )
        needle = "\tAAudioStreamBuilder_delete(builder);\n\n\tAAudioStream_setBufferSizeInFrames"
        if needle not in text:
            raise ValueError("AAudio patch no longer applies")
        text = text.replace(
            needle,
            "\tnext_sip_audio_session(AAudioStream_getSessionId(st->recorderStream));\n"
            + needle,
        )
        recorder.write_text(text)
    bb = work / (a.abi + "-baresip")
    opus = work / "include"
    opus.mkdir(exist_ok=True)
    if not (opus / "opus").exists():
        (opus / "opus").symlink_to(
            work / "opus-1.5.2/include", target_is_directory=True
        )
    # Existing Opus runtime is already shipped by neXt.
    run(
        [
            "cmake",
            "-S",
            work / "baresip-4.12.0",
            "-B",
            bb,
            *common,
            "-DSTATIC=ON",
            "-DMODULES=aaudio;g711;opus",
            "-DRE_INCLUDE_DIR=" + str(re / "include"),
            "-DRE_LIBRARY=" + str(rb / "libre.a"),
            "-Dre_DIR=" + str(re / "cmake"),
            "-DUSE_OPENSSL=OFF",
            "-DOPENSSL_INCLUDE_DIR=",
            *tls,
            "-DOPUS_INCLUDE_DIR=" + str(opus),
            "-DOPUS_LIBRARY="
            + str(ROOT / "android/app/src/main/jniLibs" / a.abi / "libopus.so"),
        ]
    )
    run(["cmake", "--build", bb, "--target", "baresip", "-j2"])
    clang = (
        ndk
        / "toolchains/llvm/prebuilt/linux-x86_64/bin"
        / (
            {
                "arm64-v8a": "aarch64-linux-android28-clang",
                "x86_64": "x86_64-linux-android28-clang",
                "armeabi-v7a": "armv7a-linux-androideabi28-clang",
            }[a.abi]
        )
    )
    output = ROOT / "android/app/src/main/jniLibs" / a.abi / "libnext_sip.so"
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            clang,
            "-shared",
            "-fPIC",
            "-O2",
            "-Wl,-z,max-page-size=16384",
            "-Wl,-z,defs",
            "-Wl,-soname,libnext_sip.so",
            "-I" + str(re / "include"),
            "-I" + str(work / "baresip-4.12.0/include"),
            ROOT / "android/sip/next_sip.c",
            "-Wl,--start-group",
            bb / "libbaresip.a",
            rb / "libre.a",
            mt / "library/libmbedtls.a",
            mt / "library/libmbedx509.a",
            mt / "library/libmbedcrypto.a",
            "-Wl,--end-group",
            ROOT / "android/app/src/main/jniLibs" / a.abi / "libopus.so",
            "-laaudio",
            "-llog",
            "-landroid",
            "-lz",
            "-lm",
            "-o",
            output,
        ]
    )
    print("SIP engine built:", a.abi)


if __name__ == "__main__":
    main()
