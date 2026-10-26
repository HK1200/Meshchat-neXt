# SPDX-License-Identifier: MIT
"""Discovery keeps subscriptions and database descriptors bounded; no radio traffic."""

import asyncio
import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from meshchatnext.src.backend.meshcore_nodes import MeshCoreNodes
from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_store import MeshCoreStore


def test_database_initialization_error_always_closes_connection(tmp_path, monkeypatch):
    store = MeshCoreStore(tmp_path / "meshcore.db")
    connection = Mock()
    connection.execute.side_effect = sqlite3.OperationalError("initialization failed")
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: connection)
    with pytest.raises(sqlite3.OperationalError):
        with store._connect():
            pytest.fail("An uninitialized connection must not be yielded")
    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_repeated_discovery_keeps_database_fds_and_subscriptions_bounded(
    tmp_path,
):
    if not os.path.isdir("/proc/self/fd"):
        pytest.skip("Descriptor inventory requires procfs")
    owner, peer = "a1" * 32, "b2" * 32
    store = MeshCoreStore(tmp_path / "meshcore.db")
    store.bind(owner, "Test client")
    subscriptions = []

    def subscribe(kind, callback):
        subscriptions.append(callback)
        return SimpleNamespace(unsubscribe=lambda: subscriptions.remove(callback))

    async def send(**kwargs):
        for callback in list(subscriptions):
            callback(
                SimpleNamespace(
                    payload={
                        "tag": kwargs["tag"].to_bytes(4, "little").hex(),
                        "node_type": 2,
                        "pubkey": peer,
                    }
                )
            )
        return SimpleNamespace(payload={}, is_error=lambda: False)

    client = SimpleNamespace(
        subscribe=subscribe, commands=SimpleNamespace(send_node_discover_req=send)
    )
    session = SimpleNamespace(
        _client=client, _lock=asyncio.Lock(), _payload=MeshCoreSession._payload
    )
    messages = SimpleNamespace(
        session=session,
        store=store,
        owner=owner,
        _check=lambda: None,
        _types=SimpleNamespace(DISCOVER_RESPONSE="discover"),
    )
    nodes = MeshCoreNodes(messages)
    nodes.DISCOVERY_WINDOW = nodes.DISCOVERY_COOLDOWN = 0
    await nodes.discover()  # Warm the thread pool before measuring.
    baseline = len(os.listdir("/proc/self/fd"))
    for _ in range(128):
        result = await nodes.discover()
        assert result["nodes"] == [{"peer": peer, "kind": 2}]
        assert subscriptions == []
    assert len(os.listdir("/proc/self/fd")) <= baseline + 4
