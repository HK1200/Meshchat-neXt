import { describe, it, expect } from "vitest";
import JSZip from "jszip";
import { cotPoint, readCot, writeTakPackage, readTakPackage } from "../../meshchatnext/src/frontend/js/meshcoreCot";
describe("local TAK point interchange", () => {
    it("round trips escaped point labels and remarks without inventing identity", async () => {
        const point = { latitude: 0, longitude: 0, label: '<test & "point">', note: "local only" };
        const result = await readTakPackage(await writeTakPackage([point]));
        expect(result.items[0]).toMatchObject({ ...point, sourceType: "a-u-G" });
        expect(result.skipped).toBe(0);
    });
    it("rejects invalid coordinates and XML entities", () => {
        expect(() => cotPoint({ latitude: 91, longitude: 0 })).toThrow();
        expect(() => readCot('<!DOCTYPE event [<!ENTITY x "hello">]><event/>')).toThrow();
        expect(() => readCot('<event><point lat="NaN" lon="0"/></event>')).toThrow();
        expect(() => readCot('<event><point lat="" lon="0"/></event>')).toThrow();
    });
    it("bounds UTF-8 fields to the MeshCore wire limits", () => {
        const result = readCot(
            cotPoint({ latitude: 0, longitude: 0, label: "😀".repeat(40), note: "é".repeat(100) })
        )[0];
        expect(new TextEncoder().encode(result.label).length).toBe(32);
        expect(new TextEncoder().encode(result.note).length).toBe(60);
    });
    it("rejects path traversal and oversized decompressed entries", async () => {
        const zip = new JSZip();
        zip.file("../bad.cot", "bad");
        await expect(readTakPackage(await zip.generateAsync({ type: "uint8array" }))).rejects.toThrow("Unsafe");
        const bomb = new JSZip();
        bomb.file("MANIFEST/manifest.xml", "x".repeat(1024 * 1024 + 1));
        await expect(
            readTakPackage(await bomb.generateAsync({ type: "uint8array", compression: "DEFLATE" }))
        ).rejects.toThrow("too large");
    });
});

it("round trips lines, polygons, circles and routes without simplifying vertices", async () => {
    const shapes = [
        {
            kind: "shape",
            shape_kind: 0,
            points: [
                [0, 0],
                [0.001, 0.001],
            ],
            label: "Line",
            color: 0,
            geofence: 0,
        },
        {
            kind: "shape",
            shape_kind: 2,
            points: [
                [0, 0],
                [0.001, 0],
                [0.001, 0.001],
            ],
            label: "Boundary",
            color: 0,
            geofence: 0,
        },
        { kind: "shape", shape_kind: 4, points: [[0, 0]], radius_m: 100, label: "Circle", color: 0, geofence: 0 },
        {
            kind: "shape",
            shape_kind: 5,
            points: [
                [0, 0],
                [0.001, 0.001],
            ],
            label: "Route",
            route_method: 1,
            color: 0,
            geofence: 0,
        },
    ];
    const result = await readTakPackage(await writeTakPackage(shapes));
    for (let i = 0; i < shapes.length; i++) expect(result.items[i]).toMatchObject(shapes[i]);
});
it("rejects invalid drawing vertices rather than exporting a misleading centre point", () => {
    expect(() =>
        cotPoint({
            kind: "shape",
            shape_kind: 2,
            points: [
                [0, 0],
                [91, 0],
                [0, 1],
            ],
        })
    ).toThrow();
});

it("preserves associated photo/voice bytes and file-only packages", async () => {
    const item = { latitude: 0, longitude: 0, label: "With media", sourceUid: "item-1" };
    const file = { uid: "item-1", name: "voice.wav", bytes: new Uint8Array([82, 73, 70, 70, 1, 2, 3]) };
    const imported = await readTakPackage(await writeTakPackage([item], { files: [file] }));
    expect(imported.files[0].bytes).toEqual(file.bytes);
    expect(imported.files[0].uid).toBe(imported.items[0].sourceUid);
    const again = await readTakPackage(await writeTakPackage(imported.items, { files: imported.files }));
    expect(again.files[0].bytes).toEqual(file.bytes);
    const filesOnly = await readTakPackage(await writeTakPackage([], { files: [file] }));
    expect(filesOnly.items).toHaveLength(0);
    expect(filesOnly.files).toHaveLength(1);
});
