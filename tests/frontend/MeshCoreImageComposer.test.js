import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import Composer from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreImageComposer.vue";
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});
function setup(extra = {}) {
    const header = new Uint8Array(24);
    header.set([137, 80, 78, 71, 13, 10, 26, 10], 0);
    header.set([73, 72, 68, 82], 12);
    new DataView(header.buffer).setUint32(16, 2);
    new DataView(header.buffer).setUint32(20, 1);
    vi.stubGlobal(
        "FileReader",
        class {
            readAsArrayBuffer() {
                this.result = header.buffer;
                this.onload();
            }
        }
    );
    vi.stubGlobal("createImageBitmap", vi.fn().mockResolvedValue({ width: 2, height: 1, close: vi.fn() }));
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
        fillRect: vi.fn(),
        drawImage: vi.fn(),
        getImageData: () => ({ data: new Uint8ClampedArray([10, 20, 30, 255, 40, 50, 60, 255]) }),
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:photo");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    window.api = {
        post: vi.fn().mockImplementation((path) =>
            Promise.resolve({
                data: {
                    result: path.endsWith("image-prepare")
                        ? { sid: "1234abcd", png_base64: btoa("PNG"), width: 2, height: 1, total: 1, bytes: 80 }
                        : { state: "submitted" },
                },
            })
        ),
    };
    wrapper = mount(Composer, { props: { owner: "a1".repeat(32), peer: "b2".repeat(32), connected: true, ...extra } });
}
async function choose(file = new File(["synthetic"], "photo.png", { type: "image/png" })) {
    const input = wrapper.find('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });
    await input.trigger("change");
    await flushPromises();
}
describe("MeshCore photo preparation and consent", () => {
    it("prepares pixels only and requires a separate explicit send", async () => {
        setup();
        await choose();
        expect(window.api.post).toHaveBeenCalledTimes(1);
        const [path, body] = window.api.post.mock.calls[0];
        expect(path).toContain("image-prepare");
        expect(body.rgb_base64).toBe(btoa(String.fromCharCode(10, 20, 30, 40, 50, 60)));
        expect(body).not.toHaveProperty("filename");
        expect(wrapper.find("img").exists()).toBe(true);
        await wrapper
            .findAll("button")
            .find((b) => b.text() === "Send photo")
            .trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls[1][0]).toContain("voice-send");
        expect(wrapper.emitted("sent")).toHaveLength(1);
    });
    it("binds channel submission to its scope and clears drafts when scope changes", async () => {
        setup({ channelId: "c3".repeat(32), peer: "c3".repeat(32), scope: "region" });
        await choose();
        await wrapper
            .findAll("button")
            .find((b) => b.text() === "Send photo")
            .trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls[1][0]).toContain("media-channel-send");
        expect(window.api.post.mock.calls[1][1]).toMatchObject({
            channel_id: "c3".repeat(32),
            expected_scope: "region",
        });
        await choose();
        await wrapper.setProps({ scope: "other" });
        expect(wrapper.find("img").exists()).toBe(false);
    });
    it("attaches a photo reference locally without publishing it", async () => {
        setup({ attachment: true });
        await choose();
        await wrapper
            .findAll("button")
            .find((b) => b.text() === "Attach photo")
            .trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledTimes(1);
        expect(wrapper.emitted("prepared")[0][0]).toMatchObject({ mode: 40, sid: "1234abcd", packets: 1 });
        expect(wrapper.emitted("sent")).toBeUndefined();
    });
    it("rejects unsupported file types without preparing or transmitting", async () => {
        setup();
        await choose(new File(["svg"], "test.svg", { type: "image/svg+xml" }));
        expect(window.api.post).not.toHaveBeenCalled();
        expect(createImageBitmap).not.toHaveBeenCalled();
    });
    it("ignores late preparation after the conversation changes", async () => {
        setup();
        let finish;
        window.api.post.mockImplementationOnce(
            () =>
                new Promise((r) => {
                    finish = r;
                })
        );
        await choose();
        await wrapper.setProps({ peer: "c3".repeat(32) });
        finish({ data: { result: { sid: "1234abcd", png_base64: btoa("PNG") } } });
        await flushPromises();
        expect(wrapper.find("img").exists()).toBe(false);
        expect(wrapper.emitted("sent")).toBeUndefined();
    });
});
