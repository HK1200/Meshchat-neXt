import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import { createRouter, createMemoryHistory } from "vue-router";
import Directory from "../../meshchatnext/src/frontend/components/layout/SidebarSettingsDirectory.vue";
async function setup(path = "/messages") {
    const router = createRouter({
        history: createMemoryHistory(),
        routes: [
            { path: "/settings/sip", name: "sip-settings", component: { template: "<div/>" } },
            { path: "/settings/features", name: "feature-settings", component: { template: "<div/>" } },
            { path: "/messages", name: "messages", component: { template: "<div/>" } },
            { path: "/settings", name: "settings", component: { template: "<div/>" } },
            { path: "/settings/meshcore", name: "meshcore-settings", component: { template: "<div/>" } },
        ],
    });
    await router.push(path);
    await router.isReady();
    return { router, wrapper: mount(Directory, { global: { plugins: [router], stubs: { RouterLink: false } } }) };
}
describe("sidebar Settings directory", () => {
    it("toggles without navigation and lists Reticulum before MeshCore", async () => {
        const { router, wrapper } = await setup();
        expect(wrapper.findAll("a")).toHaveLength(0);
        await wrapper.get("button").trigger("click");
        expect(router.currentRoute.value.name).toBe("messages");
        expect(wrapper.findAll("a").map((a) => a.text())).toEqual(["App features", "Reticulum", "MeshCore", "SIP"]);
        await wrapper.findAll("a")[1].trigger("click");
        await flushPromises();
        expect(router.currentRoute.value.name).toBe("settings");
        await wrapper.get("button").trigger("click");
        expect(wrapper.findAll("a")).toHaveLength(0);
        expect(router.currentRoute.value.name).toBe("settings");
        wrapper.unmount();
    });
    it("reveals a directly opened MeshCore settings child and supports compact navigation", async () => {
        const { wrapper } = await setup("/settings/meshcore");
        expect(wrapper.get("button").attributes("aria-expanded")).toBe("true");
        await wrapper.setProps({ collapsed: true });
        expect(wrapper.get('[aria-label="Reticulum settings"]').exists()).toBe(true);
        expect(wrapper.get('[aria-label="MeshCore settings"]').exists()).toBe(true);
        wrapper.unmount();
    });
});
