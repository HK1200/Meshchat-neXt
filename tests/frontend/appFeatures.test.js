import { beforeEach, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import {
    appFeatures,
    FEATURES_KEY,
    normalizeFeatures,
    setAppFeature,
    featureRouteAllowed,
    featureNavAllowed,
} from "../../meshchatnext/src/frontend/js/appFeatures";
import FeatureSettingsPage from "../../meshchatnext/src/frontend/components/settings/FeatureSettingsPage.vue";
import SidebarSettingsDirectory from "../../meshchatnext/src/frontend/components/layout/SidebarSettingsDirectory.vue";
beforeEach(() => {
    localStorage.clear();
    Object.assign(appFeatures, normalizeFeatures(null));
});
it("preserves existing installations by defaulting all three features on", () => {
    expect(normalizeFeatures(null)).toEqual({ reticulum: true, meshcore: true, sip: true });
    expect(normalizeFeatures({ reticulum: false, meshcore: "false", unknown: false })).toEqual({
        reticulum: false,
        meshcore: true,
        sip: true,
    });
});
it.each(Array.from({ length: 8 }, (_, bits) => [bits]))(
    "keeps feature settings reachable for combination %s",
    (bits) => {
        Object.assign(appFeatures, { reticulum: !!(bits & 1), meshcore: !!(bits & 2), sip: !!(bits & 4) });
        expect(featureRouteAllowed({ name: "feature-settings" })).toBe(true);
        expect(featureNavAllowed({ id: "settings" })).toBe(true);
        expect(featureNavAllowed({ id: "relay-chat" })).toBe(appFeatures.reticulum);
        expect(featureRouteAllowed({ name: "meshcore-channels" })).toBe(appFeatures.meshcore);
        expect(featureRouteAllowed({ name: "call", query: { network: "sip" } })).toBe(appFeatures.sip);
        expect(featureRouteAllowed({ name: "messages", query: { meshcore: "a".repeat(64) } })).toBe(
            appFeatures.meshcore
        );
        expect(featureRouteAllowed({ name: "interfaces.edit" })).toBe(appFeatures.reticulum);
        expect(featureRouteAllowed({ name: "rnpath" })).toBe(appFeatures.reticulum);
    }
);
it("switches persist independently without altering account or message storage", async () => {
    localStorage.setItem("saved-account", "keep");
    const wrapper = mount(FeatureSettingsPage, { global: { stubs: { UpdatesSettingsSection: true } } });
    const switches = wrapper.findAll('[role="switch"]');
    await switches[1].setValue(false);
    expect(appFeatures).toEqual({ reticulum: true, meshcore: false, sip: true });
    expect(JSON.parse(localStorage.getItem(FEATURES_KEY))).toEqual({ ...appFeatures });
    expect(localStorage.getItem("saved-account")).toBe("keep");
    expect(wrapper.get('[role="status"]').text()).toBe("Saved");
    wrapper.unmount();
});
it("does not apply an unsaved choice when storage fails", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("full");
    });
    expect(() => setAppFeature("sip", false)).toThrow();
    expect(appFeatures.sip).toBe(true);
    spy.mockRestore();
});
it("keeps the settings directory available with no network features", async () => {
    Object.assign(appFeatures, { reticulum: false, meshcore: false, sip: false });
    const wrapper = mount(SidebarSettingsDirectory, {
        global: { stubs: { RouterLink: { template: "<a><slot/></a>" }, MaterialDesignIcon: true } },
    });
    await wrapper.get("button").trigger("click");
    expect(wrapper.text()).toContain("App features");
    expect(wrapper.text()).not.toContain("Reticulum");
    expect(wrapper.text()).not.toContain("MeshCore");
    wrapper.unmount();
});
it("updates other open windows from persisted choices", () => {
    localStorage.setItem(FEATURES_KEY, JSON.stringify({ sip: false }));
    window.dispatchEvent(new StorageEvent("storage", { key: FEATURES_KEY }));
    expect(appFeatures.sip).toBe(false);
    expect(appFeatures.reticulum).toBe(true);
});

it("keeps application updates reachable when every communication feature is disabled", () => {
    const previous = { ...appFeatures };
    Object.assign(appFeatures, { reticulum: false, meshcore: false, sip: false });
    expect(
        featureRouteAllowed({ name: "feature-settings", path: "/settings/features", query: { section: "updates" } })
    ).toBe(true);
    Object.assign(appFeatures, previous);
});
