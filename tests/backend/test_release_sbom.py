# SPDX-License-Identifier: 0BSD
"""Exercise release scan failures with real shell scripts and stub external tools."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def tool(directory: Path, name: str, source: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env python3\n" + source)
    path.chmod(0o755)


@pytest.fixture
def scan_env(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    tool(
        tools,
        "gh",
        """import os, sys
from pathlib import Path
if sys.argv[1] == "api":
    print("v0.1.3")
else:
    if os.environ.get("MOCK_MODE") == "missing":
        sys.exit(1)
    target = Path(sys.argv[sys.argv.index("--dir") + 1])
    (target / "sbom.cyclonedx.json").write_text('{"bomFormat":"CycloneDX"}')
""",
    )
    tool(
        tools,
        "grype",
        """import os, sys, json
mode = os.environ.get("MOCK_MODE")
if mode == "scanner-failure":
    sys.exit(7)
if mode == "malformed":
    print("invalid json")
else:
    print(json.dumps({"matches": [{"vulnerability":{"id":"TEST","severity":"High"},"artifact":{"name":"test","version":"1"}}]}))
""",
    )
    return {
        **os.environ,
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "SBOM_RESCAN_REPORT": str(tmp_path / "report.json"),
        "TMPDIR": str(tmp_path),
    }


def test_rescan_reports_findings_without_failing(scan_env):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/sbom-rescan.sh")],
        env=scan_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = Path(scan_env["GITHUB_STEP_SUMMARY"]).read_text()
    assert "High" in summary and "TEST" in summary
    assert not list(Path(scan_env["TMPDIR"]).glob("meshchatnext-sbom.*"))


@pytest.mark.parametrize("mode", ["missing", "scanner-failure", "malformed"])
def test_rescan_never_treats_missing_or_broken_scan_as_clean(scan_env, mode):
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/sbom-rescan.sh")],
        env={**scan_env, "MOCK_MODE": mode},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    summary = Path(scan_env["GITHUB_STEP_SUMMARY"])
    assert not summary.exists() or "No findings." not in summary.read_text()
    assert not list(Path(scan_env["TMPDIR"]).glob("meshchatnext-sbom.*"))


@pytest.mark.parametrize(
    "components,expected", [([], False), ([{"name": "example", "version": "1"}], True)]
)
def test_release_inventory_requires_real_components(tmp_path, components, expected):
    tools = tmp_path / "bin"
    tools.mkdir()
    tool(
        tools,
        "trivy",
        """import os, sys
from pathlib import Path
Path(sys.argv[sys.argv.index("--output") + 1]).write_text(os.environ["MOCK_SBOM"])
""",
    )
    output = tmp_path / "inventory.json"
    env = {
        **os.environ,
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "MOCK_SBOM": json.dumps({"bomFormat": "CycloneDX", "components": components}),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/generate-release-sbom.sh"), str(output)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is expected
