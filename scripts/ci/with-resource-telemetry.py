#!/usr/bin/env python3
"""Run a CI command unchanged while recording bounded resource diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def snapshot() -> None:
    root = Path.cwd()
    usage = shutil.disk_usage(root)
    fs = os.statvfs(root)
    sizes = {}
    # Sizes only: never print file contents, environment or credentials.
    paths = [
        root / "mutants",
        root / "temp-tests",
        root / ".venv",
        Path(tempfile.gettempdir()),
        Path("/home/runner/actions-runner"),
        Path("/home/runner/work"),
    ]
    paths.extend(
        Path(os.environ[v])
        for v in ("RUNNER_TEMP", "UV_CACHE_DIR")
        if os.environ.get(v)
    )
    for path in paths:
        if not path.exists():
            continue
        try:
            result = subprocess.run(
                [shutil.which("du") or "/usr/bin/du", "-x", "-s", str(path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            sizes[str(path)] = int(result.stdout.split()[0]) * 1024
        except (OSError, ValueError, subprocess.SubprocessError):
            sizes[str(path)] = "unavailable"
    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemAvailable", "MemTotal", "SwapFree"}:
                memory[key] = value.strip()
    except OSError:
        pass
    print(
        "CI_RESOURCE "
        + json.dumps(
            {
                "time": time.time(),
                "free_bytes": usage.free,
                "free_inodes": fs.f_favail,
                "directory_bytes": sizes,
                "memory": memory,
            }
        ),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=60)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command or args.interval <= 0:
        parser.error("a command and positive interval are required")
    snapshot()
    child = subprocess.Popen(command)
    try:
        while True:
            try:
                code = child.wait(timeout=args.interval)
                snapshot()
                return code if code >= 0 else 128 - code
            except subprocess.TimeoutExpired:
                snapshot()
    except BaseException:
        child.terminate()
        child.wait()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
