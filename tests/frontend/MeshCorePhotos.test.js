import { describe, it, expect } from "vitest";
import { photoDimensions } from "../../meshchatnext/src/frontend/js/meshcorePhotos";
function png(w, h) {
    const data = new Uint8Array(24);
    data.set([137, 80, 78, 71, 13, 10, 26, 10]);
    data.set([73, 72, 68, 82], 12);
    new DataView(data.buffer).setUint32(16, w);
    new DataView(data.buffer).setUint32(20, h);
    return data;
}
describe("MeshCore photo source bounds", () => {
    it("accepts normal dimensions and rejects enormous or extreme-aspect compressed sources", () => {
        expect(photoDimensions(png(4000, 3000), "image/png")).toEqual({ width: 4000, height: 3000 });
        for (const [w, h] of [
            [0, 1],
            [100000, 100000],
            [1, 20000],
        ])
            expect(() => photoDimensions(png(w, h), "image/png")).toThrow();
    });
    it("reads JPEG SOF dimensions and rejects truncated headers", () => {
        const jpeg = Uint8Array.from([255, 216, 255, 192, 0, 8, 8, 0, 32, 0, 64, 0]);
        expect(photoDimensions(jpeg, "image/jpeg")).toEqual({ width: 64, height: 32 });
        expect(() => photoDimensions(jpeg.subarray(0, 8), "image/jpeg")).toThrow();
    });
    it("rejects mislabeled files before browser decoding", () => {
        expect(() => photoDimensions(png(32, 32), "image/jpeg")).toThrow();
    });
});
