import { describe, it, expect } from "vitest";
import { radialPositions } from "@/js/networkVisualiserRadial.js";

describe("Linux-compatible radial layout", () => {
    const paths = [
        { hash: "a", interface: "one", hops: 1 },
        { hash: "b", interface: "one", hops: 1 },
        { hash: "c", interface: "two", hops: 3 },
    ];
    it("places interfaces and peers in the Linux 4.9.2 hop rings", () => {
        const positions = radialPositions({ interfaces: ["one"], discovered: ["discovered"], pathTable: paths });
        expect(positions.me).toEqual({ x: 0, y: 0 });
        for (const id of ["one", "discovered"]) expect(Math.hypot(positions[id].x, positions[id].y)).toBeCloseTo(300);
        expect(Math.hypot(positions.a.x, positions.a.y)).toBeCloseTo(560);
        expect(Math.hypot(positions.c.x, positions.c.y)).toBeCloseTo(1020);
        expect(positions.a.x).toBeCloseTo(-positions.b.x);
        expect(positions.a.y).toBeCloseTo(-positions.b.y);
    });
    it("preserves positions when paths arrive in a different order and applies the hop filter", () => {
        expect(radialPositions({ pathTable: [...paths].reverse() })).toEqual(radialPositions({ pathTable: paths }));
        expect(radialPositions({ pathTable: paths, hopMax: 1 }).c).toBeUndefined();
        expect(radialPositions({ pathTable: [{ hash: "invalid", hops: NaN }] })).toEqual({ me: { x: 0, y: 0 } });
    });
});
