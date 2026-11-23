import { describe, it, expect } from "vitest";
import MicronParser from "@/js/MicronParser";

function page(attributes = 'class="Mu-nl" role="link" tabindex="0"', plain = "Download sample") {
    const root = document.createElement("div");
    root.innerHTML = `<a href="#" data-action="openNode" data-destination=":/file/sample.txt" ${attributes}><span aria-hidden="true">Visible font glyphs</span><span class="Mu-sr"></span></a>`;
    root.querySelector(".Mu-sr").textContent = plain;
    return root;
}

describe("Nomad accessible link bounds", () => {
    it("names the existing WASM link itself instead of its clipped trailing child", () => {
        const root = page();
        MicronParser.enhanceA11y(root);
        const link = root.querySelector("a");
        expect(link.getAttribute("aria-label")).toBe("Download sample");
        expect(link.querySelector(".Mu-sr").getAttribute("aria-hidden")).toBe("true");
        expect(link.getAttribute("role")).toBe("link");
        expect(link.getAttribute("tabindex")).toBe("0");
        expect(link.getAttribute("data-destination")).toBe(":/file/sample.txt");
    });
    it("keeps an explicitly supplied accessible name", () => {
        const root = page('class="Mu-nl" aria-label="Explicit name"');
        MicronParser.enhanceA11y(root);
        expect(root.querySelector("a").getAttribute("aria-label")).toBe("Explicit name");
        expect(root.querySelector(".Mu-sr").getAttribute("aria-hidden")).toBe("true");
    });
    it("preserves label references and keyboard activation", () => {
        const root = page('class="Mu-nl" aria-labelledby="label" tabindex="3"');
        MicronParser.enhanceA11y(root);
        expect(root.querySelector("a").getAttribute("aria-labelledby")).toBe("label");
        expect(root.querySelector("a").getAttribute("aria-label")).toBeNull();
        expect(root.querySelector("a").getAttribute("tabindex")).toBe("3");
    });
    it("does not treat unrelated anchors as generated Nomad links", () => {
        const root = page('class="unrelated"');
        root.querySelector("a").removeAttribute("data-action");
        MicronParser.enhanceA11y(root);
        expect(root.querySelector("a").getAttribute("aria-label")).toBeNull();
        expect(root.querySelector(".Mu-sr").getAttribute("aria-hidden")).toBeNull();
    });
    it("keeps labels as text and is idempotent without changing visible markup", () => {
        const text = '<img src=x onerror="bad()"> & sample';
        const root = page(undefined, text);
        const visible = root.querySelector('span[aria-hidden="true"]').outerHTML;
        MicronParser.enhanceA11y(root);
        MicronParser.enhanceA11y(root);
        expect(root.querySelector("a").getAttribute("aria-label")).toBe(text);
        expect(root.querySelector("img")).toBeNull();
        expect(root.querySelector('span[aria-hidden="true"]').outerHTML).toBe(visible);
        expect(root.querySelector("a").getAttribute("href")).toBe("#");
    });
});
