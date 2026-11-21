#!/usr/bin/env python3
"""Run the real mobile SIP codec profile against an APK's libraries on Android.

Uses synthetic PCM only; does not open a microphone, register, or place calls.
Run build-sip.py for the selected ABI first. A device/emulator must be online.
"""

import argparse
import os
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--abi", choices=["arm64-v8a", "armeabi-v7a", "x86_64"], required=True
    )
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--serial")
    args = parser.parse_args()
    sdk = Path(os.environ.get("ANDROID_HOME", str(Path.home() / "Android/Sdk")))
    target = {"arm64-v8a": "aarch64", "armeabi-v7a": "armv7a", "x86_64": "x86_64"}[
        args.abi
    ]
    cc = (
        sdk
        / "ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin"
        / (
            target + "-linux-androideabi28-clang"
            if target == "armv7a"
            else target + "-linux-android28-clang"
        )
    )
    cache = ROOT / ".local/sip"
    adb = ["adb"] + (["-s", args.serial] if args.serial else [])
    remote = "/data/local/tmp/next-sip-codec-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="codec-test-", dir=cache) as folder:
        work = Path(folder)
        with zipfile.ZipFile(args.apk) as apk:
            for name in ["libnext_sip.so", "libopus.so"]:
                data = apk.read("lib/" + args.abi + "/" + name)
                if (
                    data
                    != (
                        ROOT / "android/app/src/main/jniLibs" / args.abi / name
                    ).read_bytes()
                ):
                    raise RuntimeError(
                        "Packaged SIP dependency differs from the built library: "
                        + name
                    )
                (work / name).write_bytes(data)
        command = [
            str(cc),
            "-O2",
            "-I" + str(cache / "re-4.12.0/include"),
            "-I" + str(cache / "baresip-4.12.0/include"),
            "-I" + str(ROOT / "android/sip"),
            str(ROOT / "android/sip/tests/codec_profile.c"),
            str(work / "libnext_sip.so"),
            str(work / "libopus.so"),
            "-llog",
            "-ldl",
            "-lm",
            "-o",
            str(work / "codec-test"),
        ]
        subprocess.run(command, check=True)
        try:
            subprocess.run([*adb, "shell", "mkdir", "-p", remote], check=True)
            for name in ["codec-test", "libnext_sip.so", "libopus.so"]:
                subprocess.run(
                    [*adb, "push", str(work / name), remote + "/"], check=True
                )
            subprocess.run(
                [
                    *adb,
                    "shell",
                    "LD_LIBRARY_PATH=" + remote + " " + remote + "/codec-test",
                ],
                check=True,
                timeout=30,
            )
        finally:
            subprocess.run([*adb, "shell", "rm", "-rf", remote], check=True)


if __name__ == "__main__":
    main()
