import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import Composer from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreVoiceComposer.vue";
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});
function setup(getUserMedia) {
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const close = vi.fn().mockResolvedValue(),
        connect = vi.fn(),
        disconnect = vi.fn();
    vi.stubGlobal(
        "AudioContext",
        vi.fn(function () {
            return {
                sampleRate: 48000,
                audioWorklet: { addModule: vi.fn().mockResolvedValue() },
                createMediaStreamSource: () => ({ connect }),
                createGain: () => ({ gain: { value: 1 }, connect }),
                resume: vi.fn().mockResolvedValue(),
                close,
                destination: {},
            };
        })
    );
    vi.stubGlobal(
        "AudioWorkletNode",
        vi.fn(function () {
            return { port: {}, connect, disconnect };
        })
    );
    wrapper = mount(Composer, { props: { owner: "a1".repeat(32), peer: "b2".repeat(32), connected: true } });
    return { close, disconnect };
}
describe("MeshCore voice microphone lifecycle", () => {
    it("keeps a rejected recording and uses a new request only on an explicit retry", async () => {
        setup(vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }));
        vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:recording"), revokeObjectURL: vi.fn() });
        window.api = {
            post: vi.fn().mockImplementation((path) => {
                if (path.endsWith("voice-prepare"))
                    return Promise.resolve({ data: { result: { sid: "00000001", wav_base64: btoa("RIFF") } } });
                return Promise.resolve({ data: { result: { state: "rejected" } } });
            }),
        };
        await wrapper.find("button").trigger("click");
        await flushPromises();
        AudioWorkletNode.mock.results[0].value.port.onmessage({ data: new Int16Array(4800).buffer });
        await wrapper.find("button").trigger("click");
        await flushPromises();
        const send = () => wrapper.findAll("button").find((button) => button.text() === "Send voice clip");
        await send().trigger("click");
        await flushPromises();
        expect(wrapper.find("audio").exists()).toBe(true);
        expect(wrapper.text()).toContain("Your recording is kept");
        const first = window.api.post.mock.calls.filter(([path]) => path.endsWith("voice-send"));
        expect(first).toHaveLength(1);
        await send().trigger("click");
        await flushPromises();
        const attempts = window.api.post.mock.calls.filter(([path]) => path.endsWith("voice-send"));
        expect(attempts).toHaveLength(2);
        expect(attempts[1][1].request_id).not.toBe(attempts[0][1].request_id);
        expect(attempts[1][1].sid).toBe(attempts[0][1].sid);
    });

    it("stops microphone and audio context when the target changes", async () => {
        const stop = vi.fn();
        const state = setup(vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }));
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(wrapper.text()).toContain("Stop");
        await wrapper.setProps({ peer: "c3".repeat(32) });
        await flushPromises();
        expect(stop).toHaveBeenCalledOnce();
        expect(state.close).toHaveBeenCalledOnce();
        expect(wrapper.text()).toContain("Record voice clip");
    });
    it("stops capture when the app enters the background", async () => {
        const stop = vi.fn();
        setup(vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }));
        await wrapper.find("button").trigger("click");
        await flushPromises();
        vi.spyOn(document, "hidden", "get").mockReturnValue(true);
        document.dispatchEvent(new Event("visibilitychange"));
        await flushPromises();
        expect(stop).toHaveBeenCalledOnce();
        expect(wrapper.text()).toContain("Recording stopped");
    });
    it("releases a late microphone permission result after leaving the conversation", async () => {
        let resolve;
        const stop = vi.fn();
        setup(
            vi.fn(
                () =>
                    new Promise((r) => {
                        resolve = r;
                    })
            )
        );
        await wrapper.find("button").trigger("click");
        wrapper.unmount();
        wrapper = null;
        resolve({ getTracks: () => [{ stop }] });
        await flushPromises();
        expect(stop).toHaveBeenCalledOnce();
    });
});
