# SPDX-License-Identifier: MIT
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from meshchatnext.src.backend.sip_desktop_http import (
    install_sip_desktop_lifecycle,
    register_sip_desktop_routes,
)


@pytest.mark.asyncio
async def test_http_status_commands_limit_and_secret_safe_errors():
    service = SimpleNamespace(
        status=lambda: {"available": True, "registered": False},
        command=AsyncMock(return_value={"available": True}),
    )
    owner = SimpleNamespace(sip_desktop_service=service)
    routes = web.RouteTableDef()
    register_sip_desktop_routes(routes, owner)
    app = web.Application()
    app.add_routes(routes)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/v1/sip/status")
        assert (
            response.status == 200 and response.headers["Cache-Control"] == "no-store"
        )
        response = await client.post(
            "/api/v1/sip/command", json={"op": "connect", "id": "test"}
        )
        assert response.status == 200
        service.command.assert_awaited_once_with("connect", id="test")
        service.command.side_effect = ValueError("must-not-disclose-test-secret")
        response = await client.post(
            "/api/v1/sip/command", json={"op": "save", "password": "test-secret"}
        )
        assert response.status == 400 and "test-secret" not in await response.text()
        response = await client.post(
            "/api/v1/sip/command", json={"op": "save", "password": "x" * 17000}
        )
        assert response.status == 413


@pytest.mark.asyncio
async def test_missing_desktop_service_never_exposes_android_controls():
    routes = web.RouteTableDef()
    register_sip_desktop_routes(routes, SimpleNamespace())
    app = web.Application()
    app.add_routes(routes)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/v1/sip/status")
        assert (await response.json())["available"] is False
        assert (
            await client.post("/api/v1/sip/command", json={"op": "connect"})
        ).status == 503


@pytest.mark.asyncio
async def test_damaged_sip_metadata_does_not_abort_independent_app_startup(
    tmp_path, monkeypatch
):
    from meshchatnext.src.backend import sip_desktop_http

    monkeypatch.setattr(
        sip_desktop_http, "native_executable", lambda: tmp_path / "test-native"
    )
    monkeypatch.setattr(sip_desktop_http, "native_support_error", lambda: None)
    folder = tmp_path / "sip"
    folder.mkdir()
    path = folder / "accounts.json"
    path.write_text("{damaged-file")
    owner = SimpleNamespace(storage_dir=tmp_path)
    app = web.Application()
    install_sip_desktop_lifecycle(app, owner)
    await app.on_startup[-1](app)
    assert not hasattr(owner, "sip_desktop_service")
    assert "could not be opened" in owner.sip_desktop_error
    assert path.read_text() == "{damaged-file"
    await app.on_shutdown[-1](app)


@pytest.mark.asyncio
async def test_sip_commands_require_csrf_before_invoking_service(monkeypatch):
    from meshchatnext.src.backend.http.middleware import create_csrf_middleware

    monkeypatch.delenv("MESHCHAT_DISABLE_CSRF", raising=False)
    service = SimpleNamespace(command=AsyncMock())
    owner = SimpleNamespace(sip_desktop_service=service)
    routes = web.RouteTableDef()
    register_sip_desktop_routes(routes, owner)
    app = web.Application(middlewares=[create_csrf_middleware(owner)])
    app.add_routes(routes)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/api/v1/sip/command", json={"op": "connect"})
        assert response.status == 403
        service.command.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_desktop_audio_library_keeps_other_services_available(
    tmp_path, monkeypatch
):
    from meshchatnext.src.backend import sip_desktop_http

    monkeypatch.setattr(
        sip_desktop_http, "native_executable", lambda: tmp_path / "native"
    )
    monkeypatch.setattr(
        sip_desktop_http, "native_support_error", lambda: "Install libpulse0"
    )
    owner = SimpleNamespace(storage_dir=tmp_path)
    app = web.Application()
    install_sip_desktop_lifecycle(app, owner)
    await app.on_startup[-1](app)
    assert not hasattr(owner, "sip_desktop_service")
    assert owner.sip_desktop_error == "Install libpulse0"
    assert not (tmp_path / "sip").exists()
