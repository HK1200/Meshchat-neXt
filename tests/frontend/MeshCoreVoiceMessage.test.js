import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import VoiceMessage from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreVoiceMessage.vue";
const peer = "b2".repeat(32),
    owner = "a1".repeat(32),
    sid = "00000001";
let wrapper;
function snapshot(job, connected = true) {
    return { owner, connected, voice_jobs: job ? { [peer + ":" + sid]: job } : {} };
}
function setup(job, connected = true) {
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:clip"), revokeObjectURL: vi.fn() });
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { wav_base64: btoa("RIFF") } } }) };
    wrapper = mount(VoiceMessage, {
        props: {
            peer,
            row: { id: "message-1", direction: "in" },
            meta: { sid, seconds: 2 },
            snapshot: snapshot(job, connected),
        },
    });
}
afterEach(() => {
    wrapper?.unmount();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});
describe("MeshCore voice download lifecycle", () => {
    it("keeps the player source across conversation polling with unchanged identity and message", async () => {
        setup({ state: "complete", received: 2, total: 2 });
        await wrapper.find("button").trigger("click");
        await flushPromises();
        const audio = wrapper.find("audio").element;
        for (let i = 0; i < 4; i++) {
            await wrapper.setProps({
                row: { id: "message-1", direction: "in", state: "received", heard_repeats: i },
                snapshot: snapshot({ state: "complete", received: 2, total: 2 }),
            });
            await flushPromises();
            expect(wrapper.find("audio").element).toBe(audio);
            expect(wrapper.find("audio").attributes("src")).toBe("blob:clip");
        }
        expect(URL.revokeObjectURL).not.toHaveBeenCalled();
        expect(window.api.post).toHaveBeenCalledOnce();
        await wrapper.setProps({ snapshot: { ...snapshot(), owner: "c3".repeat(32) } });
        expect(wrapper.find("audio").exists()).toBe(false);
        expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:clip");
    });

    it("shows progress and opens the cached player when the download completes", async () => {
        setup({ state: "downloading", received: 1, total: 2 });
        expect(wrapper.find("progress").attributes("value")).toBe("1");
        expect(wrapper.find("button").exists()).toBe(false);
        await wrapper.setProps({ snapshot: snapshot({ state: "complete", received: 2, total: 2 }) });
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledOnce();
        expect(window.api.post.mock.calls[0][0]).toContain("voice-play");
        expect(wrapper.find("audio").attributes("src")).toBe("blob:clip");
        expect(wrapper.text()).toContain("Ready to play");
    });
    it("offers an explicit failed-download retry without sending a new announcement", async () => {
        setup({ state: "failed", error: "Not fully received" });
        window.api.post
            .mockRejectedValueOnce({ response: { status: 400 } })
            .mockResolvedValueOnce({ data: { result: { state: "downloading" } } });
        expect(wrapper.find("button").text()).toBe("Retry voice download");
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls.map((call) => call[0].split("/").pop())).toEqual([
            "voice-play",
            "voice-fetch",
        ]);
        expect(window.api.post.mock.calls[1][1]).toEqual({ peer, expected_owner: owner, message_id: "message-1" });
    });
    it("opens a requested attachment even if it completed before the first progress poll", async () => {
        setup();
        window.api.post
            .mockRejectedValueOnce({ response: { status: 400 } })
            .mockResolvedValueOnce({ data: { result: { state: "downloading" } } });
        await wrapper.find("button").trigger("click");
        await flushPromises();
        await wrapper.setProps({ snapshot: snapshot({ state: "complete", received: 1, total: 1 }) });
        await flushPromises();
        expect(wrapper.find("audio").exists()).toBe(true);
        expect(window.api.post.mock.calls.map((call) => call[0].split("/").pop())).toEqual([
            "voice-play",
            "voice-fetch",
            "voice-play",
        ]);
    });
    it("plays cached audio offline and never requests missing audio while disconnected", async () => {
        setup(null, false);
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(wrapper.find("audio").exists()).toBe(true);
        wrapper.unmount();
        setup(null, false);
        window.api.post.mockRejectedValue({ response: { status: 400 } });
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledOnce();
        expect(wrapper.text()).toContain("Reconnect the MeshCore radio");
    });
    it("does not attach a late player response to a different contact", async () => {
        setup();
        let resolve;
        window.api.post.mockImplementation(
            () =>
                new Promise((r) => {
                    resolve = r;
                })
        );
        await wrapper.find("button").trigger("click");
        await wrapper.setProps({ peer: "c3".repeat(32) });
        resolve({ data: { result: { wav_base64: btoa("RIFF") } } });
        await flushPromises();
        expect(wrapper.find("audio").exists()).toBe(false);
        expect(URL.createObjectURL).not.toHaveBeenCalled();
    });
});
