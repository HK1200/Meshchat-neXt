#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Install a source-pinned, hash-verified security SDK through supported UV metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

VENDOR = "a83ff4e7e166b048089d79dd1acfbd6c84c77ac4"
MACOS_X64_VENDOR = "de549958c79576345140088bd5482d0b0f8a2614"
PYTHON_SOURCE = "de414a57119abef52784d8993e341d53aed635fc2b05c2607d9f98a2c5b72032"
EXPAT_SOURCE = "c624ba2998fc65df1163a49641ff3f9ab73138b11641d92c86bee0fb01b1bc7f"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def host_target() -> tuple[str, str, str, str]:
    arch = "aarch64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"
    if platform.machine().lower() not in {"arm64", "aarch64", "x86_64", "amd64"}:
        raise RuntimeError("Unsupported SDK host architecture")
    if sys.platform == "win32":
        if arch != "x86_64":
            raise RuntimeError("Windows ARM SDK is not qualified")
        return "windows-x64", "windows", arch, "none"
    if sys.platform == "darwin":
        return (
            "macos-" + ("arm64" if arch == "aarch64" else "x64"),
            "darwin",
            arch,
            "none",
        )
    if sys.platform == "linux":
        return (
            "linux-" + ("arm64" if arch == "aarch64" else "x64"),
            "linux",
            arch,
            "gnu",
        )
    raise RuntimeError("Unsupported SDK host operating system")


