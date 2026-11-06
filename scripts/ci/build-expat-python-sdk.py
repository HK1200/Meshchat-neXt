#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Build a stable CPython SDK with the vendor's verified Expat security recipe.

No release publication, private profiles or signing identities are used. Only
an install subtree and its public input/hash report are staged for CI review.
"""

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
from pathlib import Path
from typing import BinaryIO, cast

SOURCE = "a83ff4e7e166b048089d79dd1acfbd6c84c77ac4"
REPOSITORY = "https://github.com/astral-sh/python-build-standalone.git"
PYTHON_SHA256 = "de414a57119abef52784d8993e341d53aed635fc2b05c2607d9f98a2c5b72032"
EXPAT_SHA256 = "c624ba2998fc65df1163a49641ff3f9ab73138b11641d92c86bee0fb01b1bc7f"
WINDOWS_BACKPORT_COMMIT = "79c504454a52990bfa02374fdb625fdce32844b0"
WINDOWS_BACKPORT_SHA256 = (
    "cb302c375b917f3730f0c13ffcc14a18f6d16754e762d22f889c821c928c77e6"
)
WINDOWS_VENDOR_HOOK_SHA256 = (
    "f761bb904e664e39a44d88bd5e59b4a690b4d0c8e4785c5b2c913a552b4c9667"
)
RUNTIME_PROBE = "import sys,pyexpat,ssl,json,xml.etree.ElementTree as E\nassert E.fromstring('<root><name>Alice \\u2603</name></root>').find('name').text=='Alice \\u2603'\npyexpat.ParserCreate().Parse('<verified/>', True)\ntry:\n    pyexpat.ParserCreate().Parse('<root>', True)\nexcept pyexpat.ExpatError:\n    pass\nelse:\n    raise AssertionError('Malformed XML accepted')\nentities=['<!ENTITY a0 \"1234567890\">']\nfor i in range(1,9):\n    entities.append('<!ENTITY a%d \"%s\">'%(i,('&a%d;'%(i-1))*10))\ntry:\n    pyexpat.ParserCreate().Parse('<!DOCTYPE a ['+''.join(entities)+']><a>&a8;</a>', True)\nexcept pyexpat.ExpatError as error:\n    assert error.code==pyexpat.errors.codes[pyexpat.errors.XML_ERROR_AMPLIFICATION_LIMIT_BREACH],error\nelse:\n    raise AssertionError('Entity amplification limit not enforced')\nprint(json.dumps({'python':sys.version.split()[0],'expat':pyexpat.EXPAT_VERSION,'openssl':ssl.OPENSSL_VERSION,'parser_cases':['ElementTree native CAPI Unicode','direct valid XML','malformed rejection','entity amplification rejection']}))\n"

TARGETS = {
    "linux-x64": ("linux", "x86_64-unknown-linux-gnu", "pgo+lto"),
    "linux-arm64": ("linux", "aarch64-unknown-linux-gnu", "pgo+lto"),
    "windows-x64": ("win32", "x86_64-pc-windows-msvc", "pgo"),
    "macos-arm64": ("darwin", "aarch64-apple-darwin", "pgo+lto"),
    "macos-x64": ("darwin", "x86_64-apple-darwin", "pgo+lto"),
}


LINUX_IMAGES = {
    "linux-x64": (
        "build.debian13-x86_64",
        "linux_x86_64",
        "sha256:d5d4394364f03b9ca1473983e8715f6907da00a29f80b36bb45dcdbd1ee4aee1",
    ),
    "linux-arm64": (
        "build.debian13",
        "linux_aarch64",
        "sha256:0df7ef726abe37921e327ebbcc60176090c468f1fa5f636c045c8a375846e323",
    ),
}


def prepare_linux_image(
    vendor: Path, target: str, uv: str, env: dict[str, str]
) -> dict[str, str]:
    """Follow upstream CI's registry-cache/image export path without source edits."""
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError(
            "Docker Buildx is required for the official Linux SDK recipe"
        )
    name, host, digest = LINUX_IMAGES[target]
    cache = "ghcr.io/astral-sh/python-build-standalone@" + digest
    run(
        [uv, "run", "--frozen", "--no-dev", "build.py", "--make-target", "empty"],
        vendor,
        env,
    )
    dockerfile = vendor / "build" / (name + ".Dockerfile")
    image_file = vendor / "build" / ("image-" + name + "." + host)
    run(
        [
            docker,
            "buildx",
            "build",
            "--progress=plain",
            "--load",
            "--cache-from",
            "type=registry,ref=" + cache,
            "--iidfile",
            str(image_file),
            "--file",
            str(dockerfile),
            ".",
        ],
        vendor,
        env,
    )
    image_id = image_file.read_text().strip()
    if not image_id.startswith("sha256:") or len(image_id) != 71:
        raise RuntimeError("Invalid loaded SDK build image identity")
    image_tar = Path(str(image_file) + ".tar")
    run([docker, "image", "save", "--output", str(image_tar), image_id], vendor, env)
    # Upstream performs this after --make-target empty, keeping image artifacts
    # newer than its generated Dockerfiles/Makefiles so make reuses the image.
    os.utime(image_file, None)
    os.utime(image_tar, None)
    return {
        "registry_cache": cache,
        "dockerfile_sha256": sha(dockerfile),
        "image_id": image_id,
        "method": "Official upstream CI cache import and image export; vendor source and authenticated dependency pins unchanged",
    }


