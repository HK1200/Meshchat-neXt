# SPDX-License-Identifier: 0BSD

"""Contract tests: aiohttp routes in meshchat.py vs checked-in manifest. Frontend /api/v1 usage."""

import os
from pathlib import Path

import pytest

from tests.backend.http_api_contract_helpers import (
    extract_frontend_api_paths,
    extract_meshchat_http_routes,
    load_route_fixture,
    path_matches_aiohttp_route,
    write_route_fixture,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MESHCHAT_PY = _REPO_ROOT / "meshchatnext" / "meshchat.py"
_FRONTEND_ROOT = _REPO_ROOT / "meshchatnext" / "src" / "frontend"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "http_api_routes.json"


def test_meshchat_http_routes_match_fixture():
    live = extract_meshchat_http_routes(_MESHCHAT_PY)
    if os.environ.get("UPDATE_HTTP_API_ROUTES") == "1":
        write_route_fixture(_FIXTURE, live)
        pytest.skip(
            "UPDATE_HTTP_API_ROUTES=1: fixture updated; re-run without the env var",
        )
    expected = load_route_fixture(_FIXTURE)
    assert live == expected, (
        "HTTP route list drifted. If you added or renamed routes, run: "
        "UPDATE_HTTP_API_ROUTES=1 uv run pytest tests/backend/test_http_api_contract.py -k "
        "meshchat_http_routes_match_fixture"
    )


def test_path_matches_aiohttp_wildcard_asset_route():
    route = "/api/v1/plugins/{plugin_id}/asset/{asset_path:.*}"
    assert path_matches_aiohttp_route(route, "/api/v1/plugins/a/asset/")
    assert path_matches_aiohttp_route(
        route,
        "/api/v1/plugins/a/asset/frontend/main.js",
    )
    assert not path_matches_aiohttp_route(route, "/api/v1/plugins/a/other")


def test_frontend_api_paths_exist_on_backend():
    backend_paths = [r["path"] for r in extract_meshchat_http_routes(_MESHCHAT_PY)]
    frontend_paths = extract_frontend_api_paths(_FRONTEND_ROOT)
    missing = [
        fp
        for fp in sorted(frontend_paths)
        if not any(path_matches_aiohttp_route(br, fp) for br in backend_paths)
    ]
    assert not missing, f"Frontend references unknown HTTP paths: {missing}"


def test_route_inventory_ignores_only_mutation_copies(tmp_path):
    package = tmp_path / "meshchatnext"
    package.mkdir()
    main = package / "meshchat.py"
    main.write_text("# source entrypoint\n")
    routes = package / "src/backend/http/routes"
    routes.mkdir(parents=True)
    source = routes / "fixture.py"
    source.write_text(
        "from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated\n"
        "def register(routes):\n"
        "    @routes.get('/api/v1/real')\n"
        "    async def real(request): pass\n"
        "def x_register__mutmut_orig(routes):\n"
        "    @routes.get('/api/v1/real')\n"
        "    async def real(request): pass\n"
        "def x_register__mutmut_1(routes):\n"
        "    @routes.get('/api/v1/XXrealXX')\n"
        "    async def real(request): pass\n"
    )
    assert extract_meshchat_http_routes(main) == [
        {"method": "GET", "path": "/api/v1/real"}
    ]
    source.write_text(
        source.read_text().replace(
            "@routes.get('/api/v1/real')", "@routes.get('/api/v1/changed')", 1
        )
    )
    assert extract_meshchat_http_routes(main) == [
        {"method": "GET", "path": "/api/v1/changed"}
    ]


def test_real_source_named_like_mutant_is_still_checked(tmp_path):
    package = tmp_path / "meshchatnext"
    package.mkdir()
    main = package / "meshchat.py"
    main.write_text(
        "def x_custom__mutmut_1(routes):\n    @routes.get('/api/v1/real')\n    async def real(request): pass\n"
    )
    assert extract_meshchat_http_routes(main) == [
        {"method": "GET", "path": "/api/v1/real"}
    ]
