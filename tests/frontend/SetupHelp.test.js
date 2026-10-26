import { it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import SetupHelp from "../../meshchatnext/src/frontend/components/setup/SetupHelp.vue";
import { SETUP_HELP } from "../../meshchatnext/src/frontend/js/setupHelp";
it("offers collapsed, native accessible help for every setup stage without configuration calls", () => {
    for (const topic of ["networks", "identity", "reticulum", "meshcore", "radio2", "sip", "ready"]) {
        const w = mount(SetupHelp, { props: { topic } });
        expect(w.findAll("details")).toHaveLength(SETUP_HELP[topic].length);
        expect(w.findAll("details").every((d) => d.attributes("open") === undefined)).toBe(true);
        expect(w.findAll("summary").every((s) => s.text().startsWith("Help ·"))).toBe(true);
        w.unmount();
    }
});
