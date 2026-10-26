import { mount, flushPromises } from "@vue/test-utils";
import { it, expect, vi } from "vitest";
import Controls from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreBeaconControls.vue";
vi.mock("../../meshchatnext/src/frontend/js/androidLocation", () => ({
    getAndroidPosition: vi.fn().mockResolvedValue({ latitude: 0, longitude: 0 }),
}));
vi.mock("../../meshchatnext/src/frontend/js/DialogUtils", () => ({
    default: { confirm: vi.fn().mockResolvedValue(true) },
}));
vi.mock("../../meshchatnext/src/frontend/js/csrfToken", () => ({ getCsrfToken: () => "test-csrf" }));
it("never starts implicitly, and requires explicit consent before native sharing", async () => {
    window.MeshchatNextAndroid = {
        startMeshCoreBeacons: vi.fn(),
        stopMeshCoreBeacons: vi.fn(),
        meshCoreBeaconStatus: () => JSON.stringify({ active: false, status: "Off" }),
    };
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { token: "test-token" } } }) };
    const owner = "a1".repeat(32),
        channel = "c3".repeat(32);
    const w = mount(Controls, {
        props: { owner, team: { enabled: true, channel_id: channel }, scope: "test-scope", connected: true },
    });
    try {
        expect(window.api.post).not.toHaveBeenCalled();
        expect(window.MeshchatNextAndroid.startMeshCoreBeacons).not.toHaveBeenCalled();
        await w.find("button").trigger("click");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith(expect.any(String), {
            expected_owner: owner,
            expected_channel_id: channel,
            expected_scope: "test-scope",
            interval: 300,
        });
        expect(window.MeshchatNextAndroid.startMeshCoreBeacons).toHaveBeenCalledWith(
            owner,
            "test-token",
            300,
            "test-csrf"
        );
        await w.setProps({ scope: "changed" });
        await flushPromises();
        expect(window.MeshchatNextAndroid.stopMeshCoreBeacons).toHaveBeenCalled();
    } finally {
        w.unmount();
        delete window.MeshchatNextAndroid;
    }
});
it("is unavailable when the native background service is absent", () => {
    delete window.MeshchatNextAndroid;
    const w = mount(Controls);
    expect(w.find("button").exists()).toBe(false);
    w.unmount();
});

it("passes the chosen automatic stop duration to Android and shows submission age", async () => {
    vi.useFakeTimers();
    let started = false;
    window.MeshchatNextAndroid = {
        startMeshCoreBeacons: vi.fn(),
        startTimedMeshCoreBeacons: vi.fn(() => {
            started = true;
        }),
        stopMeshCoreBeacons: vi.fn(),
        meshCoreBeaconStatus: () =>
            JSON.stringify(
                started
                    ? { active: true, status: "Position submitted", submitted: 3, secondsSinceSubmitted: 12 }
                    : { active: false, status: "Off" }
            ),
    };
    window.api = { post: vi.fn().mockResolvedValue({ data: { result: { token: "test-token" } } }) };
    const owner = "a1".repeat(32),
        channel = "c3".repeat(32);
    const w = mount(Controls, { props: { owner, team: { enabled: true, channel_id: channel }, connected: true } });
    try {
        await w.findAll("select")[1].setValue("15");
        await w.find("button").trigger("click");
        await flushPromises();
        expect(window.MeshchatNextAndroid.startTimedMeshCoreBeacons).toHaveBeenCalledWith(
            owner,
            "test-token",
            300,
            "test-csrf",
            15
        );
        expect(window.MeshchatNextAndroid.startMeshCoreBeacons).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1000);
        expect(w.text()).toContain("3 positions submitted");
        expect(w.text()).toContain("last 12 seconds ago");
        await w.find("button").trigger("click");
        await flushPromises();
        expect(window.MeshchatNextAndroid.stopMeshCoreBeacons).toHaveBeenCalled();
    } finally {
        w.unmount();
        delete window.MeshchatNextAndroid;
        vi.useRealTimers();
    }
});
