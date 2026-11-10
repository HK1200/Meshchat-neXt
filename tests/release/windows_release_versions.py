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
    # v0.1.11 was a source tag without a public installer release.
    published_baselines = {"0.1.12": "0.1.10"}
    baseline = published_baselines.get(version, f"{major}.{minor}.{int(patch) - 1}")
    return version, baseline
