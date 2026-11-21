"""Cached JNI libraries must not prevent SIP obtaining verified Opus headers."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "sip_build", Path(__file__).parents[2] / "scripts/android/build-sip.py"
)
sip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sip)


def test_downloads_missing_header_archive_even_with_prebuilt_opus(
    tmp_path, monkeypatch
):
    payload = b"fixture source archive"
    monkeypatch.setattr(sip, "OPUS_SHA256", hashlib.sha256(payload).hexdigest())
    calls = []

    def download(url, target):
        calls.append(url)
        target.write_bytes(payload)

    monkeypatch.setattr(sip.urllib.request, "urlretrieve", download)
    archive = tmp_path / "cache/opus.tar.gz"
    assert sip.ensure_opus_archive(archive) == archive
    assert archive.read_bytes() == payload
    sip.ensure_opus_archive(archive)
    assert calls == ["https://ftp.osuosl.org/pub/xiph/releases/opus/opus-1.5.2.tar.gz"]


def test_corrupt_download_is_never_promoted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sip.urllib.request,
        "urlretrieve",
        lambda url, target: target.write_bytes(b"corrupt"),
    )
    archive = tmp_path / "opus.tar.gz"
    with pytest.raises(ValueError, match="Opus checksum mismatch"):
        sip.ensure_opus_archive(archive)
    assert not archive.exists()
    assert not archive.with_suffix(".download").exists()


def test_corrupt_existing_archive_is_preserved_and_rejected(tmp_path):
    archive = tmp_path / "opus.tar.gz"
    archive.write_bytes(b"keep for inspection")
    with pytest.raises(ValueError, match="Opus checksum mismatch"):
        sip.ensure_opus_archive(archive)
    assert archive.read_bytes() == b"keep for inspection"
