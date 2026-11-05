# SPDX-License-Identifier: 0BSD
"""Review fixed 0.1.7 package bytes on Windows, using only disposable profiles."""

import hashlib
import json
import marshal
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

SOURCE = "263b07538d4fcfd58e7020453f9d53fbef19d0d8"
PIN = "87b2973e252645589a1543010e9fcda1"
NAMES = {
    "MeshchatNext-v0.1.7-win-portable.exe",
    "MeshchatNext-v0.1.7-win-x64-installer.exe",
}
ROOT = Path(os.environ["MESHCHAT_RELEASE_REVIEW_ROOT"]).resolve()
assert sys.platform == "win32", "Genuine Windows execution is required"
assert ROOT.parent.name == "temp-tests" and (ROOT / "source/.git").exists()
DIST = ROOT / "source/dist"
sys.path.insert(0, str(ROOT / "source"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_source_tree():
    from RNS.Utilities.rnid import extract_signed_rsg_data, validate_rsg

    source = ROOT / "source"
    raw = (source / "meshchatnext.rsm").read_bytes()
    body = extract_signed_rsg_data(raw)["message"]
    valid, _, identity = validate_rsg(
        raw, message=body, required_signer=bytes.fromhex(PIN)
    )
    assert valid and identity.hash.hex() == PIN
    lines = body.decode().splitlines()
    assert lines[0] == "# meshchatnext tree manifest v1"
    names = set()
    for line in lines[1:]:
        if not line:
            continue
        digest, name = line.split("  ", 1)
        assert name not in names and sha(source / name) == digest, name
        names.add(name)
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=source)
        .decode()
        .split("\0")
    )
    expected = {
        n
        for n in tracked
        if n
        and n != "meshchatnext.rsm"
        and not (n.startswith("vendor/") or "/vendor/" in n or n.endswith("/vendor"))
    }
    assert names == expected
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, text=True
        ).strip()
        == SOURCE
    )
    return {
        "signer": PIN,
        "rsm_sha256": sha(source / "meshchatnext.rsm"),
        "all_tracked_files": len(names),
        "passed": True,
    }


