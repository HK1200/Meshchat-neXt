import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { peerRadio2Rows } from "../../meshchatnext/src/frontend/js/meshcorePeerRadio2";
import Component from "../../meshchatnext/src/frontend/components/meshcore/MeshCorePeerRadio2.vue";

describe("saved peer Radio2 reports", () => {
    it("never treats missing timestamp or name text as a capability", () => {
        expect(peerRadio2Rows({ state: "enabled", name: "Radio2", observed: null })[0].value).toBe("Unknown");
        expect(peerRadio2Rows(null)[0].value).toBe("Unknown");
    });
    it("shows reported profile, temporary state and unauthenticated provenance", () => {
        const report = {
            state: "enabled",
            observed: 1700000000,
            frequency_mhz: 911.15,
            bandwidth_khz: 250,
            sf: 7,
            cr: 5,
            mode: "rx",
            temporary: true,
        };
        const w = mount(Component, { props: { report } });
        expect(w.text()).toContain("Reported enabled");
        expect(w.text()).toContain("receive only · temporary");
        expect(w.text()).toContain("unauthenticated");
        expect(w.text()).toContain("settings may have changed");
        w.unmount();
    });
    it("does not call unavailable reports disabled or unsupported", () => {
        expect(peerRadio2Rows({ state: "unavailable", observed: 1700000000 })[0].value).toBe("Reported unavailable");
    });
});
