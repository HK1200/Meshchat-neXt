// SPDX-License-Identifier: MIT
export function hasReportedPosition(node) {
    return (
        typeof node?.latitude === "number" &&
        Number.isFinite(node.latitude) &&
        Math.abs(node.latitude) <= 90 &&
        typeof node?.longitude === "number" &&
        Number.isFinite(node.longitude) &&
        Math.abs(node.longitude) <= 180
    );
}
export function searchMeshcoreNodes(nodes, query) {
    const text = String(query || "")
        .trim()
        .toLocaleLowerCase();
    if (!text) return [];
    return (Array.isArray(nodes) ? nodes : [])
        .filter(
            (node) =>
                hasReportedPosition(node) &&
                typeof node.peer === "string" &&
                (String(node.name || "")
                    .toLocaleLowerCase()
                    .includes(text) ||
                    node.peer.toLowerCase().startsWith(text))
        )
        .sort((a, b) => String(a.name || a.peer).localeCompare(String(b.name || b.peer)))
        .slice(0, 50)
        .map((node) => ({
            display_name: node.name || node.peer,
            lat: node.latitude,
            lon: node.longitude,
            type: `MeshCore ${{ 1: "client", 2: "repeater", 3: "room server", 4: "sensor" }[node.kind] || "node"} · reported location`,
            node,
        }));
}
