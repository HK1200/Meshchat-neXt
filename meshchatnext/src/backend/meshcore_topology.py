# SPDX-License-Identifier: MIT
"""Read-only topology from cached companion routes, never a live-link survey."""

from __future__ import annotations


def cached_route(contact):
    """Validate the companion's variable-width route without trimming zero hashes."""
    hops = contact.get("out_path_len")
    mode = contact.get("out_path_hash_mode")
    raw = contact.get("out_path")
    if type(hops) is not int or not -1 <= hops <= 63:
        return None
    if hops <= 0:
        return {"hops": hops, "hash_bytes": None, "hashes": []}
    if type(mode) is not int or not 0 <= mode <= 2 or not isinstance(raw, str):
        return None
    width = mode + 1
    if hops * width > 64 or len(raw) != hops * width * 2:
        return None
    try:
        path = bytes.fromhex(raw)
    except ValueError:
        return None
    if len(path) != hops * width:
        return None
    return {
        "hops": hops,
        "hash_bytes": width,
        "hashes": [path[i : i + width].hex() for i in range(0, len(path), width)],
    }


def topology_nodes(store, owner, cached):
    """Merge saved discoveries/contacts and retain only the latest valid cached route."""
    records = {row["peer"]: row for row in store.announces(owner)}
    for row in store.contacts(owner):
        records.setdefault(row["peer"], row)
    for peer, contact in cached.items():
        if isinstance(contact, dict):
            route = cached_route(contact)
            if route is not None:
                store.save_topology_route(owner, peer, route)
    routes = store.topology_routes(owner)
    return [
        {
            "peer": peer,
            "name": str(row.get("name") or "")[:128],
            "kind": row.get("kind", 0),
            "heard": row.get("heard"),
            "advertised": row.get("advertised"),
            "saved": bool(row.get("saved", row.get("active"))),
            "route": routes.get(peer),
        }
        for peer, row in records.items()
        if peer != owner
    ]
