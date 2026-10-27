import { mount, flushPromises } from "@vue/test-utils";
import { it, expect, vi } from "vitest";
import Controls from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreGpsdControls.vue";
import DialogUtils from "../../meshchatnext/src/frontend/js/DialogUtils";
vi.mock("../../meshchatnext/src/frontend/js/DialogUtils", () => ({ default: { confirm: vi.fn() } }));
it("requires explicit consent and keeps receiver sharing bounded and Linux labelled", async () => {
    window.electron = { getPlatform: () => "linux" };
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { active: false } } }) };
    DialogUtils.confirm.mockResolvedValue(false);
    const w = mount(Controls, {
        props: { owner: "a".repeat(64), team: { enabled: true, channel_id: "c".repeat(64) }, connected: true },
    });
    try {
        await flushPromises();
        expect(w.text()).toContain("Linux GPS receiver");
        expect(window.api.post.mock.calls.every(([url]) => url.endsWith("team-beacon-status"))).toBe(true);
        await w.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post.mock.calls.some(([url]) => url.endsWith("team-beacon-start"))).toBe(false);
        DialogUtils.confirm.mockResolvedValue(true);
        await w.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            expect.stringContaining("team-beacon-start"),
            expect.objectContaining({ source: "gpsd", duration_minutes: 15, interval: 300 })
        );
        await w.setProps({ scope: "changed" });
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(expect.stringContaining("team-beacon-stop"), {
            expected_owner: "a".repeat(64),
        });
    } finally {
        w.unmount();
        delete window.electron;
    }
});
it("does not offer receiver controls in a normal browser", () => {
    delete window.electron;
    const w = mount(Controls);
    expect(w.find("button").exists()).toBe(false);
    w.unmount();
});
