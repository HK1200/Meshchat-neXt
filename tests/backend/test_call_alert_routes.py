# SPDX-License-Identifier: 0BSD
import json
from types import SimpleNamespace

import pytest
import RNS
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from meshchatnext.src.backend import call_alerts
from meshchatnext.src.backend.call_wake import destination_hash
from meshchatnext.src.backend.database import Database
from meshchatnext.src.backend.http.routes import call_alerts as call_alert_routes

PEER = RNS.Identity()
ADDRESS = destination_hash("lxmf.delivery", PEER.get_public_key())
OTHER_PEER = RNS.Identity()
OTHER = destination_hash("lxmf.delivery", OTHER_PEER.get_public_key())
ROUTE = {
    "provider": "https://alerts.example.invalid",
    "audience": "private test",
    "public_key": PEER.get_public_key().hex(),
}


@pytest.fixture
def profile(tmp_path):
    database = Database(str(tmp_path / "database.sqlite3"))
    database.initialize()
    database.contacts.add_contact("Family recipient", "c3" * 16, lxmf_address=ADDRESS)
    row = database.contacts.get_contacts()[0]
    context = SimpleNamespace(database=database, storage_path=str(tmp_path))
    app = SimpleNamespace(current_context=context)
    yield app, row["id"], tmp_path
    database.provider.close_all()


def client_for(app):
    routes = web.RouteTableDef()
    call_alert_routes.register_call_alert_routes(routes, app)
    server = web.Application()
    server.add_routes(routes)
    return TestClient(TestServer(server))


async def test_route_controls_save_only_explicit_contact_and_revoke_without_provider_requests(
    profile, monkeypatch
):
    app, contact_id, folder = profile

    def unexpected(*_):
        raise AssertionError("Editing consent must not contact any alert provider")

    monkeypatch.setattr(call_alerts, "post", unexpected)
    path = f"/api/v1/telephone/contacts/{contact_id}/call-alert-route"
    async with client_for(app) as client:
        initial = await (await client.get(path)).json()
        assert initial["route"] is None
        assert not (folder / "call-alert-routes.json").exists()
        response = await client.post(path, json={"route": ROUTE})
        body = await response.json()
        assert response.status == 200 and body["route"] == ROUTE
        assert call_alerts.route_for(folder, ADDRESS).public_key == ROUTE["public_key"]
        assert (await (await client.get(path)).json())["route"] == ROUTE
        if __import__("os").name == "posix":
            assert (folder / "call-alert-routes.json").stat().st_mode & 0o077 == 0
        assert (await client.delete(path)).status == 200
        assert call_alerts.route_for(folder, ADDRESS) is None
        assert (
            app.current_context.database.contacts.get_contact(contact_id)["name"]
            == "Family recipient"
        )


@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"route": {**ROUTE, "secret": "not accepted"}},
        {"route": {**ROUTE, "audience": "x" + " " * 128}},
        {"route": {**ROUTE, "provider": "http://example.invalid"}},
        {"route": {**ROUTE, "provider": "https://example.invalid:invalid"}},
        {"route": {**ROUTE, "provider": "https://example.invalid/other"}},
    ],
)
async def test_invalid_form_preserves_existing_route(profile, body):
    app, contact_id, folder = profile
    call_alerts.save_route(folder, ADDRESS, ROUTE)
    before = (folder / "call-alert-routes.json").read_bytes()
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/call-alert-route", json=body
        )
        assert response.status == 400
        error = await response.json()
        assert error["code"] == "invalid_call_alert_route"
        assert error["error"] == error["message"]
    assert (folder / "call-alert-routes.json").read_bytes() == before


async def test_identity_switch_during_request_cannot_write_either_profile(
    profile, monkeypatch, tmp_path
):
    app, contact_id, folder = profile
    previous = app.current_context
    new_folder = tmp_path / "other-identity"
    new_folder.mkdir()
    replacement = SimpleNamespace(
        database=previous.database, storage_path=str(new_folder)
    )
    original = call_alert_routes.read_json_limited

    async def switch(request, **kwargs):
        body = await original(request, **kwargs)
        app.current_context = replacement
        return body

    monkeypatch.setattr(call_alert_routes, "read_json_limited", switch)
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/call-alert-route",
            json={"route": ROUTE},
        )
        assert response.status == 409
    assert not (folder / "call-alert-routes.json").exists()
    assert not (new_folder / "call-alert-routes.json").exists()


async def test_contact_address_change_during_request_cannot_assign_stale_consent(
    profile, monkeypatch
):
    app, contact_id, folder = profile
    original = call_alert_routes.read_json_limited

    async def change(request, **kwargs):
        body = await original(request, **kwargs)
        app.current_context.database.contacts.update_contact(
            contact_id, lxmf_address=OTHER
        )
        return body

    monkeypatch.setattr(call_alert_routes, "read_json_limited", change)
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/call-alert-route",
            json={"route": ROUTE},
        )
        assert response.status == 409
    assert not (folder / "call-alert-routes.json").exists()


async def test_save_failure_keeps_old_route_and_cleans_only_owned_temporary_file(
    profile, monkeypatch
):
    app, contact_id, folder = profile
    call_alerts.save_route(folder, ADDRESS, ROUTE)
    before = (folder / "call-alert-routes.json").read_bytes()

    def fail(*_):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(call_alerts.os, "replace", fail)
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/call-alert-route",
            json={"route": {**ROUTE, "audience": "changed"}},
        )
        assert response.status == 503
    assert (folder / "call-alert-routes.json").read_bytes() == before
    assert not list(folder.glob(".call-alerts-*"))


