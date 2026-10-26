#!/usr/bin/env python3
"""Build a disposable native transport test APK; never signs or replaces the HK app."""

import argparse
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk",
        type=Path,
        default=Path(os.environ.get("ANDROID_HOME", str(Path.home() / "Android/Sdk"))),
    )
    parser.add_argument(
        "--usb-jar",
        type=Path,
        required=True,
        help="usb-serial-for-android 3.8.1 classes.jar",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--keystore", type=Path, default=Path.home() / ".android/debug.keystore"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    source = root / "android/app/src/main/java"
    tools = args.sdk / "build-tools/35.0.0"
    android = args.sdk / "platforms/android-35/android.jar"
    out = (
        args.out.resolve()
        if args.out
        else Path(tempfile.mkdtemp(prefix="meshcore-sidecar-"))
    )
    out.mkdir(parents=True, exist_ok=True)
    classes = out / "classes"
    classes.mkdir(exist_ok=True)

    def run(command):
        subprocess.run([str(part) for part in command], check=True)

    files = [
        *sorted((source / "com/meshchatnext/meshcore").glob("*.java")),
        source / "com/meshchatnext/radio/DeviceAccess.java",
        Path(__file__).with_name("RadioInstrumentation.java"),
    ]
    run(
        [
            "javac",
            "-source",
            "8",
            "-target",
            "8",
            "-cp",
            str(android) + ":" + str(args.usb_jar),
            "-d",
            classes,
            *files,
        ]
    )
    run(["jar", "cf", out / "native.jar", "-C", classes, "."])
    run(
        [
            tools / "d8",
            "--min-api",
            "24",
            "--lib",
            android,
            "--output",
            out,
            out / "native.jar",
            args.usb_jar,
        ]
    )
    run(
        [
            tools / "aapt2",
            "link",
            "-o",
            out / "base.apk",
            "-I",
            android,
            "--manifest",
            Path(__file__).with_name("AndroidManifest.xml"),
        ]
    )
    with zipfile.ZipFile(out / "base.apk", "a") as archive:
        archive.write(out / "classes.dex", "classes.dex")
    run([tools / "zipalign", "-f", "4", out / "base.apk", out / "aligned.apk"])
    # Standard Android debug credentials, never a production signing identity.
    run(
        [
            tools / "apksigner",
            "sign",
            "--ks",
            args.keystore,
            "--ks-pass",
            "pass:android",
            "--out",
            out / "meshcore-tests.apk",
            out / "aligned.apk",
        ]
    )
    print(out / "meshcore-tests.apk")


if __name__ == "__main__":
    main()