def apply_windows_security_backport(root: Path, vendor: Path) -> dict[str, str]:
    """Use the vendor's existing exact source-patch hook for CPython's official fix."""
    patch = root / "scripts/ci/patches/cpython-3.14-expat-2.10.0.patch"
    hook = vendor / "cpython-windows/build.py"
    if sha(patch) != WINDOWS_BACKPORT_SHA256 or sha(hook) != WINDOWS_VENDOR_HOOK_SHA256:
        raise RuntimeError("Unexpected Windows security patch or vendor hook input")
    destination = vendor / "cpython-windows/patch-cpython-expat-2.10.0.patch"
    if destination.exists():
        raise RuntimeError("Existing Windows security patch requires review")
    original = hook.read_bytes().decode("utf-8")
    anchor = '    patches = ["patch-disable-uwp.patch"]'
    if original.count(anchor) != 1:
        raise RuntimeError("Supported Windows source-patch hook changed")
    updated = original.replace(
        anchor, anchor + '\n    patches.append("patch-cpython-expat-2.10.0.patch")'
    )
    hook.write_bytes(updated.encode("utf-8"))
    shutil.copyfile(patch, destination)
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required for security patch identity checks")
    changed = subprocess.check_output(
        [git, "diff", "--name-only"], cwd=vendor, text=True
    ).splitlines()
    untracked = subprocess.check_output(
        [git, "ls-files", "--others", "--exclude-standard"], cwd=vendor, text=True
    ).splitlines()
    if changed != ["cpython-windows/build.py"] or untracked != [
        "cpython-windows/patch-cpython-expat-2.10.0.patch"
    ]:
        raise RuntimeError("Unexpected changes to the vendor security recipe")
    return {
        "commit": WINDOWS_BACKPORT_COMMIT,
        "patch_sha256": WINDOWS_BACKPORT_SHA256,
        "vendor_hook_before_sha256": WINDOWS_VENDOR_HOOK_SHA256,
        "vendor_hook_after_sha256": sha(hook),
        "scope": "Official CPython bundled Expat2.10 security backport; existing upstream test files and vendor patches unchanged",
    }


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, cwd, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)


