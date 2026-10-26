import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import Radio2 from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreRadio2Settings.vue";
let wrapper;
const owner = "a1".repeat(32);
const defaults = { frequency_mhz: 911.15, bandwidth_khz: 250, sf: 7, cr: 5 };
afterEach(() => wrapper?.unmount());
async function setup(profile = null) {
    window.api = {
        get: vi
            .fn()
            .mockResolvedValue({ data: { result: { supported: true, enabled: Boolean(profile), profile, defaults } } }),
        post: vi.fn().mockResolvedValue({
            data: { result: { supported: true, enabled: true, profile: profile || defaults, defaults } },
        }),
    };
    wrapper = mount(Radio2, { props: { snapshot: { connected: true, owner } } });
    await wrapper
        .findAll("button")
        .find((b) => b.text() === "Read Radio2 from radio")
        .trigger("click");
    await flushPromises();
}
describe("Radio2 settings", () => {
    it("offers MediaMesh defaults only after reading and requires explicit enable/apply", async () => {
        await setup();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(wrapper.find('input[type="checkbox"]').element.checked).toBe(false);
        await wrapper.find('input[type="checkbox"]').setValue(true);
        expect(wrapper.findAll('input[type="number"]')[0].element.value).toBe("911.15");
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/radio2", {
            ...defaults,
            enabled: true,
            expected_owner: owner,
        });
    });
    it("loads the saved custom profile instead of replacing it", async () => {
        await setup({ ...defaults, frequency_mhz: 912, bandwidth_khz: 125, sf: 8 });
        expect(wrapper.findAll('input[type="number"]')[0].element.value).toBe("912");
        expect(wrapper.findAll('input[type="number"]')[1].element.value).toBe("125");
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("preserves the loaded profile and unsaved edits across ordinary status polls", async () => {
        await setup({ ...defaults, frequency_mhz: 912 });
        await wrapper.findAll('input[type="number"]')[0].setValue("912.1");
        await wrapper.setProps({ snapshot: { connected: true, owner, receiving: true } });
        expect(wrapper.findAll('input[type="number"]')[0].element.value).toBe("912.1");
    });
    it("blocks repeated writes after an uncertain result until a new read", async () => {
        await setup();
        await wrapper.find('input[type="checkbox"]').setValue(true);
        window.api.post.mockRejectedValue(new Error("timeout"));
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(wrapper.text()).toContain("could not be fully verified");
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledOnce();
    });
});
