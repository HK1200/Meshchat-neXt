# SPDX-License-Identifier: 0BSD
"""Keep custom ports, data paths and arguments through packaged restarts."""

from unittest.mock import patch

import pytest

from meshchatnext.src.backend.lifecycle import process_restart


@pytest.mark.parametrize("frozen", [False, True])
def test_restart_preserves_arguments_without_duplicating_frozen_executable(
    monkeypatch, frozen
):
    executable = "/opt/Meshchat neXt/MeshchatNext" if frozen else "/usr/bin/python3"
    entrypoint = executable if frozen else "/workspace/meshchatnext/meshchat.py"
    arguments = [
        entrypoint,
        "--host",
        "127.0.0.1",
        "--port",
        "9352",
        "--storage-dir",
        "/workspace/fixture with spaces/storage",
        "--reticulum-config-dir",
        "/workspace/fixture with spaces/.reticulum",
    ]
    monkeypatch.setattr(process_restart.sys, "executable", executable)
    monkeypatch.setattr(process_restart.sys, "argv", arguments)
    monkeypatch.setattr(process_restart.sys, "frozen", frozen, raising=False)
    with patch.object(process_restart.os, "execv") as execv:
        process_restart.restart_current_process()
    expected = arguments if frozen else [executable, *arguments]
    execv.assert_called_once_with(executable, expected)
