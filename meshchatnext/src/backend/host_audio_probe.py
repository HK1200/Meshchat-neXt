# SPDX-License-Identifier: 0BSD
"""Contain fatal native host-audio failures outside the messaging process."""

from __future__ import annotations

import subprocess
import sys

MODULE = "meshchatnext.src.backend.host_audio_probe"


def _probe_command():
    flag = "--meshchatnext-run-module" if getattr(sys, "frozen", False) else "-m"
    return [sys.executable, flag, MODULE]


def host_audio_unavailable(timeout=5.0):
    try:
        result = subprocess.run(
            _probe_command(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    return result.returncode != 0


def main():
    # PulseAudio can abort inside C before Python can catch an exception.
    # A probe must not leave large core files or terminate the parent app.
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        from LXST.Sources import Backend

        if Backend is None:
            return 1
        Backend()
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
