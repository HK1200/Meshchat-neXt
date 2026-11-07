import { ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MeshCoreNodesPage from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreNodesPage.vue";
import { copyTextToClipboard } from "../../meshchatnext/src/frontend/js/clipboardUtils";
vi.mock("../../meshchatnext/src/frontend/js/clipboardUtils", () => ({ copyTextToClipboard: vi.fn() }));
vi.mock("../../meshchatnext/src/frontend/js/ToastUtils", () => ({
    default: { success: vi.fn(), error: vi.fn() },
}));
let snapshot, action, wrapper;
const peer = "a1".repeat(32),
    sensor = "c3".repeat(32);
vi.mock("../../meshchatnext/src/frontend/js/meshcoreUi", () => ({
    useMeshCoreUi: () => ({ snapshot, error: ref(""), action, refresh: vi.fn() }),
    meshcoreNodeRoute: (peer) => ({ name: "meshcore-nodes", params: { peer } }),
}));
vi.mock("../../meshchatnext/src/frontend/js/meshcoreNotifications", () => ({
    useMeshCoreNotificationContext: vi.fn(),
}));
vi.mock("vue-router", async (original) => ({ ...(await original()), useRouter: () => ({ push: vi.fn() }) }));
function start(props = {}) {
    wrapper = mount(MeshCoreNodesPage, {
        props,
        global: {
            mocks: { $t: (k) => k },
            stubs: { MeshCoreNodeSession: true, RouterLink: { template: "<a><slot /></a>" }, MaterialDesignIcon: true },
        },
    });
}
beforeEach(() => {
    snapshot = ref({
        connected: true,
        nodes: [],
        announces: [
            { peer, name: "Tower", kind: 2 },
            { peer: sensor, name: "Weather", kind: 4 },
            { peer: "d4".repeat(32), name: "User", kind: 1 },
        ],
    });
    action = vi.fn().mockResolvedValue({ nodes: [{ peer, kind: 2 }] });
});
afterEach(() => {
    wrapper?.unmount();
    vi.unstubAllGlobals();
});
describe("Saved nodes discovery", () => {
    it("runs one explicit discovery and separates current replies from older announces", async () => {
        start();
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledExactlyOnceWith("node-discover", {});
        expect(wrapper.findAll("article")).toHaveLength(2);
        expect(wrapper.find(`[data-discovered-peer="${peer}"]`).text()).toContain("Replied to this scan");
        expect(wrapper.find(`[data-discovered-peer="${sensor}"]`).text()).toContain("Previously heard");
        expect(wrapper.text()).not.toContain("User");
    });
    it("filters sensors, searches names and saves only on explicit selection", async () => {
        start();
        await wrapper.findAll("button")[1].trigger("click");
        await wrapper.find('[aria-label="Discovered node types"]').findAll("button")[3].trigger("click");
        expect(wrapper.findAll("article")).toHaveLength(1);
        await wrapper.find("input").setValue("weather");
        await wrapper.find("article button").trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledExactlyOnceWith("node-save", { peer: sensor });
    });
    it("disables active discovery while disconnected but allows browsing heard nodes", async () => {
        snapshot.value.connected = false;
        start();
        expect(wrapper.find("button").attributes("disabled")).toBeDefined();
        await wrapper.findAll("button")[1].trigger("click");
        expect(wrapper.findAll("article")).toHaveLength(2);
        expect(action).not.toHaveBeenCalled();
    });
    it("shows an actionable request failure and releases the button", async () => {
        action.mockRejectedValue({
            response: { data: { message: "Wait 30 seconds between nearby discovery requests" } },
        });
        start();
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(wrapper.find('[role="status"]').text()).toContain("Wait 30");
        expect(wrapper.find("button").attributes("disabled")).toBeUndefined();
    });
    it("copies only the room name and public key when native sharing is unavailable", async () => {
        snapshot.value.nodes = [{ peer, name: "Trail chat", kind: 3, password: "must stay private" }];
        vi.stubGlobal("navigator", { share: undefined });
        copyTextToClipboard.mockResolvedValueOnce(true);
        start({ peer });
        await wrapper
            .findAll("button")
            .find((button) => button.text() === "Share room contact")
            .trigger("click");
        await flushPromises();
        expect(copyTextToClipboard).toHaveBeenCalledExactlyOnceWith(
            `MeshCore room server: Trail chat\nPublic key: ${peer}`
        );
        expect(action).not.toHaveBeenCalled();
    });
    it("does not show repeater login controls for a saved sensor", () => {
        snapshot.value.nodes = [{ peer: sensor, name: "Weather", kind: 4 }];
        start({ peer: sensor });
        expect(wrapper.text()).toContain("MeshCore · Sensor");
        expect(wrapper.findComponent({ name: "MeshCoreNodeSession" }).exists()).toBe(false);
    });
});
