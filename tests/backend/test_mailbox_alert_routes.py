# SPDX-License-Identifier: 0BSD
import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from meshchatnext.src.backend import mailbox_push
from meshchatnext.src.backend.database import Database
from meshchatnext.src.backend.http.routes import mailbox_alerts
from tests.backend.api_json_contract_schemas import assert_matches_schema
from tests.backend.http_api_response_schemas import MAILBOX_ALERT_ROUTE_SCHEMA

ADDRESS = "a1" * 16
OTHER = "a2" * 16
ROUTE = {
    "provider": "https://alerts.example.invalid",
    "audience": "private test",
    "relay": "b2" * 16,
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
    mailbox_alerts.register_mailbox_alert_routes(routes, app)
    server = web.Application()
    server.add_routes(routes)
    return TestClient(TestServer(server))


async def test_route_controls_save_only_explicit_contact_and_revoke_without_provider_requests(
    profile, monkeypatch
):
    app, contact_id, folder = profile

    def unexpected(*_):
        raise AssertionError("Editing consent must not contact any alert provider")

    monkeypatch.setattr(mailbox_push, "_post", unexpected)
    path = f"/api/v1/telephone/contacts/{contact_id}/mailbox-alert-route"
    async with client_for(app) as client:
        initial = await (await client.get(path)).json()
        assert initial == {"route": None}
        assert_matches_schema(initial, MAILBOX_ALERT_ROUTE_SCHEMA)
        assert not (folder / "mailbox-push-routes.json").exists()
        response = await client.post(path, json={"route": ROUTE})
        body = await response.json()
        assert response.status == 200 and body["route"] == ROUTE
        assert_matches_schema(body, MAILBOX_ALERT_ROUTE_SCHEMA)
        assert mailbox_push.route_for(folder, ADDRESS).relay == ROUTE["relay"]
        assert (await (await client.get(path)).json())["route"] == ROUTE
        if __import__("os").name == "posix":
            assert (folder / "mailbox-push-routes.json").stat().st_mode & 0o077 == 0
        assert (await client.delete(path)).status == 200
        assert mailbox_push.route_for(folder, ADDRESS) is None
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
    mailbox_push.save_route(folder, ADDRESS, ROUTE)
    before = (folder / "mailbox-push-routes.json").read_bytes()
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/mailbox-alert-route", json=body
        )
        assert response.status == 400
        error = await response.json()
        assert error["code"] == "invalid_mailbox_alert_route"
        assert error["error"] == error["message"]
    assert (folder / "mailbox-push-routes.json").read_bytes() == before


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
    original = mailbox_alerts.read_json_limited

    async def switch(request, **kwargs):
        body = await original(request, **kwargs)
        app.current_context = replacement
        return body

    monkeypatch.setattr(mailbox_alerts, "read_json_limited", switch)
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/mailbox-alert-route",
            json={"route": ROUTE},
        )
        assert response.status == 409
    assert not (folder / "mailbox-push-routes.json").exists()
    assert not (new_folder / "mailbox-push-routes.json").exists()


async def test_contact_address_change_during_request_cannot_assign_stale_consent(
    profile, monkeypatch
):
    app, contact_id, folder = profile
    original = mailbox_alerts.read_json_limited

    async def change(request, **kwargs):
        body = await original(request, **kwargs)
        app.current_context.database.contacts.update_contact(
            contact_id, lxmf_address=OTHER
        )
        return body

    monkeypatch.setattr(mailbox_alerts, "read_json_limited", change)
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/mailbox-alert-route",
            json={"route": ROUTE},
        )
        assert response.status == 409
    assert not (folder / "mailbox-push-routes.json").exists()


async def test_save_failure_keeps_old_route_and_cleans_only_owned_temporary_file(
    profile, monkeypatch
):
    app, contact_id, folder = profile
    mailbox_push.save_route(folder, ADDRESS, ROUTE)
    before = (folder / "mailbox-push-routes.json").read_bytes()

    def fail(*_):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(mailbox_push.os, "replace", fail)
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{contact_id}/mailbox-alert-route",
            json={"route": {**ROUTE, "audience": "changed"}},
        )
        assert response.status == 503
    assert (folder / "mailbox-push-routes.json").read_bytes() == before
    assert not list(folder.glob(".mailbox-alerts-*"))


def test_separate_contact_writes_and_revocation_preserve_other_routes(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    addresses = [index.to_bytes(16, "big").hex() for index in range(1, 9)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(
            pool.map(
                lambda peer: mailbox_push.save_route(tmp_path, peer, ROUTE), addresses
            )
        )
    assert len(json.loads((tmp_path / "mailbox-push-routes.json").read_text())) == len(
        addresses
    )
    mailbox_push.save_route(tmp_path, addresses[0], None)
    assert mailbox_push.route_for(tmp_path, addresses[0]) is None
    assert all(
        mailbox_push.route_for(tmp_path, peer) is not None for peer in addresses[1:]
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
    mailbox_push.save_route(folder, ADDRESS, ROUTE)
    mailbox_push.save_route(
        folder, OTHER, {**ROUTE, "audience": "keep another recipient"}
    )
    if operation.startswith("failed"):

        def fail(*_):
            raise OSError("synthetic revoke failure")

        monkeypatch.setattr(mailbox_push.os, "replace", fail)
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
            assert mailbox_push.route_for(folder, ADDRESS) is not None
        else:
            assert response.status == 200
            assert mailbox_push.route_for(folder, ADDRESS) is None
            if operation == "delete":
                assert app.database.contacts.get_contact(contact_id) is None
            else:
                assert (
                    app.database.contacts.get_contact(contact_id)["lxmf_address"]
                    == "d4" * 16
                )
    assert mailbox_push.route_for(folder, OTHER).audience == "keep another recipient"


@pytest.mark.parametrize("identifier", ["0", "-1", "not-a-number", "9" * 100])
async def test_invalid_contact_identifier_cannot_reach_storage(profile, identifier):
    app, _, folder = profile
    async with client_for(app) as client:
        response = await client.post(
            f"/api/v1/telephone/contacts/{identifier}/mailbox-alert-route",
            json={"route": ROUTE},
        )
        assert response.status == 400
    assert not (folder / "mailbox-push-routes.json").exists()
