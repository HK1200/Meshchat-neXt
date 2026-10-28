# SPDX-License-Identifier: MIT
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from meshchatnext.src.backend.meshcore_http import register_meshcore_routes


class Service:
    def __init__(self):
        self.calls = []

    def status(self):
        return {"available": True, "connected": True}

    async def connect(self, **kwargs):
        self.calls.append(("connect", kwargs))
        return self.status()

    async def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"public_key": "aa" * 32, "name": "radio"}


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = Service()
        self.owner = SimpleNamespace(meshcore_service=self.service)
        routes = web.RouteTableDef()
        register_meshcore_routes(routes, self.owner)
        app = web.Application()
        app.add_routes(routes)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_tak_enrollment_and_packages_require_owner_and_known_fields(self):
        cases = {
            "tak-connect": {"host": "localhost", "port": 8089, "auto_protocol": True},
            "tak-enroll": {
                "host": "localhost",
                "port": 8446,
                "username": "synthetic",
                "password": "test-only",
            },
            "tak-package-search": {"keywords": "synthetic"},
            "tak-package-download": {"digest": "ab" * 32},
            "tak-package-upload": {
                "zip_base64": "dGVzdA==",
                "name": "test.zip",
                "private": True,
            },
        }
        for endpoint, options in cases.items():
            with self.subTest(endpoint=endpoint):
                before = len(self.service.calls)
                for body in (
                    options,
                    {**options, "expected_owner": None},
                    {**options, "expected_owner": "a1" * 32, "unexpected": True},
                ):
                    response = await self.client.post(
                        "/api/v1/meshcore/" + endpoint, json=body
                    )
                    self.assertEqual(response.status, 400)
                self.assertEqual(len(self.service.calls), before)
                response = await self.client.post(
                    "/api/v1/meshcore/" + endpoint,
                    json={**options, "expected_owner": "a1" * 32},
                )
                self.assertEqual(response.status, 200)
                self.assertEqual(self.service.calls[-1][1]["expected_owner"], "a1" * 32)

    async def test_privacy_mode_blocks_tak_network_actions_but_allows_disconnect(self):
        self.owner.config = SimpleNamespace(
            privacy_mode_enabled=SimpleNamespace(get=lambda: True)
        )
        for endpoint, options in {
            "tak-connect": {"host": "localhost", "port": 8089},
            "tak-enroll": {
                "host": "localhost",
                "port": 8446,
                "username": "synthetic",
                "password": "test-only",
            },
            "tak-send": {"record": {"latitude": 0, "longitude": 0}},
            "tak-package-search": {},
            "tak-package-download": {"digest": "ab" * 32},
            "tak-package-upload": {"zip_base64": "dGVzdA==", "name": "test.zip"},
        }.items():
            response = await self.client.post(
                "/api/v1/meshcore/" + endpoint,
                json={**options, "expected_owner": "a1" * 32},
            )
            self.assertEqual(response.status, 403)
        self.assertEqual(self.service.calls, [])
        response = await self.client.post(
            "/api/v1/meshcore/tak-disconnect", json={"expected_owner": "a1" * 32}
        )
        self.assertEqual(response.status, 200)

    async def test_discovery_requires_identity_guard_and_rejects_arbitrary_filters(
        self,
    ):
        for body in (
            {},
            {"expected_owner": None},
            {"expected_owner": "a1" * 32, "filter": 255},
        ):
            response = await self.client.post(
                "/api/v1/meshcore/node-discover", json=body
            )
            self.assertEqual(response.status, 400)
        self.assertEqual(self.service.calls, [])
        response = await self.client.post(
            "/api/v1/meshcore/node-discover", json={"expected_owner": "a1" * 32}
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            self.service.calls, [(("nodes", "discover"), {"expected_owner": "a1" * 32})]
        )

    async def test_channel_ui_mutations_require_identity_guard_and_keep_scope(self):
        self.owner.identity = SimpleNamespace(hash=bytes.fromhex("b2" * 16))

        async def ui(account, **kwargs):
            self.service.calls.append((account, kwargs))
            return {"channel_banishments": []}

        self.service.ui = ui
        body = {"channel": "c3" * 32, "message": "message-id"}
        response = await self.client.post("/api/v1/meshcore/channel-banish", json=body)
        self.assertEqual(response.status, 400)
        self.assertEqual(self.service.calls, [])
        response = await self.client.post(
            "/api/v1/meshcore/channel-banish",
            json={**body, "expected_owner": "a1" * 32},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            self.service.calls[0],
            (
                "b2" * 16,
                {
                    "ui_action": "channel-banish",
                    "ui_body": body,
                    "expected_owner": "a1" * 32,
                },
            ),
        )

    async def test_channel_order_requires_identity_and_uses_local_preferences(self):
        self.owner.identity = SimpleNamespace(hash=bytes.fromhex("b2" * 16))

        async def ui(account, **kwargs):
            self.service.calls.append((account, kwargs))
            return {"channels": []}

        self.service.ui = ui
        body = {"channels": ["c3" * 32]}
        response = await self.client.post("/api/v1/meshcore/channel-order", json=body)
        self.assertEqual(response.status, 400)
        self.assertEqual(self.service.calls, [])
        response = await self.client.post(
            "/api/v1/meshcore/channel-order", json={**body, "expected_owner": "a1" * 32}
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            self.service.calls,
            [
                (
                    "b2" * 16,
                    {
                        "ui_action": "channel-order",
                        "ui_body": body,
                        "expected_owner": "a1" * 32,
                    },
                )
            ],
        )

    async def test_radio2_writes_require_explicit_identity_and_use_session_guard(self):
        response = await self.client.post(
            "/api/v1/meshcore/radio2", json={"enabled": True}
        )
        self.assertEqual(response.status, 400)
        response = await self.client.post(
            "/api/v1/meshcore/radio2", json={"enabled": True, "expected_owner": None}
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(self.service.calls, [])
        response = await self.client.post(
            "/api/v1/meshcore/radio2",
            json={"enabled": True, "expected_owner": "a1" * 32},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            self.service.calls,
            [
                (
                    ("session", "apply_radio2"),
                    {"enabled": True, "expected_owner": "a1" * 32},
                )
            ],
        )

    async def test_usb_discovery_and_permission_never_connect_service(self):
        devices = [
            {"path": "/dev/bus/usb/001/002", "name": "T1000-E", "permission": False}
        ]
        with patch(
            "meshchatnext.src.backend.meshcore_transport.attached_usb_devices",
            return_value=devices,
        ):
            response = await self.client.get("/api/v1/meshcore/usb-devices")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["result"], devices)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        with patch(
            "meshchatnext.src.backend.meshcore_transport.permit_usb_device",
            return_value={"granted": False, "requested": True},
        ) as permit:
            response = await self.client.post(
                "/api/v1/meshcore/usb-permission", json={"path": devices[0]["path"]}
            )
            self.assertEqual(response.status, 200)
            permit.assert_called_once_with(devices[0]["path"])
            response = await self.client.post(
                "/api/v1/meshcore/usb-permission",
                json={"path": devices[0]["path"], "all": True},
            )
            self.assertEqual(response.status, 400)
            permit.assert_called_once()
        self.assertEqual(self.service.calls, [])

    @patch(
        "meshchatnext.src.backend.meshcore_transport.transport_platform",
        return_value="android",
    )
    async def test_paired_bluetooth_listing_does_not_connect_service(self, _platform):
        devices = [{"name": "MeshCore", "address": "AA:BB:CC:DD:EE:FF"}]
        with patch(
            "meshchatnext.src.backend.meshcore_transport.paired_ble_devices",
            return_value=devices,
        ):
            response = await self.client.get("/api/v1/meshcore/bluetooth-devices")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["result"], devices)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.service.calls, [])

    async def test_name_passes_selected_owner_guard_to_service(self):
        body = {"name": "Trail radio", "expected_owner": "a1" * 32}
        response = await self.client.post("/api/v1/meshcore/name", json=body)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls, [(("session", "set_name"), body)])

    async def test_settings_passes_selected_owner_guard_to_service(self):
        body = {"sf": 10, "expected_owner": "a1" * 32}
        response = await self.client.post("/api/v1/meshcore/settings", json=body)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls, [(("session", "apply_settings"), body)])

    async def test_config_import_routes_are_explicit_and_results_are_read_only(self):
        self.service.config_preview = AsyncMock(return_value={"sections": ["name"]})
        self.service.config_apply = AsyncMock(return_value={"state": "complete"})
        self.service.config_result = AsyncMock(return_value={"state": "not_found"})
        response = await self.client.post(
            "/api/v1/meshcore/config-preview", json={"text": '{"name":"Test"}'}
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.service.config_apply.assert_not_awaited()
        response = await self.client.get(
            "/api/v1/meshcore/config-result?owner="
            + "a1" * 32
            + "&request_id=reference"
        )
        self.assertEqual(response.status, 200)
        self.service.config_result.assert_awaited_once_with("a1" * 32, "reference")
        response = await self.client.get("/api/v1/meshcore/config-apply")
        self.assertEqual(response.status, 404)
        self.service.config_apply.assert_not_awaited()

    async def test_status_and_identity_are_no_store_and_explicit(self):
        response = await self.client.get("/api/v1/meshcore/identity")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.service.calls, [(("session", "read_identity"), {})])
        response = await self.client.get("/api/v1/meshcore/backup")
        self.assertEqual(response.status, 404)

    async def test_invalid_or_oversized_body_never_calls_service(self):
        for body in (
            [],
            {"kind": "ble"},
            {"kind": "ble", "target": "chosen", "password": "not-allowed"},
        ):
            response = await self.client.post("/api/v1/meshcore/connect", json=body)
            self.assertEqual(response.status, 400)
        response = await self.client.post("/api/v1/meshcore/connect", data="x" * 17000)
        self.assertEqual(response.status, 413)
        self.assertEqual(self.service.calls, [])

    async def test_unavailable_build_does_not_construct_radio(self):
        self.owner.meshcore_service = None
        response = await self.client.get("/api/v1/meshcore/status")
        self.assertFalse((await response.json())["available"])
        response = await self.client.post("/api/v1/meshcore/connect", json={})
        self.assertEqual(response.status, 503)

    async def test_errors_never_echo_credentials_or_upstream_error_text(self):
        async def fail(*args, **kwargs):
            raise ValueError("private-key-and-password")

        self.service.call = fail
        response = await self.client.post(
            "/api/v1/meshcore/backup",
            json={"password": "my-password", "expected_public_key": "aa" * 32},
        )
        self.assertEqual(response.status, 400)
        self.assertNotIn("password", await response.text())
        self.assertNotIn("private-key", await response.text())


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_and_csrf_still_guard_meshcore_operations(self):
        import os
        from unittest.mock import patch

        from meshchatnext.src.backend.http import middleware

        service = Service()
        owner = SimpleNamespace(
            meshcore_service=service,
            current_context=SimpleNamespace(running=True),
            auth_enabled=True,
            identity=SimpleNamespace(hash=bytes.fromhex("aa" * 16)),
            _auth_session_epoch_valid=lambda session: True,
        )
        routes = web.RouteTableDef()
        register_meshcore_routes(routes, owner)
        app = web.Application(
            middlewares=[
                middleware.create_auth_middleware(owner),
                middleware.create_csrf_middleware(owner),
            ]
        )
        app.add_routes(routes)

        async def unauthenticated(request):
            return {}

        async def authenticated(request):
            return {"authenticated": True, "identity_hash": "aa" * 16}

        async with TestClient(TestServer(app)) as client:
            with patch.object(middleware, "get_session", unauthenticated):
                response = await client.get("/api/v1/meshcore/identity")
                self.assertEqual(response.status, 401)
            with (
                patch.dict(os.environ, {"MESHCHAT_DISABLE_CSRF": "0"}),
                patch.object(middleware, "get_session", authenticated),
                patch.object(middleware, "validate_csrf_header", return_value=False),
            ):
                response = await client.post(
                    "/api/v1/meshcore/backup",
                    json={
                        "password": "not-sent-to-service",
                        "expected_public_key": "aa" * 32,
                    },
                )
                self.assertEqual(response.status, 403)
            self.assertEqual(service.calls, [])


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_build_is_idle_and_shutdown_failure_does_not_block_other_cleanup(
        self,
    ):
        import tempfile
        from unittest.mock import patch

        from meshchatnext.src.backend.meshcore_http import install_meshcore_lifecycle

        events = []

        class Runtime:
            def __init__(self, folder, **kwargs):
                self.folder = folder

            async def start(self):
                events.append("start")

            async def close(self):
                events.append("meshcore_stop")
                raise ConnectionError("cleanup failed")

        async def other_stop(app):
            events.append("rns_stop")

        with tempfile.TemporaryDirectory() as folder:
            owner = SimpleNamespace(storage_dir=folder)
            app = web.Application()
            install_meshcore_lifecycle(app, owner)
            app.on_shutdown.append(other_stop)
            with (
                patch(
                    "meshchatnext.src.backend.meshcore_http.importlib.util.find_spec",
                    return_value=object(),
                ),
                patch("meshchatnext.src.backend.meshcore_http.MeshCoreFleet", Runtime),
            ):
                async with TestClient(TestServer(app)):
                    self.assertEqual(events, ["start"])
            self.assertEqual(events, ["start", "meshcore_stop", "rns_stop"])
            owner = SimpleNamespace(storage_dir=folder)
            app = web.Application()
            install_meshcore_lifecycle(app, owner)
            with patch(
                "meshchatnext.src.backend.meshcore_http.importlib.util.find_spec",
                return_value=None,
            ):
                async with TestClient(TestServer(app)):
                    self.assertFalse(hasattr(owner, "meshcore_service"))
