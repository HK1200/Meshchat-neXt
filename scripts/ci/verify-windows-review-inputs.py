#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Bind native release verification to an exact successful merged-source build."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def validate(run: dict, listing: dict, source: str, verification_source: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source) or verification_source != source:
        raise ValueError(
            "Verification tooling must be the exact expected release source"
        )
    if (
        run.get("head_sha") != source
        or run.get("head_branch") != "main"
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("path") != ".github/workflows/native-build-dev.yml"
    ):
        raise ValueError("Expected a successful exact-source main native build")
    artifacts = listing.get("artifacts", [])
    if listing.get("total_count") != len(artifacts):
        raise ValueError("Incomplete native artifact inventory")
    selected = [a for a in artifacts if a.get("name") == "next-windows-" + source]
    if len(selected) != 1:
        raise ValueError("Expected one exact-source approved Windows artifact")
    artifact = selected[0]
    if (
        artifact.get("expired")
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest") or "")
        or artifact.get("workflow_run", {}).get("id") != run["id"]
        or artifact.get("workflow_run", {}).get("head_sha") != source
    ):
        raise ValueError("Windows artifact source, digest or run identity mismatch")
    return {"passed": True, "source": source, "run_id": run["id"], "artifact": artifact}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*", args.run):
        raise ValueError("An exact numeric native build run is required")
    if (
        os.environ.get("GITHUB_REPOSITORY") != "HK1200/Meshchat-neXt"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
    ):
        raise ValueError(
            "Release verification must use the owner repository main source"
        )
    gh = shutil.which("gh")
    if gh is None:
        raise RuntimeError("GitHub CLI is required for immutable run verification")
    base = f"repos/HK1200/Meshchat-neXt/actions/runs/{args.run}"
    run = json.loads(subprocess.check_output([gh, "api", base], text=True))
    listing = json.loads(
        subprocess.check_output(
            [gh, "api", base + "/artifacts?per_page=100"], text=True
        )
    )
    if run.get("id") != int(args.run):
        raise ValueError("Native build run identifier mismatch")
    result = validate(run, listing, args.source, os.environ.get("GITHUB_SHA", ""))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "passed": True,
                "source": args.source,
                "run_id": run["id"],
                "artifact_id": result["artifact"]["id"],
            }
        )
    )


if __name__ == "__main__":
    main()
