import { afterEach, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import Route from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreMessageRoute.vue";
const state = vi.hoisted(() => ({ route: null, snapshot: null, push: vi.fn() }));
vi.mock("vue-router", () => ({ useRouter: () => ({ currentRoute: state.route, replace: vi.fn(), push: state.push }) }));
vi.mock("../../meshchatnext/src/frontend/js/meshcoreUi", () => ({
    useMeshCoreUi: () => ({ snapshot: state.snapshot }),
}));
let w;
afterEach(() => w?.unmount());
it("maps only adjacent known points, never bridges missing hops, and clears a changed identity", async () => {
    const owner = "a1".repeat(32);
    state.route = ref({ name: "map", query: { mcMessage: "one", mcOwner: owner, mcTarget: "b2".repeat(32), mcKind: "direct" } });
    state.snapshot = ref({ owner });
    window.api = {
        get: vi.fn().mockResolvedValue({
            data: {
                result: {
                    routes: [
                        {
                            route: "flood",
                            points: [
                                { order: 0, name: "Sender", latitude: 0, longitude: 0 },
                                { order: 1, name: "Repeater", latitude: 0, longitude: 0.1 },
                                { order: 3, name: "Receiver", latitude: 0, longitude: 0.3 },
                            ],
                        },
                    ],
                },
            },
        }),
    };
    const fit = vi.fn(),
        map = { addLayer: vi.fn(), removeLayer: vi.fn(), getView: () => ({ fit }) };
    w = mount(Route, { props: { map, active: true } });
    await flushPromises();
    const layer = map.addLayer.mock.calls[0][0],
        features = layer.getSource().getFeatures();
    expect(features.filter((f) => f.getGeometry().getType() === "Point")).toHaveLength(3);
    expect(features.filter((f) => f.getGeometry().getType() === "LineString")).toHaveLength(1);
    expect(fit).toHaveBeenCalled();
    await w.get('[aria-label="Back to message"]').trigger("click");
    expect(state.push).toHaveBeenCalledWith({name:"messages",query:{meshcore:"b2".repeat(32)}});
    state.snapshot.value = { owner: "c3".repeat(32) };
    await flushPromises();
    expect(layer.getSource().getFeatures()).toHaveLength(0);
    expect(w.text()).toContain("identity changed");
    w.unmount();
    expect(map.removeLayer).toHaveBeenCalledWith(layer);
});
