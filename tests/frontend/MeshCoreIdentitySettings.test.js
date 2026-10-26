import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import MeshCoreIdentitySettings from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreIdentitySettings.vue";
const owner = "a1".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
async function setup() {
    window.api = {
        get: vi.fn().mockResolvedValue({ data: { result: { public_key: owner, name: "Field radio" } } }),
        post: vi
            .fn()
            .mockImplementation((_, body) =>
                Promise.resolve({ data: { result: { public_key: owner, name: body.name } } })
            ),
    };
    wrapper = mount(MeshCoreIdentitySettings, { props: { snapshot: { owner, connected: true } } });
    await flushPromises();
}
describe("MeshCore display name", () => {
    it("reads the radio name and saves only that name with the selected owner guard", async () => {
        await setup();
        expect(wrapper.find("input").element.value).toBe("Field radio");
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.find("input").setValue("Trail radio");
        await wrapper.setProps({ snapshot: { owner, connected: true, profile_name: "Poll update" } });
        expect(wrapper.find("input").element.value).toBe("Trail radio");
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledExactlyOnceWith("/api/v1/meshcore/name", {
            name: "Trail radio",
            expected_owner: owner,
        });
        expect(wrapper.text()).toContain("saved and verified");
        expect(wrapper.emitted("saved")).toHaveLength(1);
    });
    it("enforces UTF-8 byte limits and rejects blank names without truncating", async () => {
        await setup();
        await wrapper.find("input").setValue("🛰".repeat(8));
        await wrapper.find("form").trigger("submit");
        expect(window.api.post).not.toHaveBeenCalled();
        expect(wrapper.text()).toContain("32/31 bytes");
        await wrapper.find("input").setValue("   ");
        await wrapper.find("form").trigger("submit");
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("blocks repeat submission after an uncertain result until the radio is read again", async () => {
        await setup();
        window.api.post.mockRejectedValueOnce(new Error("timeout"));
        await wrapper.find("input").setValue("Trail radio");
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(wrapper.text()).toContain("may have changed");
        await wrapper.find("form").trigger("submit");
        expect(window.api.post).toHaveBeenCalledTimes(1);
        await wrapper.findAll("button")[1].trigger("click");
        await flushPromises();
        expect(wrapper.find("input").element.value).toBe("Field radio");
        expect(wrapper.text()).not.toContain("may have changed");
    });
    it("rejects an unexpected identity and prevents editing when disconnected", async () => {
        await setup();
        window.api.get.mockResolvedValueOnce({
            data: { result: { public_key: "b2".repeat(32), name: "Other radio" } },
        });
        await wrapper.findAll("button")[1].trigger("click");
        await flushPromises();
        expect(wrapper.find("input").element.value).not.toBe("Other radio");
        await wrapper.setProps({ snapshot: { owner, connected: false } });
        await flushPromises();
        expect(wrapper.find("input").attributes("disabled")).toBeDefined();
        expect(window.api.post).not.toHaveBeenCalled();
    });
});
