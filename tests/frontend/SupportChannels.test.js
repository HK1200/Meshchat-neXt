import { it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import SupportChannels from "../../meshchatnext/src/frontend/components/SupportChannels.vue";
import { appFeatures } from "../../meshchatnext/src/frontend/js/appFeatures";
import { SUPPORT_HUB } from "../../meshchatnext/src/frontend/js/supportChannels";
const mocks = vi.hoisted(() => ({ push: vi.fn(), apply: vi.fn().mockResolvedValue({}) }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("../../meshchatnext/src/frontend/js/relayLinkUtils", async (original) => ({
    ...(await original()),
    applyRelayShareLink: mocks.apply,
}));
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    appFeatures.reticulum = true;
    vi.clearAllMocks();
});
it("only connects on a deliberate click and keeps exact room names", async () => {
    wrapper = mount(SupportChannels);
    expect(mocks.apply).not.toHaveBeenCalled();
    await wrapper
        .findAll("button")
        .find((b) => b.text() === "Feature requests & suggestions")
        .trigger("click");
    await flushPromises();
    expect(mocks.apply).toHaveBeenCalledWith({
        hub: SUPPORT_HUB,
        name: "Meshchat neXt Relay",
        room: "feature requests & suggestions",
        aspect: "rrc.hub",
    });
    expect(mocks.push).toHaveBeenCalledWith({
        name: "relay-chat",
        query: { hub: SUPPORT_HUB, room: "feature requests & suggestions" },
    });
});
it("retains an optional GitHub route and disables relay joining when Reticulum is hidden", () => {
    appFeatures.reticulum = false;
    wrapper = mount(SupportChannels, { props: { reportUrl: "https://github.com/example/next/issues" } });
    expect(wrapper.get("a").attributes("href")).toBe("https://github.com/example/next/issues");
    expect(
        wrapper
            .findAll("button")
            .filter((b) => b.text() !== "Copy link")
            .every((b) => b.attributes("disabled") !== undefined)
    ).toBe(true);
});
it("does not display an unsafe or misleading GitHub link", () => {
    wrapper = mount(SupportChannels, { props: { reportUrl: "https://github.com.invalid/issues" } });
    expect(wrapper.find("a").exists()).toBe(false);
});
