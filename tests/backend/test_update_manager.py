# SPDX-License-Identifier: 0BSD

"""Tests for signed update manifests: build/sign/verify, manager, routes."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import RNS

# mock_app replaces RNS.Identity with a keyless stub for the fixture's
# lifetime. capture the real class now so signing fixtures keep working.
_REAL_IDENTITY = RNS.Identity

from meshchatnext.src.backend.update_manager import (
    UpdateError,
    UpdateManager,
    UpdateVerifyError,
    _version_allowed,
    _version_newer,
    host_platform,
    normalize_arch,
)
from meshchatnext.src.update_rsm import sign_manifest, verify_rsm


@pytest.fixture(autouse=True)
def isolated_update_endpoint(monkeypatch):
    # Most tests inject signed CDN responses. GitHub discovery is tested
    # separately below without this override.
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_BASE_URL", "https://updates.example.test")
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", "aa" * 16)


@pytest.fixture
def signer():
    return _REAL_IDENTITY()


@pytest.fixture
def signer2():
    return _REAL_IDENTITY()


def _manifest(version="9.9.9", track="release", tag="v9.9.9", artifacts=None):
    return {
        "schema": 1,
        "app": "meshchat-next",
        "version": version,
        "tag": tag,
        "track": track,
        "released_at": "2026-10-01T00:00:00Z",
        "minimum_version": "0.0.0",
        "artifacts": artifacts
        or [
            {
                "file": "Meshchat neXt-9.9.9-linux-x64.AppImage",
                "sha256": "0" * 64,
                "size": 100,
                "kind": "appimage",
                "platform": "linux",
                "arch": "x86_64",
            },
            {
                "file": "meshchatnext-9.9.9-py3-none-any.whl",
                "sha256": "1" * 64,
                "size": 50,
                "kind": "wheel",
                "platform": "python",
                "arch": "any",
            },
        ],
    }


# --- update_rsm round-trip ---------------------------------------------------


def test_sign_verify_roundtrip(signer):
    rsm = sign_manifest(_manifest(), signer)
    out = verify_rsm(rsm, required_signer_hash=signer.hash)
    assert out["version"] == "9.9.9"
    assert out["track"] == "release"


def test_verify_rejects_tampered(signer):
    rsm = bytearray(sign_manifest(_manifest(), signer))
    rsm[-10] ^= 0xFF
    with pytest.raises(ValueError):
        verify_rsm(bytes(rsm), required_signer_hash=signer.hash)


def test_verify_rejects_wrong_signer(signer, signer2):
    rsm = sign_manifest(_manifest(), signer)
    with pytest.raises(ValueError, match="signer"):
        verify_rsm(rsm, required_signer_hash=signer2.hash)


def test_verify_rejects_wrong_schema(signer):
    m = _manifest()
    m["schema"] = 99
    rsm = sign_manifest(m, signer)
    with pytest.raises(ValueError, match="schema"):
        verify_rsm(rsm, required_signer_hash=signer.hash)


def test_verify_rejects_wrong_app(signer):
    m = _manifest()
    m["app"] = "something-else"
    rsm = sign_manifest(m, signer)
    with pytest.raises(ValueError, match="application"):
        verify_rsm(rsm, required_signer_hash=signer.hash)


def test_verify_rejects_garbage(signer):
    with pytest.raises(ValueError):
        verify_rsm(b"\x00" * 16, required_signer_hash=signer.hash)


# --- version / platform helpers ----------------------------------------------


def test_version_compare():
    assert _version_newer("4.9.5", "4.9.4")
    assert not _version_newer("4.9.4", "4.9.4")
    assert not _version_newer("4.9.3", "4.9.4")
    assert not _version_newer("garbage", "4.9.4")
    assert _version_allowed("4.9.5", "4.0.0")
    assert not _version_allowed("3.9.0", "4.0.0")


def test_normalize_arch():
    assert normalize_arch("x86_64") == "x86_64"
    assert normalize_arch("AMD64") == "x86_64"
    assert normalize_arch("aarch64") == "aarch64"
    assert normalize_arch("arm64") == "aarch64"
    assert normalize_arch("arm64-v8a") == "aarch64"
    for machine in ("armv7l", "armv8l", "armeabi-v7a", "armeabi_v7a", "armhf"):
        assert normalize_arch(machine) == "armv7"


# --- UpdateManager -----------------------------------------------------------


def _mgr(tmp_path, channel="stable", version="4.9.4"):
    return UpdateManager(str(tmp_path), current_version=version, channel=channel)


def test_track_mapping(tmp_path):
    assert _mgr(tmp_path, "stable").track == "release"
    assert _mgr(tmp_path, "beta").track == "beta"
    assert _mgr(tmp_path, "testing").track == "testing"
    assert _mgr(tmp_path, "local").track is None
    assert not _mgr(tmp_path, "local").enabled


def test_matching_artifacts_filters(tmp_path):
    mgr = _mgr(tmp_path)
    manifest = _manifest()
    arts = mgr.matching_artifacts(manifest)
    assert all(a["platform"] in ("linux", "python") for a in arts)
    plat = host_platform()
    if plat != "linux":
        return  # filtering still ran. arch specifics differ on other hosts
    assert any(a["kind"] == "appimage" and a["arch"] == "x86_64" for a in arts)


def test_matching_artifacts_rejects_traversal(tmp_path):
    mgr = _mgr(tmp_path)
    manifest = _manifest(
        artifacts=[
            {
                "file": "../../etc/evil",
                "sha256": "0" * 64,
                "size": 3,
                "kind": "appimage",
                "platform": "linux",
                "arch": "x86_64",
            }
        ]
    )
    assert mgr.matching_artifacts(manifest) == []


def test_matching_artifacts_rejects_bad_hashes(tmp_path):
    mgr = _mgr(tmp_path)
    bad = dict(_manifest()["artifacts"][0], sha256="nothex")
    assert mgr.matching_artifacts(_manifest(artifacts=[bad])) == []


@pytest.mark.asyncio
async def test_check_reports_update(tmp_path, signer, monkeypatch):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    mgr = _mgr(tmp_path)
    rsm = sign_manifest(_manifest(), signer)
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)
    result = await mgr.check()
    assert result["update_available"] is True
    assert result["manifest"]["version"] == "9.9.9"
    assert result["artifacts"]


@pytest.mark.asyncio
async def test_check_no_update_when_same_version(tmp_path, signer, monkeypatch):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    mgr = _mgr(tmp_path, version="9.9.9")
    rsm = sign_manifest(_manifest(), signer)
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)
    result = await mgr.check()
    assert result["update_available"] is False


@pytest.mark.asyncio
async def test_check_rejects_wrong_track_manifest(tmp_path, signer, monkeypatch):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    mgr = _mgr(tmp_path)
    rsm = sign_manifest(_manifest(track="beta"), signer)
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)
    with pytest.raises(UpdateError, match="track"):
        await mgr.fetch_manifest()


@pytest.mark.asyncio
async def test_check_rejects_bad_signature(tmp_path, signer, signer2, monkeypatch):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer2.hash.hex())
    mgr = _mgr(tmp_path)
    rsm = sign_manifest(_manifest(), signer)  # signed by wrong key
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)
    result = await mgr.check()
    assert result["update_available"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_check_disabled_channel(tmp_path):
    mgr = _mgr(tmp_path, channel="local")
    result = await mgr.check()
    assert result["enabled"] is False
    assert result["update_available"] is False


@pytest.mark.asyncio
async def test_check_blocked_by_privacy_mode(tmp_path):
    class _Flag:
        def get(self):
            return True

    class _Cfg:
        privacy_mode_enabled = _Flag()

    mgr = UpdateManager(
        str(tmp_path),
        current_version="4.9.4",
        channel="stable",
        config_getter=lambda: _Cfg(),
    )
    result = await mgr.check()
    assert "Privacy mode" in result.get("error", "")


@pytest.mark.asyncio
async def test_verify_local_file_match(tmp_path, signer, monkeypatch):
    payload = b"fake-appimage-payload" * 100
    sha = hashlib.sha256(payload).hexdigest()
    manifest = _manifest(
        artifacts=[
            {
                "file": "Meshchat neXt-9.9.9-linux-x64.AppImage",
                "sha256": sha,
                "size": len(payload),
                "kind": "appimage",
                "platform": host_platform(),
                "arch": normalize_arch(),
            }
        ]
    )
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    mgr = _mgr(tmp_path)
    rsm = sign_manifest(manifest, signer)
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)

    f = tmp_path / "Meshchat neXt-9.9.9-linux-x64.AppImage"
    f.write_bytes(payload)
    result = await mgr.verify_local_file(str(f))
    assert result["ok"] is True
    assert result["entry"]["file"].endswith(".AppImage")


@pytest.mark.asyncio
async def test_verify_local_file_rejects_unknown(tmp_path, signer, monkeypatch):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    mgr = _mgr(tmp_path)
    rsm = sign_manifest(_manifest(), signer)
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)
    f = tmp_path / "random.bin"
    f.write_bytes(b"not an artifact")
    with pytest.raises(UpdateVerifyError):
        await mgr.verify_local_file(str(f))


def test_stage_and_pending(tmp_path, signer):
    mgr = _mgr(tmp_path)
    manifest = _manifest()
    payload = b"payload-bytes"
    entry = dict(
        manifest["artifacts"][0],
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )
    src = tmp_path / "downloaded"
    src.write_bytes(payload)
    marker = mgr.stage(src, entry, manifest)
    assert Path(marker["path"]).is_file()
    assert mgr.pending()["version"] == "9.9.9"
    assert mgr.pending_payload_path() == Path(marker["path"])

    # corrupt the staged file -> pending_payload_path refuses
    Path(marker["path"]).write_bytes(b"corrupted")
    assert mgr.pending_payload_path() is None

    mgr.clear_pending()
    assert mgr.pending() is None


# --- routes ------------------------------------------------------------------


def _route(app, method, path):
    for r in app.get_routes():
        if getattr(r, "method", None) == method and getattr(r, "path", None) == path:
            return r.handler
    return None


def test_routes_register(mock_app):
    assert _route(mock_app, "GET", "/api/v1/update/status") is not None
    assert _route(mock_app, "GET", "/api/v1/update/pending") is not None
    assert _route(mock_app, "POST", "/api/v1/update/check") is not None
    assert _route(mock_app, "POST", "/api/v1/update/download") is not None
    assert _route(mock_app, "POST", "/api/v1/update/apply-file") is not None
    assert _route(mock_app, "POST", "/api/v1/update/discard") is not None


@pytest.mark.asyncio
async def test_route_status_shape(mock_app):
    mock_app.update_manager.channel = "local"
    handler = _route(mock_app, "GET", "/api/v1/update/status")
    resp = await handler(MagicMock())
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["enabled"] is False
    assert body["current_version"]


@pytest.mark.asyncio
async def test_route_check_disabled(mock_app):
    mock_app.update_manager.channel = "local"
    handler = _route(mock_app, "POST", "/api/v1/update/check")
    resp = await handler(MagicMock())
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["enabled"] is False


@pytest.mark.asyncio
async def test_route_download_rejects_when_disabled(mock_app):
    from tests.backend.http_request_stubs import json_request

    handler = _route(mock_app, "POST", "/api/v1/update/download")
    resp = await handler(json_request({"file": "x.AppImage"}))
    assert resp.status == 503


@pytest.mark.asyncio
async def test_route_apply_file_rejects_non_multipart(mock_app):
    handler = _route(mock_app, "POST", "/api/v1/update/apply-file")
    resp = await handler(MagicMock(content_type="application/json"))
    assert resp.status in (503, 400)


@pytest.mark.asyncio
async def test_route_discard(mock_app):
    handler = _route(mock_app, "POST", "/api/v1/update/discard")
    resp = await handler(MagicMock())
    assert resp.status == 200
    assert json.loads(resp.body)["ok"] is True


class _MultipartField:
    """Minimal aiohttp multipart field stub yielding fixed chunks."""

    def __init__(self, name: str, chunks):
        self.name = name
        self._chunks = list(chunks)
        self.filename = "update.bin"

    async def read_chunk(self, _size=65536):
        return self._chunks.pop(0) if self._chunks else b""


class _MultipartReader:
    def __init__(self, fields):
        self._fields = list(fields)

    async def next(self):
        return self._fields.pop(0) if self._fields else None


class _MultipartRequest:
    def __init__(self, fields):
        self._reader = _MultipartReader(fields)
        self.content_type = "multipart/form-data; boundary=x"

    async def multipart(self):
        return self._reader


def _enabled_mgr(app, tmp_path, signer, monkeypatch, version="4.9.4"):
    mgr = UpdateManager(str(tmp_path), current_version=version, channel="beta")
    rsm = sign_manifest(_manifest(track="beta"), signer)
    monkeypatch.setattr(mgr, "_fetch_bytes", lambda url, max_bytes, **kw: rsm)
    app.update_manager = mgr
    return mgr, signer


@pytest.mark.asyncio
async def test_route_apply_file_happy_path(mock_app, tmp_path, signer, monkeypatch):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    payload = b"verified-payload" * 64
    sha = hashlib.sha256(payload).hexdigest()
    manifest = _manifest(
        track="beta",
        artifacts=[
            {
                "file": "Meshchat neXt-9.9.9.AppImage",
                "sha256": sha,
                "size": len(payload),
                "kind": "appimage",
                "platform": host_platform(),
                "arch": normalize_arch(),
            }
        ],
    )
    mgr = UpdateManager(str(tmp_path), current_version="4.9.4", channel="beta")
    monkeypatch.setattr(
        mgr,
        "_fetch_bytes",
        lambda url, max_bytes, **kw: sign_manifest(manifest, signer),
    )
    mock_app.update_manager = mgr

    handler = _route(mock_app, "POST", "/api/v1/update/apply-file")
    req = _MultipartRequest([_MultipartField("file", [payload])])
    resp = await handler(req)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["ok"] is True
    assert body["pending"]["version"] == "9.9.9"
    assert mgr.pending() is not None


@pytest.mark.asyncio
async def test_route_apply_file_rejects_unknown_file(
    mock_app, tmp_path, signer, monkeypatch
):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_SIGNER", signer.hash.hex())
    _enabled_mgr(mock_app, tmp_path, signer, monkeypatch)
    handler = _route(mock_app, "POST", "/api/v1/update/apply-file")
    req = _MultipartRequest([_MultipartField("file", [b"totally-unknown-bytes"])])
    resp = await handler(req)
    assert resp.status == 422


def test_unconfigured_preview_never_uses_an_inherited_release_feed(
    monkeypatch, tmp_path
):
    from meshchatnext.src.backend.update_manager import UpdateUnavailable

    monkeypatch.delenv("MESHCHATNEXT_UPDATE_BASE_URL", raising=False)
    monkeypatch.delenv("MESHCHATNEXT_UPDATE_SIGNER", raising=False)
    monkeypatch.setattr("meshchatnext.src.backend.update_manager.DEFAULT_BASE_URL", "")
    monkeypatch.setattr(
        "meshchatnext.src.backend.update_manager.DEFAULT_SIGNER_HASH", ""
    )
    manager = UpdateManager(str(tmp_path), current_version="0.1.0", channel="stable")
    assert not manager.enabled
    with pytest.raises(UpdateUnavailable, match="not configured"):
        manager.manifest_url()
    with pytest.raises(UpdateUnavailable, match="not configured"):
        manager.artifact_url({"tag": "v0.1.0"}, {"file": "MeshchatNext.apk"})


def test_custom_cdn_override_keeps_existing_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_BASE_URL", "https://updates.example.test")
    manager = UpdateManager(str(tmp_path), current_version="1.0.0", channel="beta")
    assert manager.manifest_url() == "https://updates.example.test/beta/latest.rsm"
    assert (
        manager.artifact_url({"tag": "v2"}, {"file": "app.apk"})
        == "https://updates.example.test/beta/v2/app.apk"
    )


def test_hk_local_versions_compare_correctly():
    assert _version_newer("4.10.7+hk.1.0.2", "4.10.7+hk.1.0.1")
    assert not _version_newer("4.10.7+hk.1.0.1", "4.10.7+hk.1.0.2")


@pytest.mark.asyncio
async def test_verified_update_can_be_saved_on_android(mock_app, tmp_path):
    payload = b"signed apk test bytes"
    source = tmp_path / "download.apk"
    source.write_bytes(payload)
    manager = UpdateManager(str(tmp_path), current_version="1.0.0", channel="stable")
    mock_app.update_manager = manager
    manager.stage(
        source,
        {
            "file": "app.apk",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "kind": "apk",
            "platform": "android",
            "arch": "aarch64",
        },
        _manifest(),
    )
    response = await _route(mock_app, "GET", "/api/v1/update/payload")(MagicMock())
    assert response.status == 200
    assert (
        response.headers["Content-Disposition"]
        == "attachment; filename*=UTF-8''app.apk"
    )
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_saved_update_rechecks_checksum(mock_app, tmp_path):
    payload = b"verified"
    source = tmp_path / "download.apk"
    source.write_bytes(payload)
    manager = UpdateManager(str(tmp_path), current_version="1.0.0", channel="stable")
    mock_app.update_manager = manager
    manager.stage(
        source,
        {
            "file": "app.apk",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "kind": "apk",
            "platform": "android",
            "arch": "aarch64",
        },
        _manifest(),
    )
    (manager.pending_dir / "app.apk").write_bytes(b"tampered")
    response = await _route(mock_app, "GET", "/api/v1/update/payload")(MagicMock())
    assert response.status == 404


@pytest.mark.parametrize("channel,track", [("beta", "beta"), ("testing", "testing")])
def test_prerelease_manifest_requires_the_configured_product_feed(
    tmp_path, monkeypatch, channel, track
):
    monkeypatch.setenv("MESHCHATNEXT_UPDATE_BASE_URL", "https://updates.example.test")
    manager = UpdateManager(str(tmp_path), current_version="0.1.0", channel=channel)
    assert manager.manifest_url() == f"https://updates.example.test/{track}/latest.rsm"


def test_neXt_release_defaults_enable_signed_github_updates(monkeypatch, tmp_path):
    from meshchatnext.src.backend.update_manager import (
        DEFAULT_BASE_URL,
        DEFAULT_SIGNER_HASH,
        _pinned_signer_hash,
    )

    monkeypatch.delenv("MESHCHATNEXT_UPDATE_BASE_URL", raising=False)
    monkeypatch.delenv("MESHCHATNEXT_UPDATE_SIGNER", raising=False)
    manager = UpdateManager(str(tmp_path), current_version="0.1.0", channel="stable")
    assert manager.enabled
    assert _pinned_signer_hash() == bytes.fromhex(DEFAULT_SIGNER_HASH)
    assert (
        manager.manifest_url()
        == f"{DEFAULT_BASE_URL}/releases/latest/download/latest.rsm"
    )
    assert (
        manager.artifact_url({"tag": "v0.2.0"}, {"file": "app.apk"})
        == f"{DEFAULT_BASE_URL}/releases/download/v0.2.0/app.apk"
    )
