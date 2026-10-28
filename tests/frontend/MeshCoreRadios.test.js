import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { h } from "vue";
import MeshCoreRadios from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreRadios.vue";
import { useMeshCoreUi, meshcoreRoute } from "../../meshchatnext/src/frontend/js/meshcoreUi";
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.restoreAllMocks();
});
const radios = [
    {
        id: "default",
        label: "Home radio",
        connected: true,
        auto_reconnect: true,
        connection: { kind: "usb", target: "/dev/serial/by-id/home" },
    },
    {
        id: "b".repeat(32),
        label: "Portable radio",
        connected: false,
        auto_reconnect: true,
        connection: { kind: "ble", target: "AA:BB:CC:DD:EE:FF" },
    },
];
function setup() {
    const action = vi.fn().mockResolvedValue({});
    wrapper = mount(MeshCoreRadios, {
        props: { snapshot: { radios, radio_id: "default", inbox_mode: "combined" }, action },
    });
    return action;
}
describe("multiple MeshCore radios", () => {
    it("lets the user choose a saved inbox view without disconnecting radios", async () => {
        const action = setup();
        await wrapper.get('[aria-label="MeshCore inbox view"]').setValue("separate");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("radio-configure", { view: "separate" });
        expect(wrapper.text()).toContain("Every enabled radio receives and reconnects independently");
        expect(wrapper.text()).toContain("Portable radio");
    });
    it("disables only the named radio and preserves the other radio", async () => {
        const action = setup();
        await wrapper
            .findAll("button")
            .find((button) => button.text() === "Disable radio")
            .trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("radio-enabled", { radio_id: "default", enabled: false });
        expect(action).not.toHaveBeenCalledWith("disconnect", expect.anything());
    });
    it("saves a second radio with receiving and reconnect enabled", async () => {
        const action = setup();
        const form = wrapper.get("[data-add-meshcore-radio]");
        await form.findAll("input")[0].setValue("Field radio");
        await form.findAll("input")[1].setValue("11:22:33:44:55:66");
        await form.trigger("submit");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("radio-add", {
            kind: "ble",
            target: "11:22:33:44:55:66",
            label: "Field radio",
            receive: true,
            auto_reconnect: true,
        });
    });
    it("keeps the editor inside only the selected radio card and selects a card before opening it", async () => {
        const action = vi.fn().mockResolvedValue({});
        wrapper = mount(MeshCoreRadios, {
            props: { snapshot: { radios, radio_id: "default", inbox_mode: "combined" }, action },
            slots: { default: "<div data-editor-check>Identity and Radio2 editor</div>" },
        });
        expect(wrapper.findAll("[data-radio-settings]")).toHaveLength(1);
        expect(wrapper.get('[data-meshcore-radio="default"] [data-editor-check]').exists()).toBe(true);
        const other = wrapper.get(`[data-meshcore-radio="${"b".repeat(32)}"]`);
        expect(other.find("[data-editor-check]").exists()).toBe(false);
        await other.get("summary").trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("radio-configure", { active: "b".repeat(32) });
        await wrapper.setProps({ snapshot: { radios, radio_id: "b".repeat(32), inbox_mode: "combined" } });
        expect(wrapper.findAll("[data-radio-settings]")).toHaveLength(1);
        expect(other.find("[data-editor-check]").exists()).toBe(true);
        expect(wrapper.get('[data-meshcore-radio="default"]').find("[data-editor-check]").exists()).toBe(false);
    });

    it("routes a conversation and send explicitly to its chosen radio", async () => {
        const peer = "c3".repeat(32),
            owner = "b2".repeat(32),
            radio = "b".repeat(32);
        const router = createRouter({
            history: createMemoryHistory(),
            routes: [{ name: "messages", path: "/messages", component: { render: () => h("div") } }],
        });
        await router.push(meshcoreRoute(peer, radio));
        window.api = {
            get: vi.fn().mockResolvedValue({
                data: { result: { available: true, connected: true, owner, contacts: [], radio_id: radio } },
            }),
            post: vi.fn().mockResolvedValue({ data: { result: {} } }),
        };
        let ui;
        wrapper = mount(
            {
                setup() {
                    ui = useMeshCoreUi(() => peer);
                    return () => h("div");
                },
            },
            { global: { plugins: [router] } }
        );
        await flushPromises();
        expect(window.api.get.mock.calls[0][1].params).toEqual({ peer, radio });
        await ui.action("message", { peer, text: "Test" });
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/message",
            { peer, text: "Test", expected_owner: owner },
            { params: { radio } }
        );
    });
});
