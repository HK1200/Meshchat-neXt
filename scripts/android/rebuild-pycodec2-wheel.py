#!/usr/bin/env python3
"""Rebuild the pinned Android Codec2 module with its exported CPython initializer."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

SOURCE_SHA256 = "7e868cdc3927395cc4c6ec97621c62752d6700c2b94c9e990c73f41a5023b86d"
HEADER_BASE = "https://raw.githubusercontent.com/drowe67/codec2/25014a290752fb830390ff24a612a9694319a47a/"
HEADERS = {
    "src/codec2.h": "d60b760c3bae5c37891b4ca2272bac22ace62ed1088320e20b0c889a952c8c83",
    "cmake/version.h.in": "4611aba793ad9ed68bb22491952fc37dbb1b0e299f5ce4546e81a7aea1676a57",
}
TARGETS = {
    "arm64-v8a": "aarch64-linux-android",
    "x86_64": "x86_64-linux-android",
    "armeabi-v7a": "armv7a-linux-androideabi",
}


def extract(archive, prefix, destination):
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            path = Path(name)
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive entry")
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(name))


def rebuild(args):
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Choose a new output wheel to preserve the input")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.wheel) as archive:
        entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    source = entries["pycodec2/pycodec2.c"]
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("Expected the pinned pycodec2 4.1.1 C source")
    with tempfile.TemporaryDirectory(prefix="codec2-build-") as folder:
        build = Path(folder)
        extract(args.target, "include/python3.11/", build)
        extract(args.target, f"jniLibs/{args.abi}/libpython3.11.so", build)
        extract(args.numpy, "numpy/core/include/", build)
        include = build / "include/codec2"
        include.mkdir(parents=True, exist_ok=True)
        for path, digest in HEADERS.items():
            with urllib.request.urlopen(HEADER_BASE + path, timeout=30) as response:
                body = response.read(1_000_001)
            if hashlib.sha256(body).hexdigest() != digest:
                raise ValueError("Codec2 header checksum mismatch")
            if path.endswith(".in"):
                body = (body.decode().replace("@CODEC2_VERSION_MAJOR@", "1")
                        .replace("@CODEC2_VERSION_MINOR@", "2").replace("@CODEC2_VERSION_PATCH@", "0")
                        .replace("@CODEC2_VERSION@", "1.2.0").replace("#cmakedefine", "#define")).encode()
            (include / Path(path).name.removesuffix(".in")).write_bytes(body)
        source_path = build / "pycodec2.c"
        source_path.write_bytes(source)
        (build / "libcodec2.so").write_bytes(entries["pycodec2/libcodec2.so"])
        library = build / "pycodec2.so"
        subprocess.run([
            str(args.toolchain / f"{TARGETS[args.abi]}24-clang"),
            "-shared", "-O2", "-fPIC", "-fvisibility=default", "-UCYTHON_NO_PYINIT_EXPORT",
            "-I" + str(build / "include"), "-I" + str(build / "include/python3.11"),
            "-I" + str(build / "numpy/core/include"), str(source_path),
            "-L" + str(build), "-L" + str(build / "jniLibs" / args.abi),
            "-lcodec2", "-lpython3.11", "-lm", "-Wl,--no-undefined",
            "-Wl,-z,max-page-size=16384", "-o", str(library),
        ], check=True)
        symbols = subprocess.check_output(
            [str(args.toolchain / "llvm-readelf"), "--dyn-syms", "--wide", str(library)], text=True
        )
        if not any("GLOBAL DEFAULT" in line and line.rstrip().endswith(" PyInit_pycodec2")
                   and " UND " not in line for line in symbols.splitlines()):
            raise ValueError("The rebuilt library does not export PyInit_pycodec2")
        entries["pycodec2/pycodec2.so"] = library.read_bytes()
    record = next(name for name in entries if name.endswith(".dist-info/RECORD"))
    content = io.StringIO()
    writer = csv.writer(content, lineterminator="\n")
    for name, body in sorted(entries.items()):
        if name != record:
            digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip("=")
            writer.writerow([name, "sha256=" + digest, len(body)])
    writer.writerow([record, "", ""])
    entries[record] = content.getvalue().encode()
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(entries.items()):
            archive.writestr(name, body)
    proof = {
        "abi": args.abi, "source_sha256": SOURCE_SHA256, "header_sha256": HEADERS,
        "initializer_exported": True,
        "inputs": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in (args.wheel, args.numpy, args.target)},
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    output.with_suffix(".provenance.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abi", choices=TARGETS, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--numpy", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path, required=True,
                        help="Android NDK toolchains/llvm/prebuilt/linux-x86_64/bin")
    parser.add_argument("--output", type=Path, required=True)
    rebuild(parser.parse_args())
