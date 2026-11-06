# SPDX-License-Identifier: MIT
"""Keep the normal CI parser backport/guard aligned with supported Android ABIs."""

import ast
import re
import shlex
from pathlib import Path

import yaml


def test_normal_android_ci_qualifies_every_selected_abi():
    root = Path(__file__).resolve().parents[2]
    gradle = (root / "android/app/build.gradle").read_text()
    values = re.search(r"def allAndroidAbis = \[([^\]]+)\]", gradle)
    assert values is not None
    expected = set(re.findall(r'"([a-z0-9_-]+)"', values[1]))
    assert expected == {"arm64-v8a", "x86_64", "armeabi-v7a"}
    tree = ast.parse((root / "scripts/android/provision-expat.py").read_text())
    defaults = [
        key.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(
            isinstance(arg, ast.Constant) and arg.value == "--abis" for arg in node.args
        )
        for key in node.keywords
        if key.arg == "default" and isinstance(key.value, ast.Constant)
    ]
    assert len(defaults) == 1
    workflow = yaml.safe_load(
        (root / ".github/workflows/android-build.yml").read_text()
    )
    provision, verify = [], []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            for line in step.get("run", "").splitlines():
                for script, records in (
                    ("scripts/android/provision-expat.py", provision),
                    ("scripts/android/verify-apk-expat.py", verify),
                ):
                    if script in line:
                        args = shlex.split(line)
                        abis = (
                            args[args.index("--abis") + 1]
                            if "--abis" in args
                            else defaults[0]
                        )
                        records.append(set(abis.split(",")))
    assert provision == [expected]
    assert verify == [expected]
