import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import Tools from "../../meshchatnext/src/frontend/components/map/internal/MeshCoreMapTools.vue";
const route = vi.hoisted(() => ({ value: { query: {} } }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn(), currentRoute: route }) }));
describe("MeshCore map layer lifecycle", () => {
    it("reads only on opt-in, rejects invalid coordinates, and removes its own layer on exit", async () => {
        const map = { addLayer: vi.fn(), removeLayer: vi.fn(), on: vi.fn() };
        window.api = {
            get: vi.fn().mockResolvedValue({
                data: {
                    result: {
                        owner: "a1".repeat(32),
                        connected: true,
                        nodes: [
                            {
                                peer: "b2".repeat(32),
                                latitude: 1,
                                longitude: 2,
                                name: "Test",
                                kind: 1,
                                updated: Date.now() / 1000,
                            },
                            { peer: "invalid", latitude: 100, longitude: 2 },
                        ],
                        tactical: null,
                    },
                },
            }),
            post: vi.fn(),
        };
        const w = mount(Tools, { props: { map }, global: { stubs: { Teleport: true } } });
        expect(window.api.get).not.toHaveBeenCalled();
        const layer = map.addLayer.mock.calls[0][0];
        expect(layer.getVisible()).toBe(false);
        await w.find("button").trigger("click");
        await flushPromises();
        expect(layer.getSource().getFeatures()).toHaveLength(1);
        await w.find('input[type="checkbox"]').setValue(true);
        await flushPromises();
        expect(layer.getVisible()).toBe(true);
        expect(window.api.post).not.toHaveBeenCalled();
        w.unmount();
        expect(map.removeLayer).toHaveBeenCalledWith(layer);
    });
});

it("opens a geofence notification on its boundary without sharing a position", async () => {
    const owner = "a1".repeat(32),
        channel = "c3".repeat(32);
    route.value.query = { meshcoreOwner: owner, meshcoreTeam: channel, meshcoreFence: "01020304:42" };
    const fit = vi.fn();
    const map = { addLayer: vi.fn(), removeLayer: vi.fn(), on: vi.fn(), getView: () => ({ fit }) };
    window.api = {
        get: vi.fn().mockResolvedValue({
            data: {
                result: {
                    owner,
                    connected: true,
                    nodes: [],
                    channels: [],
                    tactical: {
                        enabled: true,
                        channel_id: channel,
                        records: [
                            {
                                kind: "shape",
                                alias: "01020304",
                                id: 42,
                                shape_kind: 4,
                                points: [[0, 0]],
                                radius_m: 100,
                                geofence: 3,
                            },
                        ],
                        trails: [],
                    },
                },
            },
        }),
        post: vi.fn(),
    };
    const w = mount(Tools, { props: { map }, global: { stubs: { Teleport: true, MeshCoreTeamPanel: true } } });
    try {
        await flushPromises();
        expect(fit).toHaveBeenCalledTimes(1);
        expect(w.find('[aria-label="MeshCore map layer"]').exists()).toBe(true);
        expect(map.addLayer.mock.calls[0][0].getVisible()).toBe(true);
        expect(window.api.post).not.toHaveBeenCalled();
    } finally {
        w.unmount();
        route.value.query = {};
    }
});

it("opens a location-free team alert without inventing a map position", async () => {
    const owner = "a1".repeat(32),
        channel = "c3".repeat(32);
    route.value.query = { meshcoreOwner: owner, meshcoreTeam: channel, meshcoreItem: "alert:01020304:42" };
    const animate = vi.fn(),
        fit = vi.fn();
    const map = {
        addLayer: vi.fn(),
        removeLayer: vi.fn(),
        on: vi.fn(),
        getView: () => ({ fit, animate, getCenter: () => [0, 0] }),
    };
    window.api = {
        get: vi.fn().mockResolvedValue({
            data: {
                result: {
                    owner,
                    connected: true,
                    nodes: [],
                    tactical: {
                        enabled: true,
                        channel_id: channel,
                        records: [
                            {
                                kind: "alert",
                                alias: "01020304",
                                id: 42,
                                active: true,
                                note: "Test only",
                                latitude: null,
                                longitude: null,
                            },
                        ],
                        trails: [],
                    },
                },
            },
        }),
        post: vi.fn(),
    };
    const w = mount(Tools, { props: { map }, global: { stubs: { Teleport: true, MeshCoreTeamPanel: true } } });
    try {
        await flushPromises();
        expect(w.find('[aria-label="Selected MeshCore team item"]').text()).toContain("No location included");
        expect(animate).not.toHaveBeenCalled();
        expect(fit).not.toHaveBeenCalled();
        expect(window.api.post).not.toHaveBeenCalled();
    } finally {
        w.unmount();
        route.value.query = {};
    }
});

