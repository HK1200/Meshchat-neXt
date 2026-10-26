// App navigation history is separate from WebView history (which also contains startup/auth pages).
const trails = new WeakMap();
const backTargets = new WeakMap();
const navigating = new WeakSet();

function navigate(router, target, replace = false) {
    if (navigating.has(router)) return true;
    navigating.add(router);
    Promise.resolve(replace ? router.replace(target) : router.push(target))
        .catch(() => backTargets.delete(router))
        .finally(() => navigating.delete(router));
    return true;
}

export function navigateAppUp(router, target) {
    if (navigating.has(router)) return true;
    const trail = trails.get(router);
    const path = router.resolve?.(target)?.fullPath;
    const index = path ? trail?.lastIndexOf(path, trail.length - 2) : -1;
    if (index >= 0) backTargets.set(router, index);
    return navigate(router, target, typeof router.replace === "function");
}

export function navigateAppBack(router) {
    if (navigating.has(router)) return true;
    const route = router.currentRoute.value;
    const q = route.query || {};
    if ((route.name === "map" || route.name === "map-popout") && q.mcMessage && q.mcTarget) {
        return navigateAppUp(
            router,
            q.mcKind === "channel"
                ? { name: "meshcore-channels", params: { channelId: q.mcTarget } }
                : { name: "messages", query: { meshcore: q.mcTarget } }
        );
    }
    const trail = trails.get(router);
    if (trail?.length > 1) {
        backTargets.set(router, trail.length - 2);
        return navigate(router, trail[trail.length - 2], true);
    }
    if (route.name === "meshcore-channels" && route.params?.channelId) {
        return navigateAppUp(router, { name: "meshcore-channels" });
    }
    if (route.name === "meshcore-nodes" && route.params?.peer) {
        return navigateAppUp(router, { name: "meshcore-nodes" });
    }
    const parents = {
        "interfaces.add": "interfaces",
        "bot-setup": "bots",
        "debug-logs": "about",
        "relay-host-moderation": "relay-chat",
        "interfaces.edit": "interfaces",
        "meshcore-settings": "feature-settings",
        "sip-settings": "feature-settings",
        settings: "feature-settings",
        "meshcore-tools": "tools",
        "profile.icon": "identities",
        licenses: "about",
        changelog: "about",
    };
    const toolPages = new Set([
        "ping",
        "rncp",
        "rns-filesync",
        "rnsh",
        "rnx",
        "rnstatus",
        "traffic",
        "rnpath",
        "rnpath-trace",
        "rnprobe",
        "translator",
        "bots",
        "forwarder",
        "micron-editor",
        "reticulum-config-editor",
        "mesh-server",
        "paper-message",
        "nearby",
        "sieve-filters",
        "message-blocklist",
        "rnode-flasher",
        "repository-server",
    ]);
    if (toolPages.has(route.name)) {
        return navigateAppUp(router, { name: "tools" });
    }
    if (parents[route.name]) {
        return navigateAppUp(router, { name: parents[route.name] });
    }
    if (route.name === "auth") return false;
    if (route.name !== "messages" || Object.keys(q).length) {
        return navigateAppUp(router, { name: "messages" });
    }
    return false;
}

// Close transient UI first, then use the same action as the visible app Back control.
export function handleAppBack(router, doc = document) {
    const visible = (element) => !element.disabled && element.getClientRects().length > 0;
    const layers = [
        ...doc.querySelectorAll(
            '[data-app-back-scope], [role="dialog"], [role="alertdialog"], [aria-modal="true"], .context-menu-panel, [data-app-back-overlay]'
        ),
    ].filter(visible);
    const zIndex = (element) => {
        let z = 0;
        for (let node = element; node; node = node.parentElement) {
            z = Math.max(z, Number.parseInt(doc.defaultView?.getComputedStyle(node).zIndex, 10) || 0);
        }
        return z;
    };
    // Highest visible layer wins; nested layers win over their parent at equal height.
    const layer = layers.sort((a, b) => zIndex(a) - zIndex(b)).at(-1);
    if (layer) {
        if (layer.hasAttribute("data-app-back-scope")) {
            layer.dispatchEvent(new (doc.defaultView?.CustomEvent || CustomEvent)("app-back", { bubbles: false }));
        } else if (layer.matches(".context-menu-panel")) {
            doc.defaultView?.dispatchEvent(
                new (doc.defaultView?.KeyboardEvent || KeyboardEvent)("keydown", { key: "Escape", bubbles: true })
            );
        } else if (layer.hasAttribute("data-app-back-overlay")) {
            layer.click();
        } else {
            const close = [...layer.querySelectorAll("[data-app-back], [data-confirm-cancel]")].find(visible);
            if (close) close.click();
        }
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
        const previousPosition = position;
        const replaced = Number.isInteger(position) && nextPosition === position;
        position = nextPosition;
        const target = backTargets.get(router);
        backTargets.delete(router);
        if (target != null && trail[target] === to.fullPath) {
            trail.splice(target + 1);
        } else if (
            Number.isInteger(nextPosition) &&
            Number.isInteger(previousPosition) &&
            nextPosition < previousPosition
        ) {
            const existing = trail.lastIndexOf(to.fullPath);
            if (existing >= 0) trail.splice(existing + 1);
            else trail.push(to.fullPath);
        } else if (replaced) {
            if (trail.length) trail.pop();
            trail.push(to.fullPath);
        } else if (trail.at(-1) !== to.fullPath) {
            trail.push(to.fullPath);
        }
        if (trail.length > 50) trail.shift();
    });
    // RouterLink Up controls also consume visits, rather than pushing a new return
    // page which would make the next Android Back reopen the screen just closed.
    const onBackLink = (event) => {
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.ctrlKey ||
            event.metaKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        const link = event.target?.closest?.("a[data-app-back]");
        if (!link || !link.hash?.startsWith("#/")) return;
        if (target.location && link.origin !== target.location.origin) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        navigateAppUp(router, link.hash.slice(1));
    };
    target.addEventListener?.("click", onBackLink, true);
    const handler = () => handleAppBack(router);
    target.meshchatHandleBack = handler;
    return () => {
        removeHook?.();
        target.removeEventListener?.("click", onBackLink, true);
        if (trails.get(router) === trail) trails.delete(router);
        backTargets.delete(router);
        navigating.delete(router);
        if (target.meshchatHandleBack === handler) delete target.meshchatHandleBack;
    };
}
