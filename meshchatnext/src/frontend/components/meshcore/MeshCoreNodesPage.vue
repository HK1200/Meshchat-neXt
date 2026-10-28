<template>
    <section
        class="flex-1 min-w-0 h-full overflow-y-auto bg-sem-canvas text-sem-fg p-4 md:p-6"
        aria-label="MeshCore nodes"
    >
        <div class="max-w-4xl mx-auto space-y-5">
            <header class="border-b border-sem-border pb-4">
                <h1 class="text-2xl font-bold">MeshCore Nodes</h1>
                <p class="text-sm text-sem-fg-muted">Saved repeaters, room servers and sensors</p>
            </header>
            <p v-if="error" role="alert" class="text-sm text-sem-danger">{{ error }}</p>
            <template v-if="selected">
                <button
                    data-app-back
                    type="button"
                    class="secondary-chip"
                    @click="navigateAppUp(router, { name: 'meshcore-nodes' })"
                >
                    All saved nodes
                </button>
                <div class="flex items-center gap-3">
                    <MaterialDesignIcon :icon-name="nodeIcon(selected.kind)" class="size-10 text-sem-fg-muted" />
                    <div>
                        <h2 class="text-xl font-semibold">{{ selected.name || "MeshCore node" }}</h2>
                        <p class="text-sm text-sem-fg-muted">MeshCore · {{ nodeType(selected.kind) }}</p>
                    </div>
                </div>
                <dl class="space-y-3 text-sm">
                    <div>
                        <dt class="text-sem-fg-muted">Public key</dt>
                        <dd class="font-mono break-all">{{ selected.peer }}</dd>
                    </div>
                    <div>
                        <dt class="text-sem-fg-muted">{{ selected.heard ? "Last heard" : "Advertised" }}</dt>
                        <dd>
                            {{
                                selected.heard || selected.advertised
                                    ? new Date((selected.heard || selected.advertised) * 1000).toLocaleString()
                                    : "Unknown"
                            }}
                        </dd>
                    </div>
                    <div v-if="selected.path_len != null">
                        <dt class="text-sem-fg-muted">Route</dt>
                        <dd>
                            {{
                                selected.path_len === -1
                                    ? "Flood route"
                                    : selected.path_len === 0
                                      ? "Direct connection · no repeaters"
                                      : `${selected.path_len} repeater hops`
                            }}<span v-if="selected.path_bytes"> · {{ selected.path_bytes }}-byte hashes</span>
                        </dd>
                    </div>
                </dl>
                <p v-if="selected.kind === 4" class="text-sm text-sem-fg-muted">
                    Sensor saved. Sensor telemetry controls are not available yet.
                </p>
                <MeshCoreNodePasswords
                    v-if="selected.kind === 4"
                    :owner="snapshot.owner"
                    :peer="selected.peer"
                    :disabled="!snapshot.connected"
                />
                <MeshCoreNodeSession
                    v-if="selected.kind === 2 || selected.kind === 3"
                    :node="selected"
                    :snapshot="snapshot"
                    :visit="visit"
                    @changed="refresh"
                    @busy="busy = $event"
                />
                <button type="button" class="secondary-chip" :disabled="busy" @click="remove">
                    Remove from saved nodes
                </button>
            </template>
            <template v-else>
                <div class="space-y-3" aria-label="Discover MeshCore nodes">
                    <button
                        type="button"
                        class="primary-chip"
                        :disabled="busy || discovering || !snapshot.connected"
                        @click="discover"
                    >
                        {{ discovering ? "Discovering nearby nodes…" : "Discover new nodes" }}
                    </button>
                    <button
                        type="button"
                        :data-app-back="showDiscoveries ? '' : null"
                        class="secondary-chip ml-2"
                        @click="showDiscoveries = !showDiscoveries"
                    >
                        {{ showDiscoveries ? "Hide discoveries" : "View heard nodes" }}
                    </button>
                    <p class="text-xs text-sem-fg-muted">
                        Search nearby repeaters, room servers and sensors. One request listens for 12 seconds; nodes
                        beyond direct radio range may only appear through announces.
                    </p>
                    <p v-if="discoveryStatus" role="status" class="text-sm text-sem-fg-muted">{{ discoveryStatus }}</p>
                    <div
                        v-if="showDiscoveries"
                        data-app-back-scope
                        class="space-y-3 border border-sem-border rounded-lg p-3"
                        @app-back.stop="showDiscoveries = false"
                    >
                        <SearchInput v-model="discoverySearch" placeholder="Search MeshCore nodes…" />
                        <div role="group" aria-label="Discovered node types" class="flex flex-wrap gap-2">
                            <button
                                v-for="option in [
                                    { kind: 0, label: 'All' },
                                    { kind: 2, label: 'Repeaters' },
                                    { kind: 3, label: 'Room servers' },
                                    { kind: 4, label: 'Sensors' },
                                ]"
                                :key="option.kind"
                                type="button"
                                class="secondary-chip"
                                :aria-pressed="discoveryKind === option.kind"
                                @click="discoveryKind = option.kind"
                            >
                                {{ option.label }}
                            </button>
                        </div>
                        <section
                            v-for="group in discoveryGroups"
                            :key="group.label"
                            :aria-label="group.label"
                            class="space-y-2"
                        >
                            <h3 class="font-semibold text-sm">{{ group.label }} ({{ group.nodes.length }})</h3>
                            <article
                                v-for="node in group.nodes"
                                :key="node.peer"
                                class="py-2 border-b border-sem-border"
                                :data-discovered-peer="node.peer"
                            >
                                <strong>{{ node.name || nodeType(node.kind) }}</strong>
                                <p class="text-xs text-sem-fg-muted">
                                    MeshCore · {{ nodeType(node.kind) }} ·
                                    {{ freshKeys.has(node.peer) ? "Replied to this scan" : "Previously heard" }}
                                </p>
                                <p class="text-xs font-mono break-all">{{ node.peer }}</p>
                                <span v-if="savedKeys.has(node.peer)" class="text-xs text-sem-fg-muted"
                                    >Saved node</span
                                >
                                <button
                                    v-else
                                    type="button"
                                    class="secondary-chip mt-1"
                                    :disabled="busy || discovering"
                                    @click="save(node)"
                                >
                                    Save node
                                </button>
                            </article>
                        </section>
                        <p v-if="!discoveries.length" class="text-sm text-sem-fg-muted">
                            No matching infrastructure nodes heard yet.
                        </p>
                    </div>
                </div>
                <p v-if="peer" class="text-sm text-sem-fg-muted">
                    This node is not saved for the selected MeshCore identity.
                </p>
                <RouterLink
                    v-for="node in snapshot.nodes || []"
                    :key="node.peer"
                    :to="meshcoreNodeRoute(node.peer, snapshot.radio_id)"
                    class="flex items-center gap-3 py-3 border-b border-sem-border hover:bg-sem-surface-muted"
                    ><MaterialDesignIcon :icon-name="nodeIcon(node.kind)" class="size-8 text-sem-fg-muted" />
                    <div class="min-w-0">
                        <strong>{{ node.name || "MeshCore node" }}</strong>
                        <p class="text-xs text-sem-fg-muted">MeshCore · {{ nodeType(node.kind) }}</p>
                        <p class="font-mono text-xs truncate">{{ node.peer }}</p>
                    </div></RouterLink
                >
                <p v-if="!snapshot.nodes?.length" class="text-sm text-sem-fg-muted">
                    No saved nodes yet. Discover nearby nodes below or save a node from MeshCore Announces.
                </p>
            </template>
        </div>
    </section>
