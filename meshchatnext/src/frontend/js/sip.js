// SPDX-License-Identifier: 0BSD
import { reactive, watch } from "vue";
import { appFeatures } from "./appFeatures";
import { apiPath } from "./constants";
export const HOIP_DEFAULTS = Object.freeze({
    host: "premium.hamsoverip.com",
    port: 5160,
    network: "wifi_mobile",
    allowed_networks: Object.freeze(["wifi", "mobile"]),
    save_password: true,
});
export const sipState = reactive({
    available: false,
    enabled: false,
    state: "unavailable",
    accounts: [],
    selected: "",
    registered: false,
    call_state: "idle",
    peer: "",
    error: "",
});
let desktopRefresh = null;
async function desktopCommand(op, fields = {}) {
    const api = globalThis.window?.api;
    if (!api?.post) throw new Error("SIP calling is unavailable in this build");
    const { data } = await api.post(apiPath("/sip/command"), { ...fields, op });
    Object.assign(sipState, data);
    return data;
}
watch(
    () => appFeatures.sip,
    (enabled) => {
        if (sipState.platform === "linux")
            desktopCommand("feature", { enabled }).catch(() => {
                sipState.error = "Could not update SIP feature settings";
            });
    }
);
export function refreshSip() {
    const bridge = globalThis.window?.MeshchatNextAndroid;
    if (typeof bridge?.sipStatus !== "function") {
        const api = globalThis.window?.api;
        if (api?.get && !desktopRefresh) {
            desktopRefresh = api
                .get(apiPath("/sip/status"))
                .then(async ({ data }) => {
                    Object.assign(sipState, data);
                    if (data.platform === "linux" && data.feature_enabled !== appFeatures.sip)
                        await desktopCommand("feature", { enabled: appFeatures.sip });
                })
                .catch(() => {
                    if (sipState.platform === "linux") sipState.error = "Could not read desktop SIP status";
                })
                .finally(() => {
                    desktopRefresh = null;
                });
        }
        return sipState;
    }
    try {
        Object.assign(sipState, JSON.parse(bridge.sipStatus()));
    } catch {
        sipState.error = "Could not read SIP status";
    }
    return sipState;
}
export async function sipCommand(op, fields = {}) {
    const bridge = globalThis.window?.MeshchatNextAndroid;
    if (typeof bridge?.sipCommand !== "function") return desktopCommand(op, fields);
    const result = JSON.parse(bridge.sipCommand(JSON.stringify({ ...fields, op })));
    if (!result.ok) throw new Error(result.error || "SIP action failed");
    if (result.request_id) {
        for (let attempt = 0; attempt < 50; attempt++) {
            refreshSip();
            if (sipState.last_request === result.request_id) {
                if (sipState.request_error) throw new Error(sipState.request_error);
                return;
            }
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
        throw new Error("SIP action is still pending; check connection status before retrying");
    }
}
const CONTACTS_KEY = "meshchat-next.sip.contacts.v1";
function readContacts() {
    try {
        const rows = JSON.parse(localStorage.getItem(CONTACTS_KEY) || "[]");
        return Array.isArray(rows)
            ? rows.filter(
                  (c) => typeof c.id === "string" && typeof c.name === "string" && typeof c.address === "string"
              )
            : [];
    } catch {
        return [];
    }
}
export const sipContacts = reactive(readContacts());
export function validSipAddress(address) {
    if (typeof address !== "string" || address.length > 320) return false;
    if (/^[0-9*#+]{1,64}$/.test(address)) return true;
    if (!address.toLowerCase().startsWith("sip:")) return false;
    const parts = address.slice(4).split("@");
    if (parts.length !== 2 || !/^[A-Za-z0-9_.+*%~-]{1,64}$/.test(parts[0])) return false;
    const host = parts[1].split(":");
    if (host.length > 2 || !/^[A-Za-z0-9.-]{1,253}$/.test(host[0]) || host[0].includes("..")) return false;
    return host.length === 1 || (/^[0-9]{1,5}$/.test(host[1]) && Number(host[1]) > 0 && Number(host[1]) <= 65535);
}
export function saveSipContact(contact) {
    const name = String(contact.name || "").trim(),
        address = String(contact.address || "").trim();
    if (!name || name.length > 100 || !validSipAddress(address))
        throw new Error("Enter a name and SIP extension or sip:user@server address");
    const id = contact.id || crypto.randomUUID();
    const row = {
        id,
        name,
        address,
        linked_contact: typeof contact.linked_contact === "string" ? contact.linked_contact : "",
    };
    const index = sipContacts.findIndex((c) => c.id === id);
    const next = sipContacts.map((c) => ({ ...c }));
    if (index < 0) next.push(row);
    else next[index] = row;
    localStorage.setItem(CONTACTS_KEY, JSON.stringify(next));
    sipContacts.splice(0, sipContacts.length, ...next);
    return row;
}
export function deleteSipContact(id) {
    const next = sipContacts.filter((c) => c.id !== id);
    localStorage.setItem(CONTACTS_KEY, JSON.stringify(next));
    sipContacts.splice(0, sipContacts.length, ...next);
}
export function sipContactKey(contact) {
    return contact.meshcore_only
        ? `meshcore:${contact.meshcore_key}`
        : `reticulum:${contact.remote_identity_hash || contact.remote_destination_hash || contact.id}`;
}
export function sipCallRoute(address) {
    return { path: "/call", query: { network: "sip", tab: "phone", sip_target: address } };
}
