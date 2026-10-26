import { ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vitest";
import Footer from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreAccountFooter.vue";
const snapshot = ref({});
const action = vi.fn(),
    push = vi.fn();
vi.mock("../../meshchatnext/src/frontend/js/meshcoreUi", () => ({ useMeshCoreUi: () => ({ snapshot, action }) }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));
const selection = { kind: "ble", target: "AA:BB:CC:DD:EE:FF" };
function mountFooter() {
    return mount(Footer, {
        global: { stubs: { RouterLink: true, AppModal: true, MaterialDesignIcon: true, MeshCoreIdentityShare: true } },
    });
}
async function expand(w) {
    await w.find('[aria-label="More MeshCore controls"]').trigger("click");
}
function connectionButton(w) {
    return w.find('[aria-label="MeshCore radio connection"] button');
}
beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    snapshot.value = {
        available: true,
        connected: true,
        selected: true,
        connection: selection,
        owner: "a1".repeat(32),
    };
    action.mockImplementation(async (name) => {
        if (name === "disconnect")
            snapshot.value = { ...snapshot.value, connected: false, selected: false, connection: null };
        if (name === "connect")
            snapshot.value = { ...snapshot.value, connected: true, selected: true, connection: selection };
        return {};
    });
});
it("shows status and reconnects the previously selected radio after an explicit disconnect", async () => {
    const w = mountFooter();
    try {
        await expand(w);
        expect(w.text()).toContain("Bluetooth · AA:BB:CC:DD:EE:FF");
        expect(action).not.toHaveBeenCalled();
        await connectionButton(w).trigger("click");
        await flushPromises();
        expect(action).toHaveBeenLastCalledWith("disconnect", {});
        expect(connectionButton(w).text()).toBe("Connect MeshCore");
        await connectionButton(w).trigger("click");
        await flushPromises();
        expect(action).toHaveBeenLastCalledWith("connect", { ...selection, receive: true, auto_reconnect: true });
        expect(connectionButton(w).text()).toBe("Disconnect MeshCore");
    } finally {
        w.unmount();
    }
});
it("remembers the selected radio across sidebar remounts without auto-connecting", async () => {
    const first = mountFooter();
    first.unmount();
    snapshot.value = { available: true, connected: false, selected: false, connection: null };
    const w = mountFooter();
    try {
        await expand(w);
        expect(action).not.toHaveBeenCalled();
        await connectionButton(w).trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledWith("connect", expect.objectContaining(selection));
    } finally {
        w.unmount();
    }
});
it("routes first-time users to radio selection instead of choosing a device", async () => {
    snapshot.value = { available: true, connected: false, selected: false };
    const w = mountFooter();
    try {
        await expand(w);
        await connectionButton(w).trigger("click");
        expect(push).toHaveBeenCalledWith({ name: "meshcore-settings" });
        expect(action).not.toHaveBeenCalled();
    } finally {
        w.unmount();
    }
});
it("requires USB permission before connecting and keeps failures visible", async () => {
    localStorage.setItem(
        "meshchat-next.meshcore.last-radio",
        JSON.stringify({ kind: "usb", target: "/dev/bus/usb/001/002" })
    );
    snapshot.value = { available: true, connected: false, selected: false };
    action.mockResolvedValue({ granted: false });
    const w = mountFooter();
    try {
        await expand(w);
        await connectionButton(w).trigger("click");
        await flushPromises();
        expect(action).toHaveBeenCalledTimes(1);
        expect(action).toHaveBeenCalledWith("usb-permission", { path: "/dev/bus/usb/001/002" });
        expect(w.text()).toContain("Allow USB access");
        action.mockRejectedValue(new Error("Unavailable"));
        await connectionButton(w).trigger("click");
        await flushPromises();
        expect(w.find('[role="alert"]').text()).toContain("Could not change the MeshCore connection");
    } finally {
        w.unmount();
    }
});
