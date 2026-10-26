# SPDX-License-Identifier: 0BSD
import asyncio
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from meshchatnext.src.backend import regional_map_download as module
from meshchatnext.src.backend.privacy_mode import OutboundHttpBlockedError


class Setting:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.fixture
def setup_download(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_data BLOB)")
        db.execute("INSERT INTO tiles VALUES (0, X'00')")
    payload = source.read_bytes()
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "assets": {
                    module.NAME: {
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                }
            }
        )
    )
    monkeypatch.setattr(module, "CATALOG", catalog)
    directory = tmp_path / "maps"
    config = SimpleNamespace(
        privacy_mode_enabled=Setting(False),
        map_offline_enabled=Setting(False),
        map_offline_path=Setting("old-map"),
    )
    manager = SimpleNamespace(
        config=config, get_mbtiles_dir=lambda: str(directory), close=lambda: None
    )

    class Response:
        def raise_for_status(self):
            pass

        @property
        def content(self):
            return self

        async def iter_chunked(self, size):
            yield payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Session(Response):
        def __init__(self, **kwargs):
            pass

        def get(self, url):
            assert url == module.URL
            return Response()

    monkeypatch.setattr(module.aiohttp, "ClientSession", Session)
    return module.RegionalMapDownload(manager), directory, catalog


def test_verified_download_activates_without_replacing_custom_map(setup_download):
    download, directory, _ = setup_download
    directory.mkdir()
    original = directory / module.NAME
    original.write_bytes(b"custom map")
    asyncio.run(download.run())
    assert download.state["status"] == "completed"
    assert original.read_bytes() == b"custom map"
    assert download.manager.config.map_offline_enabled.get() is True
    assert download.manager.config.map_offline_path.get() != str(original)
    assert not list(directory.glob("*.part"))


def test_bad_checksum_keeps_previous_map_and_cleans_partial(setup_download):
    download, directory, catalog = setup_download
    data = json.loads(catalog.read_text())
    data["assets"][module.NAME]["sha256"] = "0" * 64
    catalog.write_text(json.dumps(data))
    asyncio.run(download.run())
    assert download.state["status"] == "failed"
    assert download.manager.config.map_offline_path.get() == "old-map"
    assert not list(directory.iterdir())


def test_privacy_blocks_before_network_or_task(setup_download):
    download, directory, _ = setup_download
    download.manager.config.privacy_mode_enabled.set(True)
    with pytest.raises(OutboundHttpBlockedError):
        download.start()
    assert download.task is None
    assert not directory.exists()


def test_repeat_request_uses_verified_local_copy_without_network(
    setup_download, monkeypatch
):
    download, _, _ = setup_download
    asyncio.run(download.run())
    assert download.state["status"] == "completed"
    original = download.manager.config.map_offline_path.get()
    monkeypatch.setattr(
        module.aiohttp,
        "ClientSession",
        lambda **kw: pytest.fail("must reuse verified map"),
    )
    download.state = {"received": 0, "status": "downloading"}
    asyncio.run(download.run())
    assert download.state["status"] == "completed"
    assert download.manager.config.map_offline_path.get() == original


def test_early_cancellation_and_shutdown_are_safe(setup_download):
    download, directory, _ = setup_download

    async def check():
        download.start()
        download.cancel()

        owner = SimpleNamespace(regional_map_download=download)
        web = SimpleNamespace(on_shutdown=[])
        module.install_regional_map_lifecycle(web, owner)
        await web.on_shutdown[0](None)
        assert download.task.done()

    asyncio.run(check())
    assert download.state["status"] == "cancelled"
    assert not directory.exists()


def test_download_routes_wait_for_deferred_map_storage(setup_download):
    from aiohttp import web

    from meshchatnext.src.backend.http.routes.map import register_map_routes

    download, _, _ = setup_download
    owner = SimpleNamespace(map_manager=None)
    routes = web.RouteTableDef()
    register_map_routes(routes, owner)
    status = next(
        route.handler
        for route in routes
        if route.handler.__name__ == "regional_download_status"
    )
    start = next(
        route.handler
        for route in routes
        if route.handler.__name__ == "start_regional_download"
    )
    assert asyncio.run(status(None)).status == 503
    assert asyncio.run(start(None)).status == 503
    owner.map_manager = download.manager
    response = asyncio.run(status(None))
    assert response.status == 200
    assert json.loads(response.body)["status"] == "idle"
    assert owner.regional_map_download.task is None


def test_download_route_respects_privacy_mode(setup_download):
    from aiohttp import web

    from meshchatnext.src.backend.http.routes.map import register_map_routes

    download, directory, _ = setup_download
    download.manager.config.privacy_mode_enabled.set(True)
    owner = SimpleNamespace(map_manager=download.manager)
    routes = web.RouteTableDef()
    register_map_routes(routes, owner)
    start = next(
        route.handler
        for route in routes
        if route.handler.__name__ == "start_regional_download"
    )
    assert asyncio.run(start(None)).status == 403
    assert not directory.exists()
