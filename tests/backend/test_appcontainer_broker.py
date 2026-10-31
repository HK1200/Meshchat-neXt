# SPDX-License-Identifier: 0BSD
import os

import pytest

from meshchatnext.src.backend.appcontainer_broker import _flag, broker_settings
from meshchatnext.src.backend.appcontainer_temp import install_private_directory_compat


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.1", "example.com", "::"])
def test_reject_non_loopback_broker(host, tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        broker_settings(["--host", host], str(tmp_path))


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_defaults_to_https(host, tmp_path, monkeypatch):
    monkeypatch.delenv("MESHCHAT_NO_HTTPS", raising=False)
    result = broker_settings(["--host", host], str(tmp_path))
    assert result[:3] == (host, 8000, True)
    assert result[3] == str(tmp_path / "ssl" / "cert.pem")


def test_last_cli_option_wins():
    assert _flag(["--port", "8000", "--port=9338"], "--port") == "9338"


def test_reject_partial_custom_tls(tmp_path, monkeypatch):
    monkeypatch.delenv("MESHCHAT_SSL_KEY", raising=False)
    with pytest.raises(ValueError, match="Both SSL"):
        broker_settings(["--ssl-cert", "cert.pem"], str(tmp_path))


def test_temp_hook_leaves_normal_process_unchanged():
    mkdir = os.mkdir
    assert install_private_directory_compat() is False
    assert os.mkdir is mkdir


@pytest.mark.asyncio
@pytest.mark.parametrize("forged_token", ["b" * 64, "", "é" * 64])
async def test_pipe_rejects_forged_shutdown_and_forwarded_identity(forged_token):
    from unittest.mock import Mock

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    from meshchatnext.src.backend.appcontainer_pipe import trusted_pipe_middleware

    transport = Mock()
    transport.get_extra_info.return_value = True
    called = []

    async def handler(request):
        called.append((request.scheme, request.remote))
        return web.Response()

    middleware = trusted_pipe_middleware(
        "https", shutdown_token="a" * 64, shutdown_callback=Mock()
    )
    forged = make_mocked_request(
        "POST",
        "/__meshchatnext_container_quit__",
        headers={"X-MeshchatNext-Supervisor": forged_token},
        transport=transport,
    )
    with pytest.raises(web.HTTPForbidden):
        await middleware(forged, handler)
    request = make_mocked_request(
        "GET",
        "/api/v1/app/info",
        headers={"X-Forwarded-For": "192.0.2.1", "X-Forwarded-Proto": "http"},
        transport=transport,
    )
    await middleware(request, handler)
    assert called == [("https", "127.0.0.1")]


@pytest.mark.asyncio
async def test_private_pipe_requires_trusted_transport():
    from unittest.mock import Mock

    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    from meshchatnext.src.backend.appcontainer_pipe import trusted_pipe_middleware

    transport = Mock()
    transport.get_extra_info.return_value = None
    request = make_mocked_request("GET", "/", transport=transport)
    with pytest.raises(web.HTTPForbidden):
        await trusted_pipe_middleware("https")(request, Mock())


def test_launcher_resolves_data_dir_and_last_flag(tmp_path, monkeypatch):
    from meshchatnext.src.backend.appcontainer_launcher import _resolve_paths

    for name in (
        "MESHCHAT_STORAGE_DIR",
        "MESHCHAT_RETICULUM_CONFIG_DIR",
        "MESHCHAT_LOG_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    storage, reticulum, logs = _resolve_paths(
        ["--data-dir", "unused", "--data-dir", str(tmp_path)]
    )
    assert storage == str(tmp_path / "storage")
    assert reticulum == str(tmp_path / ".reticulum")
    assert logs == str(tmp_path / "storage" / "logs")
