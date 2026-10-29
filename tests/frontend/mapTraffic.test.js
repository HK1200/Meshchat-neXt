import { defineComponent, h, reactive, ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import {
    trafficGeometry,
    trafficGaps,
    useMeshCoreMapTraffic,
} from "../../meshchatnext/src/frontend/js/map/useMeshCoreMapTraffic";

const packet = { id: "one", route: "flood", points: [[1, 2], [2, 3], null, [4, 5], [5, 6]] };
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe("packet geometry", () => {
    it("breaks trails and packet movement at missing or ambiguous hops", () => {
        expect(trafficGeometry(packet, 0.1).segments).toHaveLength(2);
        expect(trafficGeometry(packet, 0.1).head).not.toBeNull();
        expect(trafficGeometry(packet, 0.4).head).toBeNull();
        expect(trafficGeometry(packet, 0.65).head).toBeNull();
        expect(trafficGeometry(packet, 0.9).head).not.toBeNull();
    });
    it("never animates a direct route as an observed traversal", () => {
        expect(trafficGeometry({ ...packet, route: "direct" }, 0.5).points).toEqual([]);
    });
    it("rejects invalid coordinates and keeps dateline crossings local", () => {
        expect(
            trafficGeometry(
                {
                    route: "flood",
                    points: [
                        [NaN, 0],
                        [1, 91],
                        [2, 3],
                    ],
                },
                0
            ).segments
        ).toEqual([]);
        const { segments } = trafficGeometry(
            {
                route: "flood",
                points: [
                    [179, 0],
                    [-179, 0],
                ],
            },
            0.5
        );
        expect(Math.abs(segments[0][1][0] - segments[0][0][0])).toBeLessThan(300000);
    });
});

it("baselines history, polls only while enabled, and removes listeners and layer on pause", async () => {
    vi.useFakeTimers();
    const map = { addLayer: vi.fn(), removeLayer: vi.fn(), render: vi.fn() };
    const options = reactive({ map, enabled: false, owner: "owner", connected: true });
    let status;
    const wrapper = mount(
        defineComponent({
            setup() {
                status = useMeshCoreMapTraffic(() => ({ ...options }));
                return () => h("div");
            },
        })
    );
    window.api = {
        get: vi.fn().mockResolvedValue({
            data: {
                result: { owner: "owner", connected: true, packets: [{ ...packet, received: Date.now() / 1000 }] },
            },
        }),
    };
    try {
        expect(window.api.get).not.toHaveBeenCalled();
        options.enabled = true;
        await flushPromises();
        expect(map.addLayer).toHaveBeenCalledTimes(1);
        expect(status.value).toContain("Listening");
        window.api.get.mockResolvedValue({
            data: {
                result: {
                    owner: "owner",
                    connected: true,
                    packets: [{ ...packet, id: "two", received: Date.now() / 1000 }],
                },
            },
        });
        await vi.advanceTimersByTimeAsync(2000);
        expect(status.value).toContain("Partial routes");
        options.enabled = false;
        await flushPromises();
        expect(map.removeLayer).toHaveBeenCalledTimes(1);
        const calls = window.api.get.mock.calls.length;
        await vi.advanceTimersByTimeAsync(4000);
        expect(window.api.get).toHaveBeenCalledTimes(calls);
    } finally {
        wrapper.unmount();
    }
});

it("keeps the tapered comet wake within a known segment and removes it in a gap", () => {
    const comet = trafficGeometry(packet, 0.2);
    expect(comet.wake).toHaveLength(21);
    expect(comet.wake.at(-1)).toEqual(comet.head);
    const [start, end] = comet.segments[0];
    for (const point of comet.wake) {
        expect(point[0]).toBeGreaterThanOrEqual(start[0]);
        expect(point[0]).toBeLessThanOrEqual(end[0]);
    }
    expect(trafficGeometry(packet, 0.4).wake).toEqual([]);
});

it("marks internal gaps without claiming positions for unknown endpoints", () => {
    const gaps = trafficGaps(packet);
    expect(gaps).toHaveLength(1);
    expect(gaps[0].count).toBe(1);
    expect(gaps[0].position.every(Number.isFinite)).toBe(true);
    expect(trafficGaps({ route: "direct", points: packet.points })).toEqual([]);
    expect(trafficGaps({ route: "flood", points: [null, [1, 2], null] })).toEqual([]);
});

it("scopes and deduplicates the gap summary without creating map overlays, then clears it on radio change", async () => {
    vi.useFakeTimers();
    const map = {
        addLayer: vi.fn(),
        removeLayer: vi.fn(),
        render: vi.fn(),
        addOverlay: vi.fn(),
        removeOverlay: vi.fn(),
    };
    const options = reactive({ map, enabled: true, owner: "owner", radioId: "radio-a", connected: true });
    const gaps = ref([]);
    let count = 0;
    window.api = {
        get: vi.fn().mockImplementation(async () => ({
            data: {
                result: {
                    owner: "owner",
                    radio_id: "radio-a",
                    connected: true,
                    packets: count++
                        ? [packet, { ...packet, id: "duplicate-path" }].map((p) => ({
                              ...p,
                              received: Date.now() / 1000,
                          }))
                        : [],
                },
            },
        })),
    };
    const wrapper = mount(
        defineComponent({
            setup() {
                useMeshCoreMapTraffic(() => ({ ...options }), gaps);
                return () => h("div");
            },
        })
    );
    try {
        await flushPromises();
        expect(window.api.get.mock.calls[0][1].params).toEqual({ radio: "radio-a", owner: "owner" });
        await vi.advanceTimersByTimeAsync(2000);
        expect(gaps.value).toEqual([{ key: expect.any(String), count: 1 }]);
        expect(map.addOverlay).not.toHaveBeenCalled();
        options.radioId = "radio-b";
        await flushPromises();
        expect(gaps.value).toEqual([]);
        expect(window.api.get.mock.calls.at(-1)[1].params.radio).toBe("radio-b");
    } finally {
        wrapper.unmount();
    }
});
