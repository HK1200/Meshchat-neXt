import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import MicronParser from "@/js/MicronParser.js";

/**
 * Loads the real bundled micron-parser-go WASM and checks the hybrid
 * conversion path. v1.2.0 emitted a single-line input for multi-row
 * fields, losing newlines in submitted text; MicronParser routes
 * those lines through the JS renderer so they work on any WASM
 * version, and the bundled renderer is pinned at v1.3.0 which
 * handles them natively.
 */

const VENDOR = resolve(__dirname, "../../meshchatnext/src/frontend/public/vendor/micron-parser-go");

// The wasm binary is fetched at build time and is not present in jobs
// that run the frontend suite without a full vendor fetch.
const wasmPresent = existsSync(resolve(VENDOR, "micron-parser-go.wasm")) && existsSync(resolve(VENDOR, "wasm_exec.js"));
const describeWasm = wasmPresent ? describe : describe.skip;

describeWasm("MicronWasmFields (bundled wasm)", () => {
    let saved = {};

    beforeAll(async () => {
        saved = {
            micronConvert: globalThis.micronConvert,
            micronCollectFields: globalThis.micronCollectFields,
            micronResolveLink: globalThis.micronResolveLink,
            micronLint: globalThis.micronLint,
            micronParse: globalThis.micronParse,
            micronVersion: globalThis.micronVersion,
            Go: globalThis.Go,
        };
        // wasm_exec.js registers Go on globalThis as a side effect.
        await import(pathToFileURL(resolve(VENDOR, "wasm_exec.js")).href);
        const buf = readFileSync(resolve(VENDOR, "micron-parser-go.wasm"));
        const go = new globalThis.Go();
        const { instance } = await WebAssembly.instantiate(buf, go.importObject);
        go.run(instance);
        // The Go main registers the micron* globals asynchronously.
        await new Promise((r) => setTimeout(r, 300));
        expect(typeof globalThis.micronConvert).toBe("function");
    });

    afterAll(() => {
        for (const [k, v] of Object.entries(saved)) {
            if (v === undefined) {
                delete globalThis[k];
            } else {
                globalThis[k] = v;
            }
        }
    });

    it("raw wasm renders multi-row fields as textareas", () => {
        const html = globalThis.micronConvert("`<80x4|reply`>", true, false);
        expect(html).toContain("<textarea");
        expect(html).toContain('rows="4"');
        expect(html).toContain('cols="80"');
    });

    it("hybrid path renders multi-row fields as textarea", () => {
        const parser = new MicronParser(true, false);
        const html = parser.convertMicronToHtml(
            "`>Reply\n`<80x4|reply`>\n`[Post`/forum/post`reply]",
            {},
            { useWasm: true }
        );
        expect(html).toContain("<textarea");
        expect(html).toContain('rows="4"');
        expect(html).toContain('cols="80"');
        expect(html).toContain('data-fields="reply"');
    });

    it("hybrid path keeps width-only fields as inputs", () => {
        const parser = new MicronParser(true, false);
        const html = parser.convertMicronToHtml("`<40|name`bob>", {}, { useWasm: true });
        expect(html).toContain("<input");
        expect(html).not.toContain("<textarea");
    });
});
