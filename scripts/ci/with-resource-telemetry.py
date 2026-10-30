#!/usr/bin/env python3
"""Run a CI command unchanged while recording bounded resource diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path


def directory_usage(path: Path) -> dict:
    """Keep useful du totals even when inaccessible children make du exit 1."""
    try:
        result = subprocess.run(
            [shutil.which("du") or "/usr/bin/du", "-x", "-s", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return {
            "bytes": int(result.stdout.split()[0]) * 1024,
            "complete": result.returncode == 0,
        }
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return {"bytes": None, "complete": False}


def open_deleted_files(only_pid: int | None = None) -> dict:
    """Measure own-user unlinked regular files that du cannot see; no paths."""
    files = {}
    deadline = time.monotonic() + 5
    try:
        processes = list(Path("/proc").iterdir())
    except OSError:
        return {"allocated_bytes": 0, "files": [], "complete": False}
    complete = True
    for process in processes:
        if time.monotonic() > deadline:
            complete = False
            break
        if only_pid is not None and process.name != str(only_pid):
            continue
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            for fd in (process / "fd").iterdir():
                if time.monotonic() > deadline:
                    complete = False
                    break
                try:
                    target = os.readlink(fd)
                    info = fd.stat()
                    if not target.endswith(" (deleted)") or not stat.S_ISREG(
                        info.st_mode
                    ):
                        continue
                    key = (info.st_dev, info.st_ino)
                    files[key] = {
                        "pid": int(process.name),
                        "bytes": info.st_size,
                        "allocated_bytes": info.st_blocks * 512,
                    }
                except OSError:
                    continue
        except OSError:
            continue
    values = sorted(
        files.values(), key=lambda row: row["allocated_bytes"], reverse=True
    )
    return {
        "allocated_bytes": sum(row["allocated_bytes"] for row in values),
        "files": values[:10],
        "complete": complete,
    }


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
        Path("/var/lib/systemd/coredump"),
        Path("/var/crash"),
        Path("/var/log"),
    ]
    paths.extend(
        Path(os.environ[v])
        for v in ("RUNNER_TEMP", "UV_CACHE_DIR")
        if os.environ.get(v)
    )
    for path in paths:
        if not path.exists():
            continue
        sizes[str(path)] = directory_usage(path)
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
                "open_deleted_files": open_deleted_files(),
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
