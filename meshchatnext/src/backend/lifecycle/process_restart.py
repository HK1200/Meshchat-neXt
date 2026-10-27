# SPDX-License-Identifier: 0BSD
"""Restart the current application without losing its launch arguments."""

from __future__ import annotations

import os
import sys


def restart_current_process() -> None:
    # Frozen applications already are the executable; passing their argv[0]
    # again makes it an extra application argument. Python source launches
    # instead need the script path after the interpreter executable.
    arguments = (
        [sys.executable, *sys.argv[1:]]
        if getattr(sys, "frozen", False)
        else [sys.executable, *sys.argv]
    )
    os.execv(sys.executable, arguments)  # noqa: S606
