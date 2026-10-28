import { it, expect } from "vitest";
import { meshcoreGraph } from "../../meshchatnext/src/frontend/components/network-visualiser/internal/meshcoreTopology.js";
const owner = "a1".repeat(32),
    peer = "b2".repeat(32),
    repeater = "c3".repeat(32);
it("distinguishes a connected companion from stored routes without inventing unknown links", () => {
    const graph = meshcoreGraph(
        {
            owner,
            connected: true,
            nodes: [
                { peer, name: "Client", route: { hops: 1, hash_bytes: 1, hashes: ["c3"] } },
                { peer: repeater, name: "Repeater", kind: 2 },
                { peer: "d4".repeat(32), name: "No path" },
            ],
        },
        "My radio"
    );
    expect(graph.edges.filter((edge) => !edge.dashes)).toHaveLength(1);
    expect(graph.edges.find((edge) => edge.id === `${peer}:0`).to).toBe(repeater);
    expect(graph.edges.find((edge) => edge.id === `${peer}:destination`).from).toBe(repeater);
    expect(graph.edges.some((edge) => edge.to === "d4".repeat(32))).toBe(false);
});
it("keeps ambiguous and unknown hops explicit, preserving route order", () => {
    const graph = meshcoreGraph({
        owner,
        nodes: [
            { peer, route: { hops: 2, hash_bytes: 1, hashes: ["c3", "00"] } },
            { peer: repeater },
            { peer: "c3" + "ab".repeat(31) },
        ],
    });
    expect(graph.nodes.find((node) => node.id === `hop:${peer}:0`).label).toContain("Ambiguous");
    expect(graph.nodes.find((node) => node.id === `hop:${peer}:1`).label).toContain("Unknown");
    expect(graph.edges.find((edge) => edge.id === `${peer}:1`)).toMatchObject({
        from: `hop:${peer}:0`,
        to: `hop:${peer}:1`,
    });
});
it("never connects flood or malformed paths and clears everything without an owner", () => {
    for (const route of [
        { hops: -1, hashes: [] },
        { hops: 2, hash_bytes: 1, hashes: ["c3"] },
        { hops: 1, hash_bytes: 1, hashes: ["zz"] },
    ])
        expect(meshcoreGraph({ owner, nodes: [{ peer, route }] }).edges).toHaveLength(1);
    expect(meshcoreGraph({ nodes: [{ peer }] }).nodes.map((n) => n.id)).toEqual(["device"]);
});
it("keeps radio graphs isolated, treats received labels as plain text, and bounds large diagrams", () => {
    const graph = meshcoreGraph({
        owner,
        nodes: [
            { peer, name: "<img onerror=alert(1)>" },
            ...Array.from({ length: 600 }, (_, i) => ({ peer: i.toString(16).padStart(64, "0") })),
        ],
    });
    expect(graph.nodes.find((n) => n.id === peer).label).toBe("<img onerror=alert(1)>");
    expect(graph.nodes.every((n) => n.title === undefined)).toBe(true);
    expect(graph.omitted).toBeGreaterThan(0);
    expect(meshcoreGraph({ owner: "e5".repeat(32), nodes: [] }).nodes.some((n) => n.id === peer)).toBe(false);
});