def package_install_only(sdk: Path, metadata_root: Path, output: Path):
    """Use the install-only layout supported by UV, retaining vendor licenses."""
    if not (metadata_root / "licenses/LICENSE.cpython.txt").is_file():
        raise RuntimeError("SDK redistribution licenses are missing")
    if not (metadata_root / "licenses/LICENSE.expat.txt").is_file():
        raise RuntimeError("Expat redistribution license is missing")
    inventory = {
        "python/" + p.relative_to(sdk).as_posix(): sha(p)
        for p in sdk.rglob("*")
        if p.is_file() and not p.is_symlink()
    }
    links = {
        "python/" + p.relative_to(sdk).as_posix(): os.readlink(p)
        for p in sdk.rglob("*")
        if p.is_symlink()
    }
    with tarfile.open(output, "w:gz") as archive:
        archive.add(sdk, arcname="python")
        for name in ["PYTHON.json", "licenses"]:
            source = metadata_root / name
            if (sdk / name).exists():
                raise RuntimeError("Unexpected duplicate SDK metadata path")
            archive.add(source, arcname="python/" + name)
            files = source.rglob("*") if source.is_dir() else [source]
            for item in files:
                if item.is_file() and not item.is_symlink():
                    inventory[
                        "python/" + item.relative_to(metadata_root).as_posix()
                    ] = sha(item)
                elif item.is_symlink():
                    links["python/" + item.relative_to(metadata_root).as_posix()] = (
                        os.readlink(item)
                    )
    return inventory, links


OFFICIAL_LINUX_ARTIFACTS = {
    "linux-x64": (
        13158523121,
        125384255866,
        "e46b48e17bf739369f9944bd75add9963b2e76f74706e53b763d6f018d9f7ac8",
    ),
    "linux-arm64": (
        13159675821,
        125384194159,
        "7cc81e1ba05e109c141edee22b1865be646dcc2a92d811adbcc38653cdb74d95",
    ),
}


