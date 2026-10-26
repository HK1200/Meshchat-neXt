#!/usr/bin/env python3
"""Assemble a fresh release tree without replacing the development native inputs."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

GIT = shutil.which("git")
if GIT is None:
    raise SystemExit("git is required to prepare a release tree")

EXTRA_SOURCE = (
    "android/app/src/main/java/com/meshchatnext/PcmFrameAccumulator.java",
    "android/app/src/main/java/com/meshchatnext/TelephoneBluetoothRoute.java",
    "android/app/src/test/java/com/meshchatnext/PcmFrameAccumulatorTest.java",
    "android/release/native-inputs.json",
    "android/release/README.md",
    "meshchatnext/android_opus.py",
    "scripts/android/OPUS.md",
    "scripts/android/provision-opus.py",
    "scripts/android/verify-native-apk.py",
    "scripts/android/runtime-tests/README.md",
    "scripts/android/runtime-tests/foreground/AndroidManifest.xml",
    "scripts/android/runtime-tests/foreground/NumpyTestActivity.java",
    "scripts/android/runtime-tests/requirements.txt",
    "scripts/android/runtime-tests/prepare-assets.py",
    "scripts/android/runtime-tests/numpy_runtime.py",
    "scripts/android/runtime-tests/numpy_full_suite.py",
    "scripts/android/runtime-tests/complex_dot_check.c",
    "scripts/android/runtime-tests/java/com/meshchatnext/NumpyInstrumentation.java",
    "scripts/android/prepare-stable-build.py",
    "tests/frontend/CallAnswerState.test.js",
    "tests/test_android_opus_provision.py",
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--native-inputs",
        required=True,
        type=Path,
        help="Root containing the exact paths pinned in android/release/native-inputs.json",
    )
    parser.add_argument(
        "--frontend",
        required=True,
        type=Path,
        help="Prepared meshchatnext/public tree (rebuild frontend after assembly)",
    )
    parser.add_argument(
        "--dest", required=True, type=Path, help="New, nonexistent build directory"
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    dest = args.dest.resolve()
    if dest.exists() or dest == repo or repo in dest.parents:
        parser.error("--dest must be a new directory outside the source checkout")
    manifest = json.loads((repo / "android/release/native-inputs.json").read_text())
    inputs = args.native_inputs.resolve()
    verified = []
    for name, expected in manifest["files"].items():
        rel = PurePosixPath(name)
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or not (
                name.startswith("android/vendor/")
                or name.startswith("android/app/src/main/jniLibs/")
            )
        ):
            raise ValueError(f"Unsafe native input path: {name}")
        source = inputs / name
        if source.is_symlink() or not source.is_file() or digest(source) != expected:
            raise ValueError(f"Missing or mismatched native input: {name}")
        verified.append((name, source))
    if not (args.frontend / "index.html").is_file():
        parser.error("--frontend must contain index.html and its prepared assets")
    tracked = (
        subprocess.check_output([GIT, "ls-files", "-z"], cwd=repo).decode().split("\0")
    )
    names = sorted(set(filter(None, tracked)) | set(EXTRA_SOURCE))
    # Check all inputs before creating any output; never scoop up untracked backups or keys.
    for name in names:
        source = repo / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Expected regular release source: {name}")
    dest.mkdir(parents=True)
    hashes = {}
    for name in names:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / name, target)
        hashes[name] = digest(target)
    shutil.copytree(args.frontend, dest / "meshchatnext/public", dirs_exist_ok=True)
    for name, source in verified:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    provenance = {
        "source_head": subprocess.check_output(
            [GIT, "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output([GIT, "status", "--porcelain"], cwd=repo)
        ),
        "tracked_sources_dirty": bool(
            subprocess.check_output([GIT, "diff", "HEAD", "--name-only"], cwd=repo)
        ),
        "excluded_untracked_files_present": bool(
            subprocess.check_output(
                [GIT, "ls-files", "--others", "--exclude-standard"], cwd=repo
            )
        ),
        "source_files_sha256": hashes,
        "native_inputs": manifest,
    }
    (dest / "release-input-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print(
        f"Prepared {len(names)} source files and {len(verified)} verified native inputs in {dest}"
    )


if __name__ == "__main__":
    main()
