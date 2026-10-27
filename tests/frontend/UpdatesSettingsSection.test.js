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

it("offers native installation without removing the manual APK fallback", async () => {
    const staged = { ...pending, kind: "apk", sha256: "a".repeat(64), size: 123 };
    window.MeshchatNextAndroid = {
        installVerifiedUpdate: vi.fn(() => JSON.stringify({ accepted: true })),
        updateInstallStatus: () =>
            JSON.stringify({ sha256: staged.sha256, state: "cancelled", message: "Installation was cancelled." }),
    };
    window.api = {
        get: vi.fn(async (url) => ({ data: url.endsWith("/pending") ? { pending: staged } : { enabled: true } })),
    };
    const w = mount(UpdatesSettingsSection, { global: { mocks: { $t: (key) => key } } });
    try {
        await flushPromises();
        expect(w.text()).toContain("Installation was cancelled.");
        expect(w.find("a[download]").exists()).toBe(true);
        await w
            .findAll("button")
            .find((b) => b.text() === "Install update")
            .trigger("click");
        expect(window.MeshchatNextAndroid.installVerifiedUpdate).toHaveBeenCalledWith(JSON.stringify(staged));
        expect(w.text()).toContain("Android will ask you to approve");
    } finally {
        w.unmount();
        delete window.MeshchatNextAndroid;
    }
});

it("reports a background native handoff rejection without claiming installation", async () => {
    const staged = { ...pending, kind: "apk", sha256: "b".repeat(64), size: 123 };
    window.MeshchatNextAndroid = {
        installVerifiedUpdate: () =>
            JSON.stringify({ accepted: false, message: "Return to the app and tap Install update." }),
        updateInstallStatus: () => "{}",
    };
    window.api = {
        get: vi.fn(async (url) => ({ data: url.endsWith("/pending") ? { pending: staged } : { enabled: true } })),
    };
    const w = mount(UpdatesSettingsSection, { global: { mocks: { $t: (key) => key } } });
    try {
        await flushPromises();
        await w
            .findAll("button")
            .find((b) => b.text() === "Install update")
            .trigger("click");
        expect(w.text()).toContain("Return to the app and tap Install update.");
        expect(w.text()).not.toContain("updated successfully");
    } finally {
        w.unmount();
        delete window.MeshchatNextAndroid;
    }
});

it("detects a native bridge which becomes ready after the settings page mounted", async () => {
    vi.useFakeTimers();
    delete window.MeshchatNextAndroid;
    const staged = { ...pending, kind: "apk", sha256: "c".repeat(64), size: 123 };
    window.api = {
        get: vi.fn(async (url) => ({ data: url.endsWith("/pending") ? { pending: staged } : { enabled: true } })),
    };
    const w = mount(UpdatesSettingsSection, { global: { mocks: { $t: (key) => key } } });
    try {
        await flushPromises();
        expect(w.findAll("button").some((b) => b.text() === "Install update")).toBe(false);
        window.MeshchatNextAndroid = { installVerifiedUpdate: vi.fn(), updateInstallStatus: () => "{}" };
        await vi.advanceTimersByTimeAsync(1000);
        expect(w.findAll("button").some((b) => b.text() === "Install update")).toBe(true);
    } finally {
        w.unmount();
        delete window.MeshchatNextAndroid;
        vi.useRealTimers();
    }
});

it("does not hide a different staged update behind a previous installed status", async () => {
    let staged = { ...pending, kind: "apk", sha256: "d".repeat(64), size: 123 };
    window.MeshchatNextAndroid = {
        installVerifiedUpdate: vi.fn(),
        updateInstallStatus: () => JSON.stringify({ sha256: "d".repeat(64), state: "installed", message: "Installed" }),
    };
    window.api = {
        get: vi.fn(async (url) => ({ data: url.endsWith("/pending") ? { pending: staged } : { enabled: true } })),
    };
    const w = mount(UpdatesSettingsSection, { global: { mocks: { $t: (key) => key } } });
    try {
        await flushPromises();
        expect(w.findAll("button").some((b) => b.text() === "Install update")).toBe(false);
        staged = { ...staged, sha256: "e".repeat(64) };
        await w.vm.refresh();
        await flushPromises();
        expect(w.findAll("button").some((b) => b.text() === "Install update")).toBe(true);
    } finally {
        w.unmount();
        delete window.MeshchatNextAndroid;
    }
});

it("prefers deb updates for a packaged Linux install", async () => {
    window.electron = { getPlatform: () => "linux" };
    const w = section();
    await flushPromises();
    w.vm.checkResult = {
        appimage_install: false,
        artifacts: [
            { file: "next.AppImage", kind: "appimage" },
            { file: "next.deb", kind: "deb" },
        ],
    };
    expect(w.vm.downloadable.map((a) => a.kind)).toEqual(["deb", "appimage"]);
    w.vm.checkResult.appimage_install = true;
    expect(w.vm.downloadable.map((a) => a.kind)).toEqual(["appimage"]);
    w.unmount();
});
