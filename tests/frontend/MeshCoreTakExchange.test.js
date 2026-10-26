import { mount, flushPromises } from "@vue/test-utils";
import { it, expect, vi } from "vitest";
import Exchange from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreTakExchange.vue";
const owner = "a1".repeat(32),
    channel = "c3".repeat(32);
async function importPoint(w) {
    const input = w.find('input[type="file"]');
    Object.defineProperty(input.element, "files", {
        configurable: true,
        value: [
            {
                name: "point.cot",
                size: 100,
                text: async () =>
                    '<event uid="test"><point lat="0" lon="0"/><detail><contact callsign="Test point"/></detail></event>',
            },
        ],
    });
    await input.trigger("change");
    await flushPromises();
}
it("previews imported points without traffic, and shares only with explicit scope", async () => {
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { state: "submitted" } } }) };
    const w = mount(Exchange, {
        props: {
            owner,
            team: { enabled: true, channel_id: channel },
            scope: "test-region",
            connected: true,
            supported: true,
        },
    });
    try {
        await importPoint(w);
        expect(w.text()).toContain("Nothing sent to the radio");
        expect(window.api.post).not.toHaveBeenCalled();
        await w
            .findAll("button")
            .find((b) => b.text() === "View on map")
            .trigger("click");
        expect(w.emitted("focus")[0][0]).toMatchObject({ latitude: 0, longitude: 0 });
        expect(window.api.post).not.toHaveBeenCalled();
        await w
            .findAll("button")
            .find((b) => b.text() === "Share as MeshCore pin")
            .trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
                expected_owner: owner,
                expected_channel_id: channel,
                expected_scope: "test-region",
                record: expect.objectContaining({ kind: "pin", label: "Test point" }),
            })
        );
        expect(w.text()).toContain("Pin submitted");
        await w.setProps({ scope: "other" });
        expect(w.text()).not.toContain("Test point");
    } finally {
        w.unmount();
    }
});
it("keeps sharing disabled offline and clears preview on identity changes", async () => {
    window.api = { post: vi.fn() };
    const w = mount(Exchange, {
        props: { owner, team: { enabled: true, channel_id: channel }, connected: false, supported: true },
    });
    try {
        await importPoint(w);
        expect(
            w
                .findAll("button")
                .find((b) => b.text() === "Share as MeshCore pin")
                .attributes("disabled")
        ).toBeDefined();
        await w.setProps({ owner: "b2".repeat(32) });
        expect(w.text()).not.toContain("Test point");
        expect(window.api.post).not.toHaveBeenCalled();
    } finally {
        w.unmount();
    }
});
