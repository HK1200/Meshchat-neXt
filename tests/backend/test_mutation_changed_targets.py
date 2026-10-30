# SPDX-License-Identifier: 0BSD
"""The changed-module runner must select real mutmut keys, not bare modules."""

import os
import shutil
import subprocess
from pathlib import Path


def test_changed_module_filters_select_mutants_without_data_payloads(tmp_path):
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
            "MUTMUT_MIN_SCORE": "",
            "MUTMUT_TARGET_LOG": str(log),
        },
        capture_output=True,
    )
    assert set(log.read_text().splitlines()) == {
        "meshchatnext.src.backend.update_manager.*",
        "meshchatnext.src.backend.http.routes.update.*",
    }
