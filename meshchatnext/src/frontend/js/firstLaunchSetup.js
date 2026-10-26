// SPDX-License-Identifier: 0BSD
import { apiPath } from "./constants";
export const RMAP_TCP = Object.freeze({ host: "rmap.world", port: 4242 });
export const RADIO2_FIRMWARE_URL = "https://github.com/mikecarper/MeshCore/releases";
export const RADIO2_GUIDE_URL =
    "https://github.com/jade-on-mesh/meshcore-open-tak/blob/main/documentation/media-mesh.md";
export const SETUP_DRAFT_KEY = "meshchat-next.setup-draft.v1";
export function setupSteps(features) {
    return [
        "networks",
        ...(features.reticulum ? ["identity", "reticulum"] : []),
        ...(features.meshcore ? ["meshcore", "radio2"] : []),
        ...(features.sip ? ["sip"] : []),
        "ready",
    ];
}
export function validateTcp(host, port) {
    if (
        !/^[a-zA-Z0-9.-]{1,253}$/.test(host) ||
        host.includes("..") ||
        !Number.isInteger(Number(port)) ||
        Number(port) < 1 ||
        Number(port) > 65535
    )
        throw new Error("Enter a valid TCP hostname and port.");
}
function enabled(row) {
    const value = row.interface_enabled ?? row.enabled ?? true;
    return ["true", "yes", "on", "1"].includes(String(value).trim().toLowerCase());
}
function uniqueName(rows, base) {
    let name = base,
        n = 2;
    while (rows[name]) name = `${base} ${n++}`;
    return name;
}
export async function configureReticulumSetup(api, options) {
    if (options.internet) validateTcp(options.host.trim(), options.port);
    const rows = { ...(await api.get(apiPath("/reticulum/interfaces"))).data.interfaces };
    const added = [];
    if (options.local && !Object.values(rows).some((row) => row.type === "AutoInterface" && enabled(row))) {
        const name = uniqueName(rows, "Local network");
        await api.post(apiPath("/reticulum/interfaces/add"), { name, type: "AutoInterface", enabled: true });
        rows[name] = { type: "AutoInterface" };
        added.push(name);
    }
    if (options.internet) {
        const host = options.host.trim().toLowerCase(),
            port = Number(options.port);
        const match = Object.entries(rows).find(
            ([, row]) =>
                ["TCPClientInterface", "BackboneInterface"].includes(row.type) &&
                String(row.target_host || row.remote || "").toLowerCase() === host &&
                Number(row.target_port) === port
        );
        if (match && !enabled(match[1])) {
            await api.post(apiPath("/reticulum/interfaces/enable"), { name: match[0] });
        } else if (!match) {
            const name = uniqueName(rows, host === RMAP_TCP.host ? "RMAP World" : "Internet TCP");
            await api.post(apiPath("/reticulum/interfaces/add"), {
                name,
                type: "TCPClientInterface",
                target_host: host,
                target_port: port,
                enabled: true,
                bootstrap_only: false,
                mode: "full",
            });
            added.push(name);
        }
    }
    // This endpoint changes only bootstrap_only, preserving IFAC secrets and all radio settings.
    const reception = (await api.post(apiPath("/reticulum/interfaces/receive-announces"))).data;
    await api.patch(apiPath("/reticulum/discovery"), { discover_interfaces: true, default_bootstrap_only: false });
    await api.patch(apiPath("/config"), {
        announce_store_lxmf_delivery: true,
        announce_store_lxst_telephony: true,
        announce_store_nomadnetwork_node: true,
        announce_store_lxmf_propagation: true,
        announce_store_map_data: true,
    });
    if (added.length || reception.reload_required) await api.post(apiPath("/reticulum/reload"));
    return { added, reception: reception.changed || [] };
}
export async function applySetupRadio2(api, choice, owner, profileChoice = "keep") {
    if (choice === "keep") return { unchanged: true };
    if (!owner) throw new Error("Connect your MeshCore client first, or choose to decide later.");
    const current = (await api.get(apiPath("/meshcore/radio2"))).data.result;
    if (!current?.supported) {
        if (choice === "standard") return { supported: false, enabled: false };
        throw new Error(
            "This client firmware does not support Radio2. Keep standard messaging for now, or install compatible firmware first."
        );
    }
    if (choice === "standard" && !current.enabled) return current;
    const enabled = choice === "media";
    const profile = enabled ? (profileChoice === "us915" ? current.defaults : current.profile) : {};
    if (enabled && !profile) throw new Error("Choose the MediaMesh profile used by your local group.");
    const result = (await api.post(apiPath("/meshcore/radio2"), { enabled, ...profile, expected_owner: owner })).data
        .result;
    if (
        !result ||
        result.enabled !== enabled ||
        (enabled && (!result.supported || result.crossing || result.media_policy !== "radio2"))
    )
        throw new Error("Radio2 settings were not verified. Reconnect and check Settings → MeshCore.");
    return result;
}
