import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import VectorSource from "ol/source/Vector";
import Feature from "ol/Feature";
import LineString from "ol/geom/LineString";
import Form from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreTeamShapeForm.vue";
let wrapper;
const owner = "a1".repeat(32),
    team = { channel_id: "c3".repeat(32), color: 0, route_methods: ["Walking"], geofences: ["Off", "Entry"] };
function setup() {
    const feature = new Feature(
        new LineString([
            [0, 0],
            [100, 100],
        ])
    );
    const source = new VectorSource({ features: [feature] });
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { bytes: 40, limit: 163, vertices: 2 } } }) };
    wrapper = mount(Form, { props: { owner, team, source, canSend: true } });
    return { feature, source };
}
const button = (name) => wrapper.findAll("button").find((b) => b.text() === name);
async function choose() {
    const option = wrapper.find('select option[value]:not([value=""])');
    await wrapper.find("select").setValue(option.attributes("value"));
}
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
describe("MeshCore shape size preview", () => {
    it("never transmits on selection, requires a current size check, and invalidates it after edits", async () => {
        const { feature } = setup();
        await choose();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(button("Share drawing").attributes("disabled")).toBeDefined();
        await button("Check size").trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls[0][0]).toContain("team-shape-preview");
        await button("Share drawing").trigger("click");
        expect(wrapper.emitted("send")).toHaveLength(1);
        feature.getGeometry().setCoordinates([
            [0, 0],
            [200, 200],
        ]);
        await flushPromises();
        expect(button("Share drawing").attributes("disabled")).toBeDefined();
        await button("Share drawing").trigger("click");
        expect(wrapper.emitted("send")).toHaveLength(1);
    });
    it("ignores a late preview from another channel and clears removed selections", async () => {
        const { feature, source } = setup();
        await choose();
        let resolve;
        window.api.post.mockImplementation(
            () =>
                new Promise((r) => {
                    resolve = r;
                })
        );
        await button("Check size").trigger("click");
        await wrapper.setProps({ team: { ...team, channel_id: "d4".repeat(32) } });
        resolve({ data: { result: { bytes: 40, limit: 163, vertices: 2 } } });
        await flushPromises();
        expect(button("Share drawing").attributes("disabled")).toBeDefined();
        source.removeFeature(feature);
        await flushPromises();
        expect(button("Share drawing")).toBeUndefined();
    });
});
