# SPDX-License-Identifier: 0BSD
"""Baseline failures remain diagnosable without exporting expected mutants."""

import json
from types import SimpleNamespace

import pytest

from tests.backend import mutation_failure_reports as plugin


@pytest.mark.parametrize("mode", ["stats", ""])
@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_baseline_failure_is_retained_privately(tmp_path, monkeypatch, mode, phase):
    folder = tmp_path / "evidence"
    monkeypatch.setenv("MUTMUT_DIAGNOSTICS_DIR", str(folder))
    monkeypatch.setenv("MUTANT_UNDER_TEST", mode)
    report = SimpleNamespace(
        failed=True,
        nodeid="private_fixture::case",
        when=phase,
        longreprtext="Original assertion failure",
    )
    plugin.pytest_runtest_logreport(report)
    files = list(folder.iterdir())
    assert len(files) == 1
    record = json.loads(files[0].read_text())
    assert record["details"] == report.longreprtext and record["phase"] == phase
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert folder.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    "mode,failed", [("some_mutant", True), ("fail", True), ("stats", False)]
)
def test_expected_mutant_and_passing_results_are_not_exported(
    tmp_path, monkeypatch, mode, failed
):
    folder = tmp_path / "evidence"
    monkeypatch.setenv("MUTMUT_DIAGNOSTICS_DIR", str(folder))
    monkeypatch.setenv("MUTANT_UNDER_TEST", mode)
    plugin.pytest_runtest_logreport(SimpleNamespace(failed=failed))
    assert not folder.exists()


def test_diagnostic_failure_does_not_replace_the_original_test_failure(
    tmp_path, monkeypatch
):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("preserve")
    monkeypatch.setenv("MUTMUT_DIAGNOSTICS_DIR", str(blocked))
    monkeypatch.setenv("MUTANT_UNDER_TEST", "stats")
    report = SimpleNamespace(
        failed=True, nodeid="private_fixture::case", when="call", longreprtext="failure"
    )
    plugin.pytest_runtest_logreport(report)
    assert blocked.read_text() == "preserve"
