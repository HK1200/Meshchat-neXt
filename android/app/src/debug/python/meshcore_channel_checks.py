# SPDX-License-Identifier: MIT
"""Opt-in temporary channel fixtures, with durable recovery and no secret logging."""

import asyncio
import hashlib
import json
import secrets
import uuid
from pathlib import Path

from meshchatnext.src.backend.meshcore_channels import MeshCoreChannels
from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_store import MeshCoreStore


class Fixture:
    def __init__(self, context, address):
        self.context = context
        self.address = address
        folder = Path(str(context.getFilesDir()))
        suffix = address.replace(":", "").lower()
        self.recovery = folder / f"meshcore-channel-recovery-{suffix}.json"
        self.database = folder / f"meshcore-channel-test-{suffix}.sqlite"
        self.session = MeshCoreSession()
        self.messages = None
        self.channels = None
        self.baseline = None
        self.settings = None
        self.slot = None
        self.test_ids = set()
        self.identity = None

    async def open(self):
        if await asyncio.to_thread(self.recovery.exists):
            raise RuntimeError("An unresolved channel recovery snapshot exists")
        await self.session.connect("ble", self.address, context=self.context)
        store = await asyncio.to_thread(MeshCoreStore, self.database)
        self.messages = MeshCoreMessaging(self.session, store)
        self.identity = await self.messages.open()
        self.channels = MeshCoreChannels(self.messages)
        self.baseline = await self.channels.refresh()
        self.settings = await self.session.read_settings()
        free = [
            row["slot"]
            for row in self.baseline
            if row["slot"] != 0 and row["kind"] == "empty"
        ]
        if not free:
            raise RuntimeError(
                "Channel test requires an empty non-default slot on each radio"
            )
        self.slot = free[0]
        # This fixture only uses an originally empty slot: no existing keys are
        # exported to disk and no existing configured channel is overwritten.
        await asyncio.to_thread(
            self.recovery.write_text,
            json.dumps(
                {
                    "owner": self.identity["public_key"],
                    "slot": self.slot,
                    "original_name": "",
                    "original_key_hex": "00" * 16,
                }
            ),
        )

    async def add(self, name, key=None):
        actual_key = hashlib.sha256(name.encode()).digest()[:16] if key is None else key
        self.test_ids.add(hashlib.sha256(actual_key).hexdigest())
        row = (
            await self.channels.add_public(name)
            if key is None
            else await self.channels.add_private(name, key=key)
        )
        if row["slot"] != self.slot:
            raise AssertionError("Test fixture did not use the reserved empty slot")
        self.test_ids.add(row["channel_id"])
        return row

    async def clear(self):
        if self.slot is None:
            return
        rows = await self.channels.refresh()
        row = rows[self.slot]
        if row["kind"] != "empty":
            if row["channel_id"] not in self.test_ids:
                raise AssertionError(
                    "Test slot changed unexpectedly; recovery snapshot retained"
                )
            await self.channels.remove(self.slot, expected_channel_id=row["channel_id"])
        if await self.channels.refresh() != self.baseline:
            raise AssertionError("Original channel configuration could not be verified")

    async def close(self):
        try:
            if self.channels is not None and self.baseline is not None:
                await self.clear()
                if (
                    self.settings is not None
                    and await self.session.read_settings() != self.settings
                ):
                    raise AssertionError("Channel test changed radio settings")
                if await asyncio.to_thread(self.recovery.exists):
                    await asyncio.to_thread(self.recovery.unlink)
        finally:
            if self.messages is not None:
                await self.messages.close()
            else:
                await self.session.disconnect()


async def _wait_for(fixture, identity, token):
    deadline = asyncio.get_running_loop().time() + 25
    while asyncio.get_running_loop().time() < deadline:
        rows = await fixture.channels.history(identity)
        if any(row["direction"] == "in" and token in row["text"] for row in rows):
            return
        await asyncio.sleep(0.5)
    raise AssertionError("Channel test packet did not arrive within the receive window")


async def _round_trip(context, target, peer):
    from java import jclass

    log = jclass("android.util.Log")
    fixtures = [Fixture(context, target), Fixture(context, peer)]
    result = {"public_round_trip": False, "private_round_trip": False}
    try:
        for fixture in fixtures:
            await fixture.open()
        first, second = fixtures
        if "testpeer" not in second.identity["name"].casefold():
            raise AssertionError("Selected peer does not identify as TestPeer")
        if first.identity["public_key"] == second.identity["public_key"]:
            raise AssertionError("Two distinct companion identities are required")
        for local, remote in ((first, second), (second, first)):
            contacts = await local.messages.sync_contacts()
            if not any(
                row["peer"] == remote.identity["public_key"] for row in contacts
            ):
                raise AssertionError(
                    "Selected radios do not match the mutually added test contacts"
                )
        for mode in ("public", "private"):
            token = uuid.uuid4().hex[:10]
            name = "#hk-test-" + token
            key = secrets.token_bytes(16) if mode == "private" else None
            channels = [await fixture.add(name, key) for fixture in fixtures]
            identity = channels[0]["channel_id"]
            if identity != channels[1]["channel_id"]:
                raise AssertionError("Test channel identities do not match")
            for fixture in fixtures:
                await fixture.messages.start_receiving()
            outgoing = await first.channels.send(
                channels[0]["slot"],
                "HK channel test " + token,
                expected_channel_id=identity,
                request_id=uuid.uuid4().hex,
            )
            if outgoing["state"] != "submitted":
                raise AssertionError("Companion did not accept test channel message")
            await _wait_for(second, identity, token)
            reply = token + "-reply"
            await second.channels.send(
                channels[1]["slot"],
                "HK channel reply " + reply,
                expected_channel_id=identity,
                request_id=uuid.uuid4().hex,
            )
            await _wait_for(first, identity, reply)
            for fixture in fixtures:
                reopened = await asyncio.to_thread(MeshCoreStore, fixture.database)
                rows = await asyncio.to_thread(
                    reopened.channel_history, fixture.messages.owner, identity
                )
                if not any(row["direction"] == "in" for row in rows):
                    raise AssertionError("Received channel history was not durable")
                await fixture.clear()
            result[mode + "_round_trip"] = True
            log.i("MeshCoreChannelsTest", "phase=" + mode + "_round_trip_passed")
    finally:
        errors = []
        for fixture in fixtures:
            try:
                await fixture.close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise RuntimeError(
                "Channel restoration failed; recovery snapshot retained"
            ) from None
    result.update(
        status="ok",
        channels_restored=True,
        settings_unchanged=True,
        history_persisted=True,
    )
    return result


def round_trip(context, target, peer):
    if not target or not peer or target.upper() == peer.upper():
        raise ValueError("Two distinct explicit BLE targets are required")
    return json.dumps(asyncio.run(_round_trip(context, target, peer)))
