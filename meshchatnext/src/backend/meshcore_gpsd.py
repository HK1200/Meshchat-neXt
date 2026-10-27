# SPDX-License-Identifier: MIT
"""Optional localhost GPSD fixes; no automatic acquisition or network geolocation.

Protocol reference: https://gpsd.io/gpsd_json.html . Error estimates are receiver
estimates, not a guaranteed confidence interval. Incomplete/stale fixes are never
sent. Opening the provider belongs to an explicit location-sharing consent flow.
"""

import asyncio
import contextlib
import json
import math
import time
from datetime import datetime
from typing import TypeGuard


def _finite_number(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and type(value) in (int, float)
        and math.isfinite(value)
    )


def gpsd_fix(report, *, now=None):
    if (
        not isinstance(report, dict)
        or report.get("class") != "TPV"
        or type(report.get("mode")) is not int
        or report["mode"] not in (2, 3)
    ):
        return None
    latitude, longitude = report.get("lat"), report.get("lon")
    if not _finite_number(latitude) or not _finite_number(longitude):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    estimates = []
    eph = report.get("eph")
    if _finite_number(eph) and eph >= 0:
        estimates.append(eph)
    x, y = report.get("epx"), report.get("epy")
    if _finite_number(x) and _finite_number(y) and x >= 0 and y >= 0:
        estimates.append(math.hypot(x, y))
    if not estimates or max(estimates) > 255:
        return None
    stamp = report.get("time")
    if not isinstance(stamp, str) or len(stamp) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        timestamp = parsed.timestamp()
    except (ValueError, OverflowError):
        return None
    if abs((time.time() if now is None else now) - timestamp) > 30:
        return None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": max(estimates),
        "timestamp": timestamp * 1000,
    }


async def gpsd_fixes(*, connector=asyncio.open_connection):
    """Open only the local GPS service, and close only this client's watch."""
    reader, writer = await asyncio.wait_for(connector("127.0.0.1", 2947, limit=8192), 5)
    try:
        writer.write(b'?WATCH={"enable":true,"json":true};\n')
        await asyncio.wait_for(writer.drain(), 3)
        while True:
            line = await asyncio.wait_for(reader.readline(), 30)
            if not line:
                raise ConnectionError("Local GPS service disconnected")
            if len(line) > 8192:
                raise ValueError("Local GPS response is too large")
            report = json.loads(line)
            fix = gpsd_fix(report)
            if fix is not None:
                yield fix
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), 2)


class GpsdBeaconSession:
    """Explicit, bounded receiver session; never persists or renews consent.

    The caller must obtain BeaconConsent first. This worker cannot create consent
    or change a team channel. It owns only its task and local GPS watch socket.
    """

    def __init__(self, consent, *, provider=gpsd_fixes):
        self.consent = consent
        self.provider = provider
        self.task = None
        self.error = None

    async def start(self, token, duration_minutes):
        if type(duration_minutes) is not int or duration_minutes not in (15, 30, 60):
            raise ValueError("Choose a supported location sharing duration")
        if not isinstance(token, str) or token != self.consent.token:
            raise ValueError("Location sharing requires current explicit consent")
        await self.stop()
        # stop() may have ended this same token's previous session.
        if token != self.consent.token:
            raise ValueError("Start a new location sharing consent session")
        self.error = None
        self.task = asyncio.create_task(self._run(token, duration_minutes * 60))

    async def stop(self):
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self, token, duration):
        stream = self.provider()
        try:
            async with asyncio.timeout(duration):
                async for fix in stream:
                    if self.consent.token != token:
                        break
                    result = await self.consent.position(token, **fix)
                    if result.get("state") not in ("submitted", "waiting"):
                        break
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            pass
        except Exception:
            # Receiver details and coordinates never enter status or logs.
            self.error = "Local GPS sharing stopped; check the receiver and start again"
        finally:
            try:
                await stream.aclose()
            finally:
                # An old task must never revoke a newer consent session.
                if self.consent.token == token:
                    self.consent.stop()
