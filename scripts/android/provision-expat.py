#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Rebuild only Chaquopy's pyexpat extension with pinned Expat security fixes.

Original vendor archives are immutable. A separate local Maven repository
replaces only pyexpat; all other archive entries are checked byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "3.11.17-0"
CPYTHON = "e6392eb68a39cef49c9fe6431253050caa17a426"
NDK = "27.3.13750724"
SOURCES = {
    "pyexpat.c": (
        f"https://raw.githubusercontent.com/python/cpython/{CPYTHON}/Modules/pyexpat.c",
        "a71e4173e667bc690a3df2b8b8fe434c64a589fff0160d4aabf8a92149ad2ee5",
    ),
    "clinic/pyexpat.c.h": (
        f"https://raw.githubusercontent.com/python/cpython/{CPYTHON}/Modules/clinic/pyexpat.c.h",
        "85101449af31c3a9749bc596b3b10efd90398c5c3d9e4a587beaa20aadb44b5c",
    ),
    "expat-2.10.0.tar.xz": (
        "https://github.com/libexpat/libexpat/releases/download/R_2_10_0/expat-2.10.0.tar.xz",
        "c624ba2998fc65df1163a49641ff3f9ab73138b11641d92c86bee0fb01b1bc7f",
    ),
}
VENDOR = {
    "target-3.11.17-0.pom": "6bcee8ab7395889bff669f13c95a07362d6089e0ce07a9d0b2bd6d6c218f139c",
    "target-3.11.17-0-stdlib-pyc.zip": "5b853d5631b8f482f4f181af3d7b8162c17f440da5eafc5e1f64b23faf53f773",
    "target-3.11.17-0-arm64-v8a.zip": "399b58d04898f2c7d5f0044e141bdf3818552e538e5f36d06d7fe0bebc298582",
    "target-3.11.17-0-x86_64.zip": "a479a9c74ca9e900f30b6089ffd23a10d74fe7a9f427d967bceddf8f3fe206f1",
    "target-3.11.17-0-armeabi-v7a.zip": "7516b90fcb8a5a2df70e5f9899aab7e63fa43efa0455c3ba7b846ae54d70ee2c",
}
COMPILERS = {
    "x86_64": "x86_64-linux-android21-clang",
    "arm64-v8a": "aarch64-linux-android21-clang",
    "armeabi-v7a": "armv7a-linux-androideabi21-clang",
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(path: Path, url: str, digest: str) -> Path:
    if not url.startswith("https://"):
        raise RuntimeError("Only pinned HTTPS sources are permitted")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_name(path.name + ".download")
        with (
            urllib.request.urlopen(url, timeout=60) as response,  # noqa: S310 - HTTPS guard and pinned digest above
            temporary.open("wb") as stream,
        ):
            shutil.copyfileobj(response, stream)
        if sha(temporary) != digest:
            raise RuntimeError(f"Untrusted download: {path.name}")
        temporary.replace(path)
    if sha(path) != digest:
        raise RuntimeError(f"Input checksum mismatch: {path.name}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--abis", default="arm64-v8a,x86_64,armeabi-v7a")
    args = parser.parse_args()
    abis = args.abis.split(",")
    if (
        not abis
        or len(set(abis)) != len(abis)
        or any(abi not in COMPILERS for abi in abis)
    ):
        raise RuntimeError("Unsupported or duplicate Android ABI")
    if sys.platform != "linux":
        raise RuntimeError(
            "This verified Android security build requires the Linux NDK host"
        )
    sdk = Path(
        os.environ.get("ANDROID_SDK_ROOT")
        or os.environ.get("ANDROID_HOME")
        or Path.home() / "Android/Sdk"
    )
    ndk = sdk / "ndk" / NDK
    compiler_root = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    if not (compiler_root / "clang").is_file():
        raise RuntimeError(f"Required existing Android NDK {NDK} is unavailable")
    cmake = shutil.which("cmake")
    if cmake is None:
        raise RuntimeError("CMake is required for the Android security build")
    work = ROOT / "temp-tests/android-expat-security"
    inputs = work / "inputs"
    repository = ROOT / "android/.expat-runtime-maven"
    destination = repository / f"com/chaquo/python/target/{VERSION}"
    destination.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in SOURCES.items():
        fetch(inputs / name, url, digest)
    source = work / "expat-2.10.0"
    if not source.exists():
        with tarfile.open(inputs / "expat-2.10.0.tar.xz") as archive:
            for member in archive.getmembers():
                if (
                    not Path(member.name).parts
                    or Path(member.name).parts[0] != "expat-2.10.0"
                    or ".." in Path(member.name).parts
                ):
                    raise RuntimeError("Unsafe Expat archive entry")
            archive.extractall(work, filter="data")
    gradle = Path(os.environ.get("GRADLE_USER_HOME", Path.home() / ".gradle"))
    vendor_cache = (
        gradle / f"caches/modules-2/files-2.1/com.chaquo.python/target/{VERSION}"
    )
    names = [f"target-{VERSION}.pom", f"target-{VERSION}-stdlib-pyc.zip"]
    names += [f"target-{VERSION}-{abi}.zip" for abi in abis]
    vendor_inputs = {}
    for name in names:
        cached = next(vendor_cache.rglob(name), None) if vendor_cache.exists() else None
        local = inputs / name
        if not local.exists() and cached is not None:
            if sha(cached) != VENDOR[name]:
                raise RuntimeError("Cached official Android target checksum mismatch")
            shutil.copyfile(cached, local)
        vendor_inputs[name] = fetch(
            local,
            f"https://repo.maven.apache.org/maven2/com/chaquo/python/target/{VERSION}/{name}",
            VENDOR[name],
        )
    reports = []
    for abi in abis:
        original = vendor_inputs[f"target-{VERSION}-{abi}.zip"]
        target = work / ("target-" + abi)
        target.mkdir(exist_ok=True)
        with zipfile.ZipFile(original) as archive:
            for name in archive.namelist():
                if ".." in Path(name).parts or name.startswith("/"):
                    raise RuntimeError("Unsafe Android target archive")
                if name.startswith(("include/", "jniLibs/")):
                    archive.extract(name, target)
        build = work / ("build-" + abi)
        subprocess.run(
            [
                cmake,
                "-S",
                str(source),
                "-B",
                str(build),
                "-DCMAKE_TOOLCHAIN_FILE="
                + str(ndk / "build/cmake/android.toolchain.cmake"),
                "-DANDROID_ABI=" + abi,
                "-DANDROID_PLATFORM=21",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DBUILD_SHARED_LIBS=OFF",
                "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
                "-DEXPAT_BUILD_TOOLS=OFF",
                "-DEXPAT_BUILD_EXAMPLES=OFF",
                "-DEXPAT_BUILD_TESTS=OFF",
                "-DEXPAT_BUILD_DOCS=OFF",
                "-DEXPAT_DTD=ON",
                "-DEXPAT_NS=ON",
                "-DCMAKE_C_FLAGS=-fvisibility=hidden",
            ],
            check=True,
        )
        subprocess.run([cmake, "--build", str(build), "--parallel", "2"], check=True)
        libraries = list(build.rglob("libexpat.a"))
        if len(libraries) != 1:
            raise RuntimeError("Expected one locally built static Expat library")
        module = work / ("pyexpat-" + abi + ".so")
        include = target / "include/python3.11"
        subprocess.run(
            [
                str(compiler_root / COMPILERS[abi]),
                "-shared",
                "-fPIC",
                "-O2",
                "-fvisibility=hidden",
                "-DXML_STATIC",
                "-DHAVE_EXPAT_CONFIG_H",
                "-I" + str(include),
                "-I" + str(include / "internal"),
                "-I" + str(source / "lib"),
                "-I" + str(build),
                str(inputs / "pyexpat.c"),
                str(libraries[0]),
                "-L" + str(target / "jniLibs" / abi),
                "-lpython3.11",
                "-lm",
                "-Wl,--no-undefined",
                "-Wl,-z,max-page-size=16384",
                "-o",
                str(module),
            ],
            check=True,
        )
        if b"expat_2.10.0" not in module.read_bytes():
            raise RuntimeError("Built parser lacks the required Expat version")
        member = f"lib-dynload/{abi}/pyexpat.cpython-311.so"
        output = destination / original.name
        temporary = output.with_suffix(".zip.new")
        with (
            zipfile.ZipFile(original) as before,
            zipfile.ZipFile(temporary, "w") as after,
        ):
            if before.namelist().count(member) != 1:
                raise RuntimeError("Expected exactly one original parser")
            for item in before.infolist():
                after.writestr(
                    item,
                    module.read_bytes()
                    if item.filename == member
                    else before.read(item.filename),
                )
        with zipfile.ZipFile(original) as before, zipfile.ZipFile(temporary) as after:
            if before.namelist() != after.namelist():
                raise RuntimeError("Android target inventory changed")
            changed = [
                name
                for name in before.namelist()
                if before.read(name) != after.read(name)
            ]
            if changed != [member]:
                raise RuntimeError("Files other than the parser changed")
        temporary.replace(output)
        reports.append(
            {
                "abi": abi,
                "original_sha256": sha(original),
                "patched_sha256": sha(output),
                "module_sha256": sha(module),
                "changed_members": changed,
            }
        )
    for name in names[:2]:
        shutil.copyfile(vendor_inputs[name], destination / name)
    licenses = repository / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copyfile(source / "COPYING", licenses / "LICENSE.expat.txt")
    report = {
        "kind": "Owner-built CPython pyexpat security backport; not an official vendor target",
        "python_kernel": "3.11.17",
        "expat": "2.10.0",
        "cpython_source": CPYTHON,
        "inputs": {name: digest for name, (_, digest) in SOURCES.items()},
        "abis": reports,
        "actual_packaged_runtime_validation_pending": True,
    }
    (repository / "PROVENANCE.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
