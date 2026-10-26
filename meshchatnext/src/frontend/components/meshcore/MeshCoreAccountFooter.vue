<template>
    <section
        v-if="snapshot.available"
        class="bg-sem-surface border-t border-sem-border text-sem-fg"
        aria-label="MeshCore identity controls"
    >
        <div class="flex items-center gap-2" :class="collapsed ? 'justify-center p-2' : 'px-3 py-2'">
            <button
                type="button"
                class="shrink-0 p-1 rounded-lg hover:bg-sem-surface-muted text-sem-accent"
                aria-label="MeshCore identity"
                :title="snapshot.profile_name || 'MeshCore identity'"
                @click="collapsed ? $router.push({ name: 'meshcore-settings' }) : (expanded = !expanded)"
            >
                <MaterialDesignIcon icon-name="radio-handheld" class="size-7" />
            </button>
            <button
                v-if="!collapsed"
                type="button"
                class="flex-1 min-w-0 text-left"
                :aria-expanded="expanded"
                aria-label="Expand MeshCore identity controls"
                @click="expanded = !expanded"
            >
                <span class="block text-[10px] text-sem-fg-muted">MeshCore · {{ connectionStatus }}</span
                ><span class="block text-sm font-semibold truncate">{{
                    snapshot.profile_name || "Radio identity"
                }}</span>
            </button>
            <template v-if="!collapsed">
                <button
                    type="button"
                    class="p-2 rounded-lg hover:bg-sem-surface-muted text-sem-fg-muted disabled:opacity-40"
                    :disabled="!snapshot.connected || busy"
                    title="Send MeshCore announce"
                    aria-label="Send MeshCore announce"
                    @click="showAnnounce = true"
                >
                    <MaterialDesignIcon icon-name="radio" class="size-5" />
                </button>
                <button
                    type="button"
                    class="p-2 rounded-lg hover:bg-sem-surface-muted text-sem-fg-muted disabled:opacity-40"
                    :disabled="!snapshot.owner"
                    title="Share MeshCore identity"
                    aria-label="Share MeshCore identity"
                    @click="showShare = true"
                >
                    <MaterialDesignIcon icon-name="qrcode" class="size-5" />
                </button>
                <button
                    type="button"
                    class="p-1 text-sem-fg-muted"
                    aria-label="More MeshCore controls"
                    :aria-expanded="expanded"
                    @click="expanded = !expanded"
                >
                    <MaterialDesignIcon :icon-name="expanded ? 'chevron-up' : 'chevron-down'" class="size-4" />
                </button>
            </template>
        </div>
        <div v-if="expanded && !collapsed" class="border-t border-sem-border p-2 space-y-2 text-xs">
            <div class="px-2 py-1.5 space-y-2" aria-label="MeshCore radio connection">
                <p role="status" class="flex items-center gap-2">
                    <span
                        class="size-2 rounded-full"
                        :class="snapshot.connected ? 'bg-sem-success' : 'bg-sem-fg-muted'"
                        aria-hidden="true"
                    ></span>
                    <span>MeshCore · {{ connectionStatus }}</span>
                </p>
                <p v-if="radio" class="text-sem-fg-muted break-all">
                    {{ radio.kind === "ble" ? "Bluetooth" : "USB" }} · {{ radio.target }}
                </p>
                <p v-else class="text-sem-fg-muted">Choose a radio in MeshCore settings to connect.</p>
                <button type="button" class="secondary-chip w-full" :disabled="busy" @click="toggleConnection">
                    {{
                        busyConnection
                            ? `${busyConnection}…`
                            : snapshot.connected || snapshot.selected
                              ? "Disconnect MeshCore"
                              : "Connect MeshCore"
                    }}
                </button>
            </div>
            <p v-if="snapshot.owner" class="font-mono break-all text-sem-fg-muted">{{ snapshot.owner }}</p>
            <RouterLink :to="{ name: 'contacts' }" class="block px-2 py-1.5 rounded-lg hover:bg-sem-surface-muted"
                >Contacts</RouterLink
            >
            <RouterLink
                :to="{ name: 'meshcore-settings' }"
                class="block px-2 py-1.5 rounded-lg hover:bg-sem-surface-muted"
                >MeshCore settings &amp; identity</RouterLink
            >
            <RouterLink :to="{ name: 'meshcore-nodes' }" class="block px-2 py-1.5 rounded-lg hover:bg-sem-surface-muted"
                >MeshCore nodes</RouterLink
            >
            <RouterLink
                :to="{ name: 'meshcore-tools', params: { tool: 'regions' } }"
                class="block px-2 py-1.5 rounded-lg hover:bg-sem-surface-muted"
                >MeshCore tools &amp; channel regions</RouterLink
            >
        </div>
        <p v-if="notice && !collapsed" role="status" class="px-3 pb-2 text-xs text-sem-fg-muted">{{ notice }}</p>
        <p v-if="problem && !collapsed" role="alert" class="px-3 pb-2 text-xs text-sem-danger">{{ problem }}</p>
        <AppModal v-model="showAnnounce" title="Send MeshCore announce" size="sm">
            <p class="text-sm text-sem-fg-muted mb-4">
                Announce this MeshCore radio identity. Choose how far to send it.
            </p>
            <div class="space-y-3">
                <button
                    type="button"
                    class="secondary-chip w-full"
                    :disabled="busy || !snapshot.connected"
                    @click="announce(false)"
                >
                    Local announce
                </button>
                <p class="text-xs text-sem-fg-muted">Direct radio range only; repeaters do not forward it.</p>
                <button
                    type="button"
                    class="primary-chip w-full"
                    :disabled="busy || !snapshot.connected"
                    @click="announce(true)"
                >
                    Flood announce
                </button>
                <p class="text-xs text-sem-fg-muted">
                    Propagate through repeaters using the radio's announce settings.
                </p>
            </div>
        </AppModal>
        <AppModal v-model="showShare" title="Share MeshCore identity"
            ><MeshCoreIdentityShare :snapshot="snapshot"
        /></AppModal>
    </section>
