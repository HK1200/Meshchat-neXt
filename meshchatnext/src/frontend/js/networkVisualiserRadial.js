// SPDX-License-Identifier: 0BSD

// Match the Linux 4.9.2 visualiser: interfaces form the inner ring and peers
// occupy concentric hop rings, with stable ordering within each ring.
export function radialPositions({ interfaces = [], discovered = [], pathTable = [], hopMax = null } = {}) {
    const positions = { me: { x: 0, y: 0 } };
    const hubs = [...new Set([...interfaces, ...discovered].filter((id) => typeof id === "string" && id))];
    hubs.forEach((id, index) => {
        const angle = (index / hubs.length) * Math.PI * 2 - Math.PI / 2;
        positions[id] = { x: 300 * Math.cos(angle), y: 300 * Math.sin(angle) };
    });
    const rings = new Map();
    for (const path of pathTable) {
        if (!path?.hash || !Number.isFinite(path.hops) || (hopMax != null && path.hops > hopMax)) continue;
        const hop = Math.max(1, Math.round(path.hops));
        if (!rings.has(hop)) rings.set(hop, []);
        rings.get(hop).push(path);
    }
    for (const [hop, peers] of rings) {
        peers.sort(
            (a, b) =>
                String(a.interface).localeCompare(String(b.interface)) || String(a.hash).localeCompare(String(b.hash))
        );
        const radius = 560 + 230 * (hop - 1);
        const offset = ((137.508 * hop) % 360) * (Math.PI / 180);
        peers.forEach((peer, index) => {
            const angle = offset + (index / peers.length) * Math.PI * 2;
            positions[peer.hash] = { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
        });
    }
    return positions;
}
