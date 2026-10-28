# SPDX-License-Identifier: 0BSD

"""Sanity checks for the Android emulator smoke CI script."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "ci" / "android-emulator-smoke.sh"


def test_smoke_script_exists_and_is_executable():
    assert _SCRIPT.is_file()
    assert os.access(_SCRIPT, os.X_OK)


def test_smoke_script_bash_syntax():
    subprocess.run(["bash", "-n", str(_SCRIPT)], check=True)  # nosec: BAN-B607


def test_smoke_script_requires_apk_arg():
    proc = subprocess.run(  # nosec: BAN-B607
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "usage:" in (proc.stderr + proc.stdout)


def test_workflow_references_smoke_script():
    workflow = (
        _REPO / ".github" / "workflows" / "android-emulator-smoke.yml"
    ).read_text(encoding="utf-8")
    assert "scripts/ci/android-emulator-smoke.sh" in workflow
    assert "reactivecircus/android-emulator-runner@" in workflow
    assert "MESHCHATNEXT_ABIS" in workflow
    assert "x86_64" in workflow
    # Runner executes each script: line with /usr/bin/sh (dash). A bare
    # set -euo pipefail there fails with "Illegal option -o pipefail".
    smoke_step = workflow.split("name: Run emulator smoke", 1)[1]
    smoke_script = smoke_step.split("script:", 1)[1].split("\n", 1)[0]
    assert "bash scripts/ci/android-emulator-smoke.sh" in smoke_script
    assert "set -euo pipefail" not in smoke_script
    assert "adb forward" in _SCRIPT.read_text(encoding="utf-8")


def test_smoke_launches_hk_package_and_retains_overrides():
    assignments = "\n".join(
        line
        for line in _SCRIPT.read_text().splitlines()
        if line.startswith(("PACKAGE=", "ACTIVITY="))
    )
    command = assignments + '\nprintf "%s\\n%s\\n" "$PACKAGE" "$ACTIVITY"'
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MESHCHATNEXT_ANDROID_PACKAGE", "MESHCHATNEXT_ANDROID_ACTIVITY")
    }
    result = subprocess.check_output(["bash", "-c", command], env=env, text=True)
    assert result.splitlines() == [
        "com.haadkoe.meshchatnext",
        "com.haadkoe.meshchatnext/com.meshchatnext.MainActivity",
    ]
    env.update(
        MESHCHATNEXT_ANDROID_PACKAGE="example.app",
        MESHCHATNEXT_ANDROID_ACTIVITY="example.app/custom.Main",
    )
    result = subprocess.check_output(["bash", "-c", command], env=env, text=True)
    assert result.splitlines() == ["example.app", "example.app/custom.Main"]


def test_smoke_default_port_matches_android_server_and_keeps_override():
    import re

    java = (
        _REPO / "android/app/src/main/java/com/meshchatnext/MainActivity.java"
    ).read_text()
    server_port = re.search(r"SERVER_PORT\s*=\s*(\d+)", java).group(1)
    assignment = next(
        line
        for line in _SCRIPT.read_text().splitlines()
        if line.startswith("DEVICE_HTTP_PORT=")
    )
    command = assignment + '\nprintf "%s" "$DEVICE_HTTP_PORT"'
    env = {k: v for k, v in os.environ.items() if k != "MESHCHATNEXT_SMOKE_DEVICE_PORT"}
    assert (
        subprocess.check_output(["bash", "-c", command], env=env, text=True)
        == server_port
    )
    env["MESHCHATNEXT_SMOKE_DEVICE_PORT"] = "18999"
    assert (
        subprocess.check_output(["bash", "-c", command], env=env, text=True) == "18999"
    )
