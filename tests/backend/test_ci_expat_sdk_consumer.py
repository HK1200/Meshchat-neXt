"""Synthetic archive rejection tests; these do not claim native runtime coverage."""

import hashlib
import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def consumer():
    path = (
        Path(__file__).resolve().parents[2] / "scripts/ci/install-expat-python-sdk.py"
    )
    spec = importlib.util.spec_from_file_location("expat_sdk_consumer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def archive_builder(tmp_path, consumer):
    def build(
        *,
        vendor=None,
        bad_inventory=False,
        escaping_link=False,
        extra_file=False,
        target="linux-x64",
    ):
        files = {
            "python/PYTHON.json": b"{}",
            "python/licenses/LICENSE.cpython.txt": b"Synthetic CPython notice",
            "python/licenses/LICENSE.expat.txt": b"Synthetic Expat notice",
        }
        distribution = tmp_path / "sdk.tar.gz"
        with tarfile.open(distribution, "w:gz") as archive:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            if escaping_link:
                member = tarfile.TarInfo("python/bin/python3")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../../outside"
                archive.addfile(member)
        digest = hashlib.sha256(distribution.read_bytes()).hexdigest()
        report = {
            "target": target,
            "upstream_source": vendor or consumer.VENDOR,
            "python_source_sha256": consumer.PYTHON_SOURCE,
            "expat_source_sha256": consumer.EXPAT_SOURCE,
            "sdk_archive_sha256": digest,
            "sdk_archive_size": distribution.stat().st_size,
            "actual_runtime": {"python": "3.14.10", "expat": "expat_2.10.0"},
            "files": {
                name: hashlib.sha256(data).hexdigest() for name, data in files.items()
            },
            "symlinks": {"python/bin/python3": "../../../outside"}
            if escaping_link
            else {},
        }
        if bad_inventory:
            report["files"]["python/PYTHON.json"] = "0" * 64
        artifact = tmp_path / "artifact.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.write(distribution, "python-sdk.tar.gz")
            archive.writestr("SDK-PROVENANCE.json", json.dumps(report))
            if extra_file:
                archive.writestr("unexpected.txt", "not permitted")
        entry = {
            "artifact_zip_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "sdk_archive_sha256": digest,
            "sdk_archive_size": distribution.stat().st_size,
        }
        return artifact, entry, tmp_path / "verified.tar.gz"

    return build


def test_synthetic_archive_integrity_only(consumer, archive_builder):
    artifact, entry, output = archive_builder()
    assert len(consumer.verify_sdk(artifact, entry, "linux-x64", output)["files"]) == 3


def test_artifact_hash_tamper_rejected(consumer, archive_builder):
    artifact, entry, output = archive_builder()
    artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="artifact checksum"):
        consumer.verify_sdk(artifact, entry, "linux-x64", output)


def test_wrong_vendor_source_rejected(consumer, archive_builder):
    artifact, entry, output = archive_builder(vendor="0" * 40)
    with pytest.raises(ValueError, match="pinned security inputs"):
        consumer.verify_sdk(artifact, entry, "linux-x64", output)


def test_complete_file_inventory_enforced(consumer, archive_builder):
    artifact, entry, output = archive_builder(bad_inventory=True)
    with pytest.raises(ValueError, match="complete file inventory"):
        consumer.verify_sdk(artifact, entry, "linux-x64", output)


def test_distribution_symlink_escape_rejected(consumer, archive_builder):
    artifact, entry, output = archive_builder(escaping_link=True)
    with pytest.raises(ValueError, match="symlink escapes"):
        consumer.verify_sdk(artifact, entry, "linux-x64", output)


def test_artifact_output_whitelist_enforced(consumer, archive_builder):
    artifact, entry, output = archive_builder(extra_file=True)
    with pytest.raises(ValueError, match="Unexpected SDK artifact"):
        consumer.verify_sdk(artifact, entry, "linux-x64", output)


def test_windows_without_official_backport_rejected(consumer, archive_builder):
    artifact, entry, output = archive_builder(target="windows-x64")
    with pytest.raises(ValueError, match="required official CPython security backport"):
        consumer.verify_sdk(artifact, entry, "windows-x64", output)


@pytest.mark.parametrize(
    "os_name,arch,libc,expected",
    [
        ("linux", "x86_64", "gnu", "cpython-3.14.10-linux-x86_64-gnu/bin/python3.14"),
        (
            "darwin",
            "aarch64",
            "none",
            "cpython-3.14.10-macos-aarch64-none/bin/python3.14",
        ),
        (
            "darwin",
            "x86_64",
            "none",
            "cpython-3.14.10-macos-x86_64-none/bin/python3.14",
        ),
        ("windows", "x86_64", "none", "cpython-3.14.10-windows-x86_64-none/python.exe"),
    ],
)
def test_uv_canonical_install_layout(consumer, tmp_path, os_name, arch, libc, expected):
    assert (
        consumer.installed_executable(tmp_path, os_name, arch, libc)
        == tmp_path / expected
    )


def test_explicit_verified_uv_does_not_depend_on_shell_path(
    consumer, tmp_path, monkeypatch
):
    executable = tmp_path / "verified-uv.exe"
    executable.write_bytes(b"synthetic tool path, not a native execution fixture")
    monkeypatch.setattr(consumer.shutil, "which", lambda _: None)
    calls = []

    def version(command, **kwargs):
        calls.append(command)
        return "uv 0.13.6 (synthetic version response)"

    monkeypatch.setattr(consumer.subprocess, "check_output", version)
    assert consumer.resolve_uv(executable) == str(executable.resolve())
    assert calls == [[str(executable.resolve()), "--version"]]


def test_explicit_uv_wrong_version_rejected(consumer, tmp_path, monkeypatch):
    executable = tmp_path / "uv.exe"
    executable.write_bytes(b"synthetic")
    monkeypatch.setattr(
        consumer.subprocess, "check_output", lambda *a, **k: "uv 0.11.15 (synthetic)"
    )
    with pytest.raises(RuntimeError, match=r"verified UV version must be 0\.13\.6"):
        consumer.resolve_uv(executable)


def test_explicit_uv_missing_file_rejected(consumer, tmp_path):
    with pytest.raises(RuntimeError, match="Pinned UV is required"):
        consumer.resolve_uv(tmp_path / "missing.exe")


def test_uv_missing_path_rejected(consumer, monkeypatch):
    monkeypatch.setattr(consumer.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Pinned UV is required"):
        consumer.resolve_uv(None)