def prepare():
    from meshchatnext.src.update_rsm import verify_rsm

    assert sys.version_info[:3] == (3, 14, 10)
    source_proof = verify_source_tree()
    proof = json.loads((DIST / "SOURCE-PACKAGES.json").read_text(encoding="utf-8-sig"))
    assert proof["source"] == SOURCE and proof["version"] == "0.1.7"
    assert {a["file"] for a in proof["assets"]} == NAMES
    assert {p.name for p in DIST.iterdir()} == NAMES | {"SOURCE-PACKAGES.json"}
    assert proof["native_ui"]["source"] == SOURCE
    for asset in proof["assets"]:
        path = DIST / asset["file"]
        assert path.stat().st_size == asset["size"] and sha(path) == asset["sha256"]
        # This is the owner's existing unsigned waiver, never OS trust bypass.
        status = subprocess.check_output(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                "(Get-AuthenticodeSignature -LiteralPath $env:MESHCHAT_REVIEW_ASSET).Status.ToString()",
            ],
            text=True,
            env={**os.environ, "MESHCHAT_REVIEW_ASSET": str(path)},
        ).strip()
        assert status == "NotSigned", (path.name, status)
    base = "https://github.com/HK1200/Meshchat-neXt/releases/download/v0.1.6/"
    response = requests.get(base + "latest.rsm", timeout=120)
    response.raise_for_status()
    manifest = verify_rsm(response.content, required_signer_hash=bytes.fromhex(PIN))
    assert manifest["version"] == "0.1.6" and manifest["tag"] == "v0.1.6"
    name = "MeshchatNext-v0.1.6-win-x64-installer.exe"
    entries = [a for a in manifest["artifacts"] if a["file"] == name]
    assert len(entries) == 1 and entries[0]["platform"] == "windows"
    old = ROOT / "old"
    old.mkdir()
    with requests.get(base + name, stream=True, timeout=120) as response:
        response.raise_for_status()
        with (old / name).open("wb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)
    assert (old / name).stat().st_size == entries[0]["size"]
    assert sha(old / name) == entries[0]["sha256"]
    seven = shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"
    outer = ROOT / "installer-payload"
    subprocess.run(
        [
            seven,
            "x",
            str(DIST / "MeshchatNext-v0.1.7-win-x64-installer.exe"),
            "-o" + str(outer),
            "-y",
        ],
        check=True,
        timeout=180,
    )
    payloads = list(outer.rglob("app-64.7z"))
    assert len(payloads) == 1, "Expected the verified installer's single x64 payload"
    unpacked = DIST / "win-unpacked"
    subprocess.run(
        [seven, "x", str(payloads[0]), "-o" + str(unpacked), "-y"],
        check=True,
        timeout=180,
    )
    assert (unpacked / "Meshchat neXt.exe").is_file()
    proof["source_signature_before_build"] = source_proof
    proof["baseline"] = {"pin": PIN, "version": "0.1.6", "artifact": entries[0]}
    proof["expected_installed_shell_sha256"] = sha(unpacked / "Meshchat neXt.exe")
    (ROOT / "input-proof.json").write_text(json.dumps(proof, indent=2))


def tree_hashes(base):
    result = {}
    for path in sorted(base.rglob("*")):
        assert not path.is_symlink(), "Unexpected symlink in fixed backend payload"
        if path.is_file():
            result[str(path.relative_to(base))] = sha(path)
    return result


def stage_repackage():
    # Native inputs and frontend come from the verified source-263 artifact.
    # Freeze Python afresh with explicit stable/source metadata; ordinary CI
    # previews have local-channel metadata and are not release installables.
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT / "source", text=True
        ).strip()
        == SOURCE
    )
    old = ROOT / "superseded-quad4"
    old.mkdir()
    for name in NAMES | {"SOURCE-PACKAGES.json"}:
        shutil.move(str(DIST / name), old / name)
    unpacked = ROOT / "original-win-unpacked"
    shutil.move(str(DIST / "win-unpacked"), unpacked)
    subprocess.run(
        ["node", "scripts/ci/github-verify-backend-manifest.mjs", str(unpacked)],
        cwd=ROOT / "source",
        check=True,
        timeout=180,
    )
    hashes = tree_hashes(unpacked / "resources/backend")
    assert hashes
    (ROOT / "original-backend-input-hashes.json").write_text(
        json.dumps(hashes, sort_keys=True)
    )
    native = ROOT / "source/.local/windows-sip"
    native.mkdir(parents=True)
    shutil.copy2(
        unpacked / "resources/backend/bin/meshchatnext-sip.exe",
        native / "meshchatnext-sip.exe",
    )
    shutil.copytree(
        unpacked / "resources/backend/licenses/windows-sip", native / "licenses"
    )
    public = ROOT / "source/meshchatnext/public"
    if public.exists():
        assert not subprocess.check_output(
            ["git", "ls-files", "meshchatnext/public"], cwd=ROOT / "source"
        ).strip()
        shutil.rmtree(public)
    shutil.copytree(unpacked / "resources/backend/public", public)
    # Reuse byte-verified current signed license artifacts; mtime only changes.
    for name in [
        "THIRD_PARTY_NOTICES.txt",
        "licenses_frontend.json",
        "licenses_backend.json",
    ]:
        path = ROOT / "source/meshchatnext/src/backend/data" / name
        assert path.is_file()
        path.touch()
    verify_source_tree()


def record_frozen():
    source_proof = verify_source_tree()
    backend = ROOT / "source/build/exe/win32-x64"
    baked = marshal.loads(
        (backend / "lib/meshchatnext/src/_build_meta_baked.pyc").read_bytes()[16:]
    )
    assert SOURCE in baked.co_consts and "stable" in baked.co_consts
    assert any(c is False for c in baked.co_consts)
    original = ROOT / "original-win-unpacked/resources/backend"
    assert sha(backend / "bin/meshchatnext-sip.exe") == sha(
        original / "bin/meshchatnext-sip.exe"
    )
    assert tree_hashes(backend / "public") == tree_hashes(original / "public")
    hashes = tree_hashes(backend)
    assert hashes
    (ROOT / "backend-input-hashes.json").write_text(json.dumps(hashes, sort_keys=True))
    proof = json.loads((ROOT / "input-proof.json").read_text())
    proof["source_signature_after_freeze"] = source_proof
    proof["fresh_stable_backend_metadata_verified"] = True
    (ROOT / "input-proof.json").write_text(json.dumps(proof, indent=2))


