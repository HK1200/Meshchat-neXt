import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import PrivateLocation from "../../meshchatnext/src/frontend/components/meshcore/MeshCorePrivateLocation.vue";
const owner = "a1".repeat(32),
    peer = "b2".repeat(32);
const position = {
    coords: { latitude: 48.75, longitude: -122.48, altitude: null, accuracy: 10, speed: null, heading: null },
    timestamp: 1793957816000,
};
const wrappers = [];
afterEach(() => {
    wrappers.splice(0).forEach((w) => w.unmount());
    vi.unstubAllGlobals();
});
async function setup(options = {}) {
    let policy = { receive: false, share: false, generation: null, ...options.policy };
    let serial = 0;
    const geo = { getCurrentPosition: vi.fn() };
    vi.stubGlobal("navigator", { geolocation: geo });
    window.api = {
        post: vi.fn(async (url, body) => {
            if (url.endsWith("-configure"))
                policy = { receive: body.receive, share: body.share, generation: "consent-" + ++serial };
            return { data: { result: url.endsWith("-send") ? { state: options.state || "accepted" } : { ...policy } } };
        }),
    };
    const w = mount(PrivateLocation, { props: { owner, peer, radioId: "selected-radio", connected: true } });
    wrappers.push(w);
    await flushPromises();
    return { w, geo, sendCalls: () => window.api.post.mock.calls.filter(([url]) => url.endsWith("-send")) };
}
describe("Private MeshCore location consent", () => {
    it("starts off and never acquires location just by opening a contact", async () => {
        const { w, geo, sendCalls } = await setup();
        expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
        expect(geo.getCurrentPosition).not.toHaveBeenCalled();
        expect(sendCalls()).toHaveLength(0);
        expect(window.api.post.mock.calls[0][1]).toEqual({ peer, expected_owner: owner });
        expect(window.api.post.mock.calls[0][2]).toEqual({ params: { radio: "selected-radio" } });
    });
    it("receive permission neither grants sending nor requests GPS", async () => {
        const { w, geo, sendCalls } = await setup();
        await w.findAll("input")[0].setValue(true);
        await flushPromises();
        expect(w.findAll("input")[0].element.checked).toBe(true);
        expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
        expect(geo.getCurrentPosition).not.toHaveBeenCalled();
        expect(sendCalls()).toHaveLength(0);
    });
    it("submits exactly once to the pinned direct contact after an explicit click", async () => {
        const { w, geo, sendCalls } = await setup();
        await w.findAll("input")[1].setValue(true);
        await flushPromises();
        expect(geo.getCurrentPosition).not.toHaveBeenCalled();
        await w.find("[data-private-location-share]").trigger("click");
        expect(sendCalls()).toHaveLength(0);
        const [success, , controls] = geo.getCurrentPosition.mock.calls[0];
        expect(controls).toEqual({ enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
        await success(position);
        await flushPromises();
        expect(sendCalls()).toHaveLength(1);
        expect(sendCalls()[0][1]).toMatchObject({
            peer,
            expected_owner: owner,
            generation: "consent-1",
            fix: { latitude: 48.75, longitude: -122.48, last_update: 1793957816 },
        });
        expect(sendCalls()[0][2]).toEqual({ params: { radio: "selected-radio" } });
        expect(w.text()).toContain("Accepted by the selected radio");
    });
    it("revoking consent while GPS is pending discards the callback", async () => {
        const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
        await w.find("[data-private-location-share]").trigger("click");
        await w.findAll("input")[1].setValue(false);
        await flushPromises();
        await geo.getCurrentPosition.mock.calls[0][0](position);
        await flushPromises();
        expect(sendCalls()).toHaveLength(0);
    });
    it.each([
        { owner: "cc".repeat(32) },
        { peer: "dd".repeat(32) },
        { radioId: "other-radio" },
        { contextKey: "other-radio" },
        { connected: false },
    ])("discards stale GPS after context change %o", async (changed) => {
        const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
        await w.find("[data-private-location-share]").trigger("click");
        await w.setProps(changed);
        await flushPromises();
        await geo.getCurrentPosition.mock.calls[0][0](position);
        await flushPromises();
        expect(sendCalls()).toHaveLength(0);
    });
    it("does not send or retry when browser permission is declined", async () => {
        const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
        await w.find("[data-private-location-share]").trigger("click");
        geo.getCurrentPosition.mock.calls[0][1]({ code: 1 });
        await flushPromises();
        expect(sendCalls()).toHaveLength(0);
        expect(w.text()).toContain("Nothing was shared");
    });
    it("an uncertain submission is never automatically repeated", async () => {
        const { w, geo, sendCalls } = await setup({ state: "unknown", policy: { share: true, generation: "old" } });
        await w.find("[data-private-location-share]").trigger("click");
        await geo.getCurrentPosition.mock.calls[0][0](position);
        await flushPromises();
        expect(sendCalls()).toHaveLength(1);
        expect(w.text()).toContain("No automatic retry");
    });
    it("failed permission writes restore the confirmed checkbox", async () => {
        const { w } = await setup();
        window.api.post.mockRejectedValueOnce(new Error("offline"));
        await w.findAll("input")[1].setValue(true);
        await flushPromises();
        expect(w.findAll("input")[1].element.checked).toBe(false);
        expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
    });
});

it("handles a synchronous browser location error without submitting", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
    geo.getCurrentPosition.mockImplementation(() => {
        throw new Error("unavailable");
    });
    await w.find("[data-private-location-share]").trigger("click");
    expect(sendCalls()).toHaveLength(0);
    expect(w.text()).toContain("Nothing was shared");
    expect(w.find("[data-private-location-share]").element.disabled).toBe(false);
});

it("discards a location callback after the conversation is unmounted", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
    await w.find("[data-private-location-share]").trigger("click");
    w.unmount();
    wrappers.splice(wrappers.indexOf(w), 1);
    await geo.getCurrentPosition.mock.calls[0][0](position);
    await flushPromises();
    expect(sendCalls()).toHaveLength(0);
});

