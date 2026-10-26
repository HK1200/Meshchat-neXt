// SPDX-License-Identifier: 0BSD
import { reactive } from "vue";
export const FEATURES_KEY = "meshchat-next.app-features.v1";
export const FEATURE_NAMES = ["reticulum", "meshcore", "sip"];
export function normalizeFeatures(value) {
    return Object.fromEntries(FEATURE_NAMES.map((name) => [name, value?.[name] !== false]));
}
function read() {
    try {
        return normalizeFeatures(JSON.parse(localStorage.getItem(FEATURES_KEY)));
    } catch {
        return normalizeFeatures(null);
    }
}
export const appFeatures = reactive(read());
export function setAppFeatures(value) {
    const next = normalizeFeatures(value);
    localStorage.setItem(FEATURES_KEY, JSON.stringify(next));
    Object.assign(appFeatures, next);
}
export function setAppFeature(name, enabled) {
    if (!FEATURE_NAMES.includes(name)) throw new Error("Unknown app feature");
    setAppFeatures({ ...appFeatures, [name]: Boolean(enabled) });
}
if (typeof window !== "undefined")
    window.addEventListener("storage", (event) => {
        if (event.key === FEATURES_KEY || event.key === null) Object.assign(appFeatures, read());
    });
export function featureRouteAllowed(route) {
    const name = String(route.name || ""),
        path = route.path || "";
    if (name === "feature-settings" || path === "/settings/features") return true;
    if (name === "sip-settings" || path === "/settings/sip") return appFeatures.sip;
    if (name.startsWith("meshcore-") || path.startsWith("/meshcore/") || path.startsWith("/tools/meshcore"))
        return appFeatures.meshcore;
    if (name === "messages" || name === "messages-popout" || path.startsWith("/messages"))
        return route.query?.meshcore ? appFeatures.meshcore : appFeatures.reticulum || appFeatures.meshcore;
    if (name === "call" || path === "/call")
        return route.query?.network && FEATURE_NAMES.includes(route.query.network)
            ? appFeatures[route.query.network]
            : appFeatures.reticulum || appFeatures.meshcore || appFeatures.sip;
    if (
        [
            "settings",
            "identities",
            "interfaces",
            "relay-chat",
            "nomadnetwork",
            "network-visualiser",
            "archives",
            "propagation-nodes",
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
            "bots",
            "bot-setup",
            "forwarder",
            "micron-editor",
            "reticulum-config-editor",
            "mesh-server",
            "paper-message",
        ].includes(name) ||
        name.startsWith("interfaces.") ||
        ["relay-chat-popout", "nomadnetwork-popout"].includes(name)
    )
        return appFeatures.reticulum;
    return true;
}
export function featureNavAllowed(item) {
    const id = item.id;
    if (
        [
            "sync-messages",
            "relay-chat",
            "nomadnetwork",
            "network-visualiser",
            "interfaces",
            "archives",
            "identities",
        ].includes(id)
    )
        return appFeatures.reticulum;
    if (["call", "contacts"].includes(id)) return appFeatures.reticulum || appFeatures.meshcore || appFeatures.sip;
    if (id === "blocked") return appFeatures.reticulum || appFeatures.meshcore;
    if (id === "messages") return appFeatures.reticulum || appFeatures.meshcore;
    return true;
}
