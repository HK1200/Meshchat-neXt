#!/usr/bin/env python3
"""Prepare isolated Android runtime-test assets from the exact packaged NumPy wheel."""

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--vendor-dir", required=True, type=Path)
parser.add_argument("--abis", default="arm64-v8a,x86_64")
parser.add_argument(
    "--output", required=True, type=Path, help="New, nonexistent test asset directory"
)
args = parser.parse_args()
if args.output.exists():
    parser.error("Refusing to overwrite existing test assets")
source = Path(__file__).resolve().parent
tags = [abi.replace("-", "_") for abi in args.abis.split(",")]
wheels = sorted(
    p for p in args.vendor_dir.glob("numpy-*.whl") if any(tag in p.name for tag in tags)
)
if not wheels:
    parser.error("No packaged NumPy wheel found")
args.output.mkdir(parents=True)
deps = args.output / "runtime-deps"
deps.mkdir()
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--dest",
        str(deps),
        "-r",
        str(source / "requirements.txt"),
    ],
    check=True,
)
for name in ["numpy_runtime.py", "numpy_full_suite.py"]:
    shutil.copy2(source / name, args.output / name)


# Python/tests/data must agree across architecture wheels; keep native imports
# in the installed app. Complete parent packages preserve relative test imports.
def test_payload(wheel):
    with zipfile.ZipFile(wheel) as archive:
        return {
            name: archive.read(name)
            for name in archive.namelist()
            if name.startswith("numpy/")
            and not name.endswith("/")
            and ".so" not in Path(name).name
        }


payload = test_payload(wheels[0])
for wheel in wheels[1:]:
    other = test_payload(wheel)
    test_names = {
        name
        for name in payload
        if "/tests/" in name
        or name.endswith("/__init__.py")
        or name == "numpy/conftest.py"
    }
    if any(other.get(name) != payload[name] for name in test_names):
        raise ValueError("NumPy Python/test payload differs across selected wheels")
with zipfile.ZipFile(deps / "numpy-tests.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(payload.items()):
        archive.writestr(name, data)
print("Prepared isolated runtime tests; production dependencies unchanged")
