# SPDX-License-Identifier: 0BSD
import hashlib
import json
import runpy
from pathlib import Path

import pytest
import RNS

from meshchatnext.src.update_rsm import APP_ID, SCHEMA, sign_manifest

verify = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/ci/verify-linux-release.py")
)["verify"]


@pytest.fixture
def release(tmp_path):
    identity = RNS.Identity()
    artifacts = []
    for name, kind in [
        ("MeshchatNext-linux-amd64.deb", "deb"),
        ("MeshchatNext-linux-x86_64.AppImage", "appimage"),
    ]:
        payload = ("test package " + kind).encode()
        (tmp_path / name).write_bytes(payload)
        artifacts.append(
            {
                "file": name,
                "platform": "linux",
                "arch": "x86_64",
                "kind": kind,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "app": APP_ID,
        "schema": SCHEMA,
        "version": "0.1.2",
        "tag": "linux-v0.1.2",
        "track": "release",
        "artifacts": artifacts,
    }

    def write():
        (tmp_path / "latest.rsm").write_bytes(sign_manifest(manifest, identity))
        (tmp_path / "latest.json").write_text(json.dumps(manifest))

    write()
    return tmp_path, identity.hash.hex(), manifest, write


def test_both_linux_release_and_channel_tags_verify(release):
    folder, signer, _, _ = release
    assert verify(folder, signer, "linux-v0.1.2")["passed"]
    assert verify(folder, signer, "linux-stable")["passed"]


def test_modified_payload_is_rejected(release):
    folder, signer, manifest, _ = release
    (folder / manifest["artifacts"][0]["file"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify(folder, signer, "linux-stable")


def test_different_signer_is_rejected(release):
    folder, _, _, _ = release
    with pytest.raises(ValueError):
        verify(folder, RNS.Identity().hash.hex(), "linux-stable")


@pytest.mark.parametrize("change", ["platform", "path", "tag", "readable"])
def test_incorrect_release_metadata_is_rejected(release, change):
    folder, signer, manifest, write = release
    if change == "platform":
        manifest["artifacts"][0]["platform"] = "android"
    elif change == "path":
        manifest["artifacts"][0]["file"] = "../private-file"
    elif change == "tag":
        manifest["tag"] = "v0.1.2"
    write()
    if change == "readable":
        (folder / "latest.json").write_text("{}")
    with pytest.raises(ValueError):
        verify(folder, signer, "linux-stable")
