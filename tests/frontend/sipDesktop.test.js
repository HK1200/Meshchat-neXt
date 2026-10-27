import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
let sip;
beforeEach(async () => {
    vi.resetModules();
    localStorage.clear();
    delete window.MeshchatNextAndroid;
    sip = await import("../../meshchatnext/src/frontend/js/sip.js");
});
afterEach(async () => {
    await flushPromises();
    delete window.api;
    delete window.MeshchatNextAndroid;
});
it("deduplicates desktop status polling while keeping the synchronous state contract", async () => {
    let resolve;
    window.api = { get: vi.fn(() => new Promise((r) => { resolve = r; })), post: vi.fn() };
    expect(sip.refreshSip()).toBe(sip.sipState);
    sip.refreshSip();
    expect(window.api.get).toHaveBeenCalledTimes(1);
    resolve({ data: { available: true, platform: "linux", feature_enabled: true, registered: true } });
    await flushPromises();
    expect(sip.sipState.registered).toBe(true);
    expect(window.api.post).not.toHaveBeenCalled();
});
it("uses the authenticated API client for Linux account actions", async () => {
    window.api = { post: vi.fn().mockResolvedValue({ data: { available: true, platform: "linux", selected: "account-one" } }) };
    await sip.sipCommand("connect", { id: "account-one" });
    expect(window.api.post).toHaveBeenCalledWith("/api/v1/sip/command", { op: "connect", id: "account-one" });
    expect(sip.sipState.selected).toBe("account-one");
});
it("propagates disabling the SIP feature to the Linux backend", async () => {
    Object.assign(sip.sipState, { platform: "linux", feature_enabled: true });
    window.api = { post: vi.fn().mockResolvedValue({ data: { platform: "linux", feature_enabled: false } }) };
    const { setAppFeature } = await import("../../meshchatnext/src/frontend/js/appFeatures.js");
    setAppFeature("sip", false);
    await flushPromises();
    expect(window.api.post).toHaveBeenCalledWith("/api/v1/sip/command", { op: "feature", enabled: false });
});
it("retains the Android native bridge without calling desktop endpoints", async () => {
    window.api = { get: vi.fn(), post: vi.fn() };
    window.MeshchatNextAndroid = {
        sipStatus: vi.fn(() => JSON.stringify({ available: true, registered: true })),
        sipCommand: vi.fn(() => JSON.stringify({ ok: true })),
    };
    sip.refreshSip();
    await sip.sipCommand("answer");
    expect(window.api.get).not.toHaveBeenCalled();
    expect(window.api.post).not.toHaveBeenCalled();
    expect(window.MeshchatNextAndroid.sipCommand).toHaveBeenCalledOnce();
});
