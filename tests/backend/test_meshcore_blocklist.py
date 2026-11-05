# SPDX-License-Identifier: 0BSD
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from aiohttp import web

from meshchatnext.src.backend.meshcore_blocklist import (
    active_blocklist,
    blocks_meshcore_message,
)
from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from meshchatnext.src.backend.message_blocklist import normalize_message_blocklist

OWNER = "a1" * 32
PEER = "b2" * 32
ROOM = "c3" * 32
CHANNEL = "d4" * 32


def rules(scope="everyone", **extra):
    return normalize_message_blocklist(
        {"scope": scope, "entries": [{"text": "spam phrase"}], **extra}
    )


def make_store(tmp_path, provider):
    store = MeshCoreStore(tmp_path / "history.sqlite", message_blocklist=provider)
    store.replace_contacts(
        OWNER,
        {
            PEER: {"public_key": PEER, "adv_name": "Alice", "type": 1},
            ROOM: {"public_key": ROOM, "adv_name": "Room", "type": 3},
        },
    )
    store.replace_channels(
        OWNER, [{"slot": 0, "channel_id": CHANNEL, "name": "Public", "kind": "public"}]
    )
    return store


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("direct", {"pubkey_prefix": PEER[:12], "txt_type": 0, "text": "SPAM PHRASE"}),
        (
            "direct",
            {
                "pubkey_prefix": ROOM[:12],
                "txt_type": 2,
                "signature": PEER[:8],
                "text": "spam phrase",
            },
        ),
        ("channel", {"channel_idx": 0, "text": "Alice: spam phrase"}),
    ],
)
def test_filters_before_history_unreads_and_notifications(tmp_path, kind, payload):
    store = make_store(tmp_path, lambda: rules())
    assert store.receive(OWNER, kind, {**payload, "sender_timestamp": 123}) is None
    assert store.history(OWNER) == []
    assert store.channel_history(OWNER, CHANNEL) == []
    assert store.ui_snapshot(OWNER, "account")["conversations"] == []
    # Nonmatching posts still pass and produce normal notification metadata.
    assert (
        store.receive(
            OWNER, kind, {**payload, "text": "Alice: hello", "sender_timestamp": 124}
        )
        is not None
    )


def test_live_settings_disable_and_changes_do_not_require_reconnect(tmp_path):
    settings = rules()
    store = make_store(tmp_path, lambda: settings)
    packet = {"pubkey_prefix": PEER[:12], "text": "spam phrase", "txt_type": 0}
    assert store.receive(OWNER, "direct", packet) is None
    settings = None
    assert store.receive(OWNER, "direct", packet) is not None
    settings = rules()
    assert store.receive(OWNER, "direct", {**packet, "sender_timestamp": 2}) is None
    assert len(store.history(OWNER, PEER)) == 1


def test_scope_never_exempts_room_or_channel_posts_using_spoofable_names(tmp_path):
    store = make_store(tmp_path, lambda: rules("non_contacts"))
    direct = {"pubkey_prefix": PEER[:12], "txt_type": 0, "text": "spam phrase"}
    assert store.receive(OWNER, "direct", direct) is not None
    assert (
        store.receive(
            OWNER,
            "direct",
            {
                **direct,
                "pubkey_prefix": ROOM[:12],
                "txt_type": 2,
                "signature": PEER[:8],
            },
        )
        is None
    )
    assert (
        store.receive(
            OWNER, "channel", {"channel_idx": 0, "text": "Alice: spam phrase"}
        )
        is None
    )
    # A blocked participant does not ban the room server or another participant.
    assert (
        store.receive(
            OWNER,
            "direct",
            {
                "pubkey_prefix": ROOM[:12],
                "txt_type": 2,
                "signature": "ff" * 4,
                "text": "hello",
            },
        )
        is not None
    )
    assert store.contacts(OWNER)[0]["active"] == 1


def test_contacts_only_and_owner_isolation(tmp_path):
    store = make_store(tmp_path, lambda: rules("contacts"))
    packet = {"pubkey_prefix": PEER[:12], "txt_type": 0, "text": "spam phrase"}
    assert store.receive(OWNER, "direct", packet) is None
    assert store.receive("ee" * 32, "direct", packet) is not None
    assert (
        store.receive(
            OWNER, "channel", {"channel_idx": 0, "text": "Alice: spam phrase"}
        )
        is not None
    )


