# SPDX-License-Identifier: MIT
"""Debug-only identity/API/recovery probe. No messages or identity replacement."""

import asyncio
import json
import secrets
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from meshchatnext.src.backend.meshcore_http import register_meshcore_routes
from meshchatnext.src.backend.meshcore_identity import decrypt_backup
from meshchatnext.src.backend.meshcore_service import MeshCoreService


async def _ready(service):
    deadline = asyncio.get_running_loop().time() + 40
    while not service.status()["connected"]:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("Selected MeshCore radio did not recover")
        await asyncio.sleep(0.2)


async def _probe(context, target):
    from java import jclass
    from usb4a.usb import set_context

    set_context(context.getApplicationContext())
    log = jclass("android.util.Log")
    folder = Path(str(context.getFilesDir())) / "meshcore-service-test"
    recovery = Path(str(context.getFilesDir())) / "meshcore-name-restore.json"
    if await asyncio.to_thread(recovery.exists):
        raise RuntimeError("An unresolved name recovery snapshot exists")
    service = MeshCoreService(folder, poll_interval=0.5, retry_max=4)
    owner = SimpleNamespace(meshcore_service=service)
    routes = web.RouteTableDef()
    register_meshcore_routes(routes, owner)
    app = web.Application()
    app.add_routes(routes)
    baseline = None
    settings = None
    result = {}
    await service.start()
    try:
        async with TestClient(TestServer(app)) as api:
            response = await api.post(
                "/api/v1/meshcore/connect", json={"kind": "ble", "target": target}
            )
            if response.status != 200:
                raise AssertionError(
                    "Internal API could not connect selected MeshCore radio"
                )
            baseline = await service.call("session", "read_identity")
            settings = await service.call("session", "read_settings")
            await asyncio.to_thread(recovery.write_text, json.dumps(baseline))
            response = await api.post(
                "/api/v1/meshcore/name",
                json={"name": "HK test " + secrets.token_hex(3)},
            )
            if response.status != 200:
                raise AssertionError("Name update did not verify")
            result["name_round_trip"] = True
            password = secrets.token_urlsafe(32)
            response = await api.post(
                "/api/v1/meshcore/backup",
                json={
                    "password": password,
                    "expected_public_key": baseline["public_key"],
                },
            )
            if response.status == 409:
                result["backup"] = "firmware_disabled"
            elif response.status == 200:
                backup = (await response.json())["result"]
                public, _ = await asyncio.to_thread(decrypt_backup, backup, password)
                if public != baseline["public_key"]:
                    raise AssertionError("Backup identity mismatch")
                # A same-identity restore is intentionally a verified no-op:
                # this probe never imports a replacement private key.
                response = await api.post(
                    "/api/v1/meshcore/restore",
                    json={
                        "backup": backup,
                        "password": password,
                        "expected_current_public_key": public,
                    },
                )
                if response.status != 200:
                    raise AssertionError("Same-identity backup restore check failed")
                result["backup"] = "encrypted_round_trip"
            else:
                raise AssertionError("Identity backup failed")
            await service.call("session", "set_name", baseline["name"])
            if await service.call("session", "read_identity") != baseline:
                raise AssertionError("Original name not restored")
            await asyncio.to_thread(recovery.unlink)
            log.i("MeshCoreServiceTest", "phase=identity_passed")
            previous = service.session
            await previous._connection.disconnect()
            await _ready(service)
            if service.session is previous:
                raise AssertionError("Recovery reused the old session")
            result["transport_loss_recovered"] = True
            await service.close()
            service = MeshCoreService(folder, poll_interval=0.5, retry_max=4)
            owner.meshcore_service = service
            await service.start()
            await _ready(service)
            result["service_restart_recovered"] = True
            if (
                await service.call("session", "read_identity") != baseline
                or await service.call("session", "read_settings") != settings
            ):
                raise AssertionError("Recovery changed radio identity or settings")
            await service.disconnect()
            await asyncio.sleep(1)
            if service.status()["connected"] or service.status()["selected"]:
                raise AssertionError("Explicit disconnect unexpectedly reconnected")
            result.update(
                manual_disconnect_stopped_recovery=True,
                identity_restored=True,
                settings_unchanged=True,
                status="ok",
            )
    finally:
        try:
            if baseline is not None and await asyncio.to_thread(recovery.exists):
                if not service.status()["connected"]:
                    await service.connect("ble", target)
                actual = await service.call("session", "read_identity")
                if actual["public_key"] != baseline["public_key"]:
                    raise AssertionError(
                        "Identity changed; name recovery snapshot retained"
                    )
                await service.call("session", "set_name", baseline["name"])
                if await service.call("session", "read_identity") != baseline:
                    raise AssertionError("Original identity name could not be verified")
                await asyncio.to_thread(recovery.unlink)
        finally:
            await service.close()
    return result


def probe(context, target):
    return json.dumps(asyncio.run(_probe(context, target)))
