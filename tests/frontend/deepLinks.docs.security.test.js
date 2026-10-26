// SPDX-License-Identifier: 0BSD

import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../../meshchatnext/src/frontend/components/App.vue";
import { handleLxmIngestUriResult } from "../../meshchatnext/src/frontend/js/ingestUriResultNavigation.js";
import ToastUtils from "../../meshchatnext/src/frontend/js/ToastUtils";

vi.mock("../../meshchatnext/src/frontend/js/ToastUtils", () => ({
    default: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
        warning: vi.fn(),
    },
}));

describe("meshchatnext://docs deep links (security / fuzz)", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("routes only hostname docs, not docs- prefix spoof", () => {
        const push = vi.fn();
        App.methods.handleProtocolLink.call({ $router: { push } }, "meshchatnext://docs-foo?reticulum=evil");
        expect(push).not.toHaveBeenCalled();
    });

    it("accepts meshchat alias and path-style manual path", () => {
        const push = vi.fn();
        App.methods.handleProtocolLink.call({ $router: { push } }, "meshchat://docs/manual/interfaces.html");
        expect(push).toHaveBeenCalledWith({
            name: "documentation",
            query: { reticulum: encodeURIComponent("manual/interfaces.html") },
        });
    });

    it("passes XSS-shaped reticulum through encodeURIComponent only (opaque to router)", () => {
        const push = vi.fn();
        const malicious = "<script>alert(1)</script>";
        App.methods.handleProtocolLink.call(
            { $router: { push } },
            `meshchatnext://docs?reticulum=${encodeURIComponent(malicious)}`
        );
        expect(push).toHaveBeenCalledWith({
            name: "documentation",
            query: { reticulum: encodeURIComponent(malicious) },
        });
    });

    it("does not treat javascript: prefix as docs link", () => {
        const push = vi.fn();
        App.methods.handleProtocolLink.call({ $router: { push } }, "javascript:meshchatnext://docs?reticulum=x");
        expect(push).not.toHaveBeenCalledWith(expect.objectContaining({ name: "documentation" }));
    });

    it("fuzz random query tails without throwing", () => {
        const push = vi.fn();
        for (let i = 0; i < 40; i++) {
            const tail = `x=${encodeURIComponent(`${i}\u0000<script>`)}`;
            expect(() =>
                App.methods.handleProtocolLink.call({ $router: { push } }, `meshchatnext://docs?${tail}`)
            ).not.toThrow();
        }
    });

    it("onWebsocketMessage docs_view navigates like handleProtocolLink", async () => {
        const push = vi.fn().mockResolvedValue(undefined);
        const handled = await handleLxmIngestUriResult(
            {
                type: "lxm.ingest_uri.result",
                status: "success",
                ingest_type: "docs_view",
                message: "Opening documentation.",
                docs_query: { reticulum: "manual/interfaces.html#x" },
            },
            { router: { push }, toast: ToastUtils }
        );
        expect(handled).toBe(true);
        expect(push).toHaveBeenCalledWith({
            name: "documentation",
            query: { reticulum: encodeURIComponent("manual/interfaces.html#x") },
        });
        expect(ToastUtils.info).toHaveBeenCalled();
    });

    it("onWebsocketMessage docs_view without docs_query opens documentation index", async () => {
        const push = vi.fn().mockResolvedValue(undefined);
        const handled = await handleLxmIngestUriResult(
            {
                type: "lxm.ingest_uri.result",
                status: "success",
                ingest_type: "docs_view",
                message: "Opening documentation.",
            },
            { router: { push }, toast: ToastUtils }
        );
        expect(handled).toBe(true);
        expect(push).toHaveBeenCalledWith({ name: "documentation" });
    });
});