</template>
<script setup>
import { navigateAppUp } from "../../js/androidBackNavigation";
import { computed, ref, watch } from "vue";
import { useMeshCoreNotificationContext } from "../../js/meshcoreNotifications";
import MeshCoreNodePasswords from "./MeshCoreNodePasswords.vue";
import MeshCoreNodeSession from "./MeshCoreNodeSession.vue";
import SearchInput from "../SearchInput.vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import { useRoute, useRouter } from "vue-router";
import { useMeshCoreUi, meshcoreNodeRoute } from "../../js/meshcoreUi";
const props = defineProps({ peer: { type: String, default: "" }, visit: { type: String, default: "" } });
const busy = ref(false);
const { snapshot, error, action, refresh } = useMeshCoreUi(
    () => props.peer || null,
    () => !busy.value,
    () => null,
    () => props.visit
);
const selected = computed(() => (snapshot.value.nodes || []).find((row) => row.peer === props.peer));
useMeshCoreNotificationContext(() => (selected.value?.kind === 3 ? snapshot.value.active_notification_key : null));
const router = useRouter();
watch(busy, (pending) => {
    if (!pending) refresh();
});
const discovering = ref(false),
    showDiscoveries = ref(useRoute()?.query?.discover === "1"),
    discoverySearch = ref(""),
    discoveryKind = ref(0),
    discoveryStatus = ref(""),
    freshKeys = ref(new Set()),
    scanResults = ref([]);
