# SPDX-License-Identifier: 0BSD
"""Private sender/provider tests. No radio, Apple credential or public HTTP."""

import json
import os
import sqlite3
import threading
import uuid
from types import SimpleNamespace

import pytest
import RNS

from meshchatnext.src.backend import call_alerts
from meshchatnext.src.backend.call_wake import (
    destination_hash,
    signed_bytes,
    voice_hash,
)


@pytest.fixture
def profile(tmp_path):
    own, peer = RNS.Identity(), RNS.Identity()
    address = destination_hash("lxmf.delivery", peer.get_public_key())
    entry = {
        "provider": "https://example.invalid",
        "audience": "private-calls",
        "public_key": peer.get_public_key().hex(),
    }
    contact = {address: {"id": 1, "name": "Private name"}}
    return SimpleNamespace(
        folder=tmp_path,
        own=own,
        peer=peer,
        address=address,
        entry=entry,
        contacts=contact,
    )


def call(p, **changes):
    fields = {
        "id": uuid.uuid4().hex,
        "peer": voice_hash(p.peer.get_public_key()),
        "requested_peer": p.address,
        "incoming": False,
    }
    return SimpleNamespace(**{**fields, **changes})


def finish(manager):
    handles = tuple(manager.pending.values())
    manager.close()
    for handle in handles:
        if handle.thread:
            handle.thread.join(timeout=6)
            assert not handle.thread.is_alive()


def test_route_changes_are_private_atomic_and_independent(profile):
    p = profile
    first = call_alerts.save_route(p.folder, p.address, p.entry)
    assert first.voice == voice_hash(p.peer.get_public_key())
    other = RNS.Identity()
    address = destination_hash("lxmf.delivery", other.get_public_key())
    entry = {**p.entry, "public_key": other.get_public_key().hex()}
    call_alerts.save_route(p.folder, address, entry)
    path = p.folder / "call-alert-routes.json"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    assert p.own.get_private_key().hex() not in path.read_text()
    assert "Private name" not in path.read_text()
    call_alerts.save_route(p.folder, p.address, None)
    assert call_alerts.route_for(p.folder, p.address) is None
    assert call_alerts.route_for(p.folder, address) is not None


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "http://example.invalid"),
        ("provider", "https://user:pass@example.invalid"),
        ("provider", "https://example.invalid/path"),
        ("provider", "https://example.invalid?secret=x"),
        ("provider", "https://example.invalid#fragment"),
        ("provider", "https://example.invalid:0"),
        ("audience", "bad/name"),
        ("audience", "private-calls\n"),
        ("public_key", "00" * 64),
    ],
)
def test_route_validation_preserves_existing_settings(profile, field, value):
    p = profile
    call_alerts.save_route(p.folder, p.address, p.entry)
    original = (p.folder / "call-alert-routes.json").read_bytes()
    with pytest.raises(ValueError):
        call_alerts.save_route(p.folder, p.address, {**p.entry, field: value})
    assert (p.folder / "call-alert-routes.json").read_bytes() == original


def test_failed_atomic_replace_and_symlinks_never_overwrite_other_data(
    profile, monkeypatch
):
    p = profile
    call_alerts.save_route(p.folder, p.address, p.entry)
    path = p.folder / "call-alert-routes.json"
    original = path.read_bytes()

    def fail(*_):
        raise OSError("private fixture")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail)
        with pytest.raises((OSError, ValueError)):
            call_alerts.save_route(p.folder, p.address, None)
    assert path.read_bytes() == original
    assert not list(p.folder.glob(".call-alerts-*"))
    if os.name != "posix":
        return
    target = p.folder / "preserved.json"
    path.rename(target)
    path.symlink_to(target)
    assert call_alerts.route_for(p.folder, p.address) is None
    with pytest.raises((OSError, ValueError)):
        call_alerts.save_route(p.folder, p.address, p.entry)
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "condition", ["no_route", "incoming", "not_saved", "blocked", "wrong_peer"]
)
def test_unapproved_or_unconfigured_calls_never_send_hints(profile, condition):
    p = profile
    requests = []
    if condition != "no_route":
        call_alerts.save_route(p.folder, p.address, p.entry)
    if condition == "not_saved":
        p.contacts.clear()
    manager = call_alerts.CallAlerts(
        p.folder,
        p.own,
        lambda: p.contacts,
        lambda _: condition == "blocked",
        sender=lambda *args: requests.append(args),
        wall_clock=lambda: 1000,
    )
    outgoing = call(p, incoming=condition == "incoming")
    if condition == "wrong_peer":
        outgoing.peer = outgoing.requested_peer = "00" * 16
    try:
        manager.started(outgoing)
    finally:
        finish(manager)
    assert requests == []