</template>
<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useMeshCoreUi } from "../../js/meshcoreUi";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import AppModal from "../AppModal.vue";
import MeshCoreIdentityShare from "./MeshCoreIdentityShare.vue";
defineProps({ collapsed: Boolean });
const { snapshot, action } = useMeshCoreUi();
const router = useRouter();
const radioKey = "meshchat-next.meshcore.last-radio";
function validRadio(value) {
    return (
        value &&
        ["ble", "usb"].includes(value.kind) &&
        typeof value.target === "string" &&
        value.target.trim() &&
        value.target.length <= 256
    );
}
function savedRadio() {
    try {
        const value = JSON.parse(localStorage.getItem(radioKey));
        return validRadio(value) ? { kind: value.kind, target: value.target } : null;
    } catch {
        return null;
    }
}
const radio = ref(savedRadio());
const busyConnection = ref("");
const connectionStatus = computed(() => {
    if (busyConnection.value) return busyConnection.value;
    if (snapshot.value.connected) return "Connected";
    if (snapshot.value.state === "connecting") return "Connecting";
    if (snapshot.value.selected && snapshot.value.auto_reconnect) return "Reconnecting";
    return "Disconnected";
});
watch(
    () => snapshot.value.connection,
    (value) => {
        if (!validRadio(value)) return;
        radio.value = { kind: value.kind, target: value.target };
        try {
            localStorage.setItem(radioKey, JSON.stringify(radio.value));
        } catch {
            /* Connecting still works without local storage. */
        }
    },
    { immediate: true }
);
const expanded = ref(false),
    showAnnounce = ref(false),
    showShare = ref(false),
    busy = ref(false),
    notice = ref(""),
    problem = ref("");
watch(
    () => snapshot.value.owner,
    () => {
        showAnnounce.value = false;
        showShare.value = false;
        notice.value = "";
        problem.value = "";
    }
);
async function toggleConnection() {
    if (busy.value) return;
    const disconnecting = snapshot.value.connected || snapshot.value.selected;
    if (!disconnecting && !radio.value) {
        await router.push({ name: "meshcore-settings" });
        return;
    }
    busy.value = true;
    busyConnection.value = disconnecting ? "Disconnecting" : "Connecting";
    notice.value = "";
    problem.value = "";
    try {
        if (disconnecting) {
            await action("disconnect", {});
            notice.value = "MeshCore disconnected.";
        } else {
            const selected = { ...radio.value };
            if (selected.kind === "usb") {
                const permission = await action("usb-permission", { path: selected.target });
                if (!permission?.granted) {
                    notice.value = "Allow USB access in the Android prompt, then tap Connect MeshCore again.";
                    return;
                }
            }
            await action("connect", { ...selected, receive: true, auto_reconnect: true });
        }
    } catch (error) {
        problem.value =
            error.response?.data?.message ||
            "Could not change the MeshCore connection. Check the radio in MeshCore settings.";
    } finally {
        busy.value = false;
        busyConnection.value = "";
    }
}
async function announce(flood) {
    if (busy.value || !snapshot.value.connected) return;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    const owner = snapshot.value.owner;
    try {
        const result = await action("announce", { flood });
        if (owner === snapshot.value.owner) {
            notice.value = `MeshCore ${result.kind} announce submitted to the radio.`;
            showAnnounce.value = false;
        }
    } catch (e) {
        problem.value =
            e.response?.data?.message ||
            "MeshCore did not confirm the announce. Check the connection before trying again.";
        showAnnounce.value = false;
    } finally {
        busy.value = false;
    }
}
</script>
