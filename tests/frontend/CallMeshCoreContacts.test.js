import { ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CallMeshCoreContacts from "../../meshchatnext/src/frontend/components/call/tabs/CallMeshCoreContacts.vue";
const peer = "ab".repeat(32);
let snapshot, action, wrapper;
vi.mock("../../meshchatnext/src/frontend/js/meshcoreUi", () => ({
    useMeshCoreUi: () => ({ snapshot, error: ref(""), action }),
    meshcoreRoute: (key) => ({ name: "messages", query: { meshcore: key } }),
}));
function start(props = {}) {
    wrapper = mount(CallMeshCoreContacts, {
        props,
        global: {
            mocks: { $t: (key) => key },
            stubs: { RouterLink: { props: ["to"], template: '<a :data-peer="to.query.meshcore"><slot /></a>' } },
        },
    });
    return wrapper;
}
beforeEach(() => {
    snapshot = ref({
        available: true,
        connected: true,
        contacts: [{ peer, name: "Alice", kind: 1, active: 1 }],
        announces: [
            { peer: "cd".repeat(32), name: "Bob", kind: 1 },
            { peer: "ef".repeat(32), name: "Repeater", kind: 2 },
        ],
    });
    action = vi.fn().mockResolvedValue({});
});
afterEach(() => wrapper?.unmount());
describe("MeshCore contacts in Telephone", () => {
    it("labels MeshCore and exposes messaging rather than an unsupported call button", () => {
        start();
        expect(wrapper.text()).toContain("MeshCore");
        expect(wrapper.text()).toContain("Live MeshCore calls are not available");
        expect(wrapper.find("a").attributes("data-peer")).toBe(peer);
        expect(wrapper.findAll("button").some((b) => b.text() === "Call")).toBe(false);
    });
    it("searches saved contacts by name and complete public key", async () => {
        start();
        await wrapper.find("input").setValue("unknown");
        expect(wrapper.findAll("li")).toHaveLength(0);
        await wrapper.find("input").setValue(peer.toUpperCase());
        expect(wrapper.findAll("li")).toHaveLength(1);
    });
    it("shows user announces and adds only the explicitly selected user", async () => {
        start({ discovery: true });
        expect(wrapper.findAll("li")).toHaveLength(1);
        expect(wrapper.text()).not.toContain("Repeater");
        await wrapper.find("li button").trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledExactlyOnceWith("contact-add", { peer: "cd".repeat(32), name: "Bob" });
    });
    it("can discover users from the Contacts submenu", async () => {
        start();
        const button = wrapper.findAll("button").find((b) => b.text() === "Add from announces");
        await button.trigger("click");
        expect(wrapper.find("li").text()).toContain("Bob");
    });
    it("validates manual MeshCore keys and UTF-8 name limits before writing", async () => {
        start();
        await wrapper.findAll("button")[0].trigger("click");
        await wrapper.find('[aria-label="MeshCore contact name"]').setValue("Alice");
        await wrapper.find('[aria-label="MeshCore contact public key"]').setValue("short");
        await wrapper.find("form").trigger("submit");
        expect(action).not.toHaveBeenCalled();
        expect(wrapper.find('[role="alert"]').text()).toContain("public key");
        await wrapper.find('[aria-label="MeshCore contact public key"]').setValue("cd".repeat(32));
        await wrapper.find('[aria-label="MeshCore contact name"]').setValue("🇺🇸".repeat(5));
        await wrapper.find("form").trigger("submit");
        expect(action).not.toHaveBeenCalled();
    });
    it("adds a manual public key through MeshCore without creating a Reticulum contact", async () => {
        start();
        await wrapper.findAll("button")[0].trigger("click");
        await wrapper.find('[aria-label="MeshCore contact name"]').setValue("Bob");
        await wrapper.find('[aria-label="MeshCore contact public key"]').setValue("CD".repeat(32));
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(action).toHaveBeenCalledExactlyOnceWith("contact-add", { peer: "cd".repeat(32), name: "Bob" });
        expect(wrapper.find("form").exists()).toBe(false);
    });
    it("prevents writes while disconnected and hides inactive contacts", async () => {
        snapshot.value.connected = false;
        snapshot.value.contacts[0].active = 0;
        start({ discovery: true });
        expect(wrapper.find("li button").attributes("disabled")).toBeDefined();
        await wrapper.find("li button").trigger("click");
        expect(action).not.toHaveBeenCalled();
    });
    it("shows a recoverable error when the radio does not confirm addition", async () => {
        action.mockRejectedValue(new Error("unconfirmed"));
        start({ discovery: true });
        await wrapper.find("li button").trigger("click");
        await flushPromises();
        expect(wrapper.find('[role="alert"]').text()).toContain("Could not add");
        expect(wrapper.find("li button").attributes("disabled")).toBeUndefined();
    });
});
