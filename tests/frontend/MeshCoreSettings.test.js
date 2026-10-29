import { describe, it, expect, vi, afterEach } from "vitest";
import { ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import MeshCoreSettings from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreSettings.vue";
const state = vi.hoisted(() => ({}));
vi.mock("../../meshchatnext/src/frontend/js/meshcoreUi", () => ({ useMeshCoreUi: () => state }));
const owner = "a1".repeat(32);
const values = {
    frequency_mhz: 906.875,
    bandwidth_khz: 250,
    sf: 11,
    cr: 5,
    tx_power_dbm: 22,
    max_tx_power_dbm: 22,
    path_hash_bytes: 2,
    path_hash_supported: true,
};
let wrapper;
afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
});
function setup(overrides = {}) {
    Object.assign(state, {
        snapshot: ref({ available: true, connected: true, owner }),
        error: ref(""),
        action: vi.fn(),
        refresh: vi.fn().mockResolvedValue(),
        ...overrides,
    });
    window.api = {
        get: vi.fn().mockResolvedValue({ data: { result: values } }),
        post: vi.fn().mockResolvedValue({ data: { result: { ...values, sf: 10 } } }),
    };
    wrapper = mount(MeshCoreSettings, {
        global: { stubs: { MeshCoreIdentitySettings: true, MeshCoreBackups: true, MeshCoreRadio2Settings: true } },
    });
    return wrapper;
}
function button(text) {
    return wrapper.findAll("button").find((b) => b.text() === text);
}
async function read() {
    await button("Read from radio").trigger("click");
    await flushPromises();
}
describe("MeshCore radio settings", () => {
    it("offers native Windows discovery without Android pairing or OTG instructions", async () => {
        setup({
            snapshot: ref({
                available: true,
                connected: false,
                owner,
                radio_platform: "windows",
                bluetooth_discovery_supported: true,
            }),
        });
        await flushPromises();
        expect(wrapper.text()).toContain("Find nearby radios");
        expect(wrapper.text()).not.toContain("Pair your radio in Android");
        const selector = wrapper.findAll("select").find((item) => item.find('option[value="usb"]').exists());
        await selector.setValue("usb");
        await flushPromises();
        expect(wrapper.text()).toContain("COM port");
        expect(wrapper.text()).not.toContain("OTG cable");
    });
    it("hides a saved connection's selectors until Edit connection is opened", async () => {
        setup({
            snapshot: ref({
                available: true,
                connected: false,
                owner,
                radio_id: "default",
                connection: { kind: "ble", target: "AA:BB:CC:DD:EE:FF" },
            }),
        });
        await flushPromises();
        const editor = wrapper.get("[data-radio-connection-editor]");
        expect(editor.attributes("open")).toBeUndefined();
        expect(editor.get("summary").text()).toBe("Edit connection");
        editor.element.open = true;
        expect(editor.element.open).toBe(true);
        expect(editor.find("select").exists()).toBe(true);
    });

    it("changes the connection editor to the selected card's saved device", async () => {
        setup({ snapshot: ref({ available: false, connected: false }) });
        const radios = [
            { id: "default", label: "Home", owner },
            { id: "b2".repeat(16), label: "Field", owner: "b2".repeat(32) },
        ];
        state.snapshot.value = {
            available: true,
            connected: false,
            owner,
            radio_platform: "linux",
            radio_id: "default",
            radios,
            connection: { kind: "ble", target: "AA:BB:CC:DD:EE:FF" },
        };
        await flushPromises();
        expect(wrapper.findAll("[data-radio-settings]")).toHaveLength(1);
        state.snapshot.value = {
            ...state.snapshot.value,
            owner: "b2".repeat(32),
            radio_id: "b2".repeat(16),
            connection: { kind: "usb", target: "/dev/serial/by-id/field" },
        };
        await flushPromises();
        const editor = wrapper.get(`[data-meshcore-radio="${"b2".repeat(16)}"] [data-radio-connection-editor]`);
        expect(editor.find("select").element.value).toBe("usb");
        expect(editor.get('[aria-label="USB radio"]').element.value).toBe("/dev/serial/by-id/field");
        expect(wrapper.get('[data-meshcore-radio="default"]').find("[data-radio-settings]").exists()).toBe(false);
    });

    it("stages the regional preset without writing the radio or changing power and path hash", async () => {
        setup();
        await read();
        window.api.post.mockClear();
        await button("Use Puget Mesh preset").trigger("click");
        expect(window.api.post).not.toHaveBeenCalled();
        const inputs = wrapper.findAll('input[type="number"]');
        expect(inputs.map((input) => input.element.value)).toEqual(["910.525", "62.5", "22"]);
        const selects = wrapper.findAll("form select").slice(-3);
        expect(selects.map((select) => select.element.value)).toEqual(["7", "5", "2"]);
        expect(wrapper.text()).toContain("Review and apply");
        expect(wrapper.text()).toContain("Radio2 are unchanged");
    });

    it("does not request discovery when the backend reports it unavailable", async () => {
        setup({ snapshot: ref({ available: true, connected: false, owner, bluetooth_discovery_supported: false }) });
        await flushPromises();
        expect(window.api.get).not.toHaveBeenCalled();
        expect(wrapper.text()).toContain("Bluetooth device discovery is unavailable on this backend");
    });

    it("offers Linux radio discovery without Android pairing instructions", async () => {
        setup({
            snapshot: ref({
                available: true,
                connected: false,
                owner,
                bluetooth_discovery_supported: true,
                radio_platform: "linux",
            }),
        });
        await flushPromises();
        expect(window.api.get).toHaveBeenCalled();
        expect(wrapper.text()).toContain("Find nearby radios");
        expect(wrapper.text()).not.toContain("Pair your radio in Android");
    });

    it("does not restart Bluetooth discovery when polling replaces the snapshot", async () => {
        setup({
            snapshot: ref({
                available: true,
                connected: false,
                owner,
                radio_platform: "linux",
                bluetooth_discovery_supported: true,
            }),
        });
        await flushPromises();
        for (let poll = 0; poll < 3; poll++) {
            state.snapshot.value = { ...state.snapshot.value, profile_name: `Poll ${poll}` };
            await flushPromises();
        }
        expect(window.api.get.mock.calls.filter(([path]) => path.endsWith("/bluetooth-devices"))).toHaveLength(1);
    });

    it("leaves saved Linux companions to reconnect without an automatic scan, while allowing manual discovery", async () => {
        setup({
            snapshot: ref({
                available: true,
                connected: false,
                owner,
                radio_platform: "linux",
                bluetooth_discovery_supported: true,
                connection: { kind: "ble", target: "AA:BB:CC:DD:EE:FF" },
            }),
        });
        await flushPromises();
        expect(window.api.get.mock.calls.filter(([path]) => path.endsWith("/bluetooth-devices"))).toHaveLength(0);
        await button("Find nearby radios").trigger("click");
        await flushPromises();
        expect(window.api.get.mock.calls.filter(([path]) => path.endsWith("/bluetooth-devices"))).toHaveLength(1);
    });

    it("cancels paired-radio discovery when the settings view is removed", async () => {
        setup({ snapshot: ref({ available: true, connected: false, owner }) });
        const call = window.api.get.mock.calls.find(([path]) => path.endsWith("/bluetooth-devices"));
        expect(call).toBeDefined();
        expect(call[1].signal.aborted).toBe(false);
        wrapper.unmount();
        wrapper = null;
        expect(call[1].signal.aborted).toBe(true);
        await flushPromises();
    });

    it("waits for backup operations before reading and refreshes imported radio and name values", async () => {
        setup({ snapshot: ref({ available: true, connected: false, owner }) });
        const backups = wrapper.findComponent({ name: "MeshCoreBackups" });
        const identity = wrapper.findComponent({ name: "MeshCoreIdentitySettings" });
        backups.vm.$emit("busy", true);
        await flushPromises();
        state.snapshot.value = { ...state.snapshot.value, connected: true };
        await flushPromises();
        expect(window.api.get).not.toHaveBeenCalledWith(
            "/api/v1/meshcore/settings",
            expect.objectContaining({ signal: expect.any(AbortSignal) })
        );
        backups.vm.$emit("changed", { state: "complete", completed: ["name", "radio"] });
        await flushPromises();
        expect(state.refresh).toHaveBeenCalledOnce();
        expect(identity.props("refreshKey")).toBe(1);
        backups.vm.$emit("busy", false);
        await flushPromises();
        expect(window.api.get).toHaveBeenCalledWith(
            "/api/v1/meshcore/settings",
            expect.objectContaining({ signal: expect.any(AbortSignal) })
        );
        expect(button("Read from radio").attributes("disabled")).toBeUndefined();
    });
    it("uses the saved connection details without treating the selected flag as a device", async () => {
        setup();
        state.snapshot.value = { ...state.snapshot.value, selected: true };
        await flushPromises();
        expect(wrapper.find('[aria-label="Paired Bluetooth radio"]').element.value).toBe("");
        state.snapshot.value = { ...state.snapshot.value, connection: { kind: "ble", target: "AA:BB:CC:DD:EE:FF" } };
        await flushPromises();
        expect(wrapper.find('[aria-label="Paired Bluetooth radio"]').element.value).toBe("AA:BB:CC:DD:EE:FF");
    });
    it("loads existing radio values automatically when it connects", async () => {
        setup({ snapshot: ref({ available: true, connected: false, owner }) });
        state.snapshot.value = { ...state.snapshot.value, connected: true };
        await flushPromises();
        expect(window.api.get).toHaveBeenCalledWith(
            "/api/v1/meshcore/settings",
            expect.objectContaining({ signal: expect.any(AbortSignal) })
        );
        expect(wrapper.text()).toContain("Current settings read from radio.");
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("lists paired radios without choosing or connecting automatically", async () => {
        setup();
        window.api.get.mockResolvedValueOnce({
            data: {
                result: [
                    { name: "MeshCore T1000-E", address: "AA:BB:CC:DD:EE:FF" },
                    { name: "RNode 2250", address: "11:22:33:44:55:66" },
                ],
            },
        });
        await flushPromises();
        await button("Refresh paired radios").trigger("click");
        await flushPromises();
        const picker = wrapper.find('[aria-label="Paired Bluetooth radio"]');
        expect(picker.text()).toContain("MeshCore T1000-E");
        expect(state.action).not.toHaveBeenCalled();
        await picker.setValue("AA:BB:CC:DD:EE:FF");
        state.snapshot.value = { ...state.snapshot.value, connected: false };
        await flushPromises();
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(state.action).toHaveBeenCalledWith("connect", {
            kind: "ble",
            target: "AA:BB:CC:DD:EE:FF",
            receive: true,
            auto_reconnect: true,
        });
    });

    it("explains USB detach and permission issues without exposing raw diagnostics", async () => {
        setup({ snapshot: ref({ available: true, connected: false, connection_issue: "usb_detached", owner }) });
        expect(wrapper.text()).toContain("USB radio or hub was disconnected");
        state.snapshot.value = { ...state.snapshot.value, connection_issue: "usb_permission_required" };
        await flushPromises();
        expect(wrapper.text()).toContain("USB access is needed");
        state.snapshot.value = { ...state.snapshot.value, connected: true };
        await flushPromises();
        expect(wrapper.text()).not.toContain("USB access is needed");
    });

    it("requires explicit USB selection and permission before connecting", async () => {
        setup({ snapshot: ref({ available: true, connected: false, owner }) });
        await flushPromises();
        window.api.get.mockResolvedValue({
            data: {
                result: [
                    { name: "T1000-E", path: "/dev/bus/usb/001/002", permission: false },
                    { name: "RNode", path: "/dev/bus/usb/001/003", permission: true },
                ],
            },
        });
        await wrapper.findAll("select")[0].setValue("usb");
        await flushPromises();
        const picker = wrapper.find('[aria-label="USB radio"]');
        expect(picker.element.value).toBe("");
        expect(state.action).not.toHaveBeenCalled();
        await picker.setValue("/dev/bus/usb/001/002");
        window.api.post.mockResolvedValueOnce({ data: { result: { granted: false, requested: true } } });
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledWith("/api/v1/meshcore/usb-permission", {
            path: "/dev/bus/usb/001/002",
        });
        expect(wrapper.text()).toContain("Allow USB access");
        expect(state.action).not.toHaveBeenCalled();
        window.api.post.mockResolvedValueOnce({ data: { result: { granted: true, requested: false } } });
        await wrapper.find("form").trigger("submit");
        await flushPromises();
        expect(state.action).toHaveBeenCalledWith("connect", {
            kind: "usb",
            target: "/dev/bus/usb/001/002",
            receive: true,
            auto_reconnect: true,
        });
    });

    it("requires a read, preserves drafts across status polls, and writes only changes with the owner guard", async () => {
        setup();
        expect(window.api.get).not.toHaveBeenCalledWith(
            "/api/v1/meshcore/settings",
            expect.objectContaining({ signal: expect.any(AbortSignal) })
        );
        expect(window.api.post).not.toHaveBeenCalled();
        await read();
        await wrapper
            .findAll("label")
            .find((l) => l.text().startsWith("Spreading factor"))
            .find("select")
            .setValue("10");
        state.snapshot.value = { ...state.snapshot.value, profile_name: "Poll update" };
        await flushPromises();
        expect(
            wrapper
                .findAll("label")
                .find((l) => l.text().startsWith("Spreading factor"))
                .find("select").element.value
        ).toBe("10");
        await wrapper.findAll("form")[1].trigger("submit");
        await flushPromises();
        expect(window.api.post).toHaveBeenCalledExactlyOnceWith("/api/v1/meshcore/settings", {
            sf: 10,
            expected_owner: owner,
        });
        expect(wrapper.text()).toContain("saved and verified");
        expect(button("Apply and verify").attributes("disabled")).toBeDefined();
    });
    it("blocks retries after an uncertain write until the radio is read again", async () => {
        setup();
        await read();
        await wrapper
            .findAll("label")
            .find((l) => l.text().startsWith("Spreading factor"))
            .find("select")
            .setValue("10");
        window.api.post.mockRejectedValueOnce(new Error("timeout"));
        await wrapper.findAll("form")[1].trigger("submit");
        await flushPromises();
        expect(wrapper.text()).toContain("Some settings may have changed");
        expect(button("Apply and verify").attributes("disabled")).toBeDefined();
        await wrapper.findAll("form")[1].trigger("submit");
        expect(window.api.post).toHaveBeenCalledTimes(1);
        await read();
        expect(wrapper.text()).not.toContain("Some settings may have changed");
    });
    it("clears the draft when the radio identity changes and discards stale read results", async () => {
        setup();
        let resolve;
        window.api.get.mockReturnValueOnce(
            new Promise((r) => {
                resolve = r;
            })
        );
        await button("Read from radio").trigger("click");
        state.snapshot.value = { ...state.snapshot.value, owner: "b2".repeat(32) };
        await flushPromises();
        window.api.get.mockResolvedValueOnce({ data: { result: { ...values, sf: 9 } } });
        resolve({ data: { result: values } });
        await flushPromises();
        expect(wrapper.findAll("form")).toHaveLength(2);
        expect(
            wrapper
                .findAll("label")
                .find((l) => l.text().startsWith("Spreading factor"))
                .find("select").element.value
        ).toBe("9");
        expect(window.api.post).not.toHaveBeenCalled();
    });
    it("disables unsupported path hashes rather than inventing a default", async () => {
        setup();
        window.api.get.mockResolvedValueOnce({
            data: { result: { ...values, path_hash_supported: false, path_hash_bytes: null } },
        });
        await read();
        const hashes = wrapper
            .findAll("label")
            .find((l) => l.text().startsWith("Default path hash"))
            .find("select");
        expect(hashes.attributes("disabled")).toBeDefined();
        expect(hashes.text()).toContain("Unsupported");
    });
});

it("hides regions during setup and preserves the tool link in normal settings", async () => {
    setup();
    await wrapper.setProps({ setupMode: true });
    expect(wrapper.text()).not.toContain("Channel regions are optional");
    expect(wrapper.text()).not.toContain("MeshCore regions & channel scoping");
    expect(
        wrapper.findAllComponents({ name: "RouterLink" }).some((link) => link.text().includes("channel scoping"))
    ).toBe(false);
    await wrapper.setProps({ setupMode: false });
    expect(wrapper.text()).toContain("MeshCore regions & channel scoping");
});
