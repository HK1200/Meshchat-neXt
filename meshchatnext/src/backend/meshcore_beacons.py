# SPDX-License-Identifier: 0BSD
"""Memory-only consent session for native Android team position beacons."""

from __future__ import annotations

import math
import secrets
import time
import uuid


class BeaconConsent:
    def __init__(self, tactical):
        self.tactical = tactical
        self.stop()

    def stop(self):
        self.token = None
        self.channel = None
        self.scope = None
        self.interval = 300
        self.last = -1e9
        return {"enabled": False}

    def start(self, interval, expected_channel_id, expected_scope):
        if type(interval) is not int or interval not in (60, 120, 300):
            raise ValueError("Choose a supported beacon interval")
        if expected_scope is not None and not isinstance(expected_scope, str):
            raise ValueError("Invalid expected channel scope")
        config = self.tactical.config
        if not config.get("enabled") or config.get("channel_id") != expected_channel_id:
            raise ValueError("Choose an enabled private team channel")
        self.stop()
        self.token = secrets.token_hex(32)
        self.channel, self.scope, self.interval = (
            expected_channel_id,
            expected_scope,
            interval,
        )
        return {"token": self.token, "interval": interval}

    async def position(self, token, latitude, longitude, accuracy, timestamp):
        if (
            not isinstance(token, str)
            or not self.token
            or not secrets.compare_digest(token, self.token)
        ):
            raise ValueError("Beacon consent expired")
        config = self.tactical.config
        if not config.get("enabled") or config.get("channel_id") != self.channel:
            self.stop()
            raise ValueError("Team changed; beacon consent ended")
        for value in (latitude, longitude, accuracy, timestamp):
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("Invalid position")
        if not (
            -90 <= latitude <= 90 and -180 <= longitude <= 180 and 0 <= accuracy <= 255
        ):
            raise ValueError("Invalid position or insufficient accuracy")
        if abs(time.time() - timestamp / 1000) > 30:
            raise ValueError("Position is not current")
        now = time.monotonic()
        if now - self.last < self.interval:
            return {"state": "waiting"}
        # Reserve before awaiting radio I/O: never duplicate an uncertain update.
        self.last = now
        try:
            result = await self.tactical.send(
                {
                    "kind": "position",
                    "latitude": latitude,
                    "longitude": longitude,
                    "accuracy": round(accuracy),
                },
                str(uuid.uuid4()),
                expected_channel_id=self.channel,
                expected_scope=self.scope,
            )
        except Exception:
            self.stop()
            raise
        if result.get("state") != "submitted":
            self.stop()
        return result
