# SPDX-License-Identifier: 0BSD
import asyncio
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from windows_release_versions import release_versions

ROOT = Path(os.environ["MESHCHAT_RELEASE_REVIEW_ROOT"]).resolve()
VERSION, BASELINE_VERSION = release_versions(ROOT / "source")
assert ROOT.parent.name == "temp-tests" and (ROOT / "source/.git").exists()
sys.path.insert(0, str(ROOT / "source"))
import RNS

from meshchatnext.src.backend.update_manager import UpdateManager, UpdateVerifyError
from meshchatnext.src.update_rsm import sign_manifest, verify_rsm

test = ROOT / "update-validation" / ("test-" + uuid.uuid4().hex[:8])
test.mkdir(parents=True)
identity = RNS.Identity()
os.environ["MESHCHATNEXT_UPDATE_SIGNER"] = identity.hash.hex()
os.environ.pop("MESHCHATNEXT_UPDATE_DISABLED", None)
report = {
    "synthetic_signer_in_memory_only": True,
    "production_signer_used": False,
    "production_feed_modified": False,
    "checks": {},
}


async def main():
    artifacts = []
    for name in (
        f"MeshchatNext-v{VERSION}-win-portable.exe",
        f"MeshchatNext-v{VERSION}-win-x64-installer.exe",
    ):
        p = ROOT / "source/dist" / name
        artifacts.append(
            {
                "file": name,
                "platform": "windows",
                "arch": "x86_64",
                "kind": "exe",
                "size": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "app": "meshchat-next",
        "schema": 1,
        "version": VERSION,
        "tag": f"v{VERSION}",
        "track": "release",
        "released_at": "2026-11-05T00:00:00Z",
        "minimum_version": "0.0.0",
        "artifacts": artifacts,
    }
    rsm = sign_manifest(manifest, identity)
    verified = verify_rsm(rsm, required_signer_hash=identity.hash)
    assert verified == manifest
    report["checks"]["signed_windows_manifest_verified"] = True
    current = UpdateManager(
        str(test / "current-storage"), current_version=VERSION, channel="stable"
    )
    current._fetch_bytes = lambda *args, **kwargs: rsm
    same = await current.check()
    assert not same["update_available"], same
    report["checks"]["current_version_not_offered_again"] = True
    mgr = UpdateManager(
        str(test / "storage"), current_version=BASELINE_VERSION, channel="stable"
    )
    mgr._fetch_bytes = lambda *args, **kwargs: rsm
    status = await mgr.check()
    assert status["update_available"] and len(status["artifacts"]) == 2
    report["checks"]["windows_x64_artifacts_selected"] = True
    for entry in artifacts:
        source = ROOT / "source/dist" / entry["file"]
        copy = test / entry["file"]
        shutil.copyfile(source, copy)
        result = await mgr.verify_local_file(str(copy))
        assert result["ok"]
        mgr.stage(copy, result["entry"], result["manifest"])
        staged = mgr.pending_payload_path()
        assert staged and staged.is_file()
        report["checks"][entry["file"] + "_verified_and_staged"] = True
        with staged.open("r+b") as f:
            first = f.read(1)
            f.seek(0)
            f.write(bytes([first[0] ^ 1]))
        assert mgr.pending_payload_path() is None
        report["checks"][entry["file"] + "_staged_tamper_rejected"] = True
        try:
            await mgr.verify_local_file(str(staged))
        except UpdateVerifyError:
            pass
        else:
            raise AssertionError("Tampered local artifact accepted")
        mgr.clear_pending()
    broken = bytearray(rsm)
    broken[0] ^= 1
    try:
        verify_rsm(bytes(broken), required_signer_hash=identity.hash)
    except ValueError:
        pass
    else:
        raise AssertionError("Tampered signed manifest accepted")
    report["checks"]["manifest_signature_tamper_rejected"] = True
    report["status"] = "passed"


try:
    asyncio.run(main())
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    (ROOT / "update-staging-validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
