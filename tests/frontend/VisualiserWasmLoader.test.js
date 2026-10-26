import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
    isVisualiserWasmBundled,
    preloadVisualiserWasm,
    isVisualiserWasmReady,
    isVisualiserWebGLSceneReady,
    callVisualiserWasmJson,
} from "@/js/VisualiserWasmLoader.js";

describe("VisualiserWasmLoader", () => {
    beforeEach(() => {
        document.getElementById("meshchatnext-visualiser-wasm-exec")?.remove();
        delete globalThis.__MESHCHATNEXT_TEST_VISUALISER_WASM_BUNDLED__;
        delete globalThis.meshchatnextVisualiserBuildPathGraph;
        delete globalThis.meshchatnextVisualiserPathHashes;
        delete globalThis.meshchatnextVisualiserDedupeIcons;
        delete globalThis.Go;
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        document.getElementById("meshchatnext-visualiser-wasm-exec")?.remove();
    });

    it("reports bundled flag from test override", () => {
        globalThis.__MESHCHATNEXT_TEST_VISUALISER_WASM_BUNDLED__ = false;
        expect(isVisualiserWasmBundled()).toBe(false);
        globalThis.__MESHCHATNEXT_TEST_VISUALISER_WASM_BUNDLED__ = true;
        expect(isVisualiserWasmBundled()).toBe(true);
    });

    it("preloadVisualiserWasm resolves false when not bundled", async () => {
        globalThis.__MESHCHATNEXT_TEST_VISUALISER_WASM_BUNDLED__ = false;
        await expect(preloadVisualiserWasm()).resolves.toBe(false);
    });

    it("preloadVisualiserWasm resolves false when WebAssembly is unavailable", async () => {
        globalThis.__MESHCHATNEXT_TEST_VISUALISER_WASM_BUNDLED__ = true;
        vi.stubGlobal("WebAssembly", undefined);
        await expect(preloadVisualiserWasm()).resolves.toBe(false);
        expect(isVisualiserWasmReady()).toBe(false);
    });

    it("callVisualiserWasmJson returns null when export missing", () => {
        expect(callVisualiserWasmJson("meshchatnextVisualiserBuildPathGraph", "{}")).toBeNull();
    });

    it("callVisualiserWasmJson parses JSON string results", () => {
        globalThis.meshchatnextVisualiserPathHashes = () => JSON.stringify(["aa", "bb"]);
        expect(callVisualiserWasmJson("meshchatnextVisualiserPathHashes", "[]", 4)).toEqual(["aa", "bb"]);
    });

    it("callVisualiserWasmJson returns null on export error object", () => {
        globalThis.meshchatnextVisualiserPathHashes = () => ({ ok: false, error: "bad" });
        expect(callVisualiserWasmJson("meshchatnextVisualiserPathHashes", "[]")).toBeNull();
    });

    it("isVisualiserWebGLSceneReady is false without scene exports", () => {
        expect(isVisualiserWebGLSceneReady()).toBe(false);
    });
});
