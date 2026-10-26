import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Details from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreMessageDetails.vue";
import Attachments from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreAttachments.vue";
const push = vi.hoisted(() => vi.fn());
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));
let w;
const owner = "a1".repeat(32),
    target = "b2".repeat(32);
const modal = { props: ["modelValue"], template: '<div v-if="modelValue"><slot/></div>' };
beforeEach(() => {
    window.api = {
        get: vi.fn().mockResolvedValue({
            data: {
                result: {
                    owner,
                    id: "one",
                    kind: "direct",
                    target,
                    direction: "out",
                    state: "accepted",
                    reported_hops: null,
                    routes: [],
                    heard_repeats: 2,
                    note: "Observed only",
                },
            },
        }),
    };
});
afterEach(() => {
    w?.unmount();
    vi.useRealTimers();
    vi.clearAllMocks();
});
it("loads only the selected message and can show unknown-path history honestly", async () => {
    w = mount(Details, { props: { owner, target, kind: "direct" }, global: { stubs: { AppModal: modal } } });
    expect(window.api.get).not.toHaveBeenCalled();
    await w.setProps({ row: { id: "one" } });
    await flushPromises();
    expect(window.api.get).toHaveBeenCalledWith("/api/v1/meshcore/message-details", {
        params: { owner, kind: "direct", target, id: "one" },
    });
    expect(w.text()).toContain("No full packet path was captured");
    expect(w.text()).toContain("2 matching repeats");
});
it("combines attachment controls into one row and unmounts the old draft on switch/close", async () => {
    w = mount(Attachments, {
        props: { owner, peer: target, connected: true },
        global: { stubs: { AppModal: modal, MeshCoreImageComposer: true, MeshCoreVoiceComposer: true } },
    });
    expect(w.find("mesh-core-image-composer-stub").exists()).toBe(false);
    await w
        .findAll("button")
        .find((b) => b.text() === "Photo")
        .trigger("click");
    expect(w.find("mesh-core-image-composer-stub").exists()).toBe(true);
    await w
        .findAll("button")
        .find((b) => b.text() === "Voice clip")
        .trigger("click");
    expect(w.find("mesh-core-image-composer-stub").exists()).toBe(false);
    expect(w.find("mesh-core-voice-composer-stub").exists()).toBe(true);
    await w.get('[aria-label="Close attachments"]').trigger("click");
    expect(w.find("mesh-core-voice-composer-stub").exists()).toBe(false);
});

it("explains an unmappable outgoing observation without presenting an inactive map button", async () => {
    const response = await window.api.get();
    response.data.result.kind = "channel";
    response.data.result.routes = [{ route: "flood", hash_bytes: 1, received: 1, hops: [], points: [] }];
    w = mount(Details, {
        props: { owner, target, kind: "channel", row: { id: "one" } },
        global: { stubs: { AppModal: modal } },
    });
    await flushPromises();
    expect(w.text()).toContain(
        "Map unavailable: no nodes in this captured packet have unambiguous reported locations."
    );
    expect(w.text()).toContain("Sent messages need a matching received copy");
    expect(w.findAll("button").some((button) => button.text() === "View captured route on map")).toBe(false);
});
it("opens an outgoing captured observation when it has a reported location", async () => {
    const response = await window.api.get();
    response.data.result.kind = "channel";
    response.data.result.routes = [
        {
            route: "flood",
            hash_bytes: 1,
            received: 1,
            hops: [],
            points: [{ peer: owner, latitude: 48, longitude: -122, order: 0 }],
        },
    ];
    w = mount(Details, {
        props: { owner, target, kind: "channel", row: { id: "one" } },
        global: { stubs: { AppModal: modal } },
    });
    await flushPromises();
    await w
        .findAll("button")
        .find((button) => button.text() === "View captured route on map")
        .trigger("click");
    expect(w.emitted("close")).toHaveLength(1);
    expect(push).toHaveBeenCalledWith({
        name: "map",
        query: {
            mcMessage: "one",
            mcOwner: owner,
            mcTarget: target,
            mcKind: "channel",
            mcObservation: "0",
        },
    });
});
