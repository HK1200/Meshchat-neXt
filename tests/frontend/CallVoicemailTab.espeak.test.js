import { mount } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import CallVoicemailTab from "@/components/call/tabs/CallVoicemailTab.vue";

function tab(status) {
    return mount(CallVoicemailTab, {
        props: {
            active: true,
            config: {},
            voicemailStatus: status,
            getContactByHash: () => null,
            formatDateTime: String,
            formatDuration: String,
            formatDestinationHash: String,
        },
        data: () => ({ isVoicemailSettingsExpanded: true }),
        global: {
            mocks: { $t: (key) => key },
            stubs: { MaterialDesignIcon: true, SearchInput: true, LxmfUserIcon: true, AudioWaveformPlayer: true },
        },
    });
}
const generate = (w) => w.findAll("button").find((button) => button.text().includes("Save & Generate"));

describe("Voicemail speech providers", () => {
    it("enables native Android speech without eSpeak and hides its unsupported word-gap setting", async () => {
        const w = tab({ has_espeak: false, has_tts: true, tts_provider: "android" });
        expect(generate(w).attributes("disabled")).toBeUndefined();
        expect(w.text()).toContain("offline Android voice");
        expect(w.text()).not.toContain("Speech generation unavailable");
        expect(w.text()).not.toContain("call.tts_word_gap");
        await generate(w).trigger("click");
        expect(w.emitted("save-and-generate")).toHaveLength(1);
        w.unmount();
    });
    it("keeps desktop speech compatibility", () => {
        const w = tab({ has_espeak: true });
        expect(generate(w).attributes("disabled")).toBeUndefined();
        expect(w.text()).toContain("eSpeak NG");
        expect(w.text()).toContain("call.tts_word_gap");
        w.unmount();
    });
    it("leaves recording, upload and voicemail enabled when no speech engine is available", () => {
        const w = tab({ has_espeak: false, has_tts: false, tts_provider: "android" });
        expect(generate(w).attributes("disabled")).toBeDefined();
        expect(w.text()).toContain("You can still record a greeting or");
        const enable = w.findAll("button").find((button) => button.classes().includes("relative"));
        expect(enable.attributes("disabled")).toBeUndefined();
        w.unmount();
    });
});
