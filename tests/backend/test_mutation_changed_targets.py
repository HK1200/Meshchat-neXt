# SPDX-License-Identifier: 0BSD
"""The changed-module runner must select real mutmut keys, not bare modules."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def test_changed_module_filters_select_mutants_without_data_payloads(
    tmp_path, monkeypatch
):
    # CI supplies a worker filter; the fixture must still test its own full plan.
    monkeypatch.setenv("MUTMUT_MODULE", "meshchatnext.src.backend.http.routes.update")
    root = Path(__file__).resolve().parents[2]
    scripts = tmp_path / "scripts/ci"
    scripts.mkdir(parents=True)
    shutil.copy2(
        root / "scripts/ci/mutation-changed.sh", scripts / "mutation-changed.sh"
    )
    (scripts / "mutation-backend.sh").write_text(
        'printf "%s\\n" "$MUTMUT_TARGET" >> "$MUTMUT_TARGET_LOG"\n'
    )
    paths = [
        "meshchatnext/src/backend/update_manager.py",
        "meshchatnext/src/backend/http/routes/update.py",
        "meshchatnext/src/backend/data/interfaces/payload.py",
    ]
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n")

    def git(*args):
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.test",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "baseline")
    git("branch", "baseline")
    for relative in paths:
        (tmp_path / relative).write_text("value = 2\n")
    git("add", ".")
    git("commit", "-qm", "change runtime modules and resource")
    log = tmp_path / "selected.txt"
    subprocess.run(
        ["bash", str(scripts / "mutation-changed.sh")],
        cwd=tmp_path,
        check=True,
        env={
            **os.environ,
            "MUTMUT_BASE_REF": "baseline",
            "MUTMUT_MODULE": "",
            "MUTMUT_MIN_SCORE": "",
            "MUTMUT_TARGET_LOG": str(log),
        },
        capture_output=True,
    )
    assert set(log.read_text().splitlines()) == {
        "meshchatnext.src.backend.update_manager.*",
        "meshchatnext.src.backend.http.routes.update.*",
    }

    env = {
        **os.environ,
        "MUTMUT_BASE_REF": "baseline",
        "MUTMUT_MODULE": "",
        "MUTMUT_MIN_SCORE": "",
        "MUTMUT_TARGET_LOG": str(log),
    }
    command = ["bash", str(scripts / "mutation-changed.sh")]
    selection = subprocess.run(
        [*command, "--list-json"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    modules = json.loads(selection.stdout)
    assert {module + ".*" for module in modules} == set(log.read_text().splitlines())
    log.unlink()
    for module in modules:
        subprocess.run(
            command,
            cwd=tmp_path,
            env={**env, "MUTMUT_MODULE": module},
            check=True,
            capture_output=True,
        )
    # Independent workers cover exactly the serial selection, once each.
    assert sorted(log.read_text().splitlines()) == sorted(
        module + ".*" for module in modules
    )
    invalid = subprocess.run(
        command,
        cwd=tmp_path,
        env={
            **env,
            "MUTMUT_MODULE": "meshchatnext.src.backend.data.interfaces.payload",
        },
        capture_output=True,
    )
    assert invalid.returncode == 2
    (scripts / "mutation-backend.sh").write_text("exit 17\n")
    failed = subprocess.run(
        command,
        cwd=tmp_path,
        env={**env, "MUTMUT_MODULE": modules[0]},
        capture_output=True,
    )
    assert failed.returncode == 17
    # A no-change plan is valid JSON and schedules no workers.
    empty = subprocess.run(
        [*command, "--list-json"],
        cwd=tmp_path,
        env={**env, "MUTMUT_BASE_REF": "HEAD"},
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(empty.stdout) == []


@pytest.mark.parametrize(
    ("plan", "modules", "worker", "success"),
    [
        ("success", '["runtime"]', "success", True),
        ("success", '["runtime"]', "failure", False),
        ("success", '["runtime"]', "cancelled", False),
        ("success", '["runtime"]', "skipped", False),
        ("failure", '["runtime"]', "success", False),
        ("cancelled", "", "skipped", False),
        ("success", "[]", "skipped", True),
    ],
)
def test_mutation_aggregate_requires_every_selected_worker(
    plan, modules, worker, success
):
    root = Path(__file__).resolve().parents[2]
    jobs = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())["jobs"]
    module = jobs["mutation-module"]
    assert module["timeout-minutes"] == 120
    assert module["strategy"]["fail-fast"] is False
    assert not module.get("continue-on-error", False)
    step = next(
        s for s in module["steps"] if s.get("name") == "Mutate changed backend modules"
    )
    assert step["env"]["MUTMUT_MIN_SCORE"] == "50"
    result = subprocess.run(
        ["bash", "-e", "-c", jobs["mutation-changed"]["steps"][0]["run"]],
        env={
            **os.environ,
            "PLAN_RESULT": plan,
            "MODULES": modules,
            "MODULE_RESULT": worker,
        },
        capture_output=True,
    )
    assert (result.returncode == 0) == success


@pytest.mark.parametrize(("survivors", "success"), [(0, True), (3, False)])
def test_backend_runner_reads_actual_mutmut_json_export(tmp_path, survivors, success):
    # Controlled metadata exercises the REAL exporter and score checker; it is
    # not evidence of a production mutation score.
    root = Path(__file__).resolve().parents[2]
    scripts = tmp_path / "scripts/ci"
    scripts.mkdir(parents=True)
    for name in ("mutation-backend.sh", "mutation-score-check.py"):
        shutil.copy2(root / "scripts/ci" / name, scripts / name)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.mutmut]\nsource_paths = ["demo.py"]\n'
    )
    (tmp_path / "demo.py").write_text("def demo(): return 1\n")
    mutants = tmp_path / "mutants"
    mutants.mkdir()
    (mutants / "demo.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": {
                    "demo.x_demo__mutmut_1": 1,
                    **{f"demo.x_demo__mutmut_{i + 2}": 0 for i in range(survivors)},
                },
                "durations_by_key": {},
                "estimated_durations_by_key": {},
            }
        )
    )
    # Stub only the costly mutation execution, not export or scoring.
    binary = tmp_path / "bin"
    binary.mkdir()
    uv = binary / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nshift\n"
        'if [[ "$1 $2" == "mutmut run" ]]; then exit 0; fi\n'
        'if [[ "$1" == "mutmut" ]]; then shift; exec "$TEST_PYTHON" -m mutmut "$@"; fi\n'
        'shift; exec "$TEST_PYTHON" "$@"\n'
    )
    uv.chmod(0o700)
    result = subprocess.run(
        ["bash", str(scripts / "mutation-backend.sh")],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "TEST_PYTHON": sys.executable,
            "MUTMUT_MIN_SCORE": "50",
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    report = json.loads((tmp_path / "mutmut-cicd-stats.json").read_text())
    assert report["killed"] == 1
    assert report["survived"] == survivors


@pytest.mark.parametrize("exit_code", [0, 17])
def test_resource_observer_preserves_command_failure_and_reports_usage(
    tmp_path, exit_code
):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/ci/with-resource-telemetry.py"),
            "--interval",
            "0.05",
            "--",
            sys.executable,
            "-c",
            f"import time; print('command-output', flush=True); time.sleep(0.12); raise SystemExit({exit_code})",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == exit_code
    assert "command-output" in result.stdout
    reports = [
        json.loads(line.removeprefix("CI_RESOURCE "))
        for line in result.stdout.splitlines()
        if line.startswith("CI_RESOURCE ")
    ]
    assert len(reports) >= 3
    assert all(
        report["free_bytes"] > 0 and report["free_inodes"] > 0 for report in reports
    )
