# SPDX-License-Identifier: 0BSD
"""Retain baseline failures even when mutation workers suppress their console."""

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path


def pytest_runtest_logreport(report):
    mode = os.environ.get("MUTANT_UNDER_TEST")
    folder = os.environ.get("MUTMUT_DIAGNOSTICS_DIR")
    if mode not in ("stats", "") or not folder or not report.failed:
        return
    target = Path(folder)
    temporary = None
    try:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.chmod(0o700)
        details = report.longreprtext.encode("utf-8", errors="replace")[:65536].decode(
            "utf-8", errors="ignore"
        )
        result = {
            "nodeid": report.nodeid,
            "phase": report.when,
            "run": "statistics" if mode == "stats" else "clean",
            "details": details,
        }
        name = (
            hashlib.sha256(
                (result["run"] + report.nodeid + report.when).encode()
            ).hexdigest()
            + ".json"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target, delete=False
        ) as output:
            temporary = Path(output.name)
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
        temporary.replace(target / name)
    except OSError:
        # A diagnostic write must never replace the original pytest failure.
        print("Could not retain mutation baseline failure details.")
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
