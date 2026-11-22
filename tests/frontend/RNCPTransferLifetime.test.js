// SPDX-License-Identifier: 0BSD
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RNCPPage from "@/components/rncp/RNCPPage.vue";
import { createApiClient } from "@/js/apiClient.js";
import { setCsrfToken } from "@/js/csrfToken.js";

describe("RNCP transfer request lifetime", () => {
    beforeEach(() => {
        setCsrfToken("fixture-token");
        window.api = createApiClient();
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        vi.useRealTimers();
    });
    it.each(["send", "fetch"])("keeps a healthy %s pending beyond the general mutation limit", async (kind) => {
        let complete;
        vi.stubGlobal(
            "fetch",
            vi.fn(() => new Promise((resolve) => (complete = resolve)))
        );
        const state = {
            sendDestinationHash: "ab".repeat(16),
            sendFilePath: "/private/fixture.bin",
            sendTimeout: 30,
            sendNoCompress: false,
            fetchDestinationHash: "ab".repeat(16),
            fetchFilePath: "fixture.bin",
            fetchTimeout: 30,
            fetchSavePath: null,
            fetchAllowOverwrite: false,
            $t: (value) => value,
            notifyRncp: vi.fn(),
        };
        const pending = RNCPPage.methods[kind + "File"].call(state);
        await vi.advanceTimersByTimeAsync(120001);
        expect(state[kind + "InProgress"]).toBe(true);
        expect(state[kind + "Result"]).toBeNull();
        const [path, request] = fetch.mock.calls[0];
        expect(path).toBe("/api/v1/rncp/" + kind);
        expect(JSON.parse(request.body).timeout).toBe(30);
        complete(
            new Response(JSON.stringify({ transfer_id: "cd".repeat(32), file_path: "/private/fixture.bin" }), {
                status: 200,
                headers: { "content-type": "application/json" },
            })
        );
        await pending;
        expect(state[kind + "InProgress"]).toBe(false);
        expect(state[kind + "Result"].success).toBe(true);
        expect(state.notifyRncp).toHaveBeenCalledOnce();
    });
});
