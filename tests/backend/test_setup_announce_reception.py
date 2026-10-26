# SPDX-License-Identifier: 0BSD
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from aiohttp import web

from meshchatnext.src.backend.http.routes.interfaces import register_interfaces_routes


def handler_for(interfaces, write=True):
    app = SimpleNamespace(
        _sync_interfaces_from_disk=Mock(),
        _get_interfaces_snapshot=lambda: copy.deepcopy(interfaces),
        _get_interfaces_section=lambda: interfaces,
        _write_reticulum_config=Mock(return_value=write),
    )
    routes = web.RouteTableDef()
    register_interfaces_routes(routes, app)
    handler = next(
        route.handler
        for route in routes
        if route.path.endswith("/reticulum/interfaces/receive-announces")
    )
    return handler, app


@pytest.mark.asyncio
async def test_reception_changes_only_bootstrap_flag_and_preserves_boundaries_and_secrets():
    rows = {
        "TCP": {
            "type": "TCPClientInterface",
            "interface_enabled": "yes",
            "bootstrap_only": "yes",
            "target_host": "host.test",
            "target_port": "4242",
            "passphrase": "fixture-secret",
            "mode": "boundary",
        },
        "Backbone": {
            "type": "BackboneInterface",
            "remote": "host.test",
            "bootstrap_only": "true",
            "mode": "internal",
        },
        "Disabled": {
            "type": "TCPClientInterface",
            "enabled": False,
            "bootstrap_only": "yes",
        },
        "Listener": {"type": "BackboneInterface", "bootstrap_only": "yes"},
        "RNode": {
            "type": "RNodeInterface",
            "frequency": 915000000,
            "bootstrap_only": "yes",
        },
        "I2P": {"type": "I2PInterface", "mode": "boundary"},
    }
    before = copy.deepcopy(rows)
    handler, app = handler_for(rows)
    response = await handler(None)
    assert response.status == 200
    assert json.loads(response.text) == {
        "changed": ["TCP", "Backbone"],
        "reload_required": True,
    }
    before["TCP"]["bootstrap_only"] = "no"
    before["Backbone"]["bootstrap_only"] = "no"
    assert rows == before
    assert app._write_reticulum_config.call_count == 1
    response = await handler(None)
    assert json.loads(response.text)["changed"] == []
    assert app._write_reticulum_config.call_count == 1


@pytest.mark.asyncio
async def test_reception_surfaces_write_failure_and_supplies_complete_rollback_snapshot():
    rows = {
        "TCP": {
            "type": "TCPClientInterface",
            "bootstrap_only": "yes",
            "network_name": "private",
            "passphrase": "fixture",
        }
    }
    before = copy.deepcopy(rows)
    handler, app = handler_for(rows, write=False)
    response = await handler(None)
    assert response.status == 500
    assert app._write_reticulum_config.call_args.kwargs["rollback_interfaces"] == before
