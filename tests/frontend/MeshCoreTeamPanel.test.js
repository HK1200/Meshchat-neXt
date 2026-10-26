import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import Panel from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreTeamPanel.vue";
const owner = "a1".repeat(32),
    channel = "c3".repeat(32);
let wrapper;
const team = () => ({
    enabled: true,
    channel_id: channel,
    callsign: "Alpha",
    role: 0,
    color: 0,
    status: 0,
    roles: ["Member"],
    colors: ["#00bcd4"],
    statuses: ["OK"],
    pin_kinds: ["Point"],
    alert_kinds: ["SOS"],
    records: [],
});
function setup(extra = {}) {
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { state: "submitted" } } }) };
    wrapper = mount(Panel, {
        props: {
            owner,
            team: team(),
            connected: true,
            supported: true,
            channels: [
                { channel_id: channel, kind: "private", name: "Team" },
                { channel_id: "public", kind: "public", name: "Public" },
            ],
            ...extra,
        },
    });
}
afterEach(() => {
    wrapper?.unmount();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});
const button = (label) => wrapper.findAll("button").find((b) => b.text() === label);
describe("MeshCore team sharing boundaries", () => {
    it("does not request location or transmit on mount, and offers only private channels", async () => {
        const locate = vi.fn();
        vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: locate } });
        setup();
        await flushPromises();
        expect(locate).not.toHaveBeenCalled();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(wrapper.findAll("select")[0].text()).toContain("Team");
        expect(wrapper.findAll("select")[0].text()).not.toContain("Public");
    });
    it("preserves unsaved callsign edits across polling", async () => {
        setup();
        const input = wrapper.find('input[maxlength="20"]');
        await input.setValue("Edited");
        await wrapper.setProps({ team: { ...team(), records: [{ kind: "position", alias: "01020304", heard: 123 }] } });
        expect(input.element.value).toBe("Edited");
    });
    it("drops a late location result when the radio identity changes", async () => {
        let resolveLocation;
        vi.stubGlobal("navigator", {
            geolocation: {
                getCurrentPosition: (resolve) => {
                    resolveLocation = resolve;
                },
            },
        });
        setup();
        await button("Share my position once").trigger("click");
        await wrapper.setProps({ owner: "b2".repeat(32), team: team() });
        resolveLocation({ coords: { latitude: 1, longitude: 2, accuracy: 5 } });
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("cancels a pending location share if the team channel changes", async () => {
        let resolveLocation;
        vi.stubGlobal("navigator", {
            geolocation: {
                getCurrentPosition: (resolve) => {
                    resolveLocation = resolve;
                },
            },
        });
        setup();
        await button("Share my position once").trigger("click");
        await wrapper.setProps({ team: { ...team(), channel_id: "e5".repeat(32) } });
        resolveLocation({ coords: { latitude: 1, longitude: 2, accuracy: 5 } });
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("cancels pending GPS when the effective channel scope changes", async () => {
        let resolveLocation;
        vi.stubGlobal("navigator", {
            geolocation: {
                getCurrentPosition: (resolve) => {
                    resolveLocation = resolve;
                },
            },
        });
        setup();
        await button("Share my position once").trigger("click");
        await wrapper.setProps({ defaultScope: "#region" });
        resolveLocation({ coords: { latitude: 1, longitude: 2, accuracy: 5 } });
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(wrapper.text()).toContain("Channel scope: #region");
    });
    it("sends one explicit owner-scoped update and never retries an uncertain result", async () => {
        vi.stubGlobal("navigator", {
            geolocation: {
                getCurrentPosition: (resolve) => resolve({ coords: { latitude: 1, longitude: 2, accuracy: 7 } }),
            },
        });
        setup();
        window.api.post.mockResolvedValue({ data: { result: { state: "unknown" } } });
        await button("Share my position once").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledOnce();
        expect(window.api.post.mock.calls[0][1]).toMatchObject({
            expected_owner: owner,
            record: { kind: "position", latitude: 1, longitude: 2, accuracy: 7 },
        });
        expect(wrapper.text()).toContain("will not be retried automatically");
        await wrapper.setProps({ team: team() });
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledOnce();
    });
});
