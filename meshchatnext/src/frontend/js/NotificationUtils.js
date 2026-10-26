import { voicePreview } from "./meshcoreVoice";
// SPDX-License-Identifier: 0BSD

class NotificationUtils {
    /** @type {Map<string, { close: () => void }[]>} */
    static _webMessageNotifications = new Map();

    static _isAndroid() {
        return Boolean(
            typeof window !== "undefined" &&
            window.MeshchatNextAndroid &&
            typeof window.MeshchatNextAndroid.getPlatform === "function" &&
            window.MeshchatNextAndroid.getPlatform() === "android"
        );
    }

    /**
     * Android OS message notifs are owned by the Python push bridge.
     * @returns {boolean}
     */
    static ownsOsMessageNotifications() {
        return !NotificationUtils._isAndroid();
    }

    static _meshCoreContext = "";
    static _rnsNotificationContext = [];
    static _notificationDnd = false;

    static setMeshCoreNotificationContext(key) {
        NotificationUtils._meshCoreContext = key || "";
        NotificationUtils.syncAndroidNotificationContext(
            NotificationUtils._rnsNotificationContext,
            NotificationUtils._notificationDnd
        );
    }

    static showMeshCoreMessageNotification(event, silent = false) {
        if (!NotificationUtils.ownsOsMessageNotifications()) return;
        const title = `MeshCore · ${event.name || (event.kind === "channel" ? "Channel" : "Direct message")}`.slice(
            0,
            200
        );
        const text = String(event.text || "New message"),
            gap = event.kind === "channel" ? text.indexOf(": ") : -1;
        const body = String(
            gap >= 0 ? text.slice(0, gap + 2) + voicePreview(text.slice(gap + 2)) : voicePreview(text)
        ).slice(0, 200);
        const key = event.notification_key;
        if (window.electron) {
            window.electron.showNotification?.(title, body, silent, key);
            return;
        }
        if (typeof window.Notification !== "function") return;
        window.Notification.requestPermission()
            .then((permission) => {
                if (permission !== "granted") return;
                const notification = new window.Notification(title, { body, tag: key, silent: Boolean(silent) });
                NotificationUtils._trackWebNotification(key, notification);
                notification.onclick = () => {
                    window.focus();
                    window.dispatchEvent(
                        new CustomEvent("meshchatnext-intent-uri", {
                            detail: `meshchatnext://app/meshcore?notification=${encodeURIComponent(key)}`,
                        })
                    );
                };
                notification.onclose = () => {
                    const list = NotificationUtils._webMessageNotifications.get(key) || [];
                    const remaining = list.filter((item) => item !== notification);
                    if (remaining.length) NotificationUtils._webMessageNotifications.set(key, remaining);
                    else NotificationUtils._webMessageNotifications.delete(key);
                };
            })
            .catch(() => {});
    }

    static _normalizeHash(destinationHash) {
        if (destinationHash == null) {
            return "";
        }
        return String(destinationHash).trim().toLowerCase();
    }

    static _messageTag(destinationHash) {
        const h = NotificationUtils._normalizeHash(destinationHash);
        return h ? `lxmf-${h}` : "new_message";
    }

    static _trackWebNotification(destinationHash, notification) {
        const key = NotificationUtils._normalizeHash(destinationHash) || "__untagged__";
        let list = NotificationUtils._webMessageNotifications.get(key);
        if (!list) {
            list = [];
            NotificationUtils._webMessageNotifications.set(key, list);
        }
        list.push(notification);
    }

    static showIncomingCallNotification(callerName) {
        if (window.electron) {
            window.electron.showNotification(
                "Incoming Call",
                callerName ? `${callerName} is calling you.` : "Someone is calling you."
            );
            return;
        }
        if (NotificationUtils._isAndroid()) {
            window.MeshchatNextAndroid.showIncomingCallNotification(callerName || "Someone");
            return;
        }
        Notification.requestPermission().then((result) => {
            if (result === "granted") {
                new window.Notification("Incoming Call", {
                    body: callerName ? `${callerName} is calling you.` : "Someone is calling you.",
                    tag: "incoming_telephone_call",
                });
            }
        });
    }

    static showMissedCallNotification(from) {
        if (window.electron) {
            window.electron.showNotification("Missed Call", `You missed a call from ${from}.`);
            return;
        }
        if (NotificationUtils._isAndroid()) {
            window.MeshchatNextAndroid.showMissedCallNotification("Missed Call", `You missed a call from ${from}.`);
            return;
        }
        Notification.requestPermission().then((result) => {
            if (result === "granted") {
                new window.Notification("Missed Call", {
                    body: `You missed a call from ${from}.`,
                    tag: "missed_call",
                });
            }
        });
    }