it("uses the existing native Android provider without requesting WebView location", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
    const fresh = vi.fn(() =>
        globalThis.dispatchEvent(
            new CustomEvent("meshchatnext-android-location", {
                detail: {
                    latitude: 48.75,
                    longitude: -122.48,
                    altitude: 0,
                    accuracy: 10,
                    speed: 0,
                    bearing: 0,
                    time: 1793957816000,
                },
            })
        )
    );
    vi.stubGlobal("MeshchatNextAndroid", {
        getPlatform: () => "android",
        isLocationPermissionGranted: () => true,
        requestFreshLocation: fresh,
    });
    expect(fresh).not.toHaveBeenCalled();
    await w.find("[data-private-location-share]").trigger("click");
    await flushPromises();
    expect(fresh).toHaveBeenCalledTimes(1);
    expect(geo.getCurrentPosition).not.toHaveBeenCalled();
    expect(sendCalls()).toHaveLength(1);
    expect(sendCalls()[0][1].fix.last_update).toBe(1793957816);
});

it("allows offline consent withdrawal while keeping location submission disabled", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { receive: true, share: true, generation: "old" } });
    await w.setProps({ connected: false });
    await flushPromises();
    expect(w.findAll("input")[0].element.checked).toBe(true);
    expect(w.findAll("input")[0].element.disabled).toBe(false);
    expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
    await w.findAll("input")[0].setValue(false);
    await flushPromises();
    expect(w.findAll("input")[0].element.checked).toBe(false);
    expect(geo.getCurrentPosition).not.toHaveBeenCalled();
    expect(sendCalls()).toHaveLength(0);
});

it("ignores a duplicate device-location callback for the same one-shot request", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
    await w.find("[data-private-location-share]").trigger("click");
    const callback = geo.getCurrentPosition.mock.calls[0][0];
    await callback(position);
    await callback(position);
    await flushPromises();
    expect(sendCalls()).toHaveLength(1);
});

it("keeps unknown permissions disabled until an explicit successful reread", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
    window.api.post.mockRejectedValueOnce(new Error("unavailable"));
    await w.setProps({ radioId: "other-radio" });
    await flushPromises();
    expect(w.findAll("input")[1].element.disabled).toBe(true);
    expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
    const retry = w.findAll("button").find((button) => button.text() === "Try reading permissions again");
    await retry.trigger("click");
    await flushPromises();
    expect(w.findAll("input")[1].element.disabled).toBe(false);
    expect(geo.getCurrentPosition).not.toHaveBeenCalled();
    expect(sendCalls()).toHaveLength(0);
});

it("does not share using a previous permission after an uncertain policy write", async () => {
    const { w, geo, sendCalls } = await setup({ policy: { share: true, generation: "old" } });
    window.api.post.mockRejectedValueOnce(new Error("response lost"));
    await w.findAll("input")[0].setValue(true);
    await flushPromises();
    expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
    expect(geo.getCurrentPosition).not.toHaveBeenCalled();
    expect(sendCalls()).toHaveLength(0);
});

it("requires a permissions reread after a rejected private submission", async () => {
    const { w, geo, sendCalls } = await setup({ state: "rejected", policy: { share: true, generation: "old" } });
    await w.find("[data-private-location-share]").trigger("click");
    await geo.getCurrentPosition.mock.calls[0][0](position);
    await flushPromises();
    expect(w.text()).toContain("Location was not sent");
    expect(w.find("[data-private-location-share]").element.disabled).toBe(true);
    expect(w.text()).toContain("Try reading permissions again");
    expect(sendCalls()).toHaveLength(1);
});