def verify_sdk(artifact: Path, entry: dict, target: str, output: Path) -> dict:
    if sha(artifact) != entry["artifact_zip_sha256"]:
        raise ValueError("SDK artifact checksum mismatch")
    with zipfile.ZipFile(artifact) as archive:
        if sorted(archive.namelist()) != ["SDK-PROVENANCE.json", "python-sdk.tar.gz"]:
            raise ValueError("Unexpected SDK artifact contents")
        if archive.getinfo("SDK-PROVENANCE.json").file_size > 16 * 1024 * 1024:
            raise ValueError("Oversized SDK provenance")
        report = json.loads(archive.read("SDK-PROVENANCE.json"))
        expected = {
            "target": target,
            "upstream_source": MACOS_X64_VENDOR if target == "macos-x64" else VENDOR,
            "python_source_sha256": PYTHON_SOURCE,
            "expat_source_sha256": EXPAT_SOURCE,
            "sdk_archive_sha256": entry["sdk_archive_sha256"],
            "sdk_archive_size": entry["sdk_archive_size"],
        }
        if any(report.get(key) != value for key, value in expected.items()):
            raise ValueError("SDK provenance does not match pinned security inputs")
        if (
            report["actual_runtime"].get("python") != "3.14.10"
            or report["actual_runtime"].get("expat") != "expat_2.10.0"
        ):
            raise ValueError("SDK producer runtime is not security fixed")
        if target == "windows-x64":
            backport = report.get("cpython_security_backport") or {}
            if (
                backport.get("commit") != "79c504454a52990bfa02374fdb625fdce32844b0"
                or backport.get("patch_sha256")
                != "cb302c375b917f3730f0c13ffcc14a18f6d16754e762d22f889c821c928c77e6"
            ):
                raise ValueError(
                    "Windows SDK lacks the required official CPython security backport"
                )
        if archive.getinfo("python-sdk.tar.gz").file_size != entry["sdk_archive_size"]:
            raise ValueError("SDK archive size mismatch")
        with (
            archive.open("python-sdk.tar.gz") as source,
            output.open("wb") as destination,
        ):
            shutil.copyfileobj(source, destination)
    if sha(output) != entry["sdk_archive_sha256"]:
        raise ValueError("SDK distribution checksum mismatch")
    found_files, found_links, seen = {}, {}, set()
    with tarfile.open(output, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or not path.parts
                or path.parts[0] != "python"
                or ".." in path.parts
                or member.name in seen
            ):
                raise ValueError("Unsafe or duplicate SDK archive path")
            seen.add(member.name)
            if member.isdir():
                continue
            if member.issym():
                link = PurePosixPath(member.linkname)
                combined = list(path.parent.parts)
                if link.is_absolute():
                    raise ValueError("Absolute SDK symlink is forbidden")
                for part in link.parts:
                    if part == "..":
                        if len(combined) <= 1:
                            raise ValueError("SDK symlink escapes distribution")
                        combined.pop()
                    elif part != ".":
                        combined.append(part)
                found_links[member.name] = member.linkname
            elif member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Missing SDK file contents")
                with stream:
                    digest = hashlib.sha256()
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                    found_files[member.name] = digest.hexdigest()
            elif member.islnk() and member.linkname in found_files:
                found_files[member.name] = found_files[member.linkname]
            else:
                raise ValueError("Unsupported SDK archive entry")
    if found_files != report["files"] or found_links != report["symlinks"]:
        raise ValueError("SDK complete file inventory mismatch")
    for required in [
        "python/PYTHON.json",
        "python/licenses/LICENSE.cpython.txt",
        "python/licenses/LICENSE.expat.txt",
    ]:
        if required not in found_files:
            raise ValueError("SDK license or metadata is missing")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        type=Path,
        default=Path(__file__).with_name("expat-runtime-inputs.json"),
    )
    parser.add_argument(
        "--artifact-file",
        type=Path,
        help="Use an already downloaded archive, still enforcing every pinned hash",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target, os_name, arch, libc = host_target()
    inputs = json.loads(args.inputs.read_text())
    if inputs.get("schema") != 1 or target not in inputs.get("targets", {}):
        raise RuntimeError("No qualified pinned security SDK exists for this target")
    entry = inputs["targets"][target]
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Pinned UV is required")
    if not subprocess.check_output([uv, "--version"], text=True).startswith(
        "uv 0.13.6 "
    ):
        raise RuntimeError("The verified UV version must be 0.13.6")
    cache = root / ".python-security-runtime" / entry["sdk_archive_sha256"][:20]
    cache.mkdir(parents=True, exist_ok=True)
    artifact = (
        args.artifact_file.resolve() if args.artifact_file else cache / "artifact.zip"
    )
    if args.artifact_file is None:
        gh = shutil.which("gh")
        if gh is None:
            raise RuntimeError("GitHub CLI is required for qualified SDK retrieval")
        repository = entry.get("repository", inputs["repository"])
        if repository not in {"HK1200/Meshchat-neXt", "HK1200/MeshChatX-HK"}:
            raise RuntimeError("Unexpected SDK repository")
        metadata = json.loads(
            subprocess.check_output(
                [
                    gh,
                    "api",
                    f"repos/{repository}/actions/artifacts/{int(entry['artifact_id'])}",
                ],
                text=True,
            )
        )
        if (
            metadata.get("expired")
            or metadata.get("digest") != "sha256:" + entry["artifact_zip_sha256"]
            or metadata.get("workflow_run", {}).get("head_sha")
            != entry["producer_head"]
            or metadata.get("workflow_run", {}).get("id") != entry["producer_run"]
            or metadata.get("name") != entry["artifact_name"]
        ):
            raise RuntimeError("SDK artifact source identity or digest mismatch")
        job = json.loads(
            subprocess.check_output(
                [
                    gh,
                    "api",
                    f"repos/{repository}/actions/jobs/{int(entry['producer_job'])}",
                ],
                text=True,
            )
        )
        if (
            job.get("conclusion") != "success"
            or job.get("run_id") != entry["producer_run"]
            or job.get("name") != f"Build Expat-fixed Python SDK ({target})"
        ):
            raise RuntimeError("Required genuine native SDK target did not pass")
        if not artifact.exists():
            with artifact.open("wb") as stream:
                subprocess.run(
                    [
                        gh,
                        "api",
                        f"repos/{repository}/actions/artifacts/{int(entry['artifact_id'])}/zip",
                    ],
                    stdout=stream,
                    check=True,
                )
    distribution = cache / "python-sdk.tar.gz"
    verify_sdk(artifact, entry, target, distribution)
    key = f"cpython-3.14.10-{os_name}-{arch}-{libc}"
    metadata = {
        key: {
            "name": "cpython",
            "arch": {"family": arch, "variant": None},
            "os": os_name,
            "libc": libc,
            "major": 3,
            "minor": 14,
            "patch": 10,
            "prerelease": "",
            "variant": None,
            "build": entry["distribution_build"],
            "url": distribution.as_uri(),
            "sha256": entry["sdk_archive_sha256"],
        }
    }
    download_json = cache / "downloads.json"
    download_json.write_text(json.dumps(metadata, indent=2))
    managed = cache / "managed"
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            word in key.upper()
            for word in [
                "TOKEN",
                "PASSWORD",
                "SECRET",
                "CREDENTIAL",
                "RNS_ID_PATH",
                "ACCESS_KEY",
            ]
        )
    }
    for variable in (
        "PYTHONHOME",
        "PYTHONPATH",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
    ):
        env.pop(variable, None)
    env["UV_PYTHON_INSTALL_BIN"] = "0"
    subprocess.run(
        [
            uv,
            "python",
            "install",
            "--install-dir",
            str(managed),
            "--python-downloads-json-url",
            str(download_json),
            "3.14.10",
        ],
        env=env,
        check=True,
    )
    executable = (
        managed / key / ("python.exe" if os_name == "windows" else "bin/python3.14")
    )
    probe = "import sys,pyexpat,ssl,json;print(json.dumps({'python':sys.version.split()[0],'expat':pyexpat.EXPAT_VERSION,'openssl':ssl.OPENSSL_VERSION}))"
    actual = json.loads(
        subprocess.check_output(
            [str(executable), "-I", "-S", "-B", "-c", probe], text=True, env=env
        )
    )
    if actual["python"] != "3.14.10" or actual["expat"] != "expat_2.10.0":
        raise RuntimeError("Actual installed SDK is not security fixed")
    result = {
        "passed": True,
        "target": target,
        "python_executable": str(executable),
        "actual_runtime": actual,
        "sdk_archive_sha256": entry["sdk_archive_sha256"],
        "artifact_zip_sha256": entry["artifact_zip_sha256"],
    }
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if os.environ.get("GITHUB_ENV"):
        with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
            stream.write("UV_PYTHON=" + str(executable) + "\n")
            sdk_root = (
                executable.parent if os_name == "windows" else executable.parent.parent
            )
            for variable in ("pythonLocation", "Python_ROOT_DIR", "Python3_ROOT_DIR"):
                stream.write(variable + "=" + str(sdk_root) + "\n")
            if os_name == "linux":
                stream.write("LD_LIBRARY_PATH=" + str(sdk_root / "lib") + "\n")
        with Path(os.environ["GITHUB_PATH"]).open("a") as stream:
            stream.write(str(executable.parent) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
