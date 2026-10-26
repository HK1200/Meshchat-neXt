import { watch, onMounted, onBeforeUnmount } from "vue";
import NotificationUtils from "./NotificationUtils";
import NotificationSoundUtils from "./NotificationSoundUtils";
import { shouldPlayMessageSound, shouldShowOsMessageNotification } from "./notificationPolicy";
const seen = new Set();
let activeKey = "",
    holder = null;
export function useMeshCoreNotificationContext(key) {
    const lease = {};
    function update() {
        const current = key();
        if (current) holder = lease;
        if (holder !== lease) return;
        const foreground = document.visibilityState !== "hidden" && document.hasFocus();
        activeKey = foreground ? current || "" : "";
        NotificationUtils.setMeshCoreNotificationContext(activeKey);
        if (activeKey) NotificationUtils.clearMessageNotifications(activeKey);
    }
    onMounted(() => {
        update();
        window.addEventListener("focus", update);
        window.addEventListener("blur", update);
        document.addEventListener("visibilitychange", update);
    });
    watch(key, update);
    onBeforeUnmount(() => {
        window.removeEventListener("focus", update);
        window.removeEventListener("blur", update);
        document.removeEventListener("visibilitychange", update);
        if (holder === lease) {
            holder = null;
            activeKey = "";
            NotificationUtils.setMeshCoreNotificationContext("");
        }
    });
}
export async function handleMeshCoreNotification(event, config, overrides = {}) {
    if (
        !event ||
        event.type !== "meshcore.message" ||
        !["direct", "channel", "tactical"].includes(event.kind) ||
        !/^meshcore-[0-9a-f]{64}$/.test(event.notification_key || "") ||
        !event.id ||
        !event.owner
    )
        return;
    const id = event.owner + ":" + event.id;
    if (seen.has(id)) return;
    seen.add(id);
    if (seen.size > 4096) seen.delete(seen.values().next().value);
    if (!NotificationUtils.ownsOsMessageNotifications()) return; // Android background bridge owns OS alerts and sound.
    const focused = overrides.hasFocus ?? (document.visibilityState !== "hidden" && document.hasFocus());
    const policy = {
        isIncoming: true,
        dnd: Boolean(config?.do_not_disturb_enabled),
        hasFocus: focused,
        sourceHash: event.notification_key,
        openDestinationHashes: [overrides.activeKey ?? activeKey],
    };
    let played = false;
    if (shouldPlayMessageSound(policy)) played = await (overrides.playSound || NotificationSoundUtils.play)(config);
    if (shouldShowOsMessageNotification(policy))
        (overrides.showNotification || NotificationUtils.showMeshCoreMessageNotification)(event, played);
}
