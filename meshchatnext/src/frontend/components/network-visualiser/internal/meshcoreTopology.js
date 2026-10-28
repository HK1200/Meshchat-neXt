// SPDX-License-Identifier: MIT
const key = (value) => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
export const meshcoreNodeType = (kind) =>
    ({ 1: "Client", 2: "Repeater", 3: "Room server", 4: "Sensor" })[kind] || "Node";
/** Saved outbound paths are observations, never proof of live RF links or hop identity. */
export function meshcoreGraph(snapshot, label = "MeshCore radio") {
    const owner = snapshot?.owner;
    const nodes = [
        {
            id: "device",
            label: "This device",
            shape: "box",
            color: "#2563eb",
            font: { color: "#ffffff" },
            details: {
                name: "This device",
                type: "Application",
                note: "MeshCore companions are independent from Reticulum interfaces.",
            },
        },
    ];
    const edges = [];
    if (!key(owner)) return { nodes, edges, omitted: 0 };
    const companion = `radio:${owner}`;
    nodes.push({
        id: companion,
        label,
        shape: "box",
        color: snapshot.connected ? "#0f766e" : "#64748b",
        font: { color: "#ffffff" },
        details: {
            name: label,
            type: "Companion",
            peer: owner,
            note: snapshot.connected
                ? "Companion connected to this device"
                : "Companion offline; stored information may be stale",
        },
    });
    edges.push({
        id: "transport",
        from: "device",
        to: companion,
        dashes: !snapshot.connected,
        label: snapshot.connected ? "Connected companion" : "Offline companion",
        color: { color: "#64748b" },
    });
    const all = (snapshot.nodes || []).filter((row) => key(row.peer) && row.peer !== owner);
    const unique = [...new Map(all.map((row) => [row.peer, row])).values()];
    const rows = unique.slice(0, 500);
    const peers = new Set(rows.map((row) => row.peer));
    for (const row of rows)
        nodes.push({
            id: row.peer,
            label: row.name || `${meshcoreNodeType(row.kind)} ${row.peer.slice(0, 8)}`,
            shape: row.kind === 2 ? "diamond" : row.kind === 3 ? "box" : "dot",
            size: row.kind === 2 ? 19 : 14,
            color: row.kind === 2 ? "#d97706" : "#0284c7",
            details: { ...row, type: meshcoreNodeType(row.kind) },
        });
    let budget = 1500;
    for (const row of rows) {
        const route = row.route;
        if (
            !route ||
            route.hops < 0 ||
            route.hops > 63 ||
            !Number.isInteger(route.hops) ||
            !Array.isArray(route.hashes) ||
            route.hashes.length !== route.hops
        )
            continue;
        if (
            route.hops &&
            (![1, 2, 3].includes(route.hash_bytes) ||
                route.hashes.some(
                    (hash) =>
                        typeof hash !== "string" || hash.length !== route.hash_bytes * 2 || !/^[0-9a-f]+$/.test(hash)
                ))
        )
            continue;
        // Skip the whole path when bounded: never join across a missing hop.
        if (budget < route.hops + 1) continue;
        budget -= route.hops + 1;
        let from = companion;
        route.hashes.forEach((hash, index) => {
            const matches = unique.filter((node) => node.peer.startsWith(hash));
            let to;
            if (matches.length === 1 && peers.has(matches[0].peer) && matches[0].peer !== row.peer)
                to = matches[0].peer;
            else {
                to = `hop:${row.peer}:${index}`;
                nodes.push({
                    id: to,
                    label: `${matches.length > 1 ? "Ambiguous" : "Unknown"} hop ${hash}`,
                    shape: "dot",
                    size: 10,
                    color: "#94a3b8",
                    details: {
                        name: `Hop ${hash}`,
                        type: matches.length > 1 ? "Ambiguous short identifier" : "Unresolved short identifier",
                        note:
                            matches.length > 1
                                ? `${matches.length} known nodes share this prefix. No identity is assumed.`
                                : "No unique known node matches this hop. It is not a verified identity.",
                    },
                });
            }
            edges.push({
                id: `${row.peer}:${index}`,
                from,
                to,
                dashes: true,
                arrows: "to",
                color: { color: "#94a3b8" },
            });
            from = to;
        });
        edges.push({
            id: `${row.peer}:destination`,
            from,
            to: row.peer,
            dashes: true,
            arrows: "to",
            label: route.hops === 0 ? "Saved direct route" : undefined,
            color: { color: "#94a3b8" },
        });
    }
    return { nodes, edges, omitted: Math.max(0, unique.length - rows.length), limited: budget < 64 };
}
