"""Synthetic first-party SDK identity tests; no native execution is claimed."""

import hashlib
import importlib.util
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("target", ["linux-x64", "macos-x64"])
@pytest.mark.parametrize("fault", [None, "source", "job", "digest", "bytes", "output"])
def test_official_linux_sdk_identity(tmp_path, monkeypatch, fault, target):
    path = Path(__file__).resolve().parents[2] / "scripts/ci/build-expat-python-sdk.py"
    spec = importlib.util.spec_from_file_location("official_sdk", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    triple = (
        "x86_64-apple-darwin" if target == "macos-x64" else "x86_64-unknown-linux-gnu"
    )
    source = module.MACOS_X64_SOURCE if target == "macos-x64" else module.SOURCE
    run_id = 42106621134 if target == "macos-x64" else 41476367331
    payload = io.BytesIO()
    member = f"cpython-3.14.10-{triple}-pgo+lto-example.tar.zst"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape" if fault == "output" else member, b"synthetic")
    data = payload.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setitem(module.OFFICIAL_LINUX_ARTIFACTS, "linux-x64", (1, 2, digest))
    monkeypatch.setattr(module, "OFFICIAL_MACOS_X64_ARTIFACT", (1, 2, digest))
    report = {
        "id": 1,
        "name": f"cpython-3.14-{triple}-pgo+lto",
        "expired": False,
        "digest": "sha256:" + ("0" * 64 if fault == "digest" else digest),
        "size_in_bytes": len(data),
        "workflow_run": {"id": run_id, "head_sha": source},
    }
    run = {
        "head_sha": "0" * 40 if fault == "source" else source,
        "event": "push",
        "head_branch": "main",
        "conclusion": "failure",
    }
    job = {
        "run_id": run_id,
        "name": triple + " / 3.14 / pgo+lto",
        "status": "completed",
        "conclusion": "failure" if fault == "job" else "success",
    }

    def check_output(command, **kwargs):
        endpoint = command[-1]
        return json.dumps(
            report
            if "/artifacts/" in endpoint
            else job
            if "/jobs/" in endpoint
            else run
        )

    def download(command, **kwargs):
        kwargs["stdout"].write(data + b"tamper" if fault == "bytes" else data)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "check_output", check_output)
    monkeypatch.setattr(module.subprocess, "run", download)
    if fault:
        with pytest.raises(RuntimeError):
            module.official_linux_archive(target, tmp_path, triple, "pgo+lto")
    else:
        result, provenance = module.official_linux_archive(
            target, tmp_path, triple, "pgo+lto"
        )
        assert result.read_bytes() == b"synthetic"
        assert provenance["parent_conclusion"] == "failure"
        assert provenance["target_job_conclusion"] == "success"
        assert provenance["source"] == source
        assert json.loads(json.dumps(provenance))["artifact_id"] == 1
