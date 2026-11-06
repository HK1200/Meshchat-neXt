"""Offline source-verification regressions: no identity cache or radio service."""

import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest
import RNS
from RNS.Utilities.rnid import create_rsg


@pytest.fixture
def verifier():
    path = Path(__file__).resolve().parents[2] / "scripts/ci/verify-pinned-source.py"
    spec = importlib.util.spec_from_file_location("ci_pinned_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def signed(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.txt").write_text("reviewed source")
    (tmp_path / "source.rsm").write_bytes(b"")
    subprocess.run(["git", "add", "source.txt", "source.rsm"], cwd=tmp_path, check=True)
    signer = RNS.Identity()
    header = "# synthetic source inventory v1"
    body = (
        header
        + "\n"
        + hashlib.sha256((tmp_path / "source.txt").read_bytes()).hexdigest()
        + "  source.txt\n"
    ).encode()
    (tmp_path / "source.rsm").write_bytes(create_rsg(signer, body, embed=True))
    return tmp_path, signer.hash.hex(), header


def test_embedded_key_validates_without_identity_cache(verifier, signed):
    root, signer, header = signed
    assert verifier.verify(root, "source.rsm", signer, header)["tracked_files"] == 1


def test_wrong_pinned_signer_is_rejected(verifier, signed):
    root, _, header = signed
    with pytest.raises(ValueError, match="Pinned source signature"):
        verifier.verify(root, "source.rsm", RNS.Identity().hash.hex(), header)


def test_changed_source_bytes_are_rejected(verifier, signed):
    root, signer, header = signed
    (root / "source.txt").write_text("modified source")
    with pytest.raises(ValueError, match="file hash mismatch"):
        verifier.verify(root, "source.rsm", signer, header)


def test_new_unlisted_tracked_file_is_rejected(verifier, signed):
    root, signer, header = signed
    (root / "extra.txt").write_text("unlisted")
    subprocess.run(["git", "add", "extra.txt"], cwd=root, check=True)
    with pytest.raises(ValueError, match="exact full tracked inventory"):
        verifier.verify(root, "source.rsm", signer, header)


def test_wrong_inventory_header_is_rejected(verifier, signed):
    root, signer, _ = signed
    with pytest.raises(ValueError, match="inventory format"):
        verifier.verify(root, "source.rsm", signer, "wrong header")
