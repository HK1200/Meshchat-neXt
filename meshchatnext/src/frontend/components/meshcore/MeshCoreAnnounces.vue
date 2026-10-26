<template>
    <section class="flex flex-col flex-1 min-h-0" aria-label="MeshCore announces">
        <div class="p-1 border-b border-sem-border space-y-1.5">
            <SearchInput v-model="search" placeholder="Search MeshCore announces…" compact />
            <div class="flex flex-wrap gap-1" role="group" aria-label="MeshCore device types">
                <button
                    v-for="option in filters"
                    :key="option.value"
                    type="button"
                    class="px-2 py-1 text-xs rounded-full border transition-colors"
                    :class="
                        kind === option.value
                            ? 'border-sem-accent text-sem-accent bg-sem-surface-muted'
                            : 'border-sem-border text-sem-fg-muted hover:bg-sem-surface-muted'
                    "
                    :aria-pressed="kind === option.value"
                    @click="kind = option.value"
                >
                    {{ option.label }}
                </button>
            </div>
        </div>
        <p class="px-2 py-1 text-xs text-sem-fg-muted">
            {{ snapshot.connected ? "Listening for MeshCore announces" : "MeshCore disconnected · saved discoveries" }}
        </p>
        <p v-if="error" class="px-2 py-1 text-xs text-sem-danger" role="alert">{{ error }}</p>
        <SidebarVirtualList
            class="flex-1 min-h-0"
            aria-label="MeshCore discovered devices"
            :items="visible"
            :item-key="(device) => device.peer"
            :virtualize="visible.length >= MIN_VIRTUAL_SIDEBAR_ITEMS"
            :estimate-size="() => 156"
        >
            <template #item="{ item: device }">
                <article class="p-2 border-b border-sem-border/60" :data-peer="device.peer">
                    <div class="flex items-start gap-2">
                        <LxmfUserIcon
                            :icon-name="
                                device.kind === 2
                                    ? 'radio-tower'
                                    : device.kind === 3
                                      ? 'forum-outline'
                                      : device.kind === 4
                                        ? 'access-point'
                                        : 'account'
                            "
                            icon-class="size-8 shrink-0"
                        />
                        <div class="min-w-0 flex-1">
                            <div class="flex items-center gap-1.5">
                                <span class="font-semibold text-sm text-sem-fg truncate">{{
                                    device.name || "Unknown device"
                                }}</span
                                ><span
                                    class="text-[10px] text-sem-fg-muted border border-sem-border rounded-full px-1.5 shrink-0"
                                    >MeshCore</span
                                >
                            </div>
                            <p class="text-xs text-sem-fg-muted">{{ types[device.kind] || "Unknown type" }}</p>
                            <p class="font-mono text-xs text-sem-fg-muted truncate" :title="device.peer">
                                {{ device.peer }}
                            </p>
                            <p class="text-xs text-sem-fg-muted" :title="date(device.heard || device.advertised)">
                                {{ device.heard ? "Last heard" : "Advertised" }}
                                {{ timeAgo(device.heard || device.advertised) }}
                            </p>
                            <p v-if="device.path_len != null" class="text-xs text-sem-fg-muted">
                                {{
                                    device.path_len === -1
                                        ? "Flood route"
                                        : `Route: ${device.path_len} ${device.path_len === 1 ? "hop" : "hops"}`
                                }}<span v-if="device.path_bytes"> · {{ device.path_bytes }}-byte hashes</span>
                            </p>
                            <div v-if="device.kind === 1" class="flex flex-wrap gap-2 mt-1">
                                <button
                                    v-if="!device.saved"
                                    type="button"
                                    class="text-xs text-sem-accent hover:underline"
                                    :disabled="!snapshot.connected || busy === device.peer"
                                    @click="add(device)"
                                >
                                    {{ busy === device.peer ? "Adding…" : "Add Contact" }}
                                </button>
                                <button
                                    v-else
                                    type="button"
                                    class="text-xs text-sem-accent hover:underline"
                                    @click="$router.push(meshcoreRoute(device.peer))"
                                >
                                    Message via MeshCore
                                </button>
                            </div>
                            <div v-if="device.kind === 2 || device.kind === 3 || device.kind === 4" class="mt-1">
                                <button
                                    v-if="!(snapshot.nodes || []).some((node) => node.peer === device.peer)"
                                    type="button"
                                    class="text-xs text-sem-accent hover:underline"
                                    :disabled="busy === device.peer"
                                    @click="saveNode(device)"
                                >
                                    {{ busy === device.peer ? "Saving…" : "Save Node" }}
                                </button>
                                <button
                                    v-else
                                    type="button"
                                    class="text-xs text-sem-accent hover:underline"
                                    @click="$router.push(meshcoreNodeRoute(device.peer))"
                                >
                                    View saved node
                                </button>
                            </div>
                        </div>
                    </div>
                </article>
            </template>
        </SidebarVirtualList>
        <div v-if="!visible.length" class="p-4 text-center text-sm text-sem-fg-muted">
            {{
                search || kind
                    ? "No matching MeshCore devices."
                    : "No MeshCore announces yet. Nearby devices appear here when the radio reports them."
            }}
        </div>
    </section>
</template>
<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from "vue";
import SearchInput from "../SearchInput.vue";
import LxmfUserIcon from "../LxmfUserIcon.vue";
import SidebarVirtualList from "../SidebarVirtualList.vue";
import { MIN_VIRTUAL_SIDEBAR_ITEMS } from "../../js/sidebarListVirtual";
import { formatMeshcoreAge } from "../../js/meshcoreTime";
import { meshcoreRoute, meshcoreNodeRoute } from "../../js/meshcoreUi";
const props = defineProps({ snapshot: { type: Object, required: true }, action: { type: Function, required: true } });
const search = ref(""),
    kind = ref(0),
    busy = ref(null),
    error = ref(""),
    tick = ref(0);
const types = { 1: "Client", 2: "Repeater", 3: "Room server", 4: "Sensor" };
const filters = [
    { value: 0, label: "All" },
    { value: 1, label: "Clients" },
    { value: 2, label: "Repeaters" },
    { value: 3, label: "Room servers" },
    { value: 4, label: "Sensors" },
];
const visible = computed(() =>
    (props.snapshot.announces || []).filter(
        (device) =>
            (!kind.value || device.kind === kind.value) &&
            `${device.name} ${device.peer}`.toLowerCase().includes(search.value.toLowerCase())
    )
);
function date(value) {
    return value ? new Date(value * 1000).toLocaleString() : "Unknown time";
}
function timeAgo(value) {
    void tick.value;
    return formatMeshcoreAge(value);
}
let timer;
onMounted(() => {
    timer = setInterval(() => tick.value++, 30000);
});
onBeforeUnmount(() => clearInterval(timer));
async function add(device) {
    busy.value = device.peer;
    error.value = "";
    try {
        let name = "";
        for (const character of device.name || "MeshCore contact") {
            if (new TextEncoder().encode(name + character).length > 31) break;
            name += character;
        }
        await props.action("contact-add", { peer: device.peer, name });
    } catch {
        error.value = "Could not add the MeshCore contact. Check the radio connection and try again.";
    } finally {
        busy.value = null;
    }
}
async function saveNode(device) {
    busy.value = device.peer;
    error.value = "";
    try {
        await props.action("node-save", { peer: device.peer });
    } catch {
        error.value = "Could not save this MeshCore node.";
    } finally {
        busy.value = null;
    }
}
</script>
