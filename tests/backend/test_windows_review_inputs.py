"""Synthetic metadata failures; these tests do not claim native Windows execution."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "source",
        "tooling",
        "branch",
        "event",
        "failure",
        "incomplete",
        "missing",
        "digest",
        "artifact-source",
        "artifact-run",
    ],
)
def test_native_review_binds_exact_merged_artifact(fault):
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/ci/verify-windows-review-metadata.py"
    )
    spec = importlib.util.spec_from_file_location("review_inputs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = "a" * 40
    run = {
        "id": 123,
        "head_sha": source,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/native-build-dev.yml",
    }
    artifact = {
        "id": 456,
        "name": "next-windows-" + source,
        "expired": False,
        "digest": "sha256:" + "b" * 64,
        "workflow_run": {"id": 123, "head_sha": source},
    }
    listing = {"total_count": 1, "artifacts": [artifact]}
    tooling = source
    if fault == "source":
        run["head_sha"] = "c" * 40
    if fault == "tooling":
        tooling = "d" * 40
    if fault == "branch":
        run["head_branch"] = "review-branch"
    if fault == "event":
        run["event"] = "pull_request"
    if fault == "failure":
        run["conclusion"] = "failure"
    if fault == "incomplete":
        listing["total_count"] = 2
    if fault == "missing":
        listing = {"total_count": 0, "artifacts": []}
    if fault == "digest":
        artifact["digest"] = None
    if fault == "artifact-source":
        artifact["workflow_run"]["head_sha"] = "e" * 40
    if fault == "artifact-run":
        artifact["workflow_run"]["id"] = 999
    if fault:
        with pytest.raises(ValueError):
            module.validate(run, listing, source, tooling)
    else:
        result = module.validate(run, listing, source, tooling)
        assert result["passed"] and result["source"] == source
        assert result["run_id"] == 123 and result["artifact"]["id"] == 456
