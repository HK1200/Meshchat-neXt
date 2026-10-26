import { mount, flushPromises } from "@vue/test-utils";
import { describe, it, expect, vi, afterEach } from "vitest";
import { radioBatteryLevel } from "../../meshchatnext/src/frontend/js/radioBattery";
import RadioBatteryIndicators from "../../meshchatnext/src/frontend/components/layout/RadioBatteryIndicators.vue";
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
    vi.useRealTimers();
});
function api(connected = true) {
    window.api = {
        get: vi.fn(async (path) => ({
            data: path.endsWith("/reticulum/interfaces")
                ? { interfaces: { radio: { type: "RNodeInterface", force_ble: true } } }
                : path.endsWith("/interface-stats")
                  ? {
                        interface_stats: {
                            interfaces: [
                                {
                                    short_name: "radio",
                                    status: connected,
                                    bluetooth_connected: connected,
                                    battery_percent: 45,
                                    battery_state: "discharging",
                                },
                            ],
                        },
                    }
                  : path.endsWith("/meshcore/status")
                    ? { connected, connection: { kind: "ble" } }
                    : { result: { voltage_mv: 3890, percent: null } },
        })),
    };
}
describe("radio sidebar batteries", () => {
    it("maps measured SOC and companion voltage to the same four-level display", () => {
        expect(radioBatteryLevel({ percent: 0 })).toBe(0);
        expect(radioBatteryLevel({ percent: 45 })).toBe(2);
        expect(radioBatteryLevel({ percent: 100 })).toBe(4);
        expect(radioBatteryLevel({ voltage_mv: 3300 })).toBe(0);
        expect(radioBatteryLevel({ voltage_mv: 3500 })).toBe(1);
        expect(radioBatteryLevel({ voltage_mv: 3700 })).toBe(2);
        expect(radioBatteryLevel({ voltage_mv: 3890 })).toBe(3);
        expect(radioBatteryLevel({ voltage_mv: 4200 })).toBe(4);
        expect(radioBatteryLevel({ voltage_mv: 0 })).toBeNull();
        expect(radioBatteryLevel({ percent: NaN })).toBeNull();
    });
    it("uses consistent compact indicators and keeps numerical readings in tooltips", async () => {
        api();
        wrapper = mount(RadioBatteryIndicators);
        await flushPromises();
        expect(wrapper.findAll("svg")).toHaveLength(2);
        expect(wrapper.text()).toContain("RNode");
        expect(wrapper.text()).toContain("MeshCore");
        expect(wrapper.text()).not.toContain("45%");
        expect(wrapper.text()).not.toContain("3.89");
        expect(wrapper.find('[title*="3.89 V"]').exists()).toBe(true);
        expect(wrapper.find('[title*="3.89 V"]').findAll('rect[fill="currentColor"]')).toHaveLength(3);
        expect(wrapper.find('[title*="45% lit"]').exists()).toBe(false);
    });
    it("clears disconnected readings and stops polling on removal", async () => {
        vi.useFakeTimers();
        api();
        wrapper = mount(RadioBatteryIndicators);
        await flushPromises();
        api(false);
        await vi.advanceTimersByTimeAsync(30000);
        await flushPromises();
        expect(wrapper.findAll("svg")).toHaveLength(0);
        const get = window.api.get;
        wrapper.unmount();
        wrapper = null;
        const calls = get.mock.calls.length;
        await vi.advanceTimersByTimeAsync(60000);
        expect(get.mock.calls.length).toBe(calls);
    });
});
