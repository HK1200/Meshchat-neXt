import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import MeshCoreBackups from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreBackups.vue";
import DownloadUtils from "../../meshchatnext/src/frontend/js/DownloadUtils";
import DialogUtils from "../../meshchatnext/src/frontend/js/DialogUtils";
vi.mock("../../meshchatnext/src/frontend/js/DownloadUtils", () => ({
    default: { downloadFile: vi.fn().mockResolvedValue() },
}));
vi.mock("../../meshchatnext/src/frontend/js/DialogUtils", () => ({
    default: { confirm: vi.fn().mockResolvedValue(true) },
}));
const owner = "a1".repeat(32),
    password = "test-password-long-enough";
const encrypted = {
    format: "meshchatnext-meshcore-identity-v1",
    public_key: owner,
    salt: "ab".repeat(16),
    nonce: "bc".repeat(12),
    ciphertext: "cd".repeat(64),
    tag: "de".repeat(16),
};
const review = {
    owner,
    preview_id: "c3".repeat(32),
    identity_replacement: false,
    sections: ["name", "contacts"],
    name: "Field radio",
    radio: {},
    contacts: { new: 1, existing: 0 },
    channels: { new: 0, existing: 0, free_slots: 1 },
    unsupported: [],
    errors: {},
};
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.clearAllMocks();
    vi.restoreAllMocks();
});
function setup() {
    window.api = {
        post: vi.fn().mockResolvedValue({ data: { result: encrypted } }),
        get: vi.fn().mockResolvedValue({ data: { result: { state: "uncertain", completed: [] } } }),
    };
    wrapper = mount(MeshCoreBackups, { props: { snapshot: { owner, connected: true } } });
}
async function passwords() {
    const inputs = wrapper.findAll('input[type="password"]');
    await inputs[0].setValue(password);
    await inputs[1].setValue(password);
}
async function file(text = '{"name":"Field radio"}') {
    const field = wrapper.find('input[type="file"]');
    Object.defineProperty(field.element, "files", {
        configurable: true,
        value: [{ size: text.length, text: async () => text }],
    });
    await field.trigger("change");
    await flushPromises();
}
function button(text) {
    return wrapper.findAll("button").find((b) => b.text() === text);
}
describe("MeshCore backups", () => {
    it("exports only encrypted fields and clears passwords after requesting download", async () => {
        setup();
        await passwords();
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            "/api/v1/meshcore/backup",
            { password, expected_public_key: owner },
            { timeout: 60000 }
        );
        expect(DownloadUtils.downloadFile).toHaveBeenCalledTimes(1);
        const [name, blob] = DownloadUtils.downloadFile.mock.calls[0];
        expect(name).toContain(owner.slice(0, 12));
        expect(blob.type).toBe("application/json");
        expect(wrapper.findAll('input[type="password"]')[0].element.value).toBe("");
        expect(wrapper.text()).toContain("download requested");
    });
    it("rejects unexpected plaintext fields and wrong-owner responses", async () => {
        setup();
        await passwords();
        window.api.post.mockResolvedValueOnce({ data: { result: { ...encrypted, private_key: "DO_NOT_SAVE" } } });
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(DownloadUtils.downloadFile).not.toHaveBeenCalled();
        await passwords();
        window.api.post.mockResolvedValueOnce({ data: { result: { ...encrypted, public_key: "b2".repeat(32) } } });
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(DownloadUtils.downloadFile).not.toHaveBeenCalled();
    });
    it("does not export with mismatched passwords and discards in-flight results after a radio change", async () => {
        setup();
        await passwords();
        await wrapper.findAll('input[type="password"]')[1].setValue("different");
        await wrapper.find("form").trigger("submit");
        expect(window.api.post).not.toHaveBeenCalled();
        await passwords();
        let resolve;
        window.api.post.mockReturnValueOnce(
            new Promise((r) => {
                resolve = r;
            })
        );
        await wrapper.find("form").trigger("submit");
        await wrapper.setProps({ snapshot: { owner: "b2".repeat(32), connected: true } });
        resolve({ data: { result: encrypted } });
        await flushPromises();
        expect(DownloadUtils.downloadFile).not.toHaveBeenCalled();
    });
    it("previews files without writes, then requires selected sections and confirmation", async () => {
        setup();
        await file();
        expect(window.api.post).not.toHaveBeenCalled();
        window.api.post.mockResolvedValueOnce({ data: { result: review } });
        await button("Preview import").trigger("click");
        await flushPromises();
        expect(button("Import selected sections").attributes("disabled")).toBeDefined();
        await wrapper.find('input[type="checkbox"]').setValue(true);
        window.api.post.mockResolvedValueOnce({
            data: { result: { state: "complete", completed: ["name"], contacts_added: 0, channels_added: 0 } },
        });
        await button("Import selected sections").trigger("click");
        await flushPromises();
        expect(DialogUtils.confirm).toHaveBeenCalled();
        const calls = window.api.post.mock.calls.filter(([path]) => path.endsWith("/config-apply"));
        expect(calls).toHaveLength(1);
        expect(calls[0][1]).toMatchObject({
            expected_owner: owner,
            preview_id: review.preview_id,
            sections: ["name"],
            replace_identity: false,
        });
        expect(wrapper.text()).toContain("completed and verified");
    });
    it("checks uncertain outcomes with a read-only request and never repeats import writes", async () => {
        setup();
        await file();
        window.api.post.mockResolvedValueOnce({ data: { result: review } });
        await button("Preview import").trigger("click");
        await flushPromises();
        await wrapper.find('input[type="checkbox"]').setValue(true);
        window.api.post.mockRejectedValueOnce(new Error("timeout"));
        await button("Import selected sections").trigger("click");
        await flushPromises();
        await button("Check import outcome").trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls.filter(([path]) => path.endsWith("/config-apply"))).toHaveLength(1);
        expect(window.api.get).toHaveBeenCalledWith(
            "/api/v1/meshcore/config-result",
            expect.objectContaining({ params: expect.objectContaining({ owner }) })
        );
    });
});


describe("first-launch backup import", () => {
    it("reads a backup before connecting, emits only its radio hint and keeps the selection for preview after connection", async () => {
        window.api={post:vi.fn(async()=>({data:{result:{...review,sections:["contacts"]}}}))};
        const wrapper=mount(MeshCoreBackups,{props:{importOnly:true,snapshot:{connected:false,owner:null}}});
        const field=wrapper.get('input[type="file"]');
        Object.defineProperty(field.element,"files",{configurable:true,value:[{name:"setup.json",size:100,text:async()=>JSON.stringify({bluetooth_address:"AA:BB:CC:DD:EE:FF",private_key:"synthetic-private",contacts:[]})}]});
        await field.trigger("change");await flushPromises();
        expect(wrapper.emitted("device-hint")[0][0]).toEqual({kind:"ble",target:"AA:BB:CC:DD:EE:FF"});
        expect(window.api.post).not.toHaveBeenCalled();
        await wrapper.setProps({snapshot:{connected:true,owner}});await flushPromises();
        const preview=wrapper.findAll('button').find(button=>button.text()==='Preview import');
        expect(preview.attributes('disabled')).toBeUndefined();
        await preview.trigger('click');await flushPromises();
        expect(window.api.post.mock.calls[0][1].text).toContain('synthetic-private');
        wrapper.unmount();
    });
});
