import { mount, flushPromises } from "@vue/test-utils";
import MeshCoreChannelsPage from "../../meshchatnext/src/frontend/components/meshcore/MeshCoreChannelsPage.vue";
import { describe, it, expect, vi, afterEach } from "vitest";
import { handleMeshCoreNotification } from "../../meshchatnext/src/frontend/js/meshcoreNotifications";
import NotificationUtils from "../../meshchatnext/src/frontend/js/NotificationUtils";
const event = (id, kind = "direct") => ({
    type: "meshcore.message",
    id,
    kind,
    owner: "a1".repeat(32),
    name: kind === "channel" ? "#field" : "Peer",
    text: "hello",
    notification_key: "meshcore-" + "b2".repeat(32),
});
afterEach(() => {
    vi.restoreAllMocks();
    delete window.MeshchatNextAndroid;
    delete window.electron;
    NotificationUtils._meshCoreContext = "";
    NotificationUtils._rnsNotificationContext = [];
    NotificationUtils._notificationDnd = false;
});
describe("MeshCore notifications", () => {
    it("releases the open channel context when returning to the channel overview", async () => {
        vi.spyOn(document, "hasFocus").mockReturnValue(true);
        const channel = "c3".repeat(32),
            key = "meshcore-" + "b2".repeat(32);
        window.api = {
            get: vi.fn().mockImplementation(async (path, options) => ({
                data: {
                    result: {
                        available: true,
                        connected: true,
                        owner: "a1".repeat(32),
                        contacts: [],
                        channels: [{ channel_id: channel, name: "#field", kind: "public", slot: 1 }],
                        channel_messages: [],
                        ...(options.params.channel_id ? { active_notification_key: key } : {}),
                    },
                },
            })),
            post: vi.fn().mockResolvedValue({ data: {} }),
        };
        const wrapper = mount(MeshCoreChannelsPage, { props: { channelId: channel } });
        try {
            await flushPromises();
            expect(NotificationUtils._meshCoreContext).toBe(key);
            await wrapper.setProps({ channelId: "" });
            await flushPromises();
            expect(NotificationUtils._meshCoreContext).toBe("");
        } finally {
            wrapper.unmount();
        }
    });
    it("uses the existing background policy, avoids repeats and labels the network", async () => {
        const playSound = vi.fn().mockResolvedValue(true),
            showNotification = vi.fn();
        const incoming = event("desktop");
        await handleMeshCoreNotification(incoming, {}, { hasFocus: false, playSound, showNotification });
        await handleMeshCoreNotification(incoming, {}, { hasFocus: false, playSound, showNotification });
        expect(showNotification).toHaveBeenCalledTimes(1);
        expect(showNotification).toHaveBeenCalledWith(incoming, true);
        window.electron = { showNotification: vi.fn() };
        NotificationUtils.showMeshCoreMessageNotification(event("label", "channel"), true);
        expect(window.electron.showNotification).toHaveBeenCalledWith(
            "MeshCore · #field",
            "hello",
            true,
            event("label").notification_key
        );
    });
    it("suppresses sound and OS alerts for DND and the focused open MeshCore view", async () => {
        const playSound = vi.fn(),
            showNotification = vi.fn();
        await handleMeshCoreNotification(
            event("dnd"),
            { do_not_disturb_enabled: true },
            { hasFocus: false, playSound, showNotification }
        );
        const incoming = event("active");
        await handleMeshCoreNotification(
            incoming,
            {},
            { hasFocus: true, activeKey: incoming.notification_key, playSound, showNotification }
        );
        expect(playSound).not.toHaveBeenCalled();
        expect(showNotification).not.toHaveBeenCalled();
    });
    it("leaves Android alerts to the background bridge and preserves both network contexts", async () => {
        window.MeshchatNextAndroid = {
            getPlatform: () => "android",
            setOpenConversationHashes: vi.fn(),
            setDoNotDisturbEnabled: vi.fn(),
        };
        const showNotification = vi.fn(),
            playSound = vi.fn();
        await handleMeshCoreNotification(event("android"), {}, { hasFocus: false, playSound, showNotification });
        expect(showNotification).not.toHaveBeenCalled();
        expect(playSound).not.toHaveBeenCalled();
        NotificationUtils.syncAndroidNotificationContext(["rns-peer"], true);
        NotificationUtils.setMeshCoreNotificationContext("meshcore-key");
        expect(window.MeshchatNextAndroid.setOpenConversationHashes).toHaveBeenLastCalledWith("rns-peer,meshcore-key");
        NotificationUtils.syncAndroidNotificationContext(["other-rns-peer"], false);
        expect(window.MeshchatNextAndroid.setOpenConversationHashes).toHaveBeenLastCalledWith(
            "other-rns-peer,meshcore-key"
        );
        NotificationUtils.setMeshCoreNotificationContext("");
        expect(window.MeshchatNextAndroid.setOpenConversationHashes).toHaveBeenLastCalledWith("other-rns-peer");
    });
});

describe("MeshCore geofence notifications", () => {
    it("uses the normal DND policy and opens the selected boundary", async () => {
        const { meshcoreNotificationRoute } =
            await import("../../meshchatnext/src/frontend/js/meshcoreNotificationRoute");
        const incoming = { ...event("fence", "tactical"), name: "Geofence", text: "Test entered boundary" };
        const showNotification = vi.fn(),
            playSound = vi.fn().mockResolvedValue(false);
        await handleMeshCoreNotification(incoming, {}, { hasFocus: false, showNotification, playSound });
        expect(showNotification).toHaveBeenCalledWith(incoming, false);
        const api = {
            get: vi.fn().mockResolvedValue({
                data: {
                    result: {
                        kind: "tactical",
                        owner: "a1".repeat(32),
                        target: "c3".repeat(32),
                        shape: "01020304:42",
                    },
                },
            }),
        };
        const route = await meshcoreNotificationRoute(incoming.notification_key, api);
        expect(route.name).toBe("map");
        expect(route.query.meshcoreFence).toBe("01020304:42");
        expect(route.query.meshcoreOwner).toBe("a1".repeat(32));
        api.get.mockResolvedValue({
            data: { result: { kind: "tactical", owner: "a1".repeat(32), target: "c3".repeat(32), shape: "invalid" } },
        });
        await expect(meshcoreNotificationRoute(incoming.notification_key, api)).rejects.toThrow(
            "Invalid MeshCore boundary"
        );
    });
});

it("routes a team alert to its map item and rejects unsupported item identifiers", async () => {
    const { meshcoreNotificationRoute } = await import("../../meshchatnext/src/frontend/js/meshcoreNotificationRoute");
    const target = { kind: "tactical", owner: "a1".repeat(32), target: "c3".repeat(32), item: "alert:01020304:42" };
    const api = { get: vi.fn().mockResolvedValue({ data: { result: target } }) };
    expect((await meshcoreNotificationRoute("meshcore-" + "b2".repeat(32), api)).query.meshcoreItem).toBe(target.item);
    api.get.mockResolvedValue({ data: { result: { ...target, item: "other:01020304:42" } } });
    await expect(meshcoreNotificationRoute("meshcore-" + "b2".repeat(32), api)).rejects.toThrow();
});
