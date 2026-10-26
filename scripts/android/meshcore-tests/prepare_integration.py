#!/usr/bin/env python3
"""Prepare a separate full Android test tree with a verified MeshCore overlay."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-inputs", type=Path, required=True)
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8000,
        help="Local port for an isolated full-UI test app",
    )
    args = parser.parse_args()
    if not 1024 <= args.backend_port <= 65535:
        parser.error("--backend-port must be between 1024 and 65535")
    repo = Path(__file__).resolve().parents[3]
    dest = args.dest.resolve()
    dependencies = json.loads(Path(__file__).with_name("dependencies.json").read_text())
    for name, expected in dependencies.items():
        path = args.dependencies / name
        if Path(name).name != name or path.is_symlink() or sha256(path) != expected:
            raise ValueError(f"Missing or mismatched MeshCore dependency: {name}")
    subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/android/prepare-stable-build.py"),
            "--native-inputs",
            str(args.native_inputs.resolve()),
            "--frontend",
            str(args.frontend.resolve()),
            "--dest",
            str(dest),
        ],
        check=True,
    )
    # Include only this feature's allowlisted files, including uncommitted additions.
    patterns = [
        "android/app/src/debug/python/meshcore_*.py",
        "android/app/src/main/java/com/meshchatnext/meshcore/*.java",
        "android/app/src/main/java/com/meshchatnext/radio/*.java",
        "android/app/src/androidTest/java/com/meshchatnext/meshcore/*.java",
        "android/app/src/test/java/com/meshchatnext/meshcore/*.java",
        "meshchatnext/src/backend/meshcore_*.py",
        "meshchatnext/src/frontend/components/meshcore/*.vue",
        "meshchatnext/src/frontend/js/meshcoreUi.js",
        "meshchatnext/src/frontend/js/meshcoreNotifications.js",
        "tests/frontend/MeshCore*.test.js",
        "meshchatnext/src/backend/http/register.py",
        "meshchatnext/meshchat.py",
        "meshchatnext/android_push_bridge.py",
        "android/app/src/main/java/com/meshchatnext/AndroidNotificationBridge.java",
        "android/app/src/main/java/com/meshchatnext/MainActivity.java",
        "android/app/src/test/java/com/meshchatnext/CallNotificationTrustedActionTest.java",
        "tests/backend/test_meshcore_*.py",
        "scripts/android/meshcore-tests/*.py",
        "scripts/android/meshcore-tests/*.json",
        "scripts/android/meshcore-tests/*.java",
        "scripts/android/meshcore-tests/*.xml",
        "scripts/android/meshcore-tests/*.txt",
    ]
    overlay = {}
    for pattern in patterns:
        for source in sorted(repo.glob(pattern)):
            if source.is_symlink():
                raise ValueError(f"Expected regular source: {source}")
            relative = source.relative_to(repo)
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            overlay[str(relative)] = sha256(target)
    for name in dependencies:
        shutil.copy2(args.dependencies / name, dest / "android/vendor" / name)
    # Only the generated test checkout changes; production retains port 8000.
    if args.backend_port != 8000:
        replacements = {
            "MainActivity.java": (
                "SERVER_PORT = 8000",
                f"SERVER_PORT = {args.backend_port}",
            ),
            "RemoteBackendUrl.java": (
                "127.0.0.1:8000",
                f"127.0.0.1:{args.backend_port}",
            ),
            "TelephoneNativeAudioSession.java": (
                "127.0.0.1:8000",
                f"127.0.0.1:{args.backend_port}",
            ),
        }
        for name, (old, new) in replacements.items():
            relative = Path("android/app/src/main/java/com/meshchatnext") / name
            target = dest / relative
            content = target.read_text()
            if old not in content:
                raise ValueError(f"Missing expected test-port source: {relative}")
            target.write_text(content.replace(old, new))
            overlay[str(relative)] = sha256(target)
    label = dest / "android/app/src/debug/res/values/meshcore.xml"
    label.parent.mkdir(parents=True, exist_ok=True)
    label.write_text(
        '<resources><string name="app_name">Meshchat neXt MeshCore Test</string></resources>\n'
    )
    (dest / "meshcore-overlay-provenance.json").write_text(
        json.dumps(
            {
                "source_overlay_sha256": overlay,
                "dependencies_sha256": dependencies,
                "backend_port": args.backend_port,
            },
            indent=2,
        )
        + "\n",
    )
    print(f"Prepared MeshCore integration tree: {dest}")
    print(
        "Build with a separate MESHCHATNEXT_APPLICATION_ID and -PmeshchatnextMeshCore."
    )


if __name__ == "__main__":
    main()
