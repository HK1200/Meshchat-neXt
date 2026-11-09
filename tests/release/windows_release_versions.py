# SPDX-License-Identifier: 0BSD
"""Version and upgrade baseline for the verified Windows release checkout."""

import json
import re
from pathlib import Path


def release_versions(source: Path) -> tuple[str, str]:
    version = json.loads((source / "package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.([1-9][0-9]*)", version)
    if not match:
        raise ValueError("Windows package review requires a stable patch release")
    major, minor, patch = match.groups()
    return version, f"{major}.{minor}.{int(patch) - 1}"
