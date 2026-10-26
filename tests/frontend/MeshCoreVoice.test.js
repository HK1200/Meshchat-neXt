import { describe, it, expect } from "vitest";
import { voiceEnvelope, pcmBase64 } from "../../meshchatnext/src/frontend/js/meshcoreVoice";
describe("MeshCore voice", () => {
    it("recognizes bounded envelopes without accepting arbitrary message text", () => {
        expect(voiceEnvelope("VE3:1:1:2:k")).toEqual({ sid: "00000001", mode: 1, total: 2, seconds: 20 });
        for (const text of ["VE3:0:1:1:1", "VE3:1:7:1:1", "VE3:1:1:zz:1", "ordinary text", null])
            expect(voiceEnvelope(text)).toBeNull();
    });
    it("downsamples mono PCM to 8 kHz with a twenty-second maximum", () => {
        expect(atob(pcmBase64([new Int16Array(48000).fill(1234)], 48000)).length).toBe(16000);
        expect(atob(pcmBase64([new Int16Array(48000 * 21)], 48000)).length).toBe(320000);
        expect(() => pcmBase64([], 48000)).toThrow();
    });
});

describe("MeshCore image envelopes", () => {
    it("recognizes bounded VI1 photos without accepting image modes as audio", () => {
        expect(voiceEnvelope("VI1:1:14:i:2s caption")).toMatchObject({
            image: true,
            mode: 40,
            total: 18,
            seconds: 100,
        });
        expect(voiceEnvelope("VE3:1:14:1:1")).toBeNull();
        expect(voiceEnvelope("VI1:1:1:1:1")).toBeNull();
    });
});
