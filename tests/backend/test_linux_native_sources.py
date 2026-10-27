# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import io
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "native_sources", Path("scripts/build-linux-native.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_offline_missing_or_corrupt_archive_never_contacts_network(
    tmp_path, monkeypatch
):
    fetch = Mock()
    monkeypatch.setattr(module.urllib.request, "urlopen", fetch)
    target = tmp_path / "source.tgz"
    digest = hashlib.sha256(b"valid").hexdigest()
    with pytest.raises(ValueError, match="Offline"):
        module.verified_archive(
            target, "https://example.test/source", digest, offline=True
        )
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        module.verified_archive(
            target, "https://example.test/source", digest, offline=False
        )
    fetch.assert_not_called()


def test_verified_download_is_atomic_and_rejected_bytes_are_removed(
    tmp_path, monkeypatch
):
    target = tmp_path / "source.tgz"
    data = b"pinned-source"
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(data)
    )
    with pytest.raises(ValueError, match="checksum"):
        module.verified_archive(
            target, "https://example.test/source", "0" * 64, offline=False
        )
    assert not target.exists() and not target.with_suffix(".tgz.part").exists()
    module.verified_archive(
        target,
        "https://example.test/source",
        hashlib.sha256(data).hexdigest(),
        offline=False,
    )
    assert target.read_bytes() == data


def test_native_archive_input_rejects_local_and_cleartext_urls(tmp_path):
    for url in ("file:///etc/passwd", "http://example.test/source"):
        with pytest.raises(ValueError, match="HTTPS"):
            module.verified_archive(tmp_path / "archive", url, "0" * 64, offline=False)
