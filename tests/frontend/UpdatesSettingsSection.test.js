import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import UpdatesSettingsSection from "@/components/settings/sections/UpdatesSettingsSection.vue";

const pending = { file: "app.apk", path: "/private/app.apk", version: "2", apply: { mode: "manual" } };
function section() {
    window.api = { get: vi.fn(async (url) => ({ data: url.endsWith("/pending") ? { pending } : { enabled: true } })) };
    return mount(UpdatesSettingsSection, { global: { mocks: { $t: (key) => key } } });
}
afterEach(() => {
    delete window.api;
    delete window.electron;
});

describe("Staged updates", () => {
    it("offers a verified download on Android instead of an inert desktop button", async () => {
        delete window.electron;
        const w = section();
        await flushPromises();
        expect(w.find("a[download]").attributes("href")).toBe("/api/v1/update/payload");
        expect(w.find("a[download]").attributes("download")).toBe("app.apk");
        expect(w.text()).not.toContain("updates.show_file");
        w.unmount();
    });
    it("retains Electron's show-in-folder action", async () => {
        window.electron = { showPathInFolder: vi.fn() };
        const w = section();
        await flushPromises();
        expect(w.find("a[download]").exists()).toBe(false);
        await w
            .findAll("button")
            .find((button) => button.text() === "updates.show_file")
            .trigger("click");
        expect(window.electron.showPathInFolder).toHaveBeenCalledWith("/private/app.apk");
        w.unmount();
    });
});