it("requests a local range fix only on click and clears it without transmitting", async () => {
    const getCurrentPosition = vi.fn((resolve) => resolve({ coords: { latitude: 1, longitude: 2, accuracy: 8 } }));
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition } });
    window.api = { get: vi.fn().mockResolvedValue({ data: { result: { nodes: [], tactical: null } } }), post: vi.fn() };
    const map = { addLayer: vi.fn(), removeLayer: vi.fn(), on: vi.fn() };
    const w = mount(Tools, { props: { map }, global: { stubs: { Teleport: true, MeshCoreTeamPanel: true } } });
    try {
        await w.find("button").trigger("click");
        await flushPromises();
        expect(getCurrentPosition).not.toHaveBeenCalled();
        await w
            .findAll("button")
            .find((b) => b.text() === "Use phone location for range")
            .trigger("click");
        await flushPromises();
        expect(w.text()).toContain("accuracy ±8 m");
        expect(window.api.post).not.toHaveBeenCalled();
        await w
            .findAll("button")
            .find((b) => b.text() === "Use map centre")
            .trigger("click");
        expect(w.text()).not.toContain("accuracy ±8 m");
    } finally {
        w.unmount();
        vi.unstubAllGlobals();
    }
});

it("ignores a range fix arriving after unmount", async () => {
    let finish;
    vi.stubGlobal("navigator", {
        geolocation: {
            getCurrentPosition: vi.fn((resolve) => {
                finish = resolve;
            }),
        },
    });
    window.api = { get: vi.fn().mockResolvedValue({ data: { result: { nodes: [], tactical: null } } }), post: vi.fn() };
    const map = { addLayer: vi.fn(), removeLayer: vi.fn(), on: vi.fn() };
    const w = mount(Tools, { props: { map }, global: { stubs: { Teleport: true, MeshCoreTeamPanel: true } } });
    try {
        await w.find("button").trigger("click");
        await flushPromises();
        await w
            .findAll("button")
            .find((b) => b.text() === "Use phone location for range")
            .trigger("click");
        w.unmount();
        finish({ coords: { latitude: 1, longitude: 2, accuracy: 8 } });
        await flushPromises();
        expect(window.api.post).not.toHaveBeenCalled();
    } finally {
        vi.unstubAllGlobals();
    }
});

it("reports denied location without sending or starting a watch", async () => {
    const watchPosition = vi.fn();
    vi.stubGlobal("navigator", {
        geolocation: { getCurrentPosition: vi.fn((resolve, reject) => reject(new Error("denied"))), watchPosition },
    });
    window.api = { get: vi.fn().mockResolvedValue({ data: { result: { nodes: [], tactical: null } } }), post: vi.fn() };
    const map = { addLayer: vi.fn(), removeLayer: vi.fn(), on: vi.fn() };
    const w = mount(Tools, { props: { map }, global: { stubs: { Teleport: true, MeshCoreTeamPanel: true } } });
    try {
        await w.find("button").trigger("click");
        await flushPromises();
        await w
            .findAll("button")
            .find((b) => b.text() === "Use phone location for range")
            .trigger("click");
        await flushPromises();
        expect(w.text()).toContain("Could not get a current location");
        expect(watchPosition).not.toHaveBeenCalled();
        expect(window.api.post).not.toHaveBeenCalled();
    } finally {
        w.unmount();
        vi.unstubAllGlobals();
    }
});
