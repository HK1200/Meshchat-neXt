# SPDX-License-Identifier: 0BSD
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend.meshcore_beacons import BeaconConsent


def consent():
    tactical = SimpleNamespace(
        config={"enabled": True, "channel_id": "c" * 64},
        send=AsyncMock(return_value={"state": "submitted"}),
    )
    return BeaconConsent(tactical), tactical


@pytest.mark.asyncio
async def test_consent_scope_rate_limit_and_stop():
    beacon, tactical = consent()
    token = beacon.start(60, "c" * 64, "test-region")["token"]
    args = {
        "token": token,
        "latitude": 0,
        "longitude": 0,
        "accuracy": 10,
        "timestamp": time.time() * 1000,
    }
    assert (await beacon.position(**args))["state"] == "submitted"
    assert (await beacon.position(**args))["state"] == "waiting"
    tactical.send.assert_awaited_once()
    assert tactical.send.call_args.kwargs["expected_scope"] == "test-region"
    beacon.stop()
    with pytest.raises(ValueError):
        await beacon.position(**args)


@pytest.mark.asyncio
async def test_stale_and_changed_channel_are_not_transmitted():
    beacon, tactical = consent()
    token = beacon.start(300, "c" * 64, None)["token"]
    with pytest.raises(ValueError):
        await beacon.position(token, 0, 0, 5, 0)
    tactical.config["channel_id"] = "d" * 64
    with pytest.raises(ValueError):
        await beacon.position(token, 0, 0, 5, time.time() * 1000)
    tactical.send.assert_not_awaited()
    assert beacon.token is None


@pytest.mark.asyncio
async def test_unknown_send_ends_consent_without_retry():
    beacon, tactical = consent()
    tactical.send.return_value = {"state": "unknown"}
    token = beacon.start(120, "c" * 64, None)["token"]
    await beacon.position(token, 0, 0, 5, time.time() * 1000)
    assert beacon.token is None


@pytest.mark.asyncio
async def test_old_native_stop_cannot_revoke_new_consent():
    from meshchatnext.src.backend.meshcore_tactical import MeshCoreTactical

    beacon, _ = consent()
    old = beacon.start(300, "c" * 64, None)["token"]
    new = beacon.start(300, "c" * 64, None)["token"]
    target = SimpleNamespace(beacons=beacon)
    with pytest.raises(ValueError):
        await MeshCoreTactical.beacon_stop(target, token=old)
    assert beacon.token == new
    await MeshCoreTactical.beacon_stop(target, token=new)
    assert beacon.token is None
