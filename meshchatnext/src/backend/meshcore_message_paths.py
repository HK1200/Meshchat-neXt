# SPDX-License-Identifier: MIT
"""Bounded message-specific observations. Never substitute a contact's saved route."""

import json
import math


def describe_paths(row, observations, announces, positions, *, owner, kind, target):
    payload = json.loads(row.get("payload") or "{}")
    event = payload.get("event", payload)
    if row["direction"] == "in":
        observations = event.get("observed_paths", [])[:32]
    known = {p["peer"]: p for p in announces}
    locations = {p["peer"]: p for p in positions}

    def node(peer):
        value = {
            "peer": peer,
            "name": known.get(peer, {}).get("name") or peer,
            "kind": known.get(peer, {}).get("kind", 0),
        }
        pos = locations.get(peer)
        if (
            pos
            and all(
                type(pos.get(k)) in (int, float) and math.isfinite(pos[k])
                for k in ("latitude", "longitude")
            )
            and -90 <= pos["latitude"] <= 90
            and -180 <= pos["longitude"] <= 180
        ):
            value.update({k: pos[k] for k in ("latitude", "longitude", "updated")})
        return value

    routes = []
    for observation in observations:
        width, hashes = observation.get("hash_bytes"), observation.get("hashes")
        if (
            width not in (1, 2, 3)
            or not isinstance(hashes, list)
            or len(hashes) * width > 64
            or observation.get("route") not in ("flood", "direct")
        ):
            continue
        if any(
            not isinstance(h, str)
            or len(h) != width * 2
            or any(c not in "0123456789abcdef" for c in h)
            for h in hashes
        ):
            continue
        hops = []
        for short in hashes:
            matches = [peer for peer in known if peer.startswith(short)]
            hops.append(
                {
                    "hash": short,
                    "matches": [node(peer) for peer in matches[:8]],
                    "candidate_count": len(matches),
                }
            )
        points = []
        # Direct packet paths are supplied/remaining paths, not an observed traversal.
        if observation["route"] == "flood":
            start = row.get("peer") if row["direction"] == "in" else owner
            ordered = [node(start) if start else None] + [
                h["matches"][0] if h["candidate_count"] == 1 else None for h in hops
            ]
            if row["direction"] == "in":
                ordered.append(node(owner))
            points = [
                {**item, "order": index}
                for index, item in enumerate(ordered)
                if item and "latitude" in item
            ]
        routes.append(
            {
                **{
                    k: observation[k]
                    for k in ("route", "hash_bytes", "received", "rssi", "snr")
                    if k in observation
                },
                "hops": hops,
                "points": points,
            }
        )
    # Firmware queue metadata survives when a full RX packet was unavailable.
    hops = event.get("path_len")
    return {
        "owner": owner,
        "kind": kind,
        "target": target,
        "id": row["id"],
        "direction": row["direction"],
        "state": row["state"],
        "heard_repeats": row.get("heard_repeats"),
        "reported_hops": hops if type(hops) is int and 0 <= hops <= 63 else None,
        "direct_routing": hops == 255,
        "snr": event.get("SNR"),
        "rssi": event.get("RSSI"),
        "routes": routes,
        "endpoints": [
            node(peer)
            for peer in ([row.get("peer"), owner] if kind == "direct" else [])
            if peer and "latitude" in node(peer)
        ],
        "note": "Observed packet paths are not verified identities or a complete list of repeaters that heard a message. Short hashes can collide. Locations are the latest saved reports, not positions at message time.",
    }