def official_linux_archive(target: str, work: Path, triple: str, options: str):
    """Qualify first-party CI bytes; never rebuild an unavailable historic sysroot."""
    gh = shutil.which("gh")
    if gh is None:
        raise RuntimeError("GitHub CLI is required for pinned official SDK retrieval")
    artifact_id, job_id, digest = OFFICIAL_LINUX_ARTIFACTS[target]
    base = "repos/astral-sh/python-build-standalone/actions/"

    def metadata(endpoint):
        return json.loads(
            subprocess.check_output([gh, "api", base + endpoint], text=True)
        )

    report = metadata("artifacts/" + str(artifact_id))
    run_report = metadata("runs/41476367331")
    job = metadata("jobs/" + str(job_id))
    expected_name = "cpython-3.14-" + triple + "-" + options
    if (
        report["id"] != artifact_id
        or report["name"] != expected_name
        or report["expired"]
        or report["digest"] != "sha256:" + digest
        or report["workflow_run"]["id"] != 41476367331
        or report["workflow_run"]["head_sha"] != SOURCE
        or run_report["head_sha"] != SOURCE
        or run_report["event"] != "push"
        or run_report["head_branch"] != "main"
        or job["run_id"] != 41476367331
        or job["name"] != triple + " / 3.14 / " + options
        or job["status"] != "completed"
        or job["conclusion"] != "success"
    ):
        raise RuntimeError(
            "Official Linux SDK source, target job or artifact identity mismatch"
        )
    artifact = work / "official-sdk.zip"
    with artifact.open("wb") as stream:
        subprocess.run(
            [gh, "api", base + "artifacts/" + str(artifact_id) + "/zip"],
            stdout=stream,
            check=True,
        )
    if sha(artifact) != digest or artifact.stat().st_size != report["size_in_bytes"]:
        raise RuntimeError("Official Linux SDK archive checksum or size mismatch")
    with zipfile.ZipFile(artifact) as archive:
        members = archive.infolist()
        prefix = "cpython-3.14.10-" + triple + "-" + options + "-"
        if (
            len(members) != 1
            or not members[0].filename.startswith(prefix)
            or not members[0].filename.endswith(".tar.zst")
            or Path(members[0].filename).name != members[0].filename
        ):
            raise RuntimeError("Unexpected official SDK artifact output")
        original = work / "official-sdk.tar.zst"
        with archive.open(members[0]) as source, original.open("wb") as destination:
            shutil.copyfileobj(source, destination)
    return original, {
        "repository": "astral-sh/python-build-standalone",
        "run_id": 41476367331,
        "job_id": job_id,
        "target_job_conclusion": "success",
        "parent_conclusion": run_report["conclusion"],
        "artifact_id": artifact_id,
        "artifact_zip_sha256": digest,
        "source": SOURCE,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    args = parser.parse_args()
    host, triple, options = TARGETS[args.target]
    if sys.platform != host:
        raise RuntimeError("SDK builds must run on the genuine target operating system")
    machine = platform.machine().lower()
    if ("arm64" in args.target) != (machine in {"arm64", "aarch64"}):
        raise RuntimeError("SDK builds must run on the genuine target architecture")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required for verified SDK source retrieval")
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("The pinned UV executable must be available")
    root = Path(__file__).resolve().parents[2]
    work = root / "temp-tests" / "security-python-sdk"
    if work.exists():
        raise RuntimeError("Existing SDK build must be reviewed before another build")
    work.mkdir(parents=True)
    vendor = work / "vendor"
    run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            REPOSITORY,
            str(vendor),
        ],
        root,
    )
    run([git, "fetch", "--depth=1", "origin", SOURCE], vendor)
    run([git, "checkout", "--detach", SOURCE], vendor)
    actual = subprocess.check_output(
        [git, "rev-parse", "HEAD"], cwd=vendor, text=True
    ).strip()
    if (
        actual != SOURCE
        or subprocess.check_output([git, "status", "--porcelain"], cwd=vendor).strip()
    ):
        raise RuntimeError(
            "Upstream SDK source identity or clean tree verification failed"
        )
    downloads = json.loads((vendor / "pythonbuild/downloads.json").read_text())
    if (
        downloads["cpython-3.14"]["sha256"] != PYTHON_SHA256
        or downloads["cpython-3.14"]["version"] != "3.14.10"
    ):
        raise RuntimeError("Unexpected CPython release input")
    if (
        downloads["expat"]["sha256"] != EXPAT_SHA256
        or downloads["expat"]["version"] != "2.10.0"
    ):
        raise RuntimeError("Unexpected Expat security input")
    cpython_backport = (
        apply_windows_security_backport(root, vendor) if host == "win32" else None
    )
    # The compiler gets no CI artifact, repository, registry or signing tokens.
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(
            word in k.upper()
            for word in (
                "TOKEN",
                "PASSWORD",
                "SECRET",
                "CREDENTIAL",
                "RNS_ID_PATH",
                "ACCESS_KEY",
            )
        )
    }
    env["UV_PROJECT_ENVIRONMENT"] = str(vendor / ".venv")
    env["CARGO_TARGET_DIR"] = str(vendor / "target")
    image_provenance = None
    if host == "win32":
        run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                "scripts/install-cygwin.ps1",
                "-Packages",
                "autoconf,automake,libtool",
            ],
            vendor,
            env,
        )
    official_provenance = None
    if host == "linux":
        original, official_provenance = official_linux_archive(
            args.target, work, triple, options
        )
    else:
        run(["cargo", "build", "--locked", "--release"], vendor, env)
        helper = "pythonbuild.exe" if host == "win32" else "pythonbuild"
        shutil.copy2(vendor / "target/release" / helper, vendor / helper)
        if host == "linux":
            image_provenance = prepare_linux_image(vendor, args.target, uv, env)
        command = [
            uv,
            "run",
            "--frozen",
            "--no-dev",
            "build.py",
            "--target-triple",
            triple,
            "--python",
            "cpython-3.14",
            "--options",
            options,
            "--compression",
            "fast",
        ]
        if host == "win32":
            command += ["--sh", "C:/cygwin/bin/sh.exe", "--vs", "2022"]
        run(command, vendor, env)
        if image_provenance is not None:
            image_name, image_host, _ = LINUX_IMAGES[args.target]
            image_file = vendor / "build" / ("image-" + image_name + "." + image_host)
            if image_file.read_text().strip() != image_provenance["image_id"]:
                raise RuntimeError("SDK build image changed after verified preparation")
        archives = list(
            (vendor / "dist").glob(f"cpython-3.14.10-{triple}-{options}-*.tar.zst")
        )
        if len(archives) != 1:
            raise RuntimeError("Expected exactly one newly built SDK archive")
        original = archives[0]
    install = work / "review"
    install.mkdir()
    from compression.zstd import ZstdFile

    with (
        original.open("rb") as raw,
        ZstdFile(raw) as stream,
        tarfile.open(fileobj=cast(BinaryIO, stream), mode="r|") as archive,
    ):
        for member in archive:
            if (
                member.name.startswith("python/install/")
                or member.name == "python/PYTHON.json"
                or member.name.startswith("python/licenses/")
            ):
                archive.extract(member, install, filter="data")
    sdk_metadata = json.loads((install / "python/PYTHON.json").read_text())
    if (
        sdk_metadata["target_triple"] != triple
        or sdk_metadata["python_version"] != "3.14.10"
    ):
        raise RuntimeError(
            "Built SDK target metadata does not match the requested stable runtime"
        )
    sdk = install / "python/install"
    executable = sdk / ("python.exe" if host == "win32" else "bin/python3.14")
    probe = RUNTIME_PROBE
    probe_env = {
        key: value
        for key, value in env.items()
        if key.upper()
        not in {
            "PYTHONHOME",
            "PYTHONPATH",
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
            "DYLD_LIBRARY_PATH",
            "DYLD_FALLBACK_LIBRARY_PATH",
            "DYLD_INSERT_LIBRARIES",
        }
    }
    runtime = json.loads(
        subprocess.check_output(
            [str(executable), "-I", "-S", "-B", "-c", probe], text=True, env=probe_env
        )
    )
    print(json.dumps({"observed_sdk_runtime": runtime}), flush=True)
    if runtime["python"] != "3.14.10" or runtime["expat"] != "expat_2.10.0":
        raise RuntimeError(
            "Actual built SDK does not contain the required fixed runtime"
        )
    out = root / "temp-tests/security-python-sdk-report"
    out.mkdir()
    output = out / "python-sdk.tar.gz"
    inventory, links = package_install_only(sdk, install / "python", output)
    report = {
        "upstream_source": SOURCE,
        "repository": REPOSITORY,
        "python_source_sha256": PYTHON_SHA256,
        "expat_source_sha256": EXPAT_SHA256,
        "target": args.target,
        "triple": triple,
        "actual_runtime": runtime,
        "linux_build_image": image_provenance,
        "official_linux_artifact": official_provenance,
        "cpython_security_backport": cpython_backport,
        "full_vendor_archive_sha256": sha(original),
        "sdk_archive_sha256": sha(output),
        "sdk_archive_size": output.stat().st_size,
        "files": inventory,
        "symlinks": links,
        "kind": "Native-verified install-only SDK from pinned first-party Linux CI bytes or owner-built vendor recipe with the declared official Windows backport; not an upstream tagged binary release",
    }
    (out / "SDK-PROVENANCE.json").write_text(json.dumps(report, indent=2) + "\n")
    if {p.name for p in out.iterdir()} != {"python-sdk.tar.gz", "SDK-PROVENANCE.json"}:
        raise RuntimeError("Unexpected SDK review output")
    print(
        json.dumps(
            {
                "target": args.target,
                "actual_runtime": runtime,
                "sdk_archive_sha256": report["sdk_archive_sha256"],
                "output": str(out),
            }
        )
    )


if __name__ == "__main__":
    main()
