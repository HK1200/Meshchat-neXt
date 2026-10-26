// App navigation history is separate from WebView history (which also contains startup/auth pages).
const trails = new WeakMap();

export function navigateAppBack(router) {
    const route = router.currentRoute.value;
    const q = route.query || {};
    if ((route.name === "map" || route.name === "map-popout") && q.mcMessage && q.mcTarget) {
        void router.push(
            q.mcKind === "channel"
                ? { name: "meshcore-channels", params: { channelId: q.mcTarget } }
                : { name: "messages", query: { meshcore: q.mcTarget } }
        );
        return true;
    }
    const trail = trails.get(router);
    if (trail?.length > 1) {
        void router.replace(trail[trail.length - 2]);
        return true;
    }
    if (route.name === "meshcore-channels" && route.params?.channelId) {
        void router.push({ name: "meshcore-channels" });
        return true;
    }
    if (route.name === "meshcore-nodes" && route.params?.peer) {
        void router.push({ name: "meshcore-nodes" });
        return true;
    }
    const parents = {
        "interfaces.add": "interfaces",
        "interfaces.edit": "interfaces",
        "meshcore-settings": "feature-settings",
        "sip-settings": "feature-settings",
        settings: "feature-settings",
        "meshcore-tools": "tools",
        "profile.icon": "identities",
        licenses: "about",
        changelog: "about",
    };
    if (parents[route.name]) {
        void router.push({ name: parents[route.name] });
        return true;
    }
    if (route.name === "auth") return false;
    if (route.name !== "messages" || Object.keys(q).length) {
        void router.push({ name: "messages" });
        return true;
    }
    return false;
}

// Close transient UI first, then use the same action as the visible app Back control.
export function handleAppBack(router, doc = document) {
    const visible = (element) => !element.disabled && element.getClientRects().length > 0;
    const dialog = [...doc.querySelectorAll('[role="dialog"], [aria-modal="true"]')].filter(visible).at(-1);
    const menu = [...doc.querySelectorAll(".context-menu-panel")].filter(visible).at(-1);
    if (menu) {
        doc.defaultView?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        return true;
    }
    if (dialog) {
        const close = [...dialog.querySelectorAll("[data-app-back], [data-confirm-cancel]")].find(visible);
        if (close) close.click();
        return true;
    }
    const overlay = [...doc.querySelectorAll("[data-app-back-overlay]")].filter(visible).at(-1);
    if (overlay) {
        overlay.click();
        return true;
    }
    const back = [...doc.querySelectorAll("[data-app-back]")].filter(visible).at(-1);
    if (back) {
        back.click();
        return true;
    }
    return navigateAppBack(router);
}

export function installAndroidBackNavigation(router, target = window) {
    const initial = router.currentRoute?.value || {};
    const trail = initial.name === "auth" || !initial.fullPath ? [] : [initial.fullPath];
    trails.set(router, trail);
    let position = router.options?.history?.state?.position;
    const removeHook = router.afterEach?.((to, _from, failure) => {
        if (failure || !to.fullPath) return;
        if (to.name === "auth") {
            trail.length = 0;
            return;
        }
        const nextPosition = router.options?.history?.state?.position;
        const replaced = Number.isInteger(position) && nextPosition === position;
        position = nextPosition;
        const existing = trail.lastIndexOf(to.fullPath);
        if (existing >= 0) trail.splice(existing + 1);
        else {
            if (replaced) trail.pop();
            trail.push(to.fullPath);
            if (trail.length > 50) trail.shift();
        }
    });
    const handler = () => handleAppBack(router);
    target.meshchatHandleBack = handler;
    return () => {
        removeHook?.();
        if (trails.get(router) === trail) trails.delete(router);
        if (target.meshchatHandleBack === handler) delete target.meshchatHandleBack;
    };
}
