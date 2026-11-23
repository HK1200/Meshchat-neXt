// SPDX-License-Identifier: 0BSD
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RNCPPage from "@/components/rncp/RNCPPage.vue";

function state() {
    const value = { ...RNCPPage.data(), $t: (key) => key };
    for (const [key, method] of Object.entries(RNCPPage.methods)) value[key] = method.bind(value);
    return value;
}
function selection(size = 5) {
    return { target: { files: [new File([new Uint8Array(size)], "picked.bin")], value: "selected" } };
}
describe("RNCP selected-file imports", () => {
    beforeEach(() => {
        window.api = {
            get: vi.fn().mockResolvedValue({ data: { files: [], max_file_bytes: 512 * 1048576 } }),
            post: vi.fn(),
            delete: vi.fn(),
        };
    });
    afterEach(() => vi.restoreAllMocks());
    it("uploads only the selected bytes and selects the server-issued private path", async () => {
        window.api.post.mockResolvedValue({ data: { id: "ab", file_path: "/private/rncp_uploads/ab/picked.bin" } });
        const page = state();
        const event = selection();
        await page.onWebSendFilePicked(event);
        const [url, body, options] = window.api.post.mock.calls[0];
        expect(url).toBe("/api/v1/rncp/upload");
        expect(body).toBeInstanceOf(FormData);
        expect(body.get("file").name).toBe("picked.bin");
        expect(body.get("file").size).toBe(5);
        expect(options.timeout).toBe(0);
        expect(options.signal).toBeInstanceOf(AbortSignal);
        expect(page.sendFilePath).toBe("/private/rncp_uploads/ab/picked.bin");
        expect(page.importInProgress).toBe(false);
        expect(event.target.value).toBe("");
    });
    it("retains the previous file when import fails and presents the server error", async () => {
        window.api.post.mockRejectedValue({ response: { data: { message: "Storage full" } } });
        const page = state();
        page.sendFilePath = "/previous.bin";
        await page.onWebSendFilePicked(selection());
        expect(page.sendFilePath).toBe("/previous.bin");
        expect(page.importError).toBe("Storage full");
    });
    it("rejects empty or oversized selections before sending", async () => {
        const page = state();
        page.importLimit = 2;
        await page.onWebSendFilePicked(selection(0));
        await page.onWebSendFilePicked(selection(3));
        expect(window.api.post).not.toHaveBeenCalled();
        expect(page.importError).toBe("rncp.import_size_limit");
    });
    it("does not send or delete a copy while its import is pending", async () => {
        const page = state();
        page.importInProgress = true;
        await page.sendFile();
        await page.removeImportedFile({ id: "ab" });
        await page.onWebSendFilePicked(selection());
        expect(window.api.post).not.toHaveBeenCalled();
        expect(window.api.delete).not.toHaveBeenCalled();
    });
    it("does not erase the selection after the server refuses deletion of an active copy", async () => {
        const page = state();
        page.sendFilePath = "/copy";
        window.api.delete.mockRejectedValue({ response: { data: { message: "Transfer in progress" } } });
        await page.removeImportedFile({ id: "ab", file_path: "/copy" });
        expect(page.sendFilePath).toBe("/copy");
        expect(page.importError).toBe("Transfer in progress");
    });
    it("removes only the identified imported copy and clears its stale selection", async () => {
        const page = state();
        page.sendFilePath = "/copy";
        window.api.delete.mockResolvedValue({});
        await page.removeImportedFile({ id: "ab", file_path: "/copy" });
        expect(window.api.delete).toHaveBeenCalledWith("/api/v1/rncp/uploads/ab");
        expect(page.sendFilePath).toBe("");
    });
    it("aborts an import on leaving without changing the disposed page", async () => {
        window.api.post.mockImplementation(
            (_url, _data, options) =>
                new Promise((_resolve, reject) => {
                    options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
                })
        );
        const page = state();
        page.sendFilePath = "/previous";
        page.cancelSend = vi.fn();
        page.cancelFetch = vi.fn();
        const pending = page.onWebSendFilePicked(selection());
        RNCPPage.beforeUnmount.call(page);
        await pending;
        expect(page.importController.signal.aborted).toBe(true);
        expect(page.sendFilePath).toBe("/previous");
        expect(page.importError).toBeNull();
        expect(window.api.get).not.toHaveBeenCalled();
    });
});