@pytest.mark.parametrize("lost_ack", [False, True, "exception"])
def test_signed_wake_and_ordered_cancel_survive_lost_provider_ack(profile, lost_ack):
    p = profile
    call_alerts.save_route(p.folder, p.address, p.entry)
    operations = []
    received = threading.Event()

    def post(route, operation, raw):
        packet = json.loads(raw)
        assert set(packet) == {"recipient", "call", "sender", "issued", "signature"}
        assert p.own.validate(
            bytes.fromhex(packet["signature"]),
            signed_bytes(packet, route.audience, cancel=operation == "call-cancel"),
        )
        assert packet["recipient"] == voice_hash(p.peer.get_public_key())
        assert packet["sender"] == p.own.get_public_key().hex()
        operations.append((operation, packet))
        if operation == "call-alert":
            received.set()
            if lost_ack == "exception":
                raise OSError("Response lost after acceptance")
            return 503 if lost_ack else 204
        return 204

    manager = call_alerts.CallAlerts(
        p.folder,
        p.own,
        lambda: p.contacts,
        lambda _: False,
        sender=post,
        wall_clock=lambda: 1000,
    )
    outgoing = call(p)
    try:
        manager.started(outgoing)
        assert received.wait(5)
        manager.started(outgoing)
    finally:
        finish(manager)
    assert [kind for kind, _ in operations] == ["call-alert", "call-cancel"]
    assert operations[0][1]["call"] == operations[1][1]["call"] == outgoing.id
    assert p.own.get_private_key().hex() not in json.dumps(operations)
    assert "Private name" not in json.dumps(operations)


def test_route_removal_while_post_is_in_flight_cancels_the_original_attempt(profile):
    p = profile
    call_alerts.save_route(p.folder, p.address, p.entry)
    entered = threading.Event()
    release = threading.Event()
    operations = []

    def post(route, operation, raw):
        operations.append(operation)
        if operation == "call-alert":
            entered.set()
            assert release.wait(5)
        return 204

    manager = call_alerts.CallAlerts(
        p.folder,
        p.own,
        lambda: p.contacts,
        lambda _: False,
        sender=post,
        wall_clock=lambda: 1000,
    )
    outgoing = call(p)
    try:
        manager.started(outgoing)
        assert entered.wait(5)
        call_alerts.save_route(p.folder, p.address, None)
        release.set()
        manager.pending[outgoing.id].thread.join(timeout=5)
    finally:
        release.set()
        finish(manager)
    assert operations == ["call-alert", "call-cancel"]


def test_transport_rejects_http_and_unknown_operations_without_network(profile):
    p = profile
    route = call_alerts.Route(
        "http://127.0.0.1", "private-calls", p.peer.get_public_key().hex()
    )
    assert call_alerts.post(route, "call-alert", b"{}") == 400
    assert call_alerts.post(route, "unrelated", b"{}") == 400


def test_hint_workers_never_access_the_app_loops_sqlite_connection(profile):
    p = profile
    call_alerts.save_route(p.folder, p.address, p.entry)
    database = sqlite3.connect(":memory:")
    database.execute("CREATE TABLE contacts (address TEXT, id INTEGER)")
    database.execute("INSERT INTO contacts VALUES (?, 1)", (p.address,))

    def contacts():
        return {
            row[0]: {"id": row[1]}
            for row in database.execute("SELECT address, id FROM contacts")
        }

    received, cancelled = threading.Event(), threading.Event()
    operations = []

    def post(route, operation, raw):
        operations.append(operation)
        (received if operation == "call-alert" else cancelled).set()
        return 204

    manager = call_alerts.CallAlerts(
        p.folder, p.own, contacts, lambda _: False, sender=post, wall_clock=lambda: 1000
    )
    try:
        manager.started(call(p))
        assert received.wait(5), (
            "A worker must not silently drop its hint by reading main-thread SQLite"
        )
        database.execute("DELETE FROM contacts")
        manager.refresh_contacts()
        assert cancelled.wait(5), (
            "Removing approval must cancel even before the voice call ends"
        )
    finally:
        finish(manager)
        database.close()
    assert operations == ["call-alert", "call-cancel"]
