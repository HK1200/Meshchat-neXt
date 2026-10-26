import { mount } from "@vue/test-utils";
import { describe, it, expect } from "vitest";
import Form from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreTeamReportForm.vue";
describe("MeshCore tactical report form", () => {
    it("requires explicit coordinates and never silently inserts zero", async () => {
        const w = mount(Form, { props: { team: {}, canSend: true } });
        await w.find("form").trigger("submit");
        expect(w.emitted("send")).toBeUndefined();
        expect(w.text()).toContain("Enter the report coordinates");
        w.unmount();
    });
    it("clears SALUTE-only fields when submitting a general report", async () => {
        const w = mount(Form, { props: { team: {}, canSend: true } });
        await w.findAll('input[type="number"]')[0].setValue("4");
        await w.findAll("select")[0].setValue("1");
        const coords = w.findAll('input[type="number"]');
        await coords[0].setValue("1.5");
        await coords[1].setValue("2.5");
        await w.find("form").trigger("submit");
        expect(w.emitted("send")[0][0]).toMatchObject({
            report_kind: 1,
            latitude: 1.5,
            longitude: 2.5,
            vehicles: 0,
            people: 0,
            unit: "",
            equipment: "",
        });
        w.unmount();
    });
});
