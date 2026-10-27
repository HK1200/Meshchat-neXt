# SPDX-License-Identifier: MIT
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from meshchatnext.src.backend.meshcore_gpsd import gpsd_fix, gpsd_fixes

NOW = 1793084400
BASE = {
    "class": "TPV",
    "mode": 3,
    "lat": 1.0,
    "lon": 2.0,
    "epx": 3,
    "epy": 4,
    "time": datetime.fromtimestamp(NOW, UTC).isoformat(),
}


def test_gpsd_requires_complete_fresh_accurate_receiver_fix():
    assert gpsd_fix(BASE, now=NOW) == {
        "latitude": 1.0,
        "longitude": 2.0,
        "accuracy": 5,
        "timestamp": NOW * 1000,
    }
    assert gpsd_fix({**BASE, "eph": 8}, now=NOW)["accuracy"] == 8
    assert gpsd_fix(BASE, now=NOW + 31) is None
    assert gpsd_fix({"class": "VERSION"}, now=NOW) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": True},
        {"mode": 1},
        {"lat": float("nan")},
        {"lon": 181},
        {"epx": None, "epy": None},
        {"epx": 300},
        {"time": "2026-01-01T00:00:00"},
        {"time": "bad"},
    ],
)
def test_unusable_gpsd_data_never_becomes_a_position(changes):
    assert gpsd_fix({**BASE, **changes}, now=NOW) is None


@pytest.mark.asyncio
async def test_gpsd_watch_is_local_only_and_cancel_closes_own_connection(monkeypatch):
    import json
    import time

    reader = asyncio.StreamReader(limit=8192)
    report = {
        **BASE,
        "time": datetime.fromtimestamp(time.time(), UTC).isoformat(),
    }
    reader.feed_data((json.dumps(report) + "\n").encode())
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
    connector = AsyncMock(return_value=(reader, writer))
    stream = gpsd_fixes(connector=connector)
    fix = await anext(stream)
    assert fix["accuracy"] == 5
    connector.assert_awaited_once_with("127.0.0.1", 2947, limit=8192)
    writer.write.assert_called_once_with(b'?WATCH={"enable":true,"json":true};\n')
    await stream.aclose()
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_receiver_session_closes_and_revokes_only_its_own_consent():
    from meshchatnext.src.backend.meshcore_gpsd import GpsdBeaconSession

    closed = asyncio.Event()
    sent = asyncio.Event()
    consent = Mock(token="explicit")

    async def position(*args, **kwargs):
        sent.set()
        return {"state": "submitted"}

    consent.position = position

    async def provider():
        try:
            yield {
                "latitude": 1,
                "longitude": 2,
                "accuracy": 5,
                "timestamp": NOW * 1000,
            }
            await asyncio.Event().wait()
        finally:
            closed.set()

    session = GpsdBeaconSession(consent, provider=provider)
    await session.start("explicit", 15)
    await asyncio.wait_for(sent.wait(), 1)
    consent.token = "new-consent"
    await session.stop()
    assert closed.is_set()
    consent.stop.assert_not_called()


@pytest.mark.asyncio
async def test_receiver_session_failure_is_redacted_and_ends_consent():
    from meshchatnext.src.backend.meshcore_gpsd import GpsdBeaconSession

    consent = Mock(token="explicit")

    async def provider():
        raise RuntimeError("sensitive receiver details")
        yield

    session = GpsdBeaconSession(consent, provider=provider)
    with pytest.raises(ValueError):
        await session.start("other", 15)
    with pytest.raises(ValueError):
        await session.start("explicit", True)
    await session.start("explicit", 15)
    await session.task
    consent.stop.assert_called_once()
    assert "sensitive" not in session.error


@pytest.mark.asyncio
async def test_tactical_linux_start_stop_and_invalid_platform(monkeypatch):
    from types import SimpleNamespace

    from meshchatnext.src.backend import meshcore_tactical as module
    from meshchatnext.src.backend.meshcore_beacons import BeaconConsent

    tactical = SimpleNamespace(config={"enabled": True, "channel_id": "c" * 64})
    tactical.beacons = BeaconConsent(tactical)
    tactical.gpsd_beacons = Mock(
        stop=AsyncMock(), start=AsyncMock(), error=None, task=None
    )
    monkeypatch.setattr(module, "transport_platform", lambda: "linux")
    result = await module.MeshCoreTactical.beacon_start(
        tactical, 60, "c" * 64, None, source="gpsd", duration_minutes=15
    )
    tactical.gpsd_beacons.start.assert_awaited_once_with(result["token"], 15)
    with pytest.raises(ValueError):
        await module.MeshCoreTactical.beacon_stop(tactical, token="stale")
    assert tactical.beacons.token == result["token"]
    await module.MeshCoreTactical.beacon_stop(tactical, token=result["token"])
    assert tactical.beacons.token is None
    monkeypatch.setattr(module, "transport_platform", lambda: "android")
    with pytest.raises(ValueError):
        await module.MeshCoreTactical.beacon_start(
            tactical, 60, "c" * 64, None, source="gpsd"
        )
    # The existing Android/manual token flow remains available.
    assert (await module.MeshCoreTactical.beacon_start(tactical, 60, "c" * 64, None))[
        "token"
    ]


@pytest.mark.asyncio
async def test_receiver_duration_expires_without_a_fix_and_releases_watch():
    from meshchatnext.src.backend.meshcore_gpsd import GpsdBeaconSession

    closed = asyncio.Event()
    consent = Mock(token="explicit")

    async def provider():
        try:
            await asyncio.Event().wait()
            yield
        finally:
            closed.set()

    session = GpsdBeaconSession(consent, provider=provider)
    await asyncio.wait_for(session._run("explicit", 0.01), 1)
    assert closed.is_set()
    consent.stop.assert_called_once()
    assert session.error is None
