import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import Attachment from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreTeamAttachment.vue";
import { attachmentContacts } from "../../meshchatnext/src/frontend/js/meshcoreAttachments";
const owner = "a1".repeat(32),
    peer = "b2".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
function setup(contacts = []) {
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { wav_base64: "UklGRg==" } } }) };
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:clip");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    wrapper = mount(Attachment, {
        props: {
            owner,
            channelId: "c3".repeat(32),
            connected: true,
            contacts,
            item: {
                kind: "pin",
                alias: "b2b2b2b2",
                id: 1,
                attachment: { mode: 1, sid: "1234abcd", packets: 1, extra: 1 },
            },
        },
        global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
}
describe("Tactical attachment sender selection", () => {
    it("uses a unique saved MeshCore contact without manual key entry or implicit traffic", async () => {
        setup([{ peer, name: "Bravo", active: true }]);
        expect(wrapper.text()).toContain("From Bravo · MeshCore");
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls[0][1].peer).toBe(peer);
        expect(wrapper.find("audio").exists()).toBe(true);
    });
    it("requires a choice when short aliases collide", async () => {
        setup([
            { peer, name: "Bravo" },
            { peer: "b2b2b2b2" + "c3".repeat(28), name: "Other" },
        ]);
        expect(wrapper.find("select").exists()).toBe(true);
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(wrapper.text()).toContain("Select the sender");
    });
    it("offers contacts and an advanced fallback for unknown senders", () => {
        setup();
        expect(wrapper.text()).toContain("Find or add a MeshCore contact");
        expect(wrapper.text()).toContain("Advanced: use a full public key");
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("deduplicates saved keys and rejects malformed and inactive matches", () => {
        expect(
            attachmentContacts(
                [{ peer }, { peer }, { peer: "bad" }, { peer: "b2b2b2b2" + "c3".repeat(28), active: false }],
                "b2b2b2b2"
            )
        ).toEqual([{ peer }]);
        expect(attachmentContacts([{ peer }], "")).toEqual([]);
    });
});
