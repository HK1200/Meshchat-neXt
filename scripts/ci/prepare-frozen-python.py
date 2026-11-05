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
                "--no-binary",
                ":all:",
                str(archive),
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
        "build_dependencies_from_frozen_environment": True,
        "base_hashes": {
            p.name: hashlib.file_digest(p.open("rb"), "sha256").hexdigest()
            for p in sorted(bases.iterdir())
            if p.is_file()
        },
    }
    output = root / "reports/freezer-source.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Built locked freeze-core {package['version']} with Python {expected}")


if __name__ == "__main__":
    main()
