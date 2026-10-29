# SPDX-License-Identifier: 0BSD
"""Windows test-directory process checks must never signal a process."""

import os
import subprocess
import sys
from unittest.mock import Mock

import psutil
import pytest

from tests.backend.support import test_temp_dir

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows process semantics")


@pytest.mark.parametrize("alive", [False, True])
def test_windows_pid_check_queries_without_signalling(monkeypatch, alive):
    query = Mock(return_value=alive)
    signal = Mock(side_effect=AssertionError("Process check must not signal"))
    monkeypatch.setattr(psutil, "pid_exists", query)
    monkeypatch.setattr(os, "kill", signal)
    assert test_temp_dir._pid_alive(1234) is alive
    query.assert_called_once_with(1234)
    signal.assert_not_called()


def test_windows_pid_check_does_not_terminate_its_caller():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from tests.backend.support.test_temp_dir import _pid_alive; assert _pid_alive(os.getpid()); print('still running')",
        ],
        cwd=test_temp_dir.REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "still running" in result.stdout
