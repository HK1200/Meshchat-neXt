import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { combineNetworkContacts, meshcoreRoute } from "../../meshchatnext/src/frontend/js/meshcoreUi";
import MeshCoreAnnounces from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreAnnounces.vue";
import MeshCoreThread from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreThread.vue";
import MeshCoreContactNetworks from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreContactNetworks.vue";

const peer = "b2".repeat(32),
    owner = "a1".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.restoreAllMocks();
});
describe("MeshCore network boundaries", () => {
    it("never joins contacts by name, only by an explicit persisted link", () => {
        const rns = [{ id: 1, name: "Same Name" }];
        const snapshot = { contacts: [{ peer, name: "Same Name" }], links: [] };
        expect(combineNetworkContacts(rns, snapshot)).toHaveLength(2);
        snapshot.links = [{ contact: 1, peer }];
        expect(combineNetworkContacts(rns, snapshot)).toHaveLength(1);
        expect(combineNetworkContacts(rns, snapshot)[0].meshcore_key).toBe(peer);
        expect(combineNetworkContacts([], snapshot)).toHaveLength(1);
    });
    it("uses a separate MeshCore route and clears any Reticulum destination", () => {
        expect(meshcoreRoute(peer)).toEqual({
            name: "messages",
            params: { destinationHash: "" },
            query: { meshcore: peer },
        });
        expect(() => meshcoreRoute("rns-hash")).toThrow();
    });
    it("links only after an explicit selection and click, carrying both account guards", async () => {
        window.api = { post: vi.fn().mockResolvedValue({ data: {} }) };
        wrapper = mount(MeshCoreContactNetworks, {
            props: {
                contact: { id: 1, name: "Same Name" },
                snapshot: { available: true, owner, contacts: [{ peer, name: "Same Name" }], links: [] },
            },
        });
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.find("select").setValue(peer);
        await wrapper.setProps({ snapshot: { ...wrapper.props("snapshot"), connected: false } });
        expect(wrapper.find("select").element.value).toBe(peer);
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.findAll("button")[0].trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/contact-link", {
            contact: 1,
            peer,
            expected_owner: owner,
        });
    });
    it("filters MeshCore discovery types and offers contact actions only for clients", async () => {
        const action = vi.fn().mockResolvedValue({});
        wrapper = mount(MeshCoreAnnounces, {
            props: {
                action,
                snapshot: {
                    connected: true,
                    announces: [
                        { peer, name: "Client", kind: 1, saved: 0 },
                        { peer: "c3".repeat(32), name: "Repeater", kind: 2, saved: 0 },
                        { peer: "d4".repeat(32), name: "Room", kind: 3, saved: 0 },
                    ],
                },
            },
        });
        expect(wrapper.findAll("article")).toHaveLength(3);
        expect(wrapper.findAll("article button")).toHaveLength(3);
        await wrapper.find("article button").trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("contact-add", { peer, name: "Client" });
        await wrapper.find('[aria-label="MeshCore device types"]').findAll("button")[2].trigger("click");
        expect(wrapper.findAll("article")).toHaveLength(1);
        expect(wrapper.find("article").text()).toContain("Repeater");
        expect(wrapper.find("article button").text()).toBe("Save Node");
        await wrapper.find("article button").trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("node-save", { peer: "c3".repeat(32) });
    });
    it("labels the composer and sends through MeshCore with a stable id across uncertain retries", async () => {
        const snapshot = {
            available: true,
            owner,
            connected: true,
            contacts: [{ peer, name: "Test" }],
            links: [],
            messages: [],
        };
        window.api = {
            get: vi.fn().mockResolvedValue({ data: { result: snapshot } }),
            post: vi.fn().mockRejectedValue(new Error("response lost")),
        };
        wrapper = mount(MeshCoreThread, { props: { peer }, global: { mocks: { $router: { push: vi.fn() } } } });
        await flushPromises();
        expect(wrapper.text()).toContain("Message via MeshCore");
        await wrapper.find("textarea").setValue("hello");
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        const calls = window.api.post.mock.calls;
        expect(calls).toHaveLength(2);
        expect(calls[0][0]).toBe("/api/v1/meshcore/message");
        expect(calls[0][1].expected_owner).toBe(owner);
        expect(calls[0][1].request_id).toBe(calls[1][1].request_id);
        expect(calls.every(([path]) => !path.includes("lxmf"))).toBe(true);
    });
});
