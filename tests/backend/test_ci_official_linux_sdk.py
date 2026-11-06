"""Synthetic first-party SDK identity tests; no native execution is claimed."""

import hashlib
import importlib.util
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("fault", [None, "source", "job", "digest", "bytes", "output"])
def test_official_linux_sdk_identity(tmp_path, monkeypatch, fault):
    path = Path(__file__).resolve().parents[2] / "scripts/ci/build-expat-python-sdk.py"
    spec = importlib.util.spec_from_file_location("official_sdk", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = io.BytesIO()
    member = "cpython-3.14.10-x86_64-unknown-linux-gnu-pgo+lto-example.tar.zst"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape" if fault == "output" else member, b"synthetic")
    data = payload.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setitem(module.OFFICIAL_LINUX_ARTIFACTS, "linux-x64", (1, 2, digest))
    report = {
        "id": 1,
        "name": "cpython-3.14-x86_64-unknown-linux-gnu-pgo+lto",
        "expired": False,
        "digest": "sha256:" + ("0" * 64 if fault == "digest" else digest),
        "size_in_bytes": len(data),
        "workflow_run": {"id": 41476367331, "head_sha": module.SOURCE},
    }
    run = {
        "head_sha": "0" * 40 if fault == "source" else module.SOURCE,
        "event": "push",
        "head_branch": "main",
        "conclusion": "failure",
    }
    job = {
        "run_id": 41476367331,
        "name": "x86_64-unknown-linux-gnu / 3.14 / pgo+lto",
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
            module.official_linux_archive(
                "linux-x64", tmp_path, "x86_64-unknown-linux-gnu", "pgo+lto"
            )
    else:
        result, provenance = module.official_linux_archive(
            "linux-x64", tmp_path, "x86_64-unknown-linux-gnu", "pgo+lto"
        )
        assert result.read_bytes() == b"synthetic"
        assert provenance["parent_conclusion"] == "failure"
        assert provenance["target_job_conclusion"] == "success"
