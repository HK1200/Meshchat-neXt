import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import QRCode from "qrcode";
import MeshCoreIdentityShare from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreIdentityShare.vue";
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,qr") } }));
const owner = "a1".repeat(32);
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
    QRCode.toDataURL.mockReset().mockResolvedValue("data:image/png;base64,qr");
});
function setup(snapshot = {}) {
    Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText: vi.fn().mockResolvedValue() },
    });
    Object.defineProperty(navigator, "share", { configurable: true, value: vi.fn().mockResolvedValue() });
    window.api = { get: vi.fn(), post: vi.fn() };
    wrapper = mount(MeshCoreIdentityShare, {
        props: {
            snapshot: {
                owner,
                connected: true,
                profile_name: "Field radio",
                private_key: "NEVER_EXPORT_THIS",
                ...snapshot,
            },
        },
    });
}
describe("MeshCore public identity sharing", () => {
    it("encodes and shares only the public key, without requesting a private-key export", async () => {
        setup();
        await flushPromises();
        expect(QRCode.toDataURL).toHaveBeenCalledWith(owner, { margin: 1, scale: 6 });
        await wrapper.findAll("button")[0].trigger("click");
        await flushPromises();
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith(owner);
        await wrapper.findAll("button")[1].trigger("click");
        await flushPromises();
        expect(navigator.share).toHaveBeenCalledWith({ title: "MeshCore identity", text: owner });
        expect(window.api.get).not.toHaveBeenCalled();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(wrapper.text()).not.toContain("NEVER_EXPORT_THIS");
    });
    it("clears the old QR immediately and discards stale generation after switching radios", async () => {
        let resolve;
        QRCode.toDataURL.mockReturnValueOnce(
            new Promise((r) => {
                resolve = r;
            })
        );
        setup();
        await wrapper.setProps({ snapshot: { owner: "b2".repeat(32), connected: false } });
        await flushPromises();
        resolve("data:image/png;base64,old");
        await flushPromises();
        expect(wrapper.find("img").attributes("src")).toBe("data:image/png;base64,qr");
        expect(wrapper.text()).not.toContain(owner);
        expect(wrapper.text()).toContain("Last connected radio identity");
    });
    it("offers no share action without a valid public identity", async () => {
        setup({ owner: null });
        await flushPromises();
        expect(wrapper.findAll("button")).toHaveLength(0);
        expect(QRCode.toDataURL).not.toHaveBeenCalled();
    });
    it("keeps copying available if QR rendering fails, and does not copy after sharing is cancelled", async () => {
        QRCode.toDataURL.mockRejectedValueOnce(new Error("QR error"));
        setup();
        await flushPromises();
        expect(wrapper.text()).toContain("QR unavailable");
        navigator.share.mockRejectedValueOnce(Object.assign(new Error("cancelled"), { name: "AbortError" }));
        await wrapper.findAll("button")[1].trigger("click");
        await flushPromises();
        expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
    });
});