def test_shared_regex_and_combined_targets():
    policy = rules(
        match_peer_fields=True, entries=[{"text": "spam|alice", "match_mode": "regex"}]
    )
    contacts = [{"peer": PEER, "name": "Alice", "active": 1}]
    assert blocks_meshcore_message(
        policy, "direct", {"pubkey_prefix": PEER[:12], "text": "SPAM"}, contacts
    )
    assert not blocks_meshcore_message(
        policy, "direct", {"pubkey_prefix": PEER[:12], "text": "hello"}, contacts
    )
    assert not blocks_meshcore_message(
        policy, "channel", {"text": "Bob: spam"}, contacts
    )
    assert blocks_meshcore_message(policy, "channel", {"text": "Alice: spam"}, contacts)


def test_disabled_entries_empty_lists_and_non_chat_payloads():
    packet = {"pubkey_prefix": PEER[:12], "text": "spam phrase"}
    assert not blocks_meshcore_message(rules(entries=[]), "direct", packet, [])
    assert not blocks_meshcore_message(
        rules(entries=[{"text": "spam phrase", "enabled": False}]), "direct", packet, []
    )
    assert not blocks_meshcore_message(rules(), "direct", {**packet, "txt_type": 1}, [])
    assert not blocks_meshcore_message(rules(), "channel_data", packet, [])
    assert not blocks_meshcore_message(rules(), "direct", {"text": b"spam phrase"}, [])


def test_provider_tracks_active_account_and_enable_switch():
    enabled = SimpleNamespace(value=True)
    config = SimpleNamespace(
        message_blocklist_enabled=SimpleNamespace(get=lambda: enabled.value),
        message_blocklist_json=SimpleNamespace(get=lambda: json.dumps(rules())),
    )
    app = SimpleNamespace(current_context=SimpleNamespace(config=config))
    assert active_blocklist(app)["entries"]
    enabled.value = False
    assert active_blocklist(app) is None
    enabled.value = True
    app.current_context = None
    assert active_blocklist(app) is None


@pytest.mark.asyncio
async def test_lifecycle_installs_policy_on_real_store(tmp_path):
    from meshchatnext.src.backend.meshcore_http import install_meshcore_lifecycle

    created = []

    class Runtime:
        def __init__(self, folder, **kwargs):
            created.append(kwargs["store_factory"](tmp_path / "wired.sqlite"))

        async def start(self):
            pass

    config = SimpleNamespace(
        message_blocklist_enabled=SimpleNamespace(get=lambda: True),
        message_blocklist_json=SimpleNamespace(get=lambda: json.dumps(rules())),
    )
    owner = SimpleNamespace(
        storage_dir=str(tmp_path), current_context=SimpleNamespace(config=config)
    )
    app = web.Application()
    install_meshcore_lifecycle(app, owner)
    with (
        patch(
            "meshchatnext.src.backend.meshcore_http.importlib.util.find_spec",
            return_value=object(),
        ),
        patch("meshchatnext.src.backend.meshcore_http.MeshCoreFleet", Runtime),
    ):
        await app.on_startup[-1](app)
    assert created[0].receive(OWNER, "direct", {"text": "spam phrase"}) is None
    assert created[0].history(OWNER) == []


@pytest.mark.asyncio
async def test_receive_worker_drains_filtered_packets_without_alerts(tmp_path):
    from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
    from tests.backend.test_meshcore_messaging import Session, Types, event

    store = make_store(tmp_path, lambda: rules())
    session = Session()
    messenger = MeshCoreMessaging(session, store, event_types=Types)
    await messenger.open()
    alerts = []
    messenger.on_message = alerts.append
    session._client.incoming.extend(
        [
            event(
                Types.CONTACT_MSG_RECV,
                {"pubkey_prefix": PEER[:12], "txt_type": 0, "text": "spam phrase"},
            ),
            event(
                Types.CONTACT_MSG_RECV,
                {
                    "pubkey_prefix": ROOM[:12],
                    "txt_type": 2,
                    "signature": PEER[:8],
                    "text": "spam phrase",
                },
            ),
            event(
                Types.CHANNEL_MSG_RECV, {"channel_idx": 0, "text": "Alice: spam phrase"}
            ),
        ]
    )
    try:
        for _ in range(3):
            assert await messenger._fetch_message() is True
        assert await messenger._fetch_message() is False
        assert alerts == []
        assert store.history(messenger.owner) == []
        assert store.channel_history(messenger.owner, CHANNEL) == []
    finally:
        await messenger.close()
