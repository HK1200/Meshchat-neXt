import { mount } from "@vue/test-utils";
import { ref, nextTick } from "vue";
import { it, expect, vi } from "vitest";
import Tools from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreMapTools.vue";

const state = vi.hoisted(() => ({}));
vi.mock("vue-router", () => ({ useRouter: () => ({ currentRoute: { value: { query: {} } } }) }));
vi.mock("../../meshchatnext/src/frontend/js/map/useMeshCoreMapTraffic", () => ({
    useMeshCoreMapTraffic: (_options, gaps) => {
        state.gaps = gaps;
        return ref("");
    },
}));

it("uses one collapsed gap badge, expands on demand, and disappears when traffic clears", async () => {
    const map = { addLayer: vi.fn(), removeLayer: vi.fn(), on: vi.fn() };
    const wrapper = mount(Tools, { props: { map }, global: { stubs: { Teleport: true } } });
    try {
        expect(wrapper.find("details").exists()).toBe(false);
        state.gaps.value = [
            { key: "first", count: 2 },
            { key: "second", count: 1 },
        ];
        await nextTick();
        expect(wrapper.findAll("details")).toHaveLength(1);
        const badge = wrapper.get('details[aria-label="Unknown route gaps"]');
        expect(badge.element.open).toBe(false);
        expect(badge.get("summary").text()).toContain("? 2 gaps");
        badge.get("summary").element.click();
        expect(badge.element.open).toBe(true);
        expect(badge.text()).toContain("Gap 1: 2 unknown hops");
        badge.get("summary").element.click();
        expect(badge.element.open).toBe(false);
        state.gaps.value = [];
        await nextTick();
        expect(wrapper.find("details").exists()).toBe(false);
    } finally {
        wrapper.unmount();
    }
});
