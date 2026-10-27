// SPDX-License-Identifier: 0BSD
export function createSipCallNotifications({ Notification, getWindow, setCallActive = () => {} }) {
    let active = null;
    let currentId = null;
    function close() {
        if (active) active.close();
        active = null;
    }
    return function update(payload) {
        if (!payload || typeof payload !== "object" || typeof payload.enabled !== "boolean") return false;
        if (
            typeof payload.incoming !== "boolean" ||
            (payload.active !== undefined && typeof payload.active !== "boolean")
        )
            return false;
        setCallActive(payload.enabled && (payload.active === true || payload.incoming));
        const window = getWindow();
        window?.webContents?.setBackgroundThrottling(!payload.enabled);
        if (!payload.enabled || !payload.incoming || payload.dnd === true) {
            close();
            currentId = null;
            return true;
        }
        if (
            !/^[0-9a-f]{32}$/.test(payload.callId || "") ||
            typeof payload.peer !== "string" ||
            payload.peer.length > 320 ||
            [...payload.peer].some((character) => character.charCodeAt(0) < 32)
        )
            return false;
        if (currentId === payload.callId) return true;
        close();
        currentId = payload.callId;
        const id = currentId;
        const notification = new Notification({
            title: "SIP · Incoming call",
            body: payload.peer.slice(0, 200),
            silent: false,
            timeoutType: "never",
            actions: [
                { type: "button", text: "Answer" },
                { type: "button", text: "Decline" },
            ],
        });
        active = notification;
        function open(action) {
            const target = getWindow();
            if (!target || currentId !== id) return;
            target.show();
            target.focus();
            target.webContents.send("open-sip-call", { action, callId: id });
        }
        notification.on("click", () => open("open"));
        notification.on("action", (_event, index) => open(index === 0 ? "answer" : "decline"));
        notification.show();
        return true;
    };
}
