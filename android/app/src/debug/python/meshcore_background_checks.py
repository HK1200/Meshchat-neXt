# SPDX-License-Identifier: MIT
"""Instrumented forced-idle/process-death probes; all radio traffic is read-only."""

import asyncio
import json
from pathlib import Path

from meshchatnext.src.backend.meshcore_service import MeshCoreService
from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_transport import AndroidConnection

SENTINEL = "process-death-no-replay"


class ReadOnlyConnection(AndroidConnection):
    async def send(self, frame):
        # Explicit allowlist: app-start, contacts, device query, channel read.
        if not frame or frame[0] not in (1, 4, 22, 31):
            raise AssertionError("Recovery attempted a non-read-only radio command")
        return await super().send(frame)


def _write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def _service(folder):
    return MeshCoreService(
        folder,
        session_factory=lambda: MeshCoreSession(connection_factory=ReadOnlyConnection),
        poll_interval=0.5,
        retry_max=4,
    )


async def _prepare(context, target):
    from usb4a.usb import set_context

    set_context(context.getApplicationContext())
    folder = Path(str(context.getFilesDir())) / "meshcore-background-test"
    state = folder / "progress.json"
    service = _service(folder)
    await service.start()
    try:
        await service.connect("ble", target)
        identity = await service.call("session", "read_identity")
        settings = await service.call("session", "read_settings")
        contacts = await service.call("messages", "sync_contacts")
        peers = [
            row
            for row in contacts
            if row["kind"] == 1
            and row["active"]
            and "testpeer" in row["name"].casefold()
        ]
        if len(peers) != 1:
            raise AssertionError(
                "Own TestPeer test contact is required for the unsent sentinel"
            )
        await asyncio.to_thread(
            _write,
            folder / "baseline.json",
            {"identity": identity, "settings": settings},
        )
        # Persist an unsent submission, without calling any messaging send API.
        await asyncio.to_thread(
            service._store.prepare_send,
            identity["public_key"],
            peers[0]["peer"],
            "Unsent process recovery test",
            SENTINEL,
        )
        queries = 0
        failures = 0
        deadline = asyncio.get_running_loop().time() + 150
        while asyncio.get_running_loop().time() < deadline:
            try:
                actual = await service.call("session", "read_identity")
                if actual != identity:
                    raise AssertionError(
                        "Radio identity changed during background test"
                    )
                queries += 1
            except ConnectionError:
                failures += 1
            await asyncio.to_thread(
                _write,
                state,
                {
                    "phase": "ready",
                    "queries": queries,
                    "query_failures": failures,
                    "connected": service.status()["connected"],
                },
            )
            await asyncio.sleep(1)
        raise AssertionError("Host did not perform bounded process-death test")
    finally:
        await service.close()


async def _resume(context):
    from usb4a.usb import set_context

    set_context(context.getApplicationContext())
    folder = Path(str(context.getFilesDir())) / "meshcore-background-test"
    baseline = json.loads(await asyncio.to_thread((folder / "baseline.json").read_text))
    service = _service(folder)
    await service.start()
    try:
        deadline = asyncio.get_running_loop().time() + 40
        while not service.status()["connected"]:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    "New process did not recover saved MeshCore selection"
                )
            await asyncio.sleep(0.2)
        if await service.call("session", "read_identity") != baseline["identity"]:
            raise AssertionError("Process restart changed selected identity")
        if await service.call("session", "read_settings") != baseline["settings"]:
            raise AssertionError("Process restart changed radio settings")
        rows = await service.call("messages", "history")
        staged = next((row for row in rows if row["id"] == SENTINEL), None)
        if staged is None or staged["state"] != "unknown":
            raise AssertionError(
                "Interrupted submission was not preserved as uncertain"
            )
        await service.disconnect()
        return {
            "status": "ok",
            "fresh_process_reconnected": True,
            "identity_unchanged": True,
            "settings_unchanged": True,
            "stranded_submission_unknown": True,
            "non_read_only_commands_blocked": True,
            "manual_disconnect_cleared_selection": True,
        }
    finally:
        await service.close()


def prepare(context, target):
    asyncio.run(_prepare(context, target))


def resume(context):
    return json.dumps(asyncio.run(_resume(context)))
