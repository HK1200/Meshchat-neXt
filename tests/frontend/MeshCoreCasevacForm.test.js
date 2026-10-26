import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import Form from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreCasevacForm.vue";
import DialogUtils from "../../meshchatnext/src/frontend/js/DialogUtils";
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
function setup() {
    return (wrapper = mount(Form, {
        props: {
            team: { channel_id: "a1".repeat(32) },
            canSend: true,
            map: { getView: () => ({ getCenter: () => [0, 0] }) },
        },
    }));
}
async function fill(w) {
    await w
        .findAll("button")
        .find((b) => b.text() === "Use map centre for pickup")
        .trigger("click");
    await w.find('[aria-label="Urgent"]').setValue(1);
}
describe("CASEVAC review boundary", () => {
    it("does not send or request GPS on mount; requires patients and pickup coordinates", async () => {
        const confirm = vi.spyOn(DialogUtils, "confirm").mockResolvedValue(true);
        const w = setup();
        await w.find("form").trigger("submit");
        expect(w.find("[role=alert]").text()).toContain("coordinates");
        await fill(w);
        await w.find("form").trigger("submit");
        await flushPromises();
        expect(confirm).toHaveBeenCalledOnce();
        expect(w.emitted("send")[0][0]).toMatchObject({ kind: "casevac", latitude: 0, longitude: 0, urgent: 1 });
    });
    it("drops confirmation if the team channel changes", async () => {
        let accept;
        vi.spyOn(DialogUtils, "confirm").mockImplementation(() => new Promise((r) => (accept = r)));
        const w = setup();
        await fill(w);
        await w.find("form").trigger("submit");
        await w.setProps({ team: { channel_id: "b2".repeat(32) } });
        accept(true);
        await flushPromises();
        expect(w.emitted("send")).toBeUndefined();
    });
    it("rejects fractional patient counts and overlong UTF-8 text", async () => {
        const w = setup();
        await fill(w);
        await w.find('[aria-label="Urgent"]').setValue(1.5);
        await w.find("form").trigger("submit");
        expect(w.find("[role=alert]").text()).toContain("whole numbers");
        await w.find('[aria-label="Urgent"]').setValue(1);
        const remarks = w.find('input[maxlength="40"]');
        await remarks.setValue("🚑".repeat(11));
        await w.find("form").trigger("submit");
        expect(w.find("[role=alert]").text()).toContain("byte limit");
    });
});
