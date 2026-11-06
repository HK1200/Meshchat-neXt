"""Synthetic APK payload integrity tests; not native Android coverage."""

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("fault", [None, "stale", "missing", "unknown-abi", "source"])
def test_packaged_parser_integrity(tmp_path, fault):
    path = Path(__file__).resolve().parents[2] / "scripts/android/verify-apk-expat.py"
    spec = importlib.util.spec_from_file_location("apk_expat", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = b"synthetic-fixed-parser"
    provenance = {
        "python_kernel": "3.11.17",
        "expat": "2.10.0",
        "cpython_source": "e6392eb68a39cef49c9fe6431253050caa17a426",
        "inputs": {
            "expat-2.10.0.tar.xz": "c624ba2998fc65df1163a49641ff3f9ab73138b11641d92c86bee0fb01b1bc7f"
        },
        "abis": [{"abi": "x86_64", "module_sha256": hashlib.sha256(data).hexdigest()}],
    }
    if fault == "source":
        provenance["cpython_source"] = "0" * 40
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        if fault != "missing":
            archive.writestr(
                "pyexpat.cpython-311.so", b"old-parser" if fault == "stale" else data
            )
    apk = tmp_path / "synthetic.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("assets/chaquopy/stdlib-x86_64.imy", inner.getvalue())
        if fault == "unknown-abi":
            archive.writestr("assets/chaquopy/stdlib-unqualified.imy", inner.getvalue())
    if fault:
        with pytest.raises(ValueError):
            module.verify(apk, provenance, {"x86_64"})
    else:
        report = module.verify(apk, provenance, {"x86_64"})
        assert report["parser_sha256"]["x86_64"] == hashlib.sha256(data).hexdigest()
