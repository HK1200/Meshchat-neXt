# SPDX-License-Identifier: MIT
import asyncio
import unittest
from types import SimpleNamespace

from meshchatnext.src.backend.meshcore_session import MeshCoreSession


class FakeConnection:
    def __init__(self, kind, target, **kwargs):
        self.kind = kind
        self.target = target
        self.is_connected = False
        self.closes = 0

    async def disconnect(self):
        self.closes += 1
        self.is_connected = False


class FakeClient:
    def __init__(self, connection, *, fail_query=False, **kwargs):
        self.connection = connection
        self.fail_query = fail_query
        self.commands = self
        self.closed = False
        self.queries = 0

    @staticmethod
    def event(payload, error=False):
        return SimpleNamespace(payload=payload, is_error=lambda: error)

    async def connect(self):
        self.connection.is_connected = True
        return self.event({"name": "test", "private_key": "do-not-expose"})

    async def send_device_query(self):
        self.queries += 1
        return self.event({"model": "test"}, self.fail_query)

    async def disconnect(self):
        self.closed = True


class MeshCoreSessionTests(unittest.IsolatedAsyncioTestCase):
    def make(self, **options):
        clients = []

        def factory(connection, **kwargs):
            client = FakeClient(connection, **kwargs, **options)
            clients.append(client)
            return client

        return MeshCoreSession(
            connection_factory=FakeConnection, client_factory=factory
        ), clients

    async def test_no_connection_until_explicit_connect_and_status_has_no_secrets(self):
        session, clients = self.make()
        self.assertFalse(session.is_connected)
        self.assertEqual(clients, [])
        try:
            result = await session.connect("ble", "selected")
            self.assertEqual(
                result,
                {
                    "connected": True,
                    "transport": "ble",
                    "device_queried": True,
                    "identity_read": True,
                },
            )
            self.assertNotIn("private_key", str(result))
        finally:
            await session.disconnect()
        self.assertFalse(session.is_connected)
        self.assertTrue(clients[0].closed)
        self.assertGreaterEqual(clients[0].connection.closes, 1)

    async def test_failed_initial_query_closes_native_and_client(self):
        session, clients = self.make(fail_query=True)
        with self.assertRaises(ConnectionError):
            await session.connect("ble", "selected")
        self.assertTrue(clients[0].closed)
        self.assertGreaterEqual(clients[0].connection.closes, 1)
        self.assertFalse(session.status()["device_queried"])

    async def test_reconnect_replaces_client_and_cleans_previous_connection(self):
        session, clients = self.make()
        try:
            await session.connect("ble", "first")
            await session.connect("usb", "second")
            self.assertTrue(clients[0].closed)
            self.assertFalse(clients[0].connection.is_connected)
            self.assertTrue(clients[1].connection.is_connected)
            self.assertEqual(session.status()["transport"], "usb")
        finally:
            await session.disconnect()

    async def test_link_loss_prevents_queries_and_still_cleans_native_resources(self):
        session, clients = self.make()
        await session.connect("ble", "selected")
        clients[0].connection.is_connected = False
        with self.assertRaises(ConnectionError):
            await session.query_device()
        await session.disconnect()
        self.assertTrue(clients[0].closed)
        self.assertEqual(clients[0].queries, 1)
        self.assertGreaterEqual(clients[0].connection.closes, 1)

    async def test_two_session_lifecycles_are_independent(self):
        first, _ = self.make()
        second, clients = self.make()
        await asyncio.gather(first.connect("ble", "one"), second.connect("usb", "two"))
        try:
            await first.disconnect()
            self.assertTrue((await second.query_device())["connected"])
            self.assertFalse(clients[0].closed)
        finally:
            await second.disconnect()


class ClockTests(unittest.IsolatedAsyncioTestCase):
    async def test_clock_read_is_validated_and_never_sets_time(self):
        from unittest.mock import AsyncMock

        session = MeshCoreSession()
        event = SimpleNamespace(payload={"time": 123}, is_error=lambda: False)
        get_time = AsyncMock(return_value=event)
        session._client = SimpleNamespace(commands=SimpleNamespace(get_time=get_time))
        result = await session.read_clock()
        self.assertEqual(result["radio_time"], 123)
        self.assertEqual(result["offset_seconds"], 123 - result["phone_time"])
        get_time.assert_awaited_once()
        event.payload = {"time": True}
        with self.assertRaises(ConnectionError):
            await session.read_clock()
