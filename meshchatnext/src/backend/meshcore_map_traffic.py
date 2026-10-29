# SPDX-License-Identifier: MIT
"""Read-only packet visualisation; never infer a traversal from a direct route."""

import hashlib
import math
import time

from meshchatnext.src.backend.meshcore_repeats import packet_path


def describe_traffic(log, announces, positions, *, now=None):
    now = time.time() if now is None else now
    known = {item["peer"] for item in announces}
    locations = {item["peer"]: item for item in positions}
    packets = []
    for item in list(log)[-64:]:
        received, raw = item.get("received"), item.get("raw")
        if (
            type(received) not in (int, float)
            or not math.isfinite(received)
            or not 0 <= now - received <= 15
            or not isinstance(raw, str)
        ):
            continue
        try:
            observation = packet_path(bytes.fromhex(raw), received=received)
        except ValueError:
            continue
        if not observation:
            continue
        points = []
        if observation["route"] == "flood":
            for short in observation["hashes"]:
                matches = [peer for peer in known if peer.startswith(short)]
                position = locations.get(matches[0]) if len(matches) == 1 else None
                if position and all(
                    type(position.get(k)) in (int, float) and math.isfinite(position[k])
                    for k in ("latitude", "longitude")
                ):
                    lat, lon = position["latitude"], position["longitude"]
                    points.append(
                        [lon, lat] if -90 <= lat <= 90 and -180 <= lon <= 180 else None
                    )
                else:
                    points.append(None)
        packets.append(
            {
                "id": hashlib.sha256(f"{received}:{raw}".encode()).hexdigest()[:24],
                "received": received,
                "route": observation["route"],
                "points": points,
                # RX logs do not establish the sender or the destination's position.
                "incomplete": True,
                "missing_hops": sum(point is None for point in points),
            }
        )
    return packets[-32:]