const savedKeys = computed(() => new Set((snapshot.value.nodes || []).map((n) => n.peer)));
const discoveries = computed(() => {
    const known = new Map(
        [...(snapshot.value.announces || []), ...(snapshot.value.nodes || [])].map((node) => [node.peer, node])
    );
    for (const node of scanResults.value) known.set(node.peer, { ...known.get(node.peer), ...node });
    return [...known.values()]
        .filter(
            (node) =>
                [2, 3, 4].includes(node.kind) &&
                (!discoveryKind.value || node.kind === discoveryKind.value) &&
                `${node.name || ""} ${node.peer}`.toLowerCase().includes(discoverySearch.value.toLowerCase())
        )
        .sort((a, b) => String(a.name || a.peer).localeCompare(String(b.name || b.peer)));
});
const discoveryGroups = computed(() =>
    [
        { label: "Replied to this scan", nodes: discoveries.value.filter((node) => freshKeys.value.has(node.peer)) },
        { label: "Previously heard", nodes: discoveries.value.filter((node) => !freshKeys.value.has(node.peer)) },
    ].filter((group) => group.nodes.length)
);

function nodeType(kind) {
    return { 2: "Repeater", 3: "Room server", 4: "Sensor" }[kind] || "Node";
}
function nodeIcon(kind) {
    return { 2: "radio-tower", 3: "forum-outline", 4: "access-point" }[kind] || "radio-tower";
}
watch(
    () => snapshot.value.owner,
    () => {
        freshKeys.value = new Set();
        scanResults.value = [];
        discoveryStatus.value = "";
    }
);
async function discover() {
    if (discovering.value || !snapshot.value.connected) return;
    discovering.value = true;
    showDiscoveries.value = true;
    busy.value = true;
    freshKeys.value = new Set();
    scanResults.value = [];
    discoveryStatus.value = "Listening for nearby infrastructure nodes…";
    const owner = snapshot.value.owner;
    try {
        const result = await action("node-discover", {});
        if (snapshot.value.owner !== owner) return;
        scanResults.value = result.nodes || [];
        freshKeys.value = new Set(scanResults.value.map((node) => node.peer));
        const count = freshKeys.value.size;
        discoveryStatus.value = count
            ? `${count} nearby ${count === 1 ? "node replied" : "nodes replied"}. See Replied to this scan below.`
            : "No nearby nodes replied to this scan. Previously heard nodes remain listed separately.";
    } catch (e) {
        discoveryStatus.value =
            e.response?.data?.message ||
            "Discovery was not confirmed. Check the radio connection; some firmware does not support active discovery.";
    } finally {
        discovering.value = false;
        busy.value = false;
    }
}
async function save(node) {
    busy.value = true;
    try {
        await action("node-save", { peer: node.peer });
    } catch {
        error.value = "Could not save this MeshCore node.";
    } finally {
        busy.value = false;
    }
}
async function remove() {
    busy.value = true;
    try {
        await action("node-remove", { peer: props.peer });
        router.push({ name: "meshcore-nodes" });
    } catch {
        error.value = "Could not remove this saved node.";
    } finally {
        busy.value = false;
    }
}
</script>