def test_separate_contact_writes_and_revocation_preserve_other_routes(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    keys = [RNS.Identity().get_public_key().hex() for _ in range(8)]
    entries = {
        destination_hash("lxmf.delivery", bytes.fromhex(key)): {
            **ROUTE,
            "public_key": key,
        }
        for key in keys
    }
    addresses = list(entries)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(
            pool.map(
                lambda peer: call_alerts.save_route(tmp_path, peer, entries[peer]),
                addresses,
            )
        )
    assert len(json.loads((tmp_path / "call-alert-routes.json").read_text())) == len(
        addresses
    )
    call_alerts.save_route(tmp_path, addresses[0], None)
    assert call_alerts.route_for(tmp_path, addresses[0]) is None
    assert all(
        call_alerts.route_for(tmp_path, peer) is not None for peer in addresses[1:]
    )


@pytest.mark.parametrize(
    "operation", ["delete", "change_address", "failed_delete", "failed_change"]
)
async def test_contact_lifecycle_revokes_alerts_before_forgetting_the_old_address(
    profile, monkeypatch, operation
):
    from meshchatnext.src.backend.http.routes.contacts import register_contacts_routes

    app, contact_id, folder = profile
    app.database = app.current_context.database
    app.sync_telephone_call_policy = lambda: None
    call_alerts.save_route(folder, ADDRESS, ROUTE)
    call_alerts.save_route(
        folder,
        OTHER,
        {
            **ROUTE,
            "audience": "keep another recipient",
            "public_key": OTHER_PEER.get_public_key().hex(),
        },
    )
    if operation.startswith("failed"):

        def fail(*_):
            raise OSError("synthetic revoke failure")

        monkeypatch.setattr(call_alerts.os, "replace", fail)
    routes = web.RouteTableDef()
    register_contacts_routes(routes, app)
    server = web.Application()
    server.add_routes(routes)
    async with TestClient(TestServer(server)) as client:
        path = f"/api/v1/telephone/contacts/{contact_id}"
        response = (
            await client.delete(path)
            if operation.endswith("delete")
            else await client.patch(path, json={"lxmf_address": "d4" * 16})
        )
        if operation.startswith("failed"):
            assert response.status == 503
            assert (
                app.database.contacts.get_contact(contact_id)["lxmf_address"] == ADDRESS
            )
            assert call_alerts.route_for(folder, ADDRESS) is not None
        else:
            assert response.status == 200
            assert call_alerts.route_for(folder, ADDRESS) is None
            if operation == "delete":
                assert app.database.contacts.get_contact(contact_id) is None
            else:
                assert (
                    app.database.contacts.get_contact(contact_id)["lxmf_address"]
                    == "d4" * 16
                )
    assert call_alerts.route_for(folder, OTHER).audience == "keep another recipient"


@pytest.mark.parametrize("identifier", ["0", "-1", "not-a-number", "9" * 100])
async def test_invalid_contact_identifier_cannot_reach_storage(profile, identifier):
    app, _, folder = profile
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{identifier}/call-alert-route",
            json={"route": ROUTE},
        )
        assert response.status == 400
    assert not (folder / "call-alert-routes.json").exists()


async def test_only_a_cryptographically_bound_recalled_key_is_exposed(
    profile, monkeypatch
):
    app, contact_id, _ = profile
    path = f"/api/v1/telephone/contacts/{contact_id}/call-alert-route"
    async with client_for(app) as client:
        monkeypatch.setattr(RNS.Identity, "recall", lambda *_: PEER)
        assert (await (await client.get(path)).json())[
            "public_key"
        ] == PEER.get_public_key().hex()
        wrong = RNS.Identity()
        monkeypatch.setattr(RNS.Identity, "recall", lambda *_: wrong)
        assert (await (await client.get(path)).json())["public_key"] is None


async def test_blocked_contact_cannot_save_or_read_a_call_route(profile):
    app, contact_id, folder = profile
    app.is_destination_blocked = lambda *_a, **_kw: True
    path = f"/api/v1/telephone/contacts/{contact_id}/call-alert-route"
    async with client_for(app) as client:
        assert (await client.post(path, json={"route": ROUTE})).status == 403
        assert (await client.get(path)).status == 403
    assert not (folder / "call-alert-routes.json").exists()


def test_banishing_contact_removes_its_call_alert_route_without_other_settings(profile):
    from unittest.mock import MagicMock

    from meshchatnext.meshchat import ReticulumMeshChat

    app, contact_id, folder = profile
    context = app.current_context
    context.message_router = None
    context.telephone_manager = SimpleNamespace(call_alerts=MagicMock())
    call_alerts.save_route(folder, ADDRESS, ROUTE)
    regular = folder / "unrelated-setting.json"
    regular.write_text('{"preserve":true}')
    fixture = SimpleNamespace(
        current_context=context,
        _resolve_contact_for_hash=lambda *_a, **_kw: dict(
            context.database.contacts.get_contact(contact_id)
        ),
    )
    ReticulumMeshChat._delete_contact_and_stamp_ticket(
        fixture, ADDRESS, context=context
    )
    assert call_alerts.route_for(folder, ADDRESS) is None
    assert context.database.contacts.get_contact(contact_id) is None
    context.telephone_manager.call_alerts.refresh_contacts.assert_called_once()
    assert regular.read_text() == '{"preserve":true}'