    static showNewVoicemailNotification(from) {
        if (window.electron) {
            window.electron.showNotification("New Voicemail", `You have a new voicemail from ${from}.`);
            return;
        }
        if (NotificationUtils._isAndroid()) {
            window.MeshchatNextAndroid.showNotification("New Voicemail", `You have a new voicemail from ${from}.`);
            return;
        }
        Notification.requestPermission().then((result) => {
            if (result === "granted") {
                new window.Notification("New Voicemail", {
                    body: `You have a new voicemail from ${from}.`,
                    tag: "new_voicemail",
                });
            }
        });
    }

    /**
     * @param {string} from
     * @param {string} content
     * @param {boolean} [silent]
     * @param {string|null} [destinationHash]
     */
    static showNewMessageNotification(from, content, silent = false, destinationHash = null) {
        if (!NotificationUtils.ownsOsMessageNotifications()) {
            return;
        }
        const body = from ? `${from}: ${content || "Sent a message."}` : "Someone sent you a message.";
        const hash = NotificationUtils._normalizeHash(destinationHash);

        if (window.electron) {
            if (typeof window.electron.showNotification === "function") {
                window.electron.showNotification("New Message", body, silent, hash || null);
            }
            return;
        }

        Notification.requestPermission().then((result) => {
            if (result !== "granted") {
                return;
            }
            const notification = new window.Notification("New Message", {
                body,
                tag: NotificationUtils._messageTag(hash),
                silent: Boolean(silent),
            });
            NotificationUtils._trackWebNotification(hash, notification);
            notification.onclose = () => {
                const key = hash || "__untagged__";
                const list = NotificationUtils._webMessageNotifications.get(key);
                if (!list) {
                    return;
                }
                const idx = list.indexOf(notification);
                if (idx >= 0) {
                    list.splice(idx, 1);
                }
                if (list.length === 0) {
                    NotificationUtils._webMessageNotifications.delete(key);
                }
            };
        });
    }

    /**
     * Clear OS message notifications for a peer, or all when hash is empty.
     * @param {string|null|undefined} [destinationHash]
     */
    static clearMessageNotifications(destinationHash) {
        const hash = NotificationUtils._normalizeHash(destinationHash);

        if (window.electron && typeof window.electron.closeMessageNotifications === "function") {
            window.electron.closeMessageNotifications(hash || null);
        }

        if (NotificationUtils._isAndroid()) {
            if (hash && typeof window.MeshchatNextAndroid.cancelMessageNotifications === "function") {
                window.MeshchatNextAndroid.cancelMessageNotifications(hash);
            } else if (!hash && typeof window.MeshchatNextAndroid.cancelAllMessageNotifications === "function") {
                window.MeshchatNextAndroid.cancelAllMessageNotifications();
            }
        }

        if (hash) {
            const list = NotificationUtils._webMessageNotifications.get(hash) || [];
            for (const n of list.slice()) {
                try {
                    n.close();
                } catch {
                    // ignore
                }
            }
            NotificationUtils._webMessageNotifications.delete(hash);
            return;
        }

        for (const [, list] of NotificationUtils._webMessageNotifications) {
            for (const n of list.slice()) {
                try {
                    n.close();
                } catch {
                    // ignore
                }
            }
        }
        NotificationUtils._webMessageNotifications.clear();
    }

    static clearAllMessageNotifications() {
        NotificationUtils.clearMessageNotifications(null);
    }

    /**
     * Sync open peers + DND into the Android Python push bridge via Java.
     * @param {string[]} hashes
     * @param {boolean} [dndEnabled]
     */
    static syncAndroidNotificationContext(hashes, dndEnabled = false) {
        NotificationUtils._rnsNotificationContext = [...(hashes || [])];
        NotificationUtils._notificationDnd = Boolean(dndEnabled);
        if (!NotificationUtils._isAndroid()) {
            return;
        }
        try {
            if (typeof window.MeshchatNextAndroid.setOpenConversationHashes === "function") {
                const joined = [...(hashes || []), NotificationUtils._meshCoreContext]
                    .map((h) => NotificationUtils._normalizeHash(h))
                    .filter(Boolean)
                    .join(",");
                window.MeshchatNextAndroid.setOpenConversationHashes(joined);
            }
            if (typeof window.MeshchatNextAndroid.setDoNotDisturbEnabled === "function") {
                window.MeshchatNextAndroid.setDoNotDisturbEnabled(Boolean(dndEnabled));
            }
        } catch (e) {
            console.error("Failed to sync Android notification context", e);
        }
    }

    static cancelIncomingCallNotification() {
        if (NotificationUtils._isAndroid()) {
            window.MeshchatNextAndroid.cancelIncomingCallNotification();
        }
    }
}

export default NotificationUtils;
