# SPDX-License-Identifier: 0BSD
# Runtime checks remain enforced under python -O.
"""Build the lock-pinned freezer base against the selected Python patch."""

import hashlib
import http.client
import importlib.metadata
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlparse


def main():
    if not sys.platform.startswith("linux"):
        raise SystemExit("This source-base preparation is Linux-only")
    root = Path(__file__).resolve().parents[2]
    expected = os.environ.get("PYTHON_VERSION", platform.python_version())
    if not platform.python_version() == expected:
        raise RuntimeError((platform.python_version(), expected))
    lock = tomllib.loads((root / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == "freeze-core")
    setuptools = next(p for p in lock["package"] if p["name"] == "setuptools")
    if not importlib.metadata.version("setuptools") == setuptools["version"]:
        raise RuntimeError(
            "Build invariant failed: importlib.metadata.version('setuptools') == setuptools['version']"
        )
    source = package["sdist"]
    url = urlparse(source["url"])
    if not (url.scheme == "https" and url.hostname == "files.pythonhosted.org"):
        raise RuntimeError(
            "Build invariant failed: url.scheme == 'https' and url.hostname == 'files.pythonhosted.org'"
        )
    if not re.fullmatch("sha256:[0-9a-f]{64}", source["hash"]):
        raise RuntimeError(
            "Build invariant failed: re.fullmatch('sha256:[0-9a-f]{64}', source['hash'])"
        )
    temp = root / "temp-tests"
    temp.mkdir(exist_ok=True)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("The pinned UV tool must be on PATH")
    with tempfile.TemporaryDirectory(prefix="freezer-source-", dir=temp) as folder:
        archive = Path(folder) / "freeze-core-source.tar.gz"
        connection = http.client.HTTPSConnection(
            url.hostname, context=ssl.create_default_context(), timeout=120
        )
        try:
            connection.request("GET", url.path)
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f"Pinned source returned HTTP {response.status}")
            data = response.read(source["size"] + 1)
        finally:
            connection.close()
        if (
            len(data) != source["size"]
            or "sha256:" + hashlib.sha256(data).hexdigest() != source["hash"]
        ):
            raise RuntimeError("Freezer source differs from the signed lockfile hash")
        archive.write_bytes(data)
        source_root = Path(folder) / "source"
        source_root.mkdir()
        with tarfile.open(archive) as package_archive:
            package_archive.extractall(source_root, filter="data")
        projects = list(source_root.iterdir())
        if len(projects) != 1 or not (projects[0] / "setup.py").is_file():
            raise RuntimeError("The pinned source archive has an unexpected layout")
        wheelhouse = Path(folder) / "wheels"
        # The upstream launcher places LIBM before static libpython. Keep it
        # linked on hosted interpreters; this affects only this source build.
        build_env = dict(os.environ)
        compiler = build_env.get("CC") or sysconfig.get_config_var("CC")
        if not isinstance(compiler, str) or not compiler.strip():
            raise RuntimeError("The selected Python has no configured C compiler")
        build_env["CC"] = compiler + " -Wl,--no-as-needed"
        subprocess.run(
            [
                sys.executable,
                "setup.py",
                "build_ext",
                "--force",
                "bdist_wheel",
                "--dist-dir",
                str(wheelhouse),
            ],
            cwd=projects[0],
            env=build_env,
            check=True,
        )
        wheels = list(wheelhouse.glob("freeze_core-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(
                "Expected exactly one locally source-built freezer wheel"
            )
        subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--python",
                sys.executable,
                "--no-deps",
                "--no-build-isolation",
                "--no-cache",
                "--reinstall",
                str(wheels[0]),
            ],
            cwd=root,
            check=True,
        )
    if not importlib.metadata.version("freeze-core") == package["version"]:
        raise RuntimeError(
            "Build invariant failed: importlib.metadata.version('freeze-core') == package['version']"
        )
    import freeze_core

    bases = Path(freeze_core.__file__).parent / "bases"
    report = {
        "passed": True,
        "build_python": platform.python_version(),
        "freeze_core": package["version"],
        "locked_sdist": source,
        "source_build_without_binary_or_build_cache": True,
        "explicit_locked_source_build_ext_and_bdist_wheel": True,
        "hosted_static_python_math_libraries_retained": True,
        "build_dependencies_from_frozen_environment": True,
        "base_hashes": {
            p.name: hashlib.file_digest(p.open("rb"), "sha256").hexdigest()
            for p in sorted(bases.iterdir())
            if p.is_file()
        },
    }
    report["base_names"] = sorted(p.name for p in bases.iterdir())
    report["python_soabi"] = sysconfig.get_config_var("SOABI")
    report["python_exe_suffix"] = sysconfig.get_config_var("EXE")
    print(json.dumps(report, sort_keys=True), flush=True)
    from cx_Freeze import Executable

    probe = Executable(script=str(root / "scripts/ci/prepare-frozen-python.py"))
    if not Path(probe.base).is_file():
        raise RuntimeError("Source-built console base is missing")
    output = root / "reports/freezer-source.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Built locked freeze-core {package['version']} with Python {expected}")


if __name__ == "__main__":
    main()
