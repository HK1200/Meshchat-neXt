import { mount, flushPromises } from "@vue/test-utils";
import { it, expect, vi } from "vitest";
import DialogUtils from "../../meshchatnext/src/frontend/js/DialogUtils";
import Server from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreCotServer.vue";
it("stays disconnected and sends nothing until an explicit connection", async () => {
    window.api = {
        get: vi.fn().mockResolvedValue({ data: { result: { connected: true, state: "connected", items: [] } } }),
        post: vi.fn().mockResolvedValue({ data: { result: { connected: true } } }),
    };
    const owner = "a1".repeat(32);
    const w = mount(Server, { props: { owner, connected: true } });
    try {
        expect(window.api.get).not.toHaveBeenCalled();
        expect(window.api.post).not.toHaveBeenCalled();
        w.find("details").element.open = true;
        await w.find("details").trigger("toggle");
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
        // Status refresh alone may show a previously explicit session, but cannot open one.
        expect(window.api.get).toHaveBeenCalledWith(expect.any(String), { params: { owner } });
    } finally {
        w.unmount();
    }
});

it("requires enrollment confirmation and drops an approval after identity changes", async () => {
    window.api = {
        get: vi.fn().mockResolvedValue({ data: { result: {} } }),
        post: vi.fn().mockResolvedValue({ data: { result: {} } }),
    };
    let decide;
    const confirm = vi.spyOn(DialogUtils, "confirm").mockImplementation(
        () =>
            new Promise((resolve) => {
                decide = resolve;
            })
    );
    const w = mount(Server, { props: { owner: "a1".repeat(32), connected: true } });
    try {
        const input = (label) =>
            w
                .findAll("label")
                .find((l) => l.text().startsWith(label))
                .find("input");
        await input("Server address").setValue("localhost");
        await input("Username").setValue("synthetic-user");
        await input("Password").setValue("synthetic-secret");
        await w
            .findAll("button")
            .find((b) => b.text() === "Enroll certificate")
            .trigger("click");
        expect(confirm).toHaveBeenCalled();
        expect(window.api.post).not.toHaveBeenCalled();
        await w.setProps({ owner: "b2".repeat(32) });
        decide(true);
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
        expect(input("Password").element.value).toBe("");
    } finally {
        w.unmount();
        confirm.mockRestore();
    }
});

it("downloads a verified package for local review without forwarding it to a radio", async () => {
    const owner = "a1".repeat(32),
        digest = "ab".repeat(32);
    window.api = {
        get: vi.fn().mockResolvedValue({ data: { result: { connected: true, items: [] } } }),
        post: vi.fn(async (path) => ({
            data: {
                result: path.endsWith("tak-package-search")
                    ? [{ hash: digest, name: "Synthetic package" }]
                    : { zip_base64: btoa("synthetic-package-bytes") },
            },
        })),
    };
    const w = mount(Server, { props: { owner, connected: true } });
    try {
        w.find("details").element.open = true;
        await w.find("details").trigger("toggle");
        await flushPromises();
        await w
            .findAll("button")
            .find((b) => b.text() === "Search server packages")
            .trigger("click");
        await flushPromises();
        await w
            .findAll("button")
            .find((b) => b.text().includes("Download"))
            .trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls.map(([path]) => path.split("/").pop())).toEqual([
            "tak-package-search",
            "tak-package-download",
        ]);
        expect(w.emitted("package")[0][0]).toMatchObject({ owner });
        expect(new TextDecoder().decode(w.emitted("package")[0][0].bytes)).toBe("synthetic-package-bytes");
        await w.setProps({ owner: "b2".repeat(32) });
        expect(w.text()).not.toContain("Synthetic package");
    } finally {
        w.unmount();
    }
});
