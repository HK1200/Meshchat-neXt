# SPDX-License-Identifier: 0BSD
"""Pinned build-input fetches tolerate temporary outages without trusting bad bytes."""

import hashlib
import importlib.util
import io
import ssl
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

URL = "https://example.invalid/pinned-input"
DATA = b"verified synthetic build input"
DIGEST = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def fetcher(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/android/provision-expat.py"
    spec = importlib.util.spec_from_file_location("pinned_expat_fetch", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    waits = []
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(sleep=waits.append, time=lambda: 0),
        raising=False,
    )
    calls = []

    def responses(*items):
        queue = list(items)

        def open_url(url, *, timeout):
            assert url == URL and timeout == 60
            calls.append(url)
            result = queue.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result

        # Scope the transport mock to the build script, not global urllib.
        monkeypatch.setattr(
            module,
            "urllib",
            SimpleNamespace(
                request=SimpleNamespace(urlopen=open_url),
                error=urllib.error,
            ),
        )

    return module, responses, waits, calls


def http_error(code, headers=None):
    return urllib.error.HTTPError(URL, code, "Synthetic response", headers or {}, None)


def test_rate_limit_waits_then_accepts_only_verified_input(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses(http_error(429, {"Retry-After": "7"}), io.BytesIO(DATA))
    path = tmp_path / "input.bin"
    assert module.fetch(path, URL, DIGEST) == path
    assert path.read_bytes() == DATA and len(calls) == 2 and waits == [7]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input.bin"]


def test_http_date_retry_after_is_respected(fetcher, tmp_path):
    module, responses, waits, _ = fetcher
    responses(
        http_error(503, {"Retry-After": "Thu, 01 Jan 1970 00:00:09 GMT"}),
        io.BytesIO(DATA),
    )
    module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert waits == [9]


def test_long_server_delay_does_not_trigger_an_early_retry(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses(http_error(429, {"Retry-After": "3600"}))
    with pytest.raises(urllib.error.HTTPError):
        module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert len(calls) == 1 and waits == [] and not list(tmp_path.iterdir())


def test_exhausted_retries_leave_no_cached_or_partial_input(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses(*(http_error(502) for _ in range(4)))
    with pytest.raises(urllib.error.HTTPError):
        module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert len(calls) == 4 and len(waits) == 3 and not list(tmp_path.iterdir())


def test_partial_read_is_removed_before_retry(fetcher, tmp_path):
    module, responses, waits, calls = fetcher

    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise TimeoutError("Synthetic interrupted download")
            return super().read(3)

    responses(Interrupted(DATA), io.BytesIO(DATA))
    path = module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert path.read_bytes() == DATA and len(calls) == 2 and len(waits) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input.bin"]


@pytest.mark.parametrize(
    "failure",
    [
        http_error(404),
        urllib.error.URLError(
            ssl.SSLCertVerificationError("Synthetic untrusted certificate")
        ),
    ],
)
def test_permanent_or_certificate_errors_are_not_retried(fetcher, tmp_path, failure):
    module, responses, waits, calls = fetcher
    responses(failure)
    with pytest.raises(type(failure)):
        module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert len(calls) == 1 and waits == [] and not list(tmp_path.iterdir())


def test_checksum_mismatch_is_not_retried_or_cached(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses(io.BytesIO(b"wrong input"))
    with pytest.raises(RuntimeError, match="Untrusted download"):
        module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert len(calls) == 1 and waits == [] and not list(tmp_path.iterdir())


def test_verified_cache_needs_no_network(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses()
    path = tmp_path / "input.bin"
    path.write_bytes(DATA)
    assert module.fetch(path, URL, DIGEST) == path
    assert not calls and not waits


def test_corrupt_existing_cache_is_not_silently_replaced(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses()
    path = tmp_path / "input.bin"
    path.write_bytes(b"damaged cache")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        module.fetch(path, URL, DIGEST)
    assert path.read_bytes() == b"damaged cache" and not calls and not waits


def test_plain_http_never_reaches_the_transport(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses()
    with pytest.raises(RuntimeError, match="HTTPS"):
        module.fetch(tmp_path / "input.bin", "http://example.invalid/input", DIGEST)
    assert not calls and not waits


def test_oversized_body_is_not_retried_or_cached(fetcher, tmp_path, monkeypatch):
    module, responses, waits, calls = fetcher
    monkeypatch.setattr(module, "MAX_DOWNLOAD_BYTES", 3)
    responses(io.BytesIO(DATA))
    with pytest.raises(RuntimeError, match="Oversized build input"):
        module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert len(calls) == 1 and waits == [] and not list(tmp_path.iterdir())


def test_rate_limit_without_header_uses_a_meaningful_backoff(fetcher, tmp_path):
    module, responses, waits, calls = fetcher
    responses(http_error(429), io.BytesIO(DATA))
    module.fetch(tmp_path / "input.bin", URL, DIGEST)
    assert len(calls) == 2 and waits == [15]