def record_repackage():
    proof = json.loads((ROOT / "input-proof.json").read_text())
    before = json.loads((ROOT / "backend-input-hashes.json").read_text())
    after = tree_hashes(DIST / "win-unpacked/resources/backend")
    differences = {
        "removed": sorted(before.keys() - after.keys()),
        "added": sorted(after.keys() - before.keys()),
        "modified": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
    }
    if before != after:
        print(json.dumps({"backend_integrity_differences": differences}), flush=True)
    assert before == after, "Repackaging changed the verified immutable backend"
    ui = json.loads((ROOT / "source/reports/windows-node-ui.json").read_text())
    assert ui["source"] == SOURCE and ui["passed"]
    assert {r["mode"] for r in ui["results"]} == {"default", "forced"}
    assert all(r["actual_packaged_ui"] and r["normal_quit"] for r in ui["results"])
    assert next(r for r in ui["results"] if r["mode"] == "forced")[
        "appcontainer_active"
    ]
    proof["superseded_quad4_assets"] = proof["assets"]
    proof["superseded_quad4_native_ui"] = proof["native_ui"]
    proof["native_ui"] = ui
    proof["assets"] = []
    for name in sorted(NAMES):
        path = DIST / name
        assert path.is_file()
        status = subprocess.check_output(
            [
                "pwsh",
                "-NoProfile",
                "-Command",
                "(Get-AuthenticodeSignature -LiteralPath $env:MESHCHAT_REVIEW_ASSET).Status.ToString()",
            ],
            env={**os.environ, "MESHCHAT_REVIEW_ASSET": str(path)},
            text=True,
        ).strip()
        assert status == "NotSigned", (name, status)
        proof["assets"].append(
            {"file": name, "size": path.stat().st_size, "sha256": sha(path)}
        )
    proof["expected_installed_shell_sha256"] = sha(
        DIST / "win-unpacked/Meshchat neXt.exe"
    )
    proof["build_configuration"] = {
        "extraMetadata.author.name": "HK1200",
        "upstream_source_author_unchanged": True,
        "backend_files_unchanged_during_packaging": len(before),
        "MESHCHATNEXT_BUILD_CHANNEL": "stable",
        "MESHCHATNEXT_GIT_COMMIT": SOURCE,
        "fresh_frozen_backend": True,
        "backend_tree_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True).encode()
        ).hexdigest(),
        "fresh_repackaged_native_ui": True,
    }
    (ROOT / "input-proof.json").write_text(json.dumps(proof, indent=2))


def collect():
    proof = json.loads((ROOT / "input-proof.json").read_text())
    upgrade = json.loads((ROOT / "upgrade-validation.json").read_text())
    update = json.loads((ROOT / "update-staging-validation.json").read_text())
    assert upgrade["status"] == update["status"] == "passed"
    assert upgrade["upgraded_version"] == "0.1.7"
    assert upgrade["in_place_upgrade_preserves_all_profile_bytes"]
    assert upgrade["uninstall_preserves_profile_bytes"]
    assert upgrade["synthetic_message_restored_from_backup"]
    assert upgrade["contact_restored_from_backup"]
    assert (
        update["synthetic_signer_in_memory_only"]
        and not update["production_signer_used"]
    )
    assert (
        upgrade["installed_stable_channel"]
        and upgrade["installed_is_dev_build"] is False
    )
    proof["source_signature_after_native_checks"] = verify_source_tree()
    proof["native_installer_upgrade"] = upgrade
    proof["native_signed_update_staging"] = update
    proof["verification_commit"] = os.environ["GITHUB_SHA"]
    proof["genuine_windows_release_checks_passed"] = True
    out = ROOT / "verified-report"
    out.mkdir()
    for name in NAMES:
        shutil.copy2(DIST / name, out / name)
    (out / "SOURCE-PACKAGES.json").write_text(json.dumps(proof, indent=2))


if __name__ == "__main__":
    {
        "prepare": prepare,
        "stage": stage_repackage,
        "frozen": record_frozen,
        "record": record_repackage,
        "collect": collect,
    }[sys.argv[1]]()
