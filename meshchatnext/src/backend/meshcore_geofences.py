# SPDX-License-Identifier: MIT
"""Local-only crossing detection from received, unverified team positions.

No GPS polling or radio sends. Baselines are deliberately not restored after a
restart, channel/config change, long receive gap, or boundary edit.
"""

import hashlib
import json
import math

MAX_GAP = 600
EARTH = 6371008.8


def side(shape, position):
    """Inside/outside, or None within the accuracy/10m boundary margin."""
    lat, lon = position["latitude"], position["longitude"]
    margin = max(10, position.get("accuracy", 0))
    points = shape.get("points", [])
    if shape.get("shape_kind") == 4 and len(points) == 1:
        a, b = points[0]
        dlat, dlon = math.radians(a - lat), math.radians(b - lon)
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat))
            * math.cos(math.radians(a))
            * math.sin(dlon / 2) ** 2
        )
        distance = 2 * EARTH * math.asin(min(1, math.sqrt(h)))
        delta = distance - shape["radius_m"]
        return None if abs(delta) <= margin else delta < 0
    if shape.get("shape_kind") not in (2, 3) or len(points) < 3:
        return None
    # Unwrap around the observed position, including small dateline boundaries.
    projected = [
        (
            (((b - lon + 180) % 360) - 180)
            * math.cos(math.radians(lat))
            * math.pi
            / 180
            * EARTH,
            (a - lat) * math.pi / 180 * EARTH,
        )
        for a, b in points
    ]
    if max(p[0] for p in projected) - min(
        p[0] for p in projected
    ) > math.pi * EARTH * max(0.001, math.cos(math.radians(lat))):
        return None  # Ambiguous global/polar geometry is not monitored.
    inside = False
    for (x, y), (u, v) in zip(projected, projected[1:] + projected[:1], strict=True):
        length = (u - x) ** 2 + (v - y) ** 2
        t = max(0, min(1, -(x * (u - x) + y * (v - y)) / length)) if length else 0
        if math.hypot(x + t * (u - x), y + t * (v - y)) <= margin:
            return None
        if (y > 0) != (v > 0) and x + (u - x) * (-y) / (v - y) > 0:
            inside = not inside
    return inside


def boundary_version(shape):
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()


class CrossingMonitor:
    def __init__(self):
        self.states = {}
        self.positions = {}

    def reset(self):
        self.states.clear()
        self.positions.clear()

    def update(self, position, shapes, now):
        alias = position["alias"]
        fingerprint = json.dumps(position, sort_keys=True)
        previous = self.positions.get(alias)
        if previous and previous[0] == fingerprint and now - previous[1] < MAX_GAP:
            return []  # Repeats are not new observations and do not refresh age.
        self.positions[alias] = (fingerprint, now)
        if len(self.positions) > 500:
            self.positions.pop(next(iter(self.positions)))
        shapes = [
            s for s in shapes if not s.get("deleted") and s.get("geofence") in (1, 2, 3)
        ]
        live = {(s["alias"], s["id"]) for s in shapes}
        self.states = {
            k: v
            for k, v in self.states.items()
            if k[:2] in live and now - v[1] < MAX_GAP
        }
        events = []
        for shape in shapes:
            key = (shape["alias"], shape["id"], alias)
            version = boundary_version(shape)
            value = side(shape, position)
            old = self.states.get(key)
            if value is None:
                continue
            self.states[key] = (value, now, version)
            if old and old[2] == version and old[0] != value:
                crossing = "entered" if value else "left"
                if shape["geofence"] == 3 or shape["geofence"] == (1 if value else 2):
                    events.append((shape, crossing))
        # Bound hostile channel state growth independently of stored history.
        while len(self.states) > 5000:
            self.states.pop(next(iter(self.states)))
        return events
