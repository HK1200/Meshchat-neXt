import { it, expect } from "vitest";
import { searchMeshcoreNodes, hasReportedPosition } from "../../meshchatnext/src/frontend/js/meshcoreNodeSearch";
it("finds saved names case-insensitively and key prefixes without accepting invalid coordinates", () => {
    const nodes = [
        { peer: "ab".repeat(32), name: "Hill Repeater", kind: 2, latitude: 0, longitude: 0 },
        { peer: "cd".repeat(32), name: "Hill Repeater", kind: 2, latitude: 49, longitude: -123 },
        { peer: "ef".repeat(32), name: "Hill", latitude: null, longitude: -123 },
    ];
    expect(searchMeshcoreNodes(nodes, " HILL ")).toHaveLength(2);
    expect(searchMeshcoreNodes(nodes, "ABAB")[0].node.peer).toBe(nodes[0].peer);
    expect(searchMeshcoreNodes(nodes, "missing")).toEqual([]);
    expect(searchMeshcoreNodes(nodes, " ")).toEqual([]);
    expect(hasReportedPosition({ latitude: NaN, longitude: 2 })).toBe(false);
    expect(hasReportedPosition({ latitude: 49, longitude: 181 })).toBe(false);
    expect(hasReportedPosition({ latitude: "49", longitude: 2 })).toBe(false);
});
