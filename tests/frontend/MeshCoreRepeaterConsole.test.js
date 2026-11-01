import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import Console from "@/components/meshcore/MeshCoreRepeaterConsole.vue";
const response = (action) =>
    ({
        radio: "> 910.525,62.5,7,5",
        radio2: "> 911.150,250.000,7,5,rxtx,12 (auto)",
        "radio2-cross": "> off",
        "radio2-media": "> tx.media radio2",
    })[action] || "OK";
describe("Repeater MediaMesh and terminal", () => {
    it("does not probe or transmit on mount and detects unsupported firmware", async () => {
        const request = vi.fn().mockResolvedValue("Unknown command");
        const w = mount(Console, { props: { request } });
        expect(request).not.toHaveBeenCalled();
        await w.find("button").trigger("click");
        await flushPromises();
        expect(w.text()).toContain("does not report compatible");
        expect(request).toHaveBeenCalledTimes(1);
        w.unmount();
    });
    it("reads capability, confirms writes and verifies unchanged primary profile", async () => {
        const request = vi.fn(async (action) => response(action));
        const w = mount(Console, { props: { request } });
        await w.find("button").trigger("click");
        await flushPromises();
        const form = w.findAll("form")[0];
        expect(form.find("button.primary-chip").attributes("disabled")).toBeDefined();
        await form.find('input[type="checkbox"]').setValue(true);
        await form.trigger("submit");
        await flushPromises();
        expect(w.text()).toContain("settings verified");
        expect(request.mock.calls.filter((c) => c[0] === "radio")).toHaveLength(2);
        expect(request).toHaveBeenCalledWith("set-radio2", "911.15,250,7,5,rxtx", true);
        expect(request).toHaveBeenCalledWith("set-radio2-preset", "mediamesh", true);
        expect(request.mock.calls.some((c) => c[0].includes("media") && c[0] !== "set-radio2-preset")).toBe(false);
        w.unmount();
    });
    it("sends a terminal command only after confirmation, clears its input and never retries", async () => {
        const request = vi.fn().mockRejectedValue(new Error("No verified response"));
        const w = mount(Console, { props: { request } });
        const form = w.findAll("form").at(-1);
        await form.find('input:not([type="checkbox"])').setValue("ver");
        await form.trigger("submit");
        expect(request).not.toHaveBeenCalled();
        await form.find('input[type="checkbox"]').setValue(true);
        await form.trigger("submit");
        await flushPromises();
        expect(request).toHaveBeenCalledExactlyOnceWith("terminal", "ver", true);
        expect(form.find('input:not([type="checkbox"])').element.value).toBe("");
        expect(w.text()).toContain("No verified response");
        w.unmount();
    });
    it("does not continue a capability sequence after the repeater component is replaced", async () => {
        let finish;
        const request = vi.fn(
            () =>
                new Promise((resolve) => {
                    finish = resolve;
                })
        );
        const w = mount(Console, { props: { request } });
        await w.find("button").trigger("click");
        w.unmount();
        finish(response("radio2"));
        await flushPromises();
        expect(request).toHaveBeenCalledTimes(1);
    });
    it("stops after a rejected policy write and does not report success", async () => {
        const request = vi.fn(async (action) =>
            action === "set-radio2-cross" ? "Error: unsupported" : response(action)
        );
        const w = mount(Console, { props: { request } });
        await w.find("button").trigger("click");
        await flushPromises();
        const form = w.findAll("form")[0];
        await form.find('input[type="checkbox"]').setValue(true);
        await form.trigger("submit");
        await flushPromises();
        expect(request.mock.calls.some((c) => c[0] === "set-radio2")).toBe(false);
        expect(w.text()).toContain("No automatic retry");
        expect(w.text()).not.toContain("settings verified");
        w.unmount();
    });
    it("reports readback mismatch rather than treating an OK as verified", async () => {
        let reads = 0;
        const request = vi.fn(async (action) => (action === "radio2" && ++reads > 1 ? "> off" : response(action)));
        const w = mount(Console, { props: { request } });
        await w.find("button").trigger("click");
        await flushPromises();
        const form = w.findAll("form")[0];
        await form.find('input[type="checkbox"]').setValue(true);
        await form.trigger("submit");
        await flushPromises();
        expect(w.text()).toContain("Readback differs");
        expect(w.text()).not.toContain("settings verified");
        w.unmount();
    });
});
