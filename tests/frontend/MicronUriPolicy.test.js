import { describe, expect, it } from "vitest";
import MicronParser from "../../meshchatnext/src/frontend/js/MicronParser";

function href(value) {
    const container = document.createElement("div");
    container.innerHTML = MicronParser.sanitizeRenderedMicronHtml(`<a href="${value}">fixture</a>`);
    return container.querySelector("a")?.getAttribute("href");
}

describe("Micron URI policy", () => {
    it("does not admit unknown schemes through a hyphen", () => {
        expect(href("unknown-scheme:fixture")).toBeNull();
        expect(href("javascript:alert(1)")).toBeNull();
    });

    it("preserves supported schemes and ordinary relative links", () => {
        for (const value of [
            "https://example.invalid/page",
            "nomadnetwork://example.invalid/page",
            "lxmf://00112233445566778899aabbccddeeff",
            "mailto:fixture@example.invalid",
            "docs/my-page.md",
        ]) {
            expect(href(value)).toBe(value);
        }
    });
});
