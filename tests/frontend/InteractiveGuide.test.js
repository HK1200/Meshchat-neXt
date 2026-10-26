import { readFileSync } from "node:fs";
import { beforeEach, afterEach, it, expect, vi } from "vitest";
const dir = process.cwd() + "/docs/guide/";
const read = (file) => readFileSync(dir + file, "utf8");
const content = read("content.js"),
    script = read("guide.js");
beforeEach(() => {
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    localStorage.clear();
    document.body.innerHTML = read("index.html").replace(/<script[^>]*>[\s\S]*?<\/script>/g, "");
    window.history.replaceState({}, "", "#home");
    window.eval(content);
    window.eval(script);
});
afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
});
it("contains complete newcomer paths, article references and protocol limits", () => {
    const data = window.NEXT_GUIDE,
        ids = new Set(data.articles.map((a) => a.id));
    expect(ids.size).toBe(data.articles.length);
    expect(ids.size).toBeGreaterThan(25);
    for (const a of data.articles) for (const id of a.related) expect(ids.has(id)).toBe(true);
    for (const [, , id] of data.faqs) expect(ids.has(id)).toBe(true);
    for (const p of Object.values(data.paths)) for (const id of p.ids) expect(ids.has(id)).toBe(true);
    expect(document.querySelector("h1").textContent).toContain("Find your way");
    expect(document.querySelector('[role="img"]').getAttribute("aria-label")).toContain("No automatic bridge");
});
it("searches FAQs and topics locally and provides an empty-state recovery", () => {
    const input = document.getElementById("search");
    input.value = "offline map";
    input.dispatchEvent(new Event("input"));
    expect(document.getElementById("reader").textContent).toContain("offline");
    input.value = "zzzz-no-such-topic";
    input.dispatchEvent(new Event("input"));
    expect(document.getElementById("reader").textContent).toContain("No match");
});
it("stores checklist progress without device or account data", () => {
    window.history.replaceState({}, "", "#article/meshcore");
    window.dispatchEvent(new Event("hashchange"));
    const input = document.querySelector(".checklist input");
    input.checked = true;
    input.dispatchEvent(new Event("change"));
    expect(JSON.parse(localStorage.getItem("meshchat-next.guide-progress.v1"))).toEqual({ "meshcore:0": true });
    expect(document.querySelector("progress").value).toBe(1);
});
