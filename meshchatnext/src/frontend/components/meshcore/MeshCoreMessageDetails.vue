<template>
    <AppModal
        show-close
        :model-value="Boolean(row)"
        title="MeshCore message details"
        body-class="overflow-y-auto p-4 space-y-4"
        @update:model-value="!$event && $emit('close')"
    >
        <p v-if="loading" role="status" class="text-sm">Loading captured path information…</p>
        <p v-if="error" role="alert" class="text-sm text-sem-danger">{{ error }}</p>
        <template v-if="details">
            <p class="text-sm">{{ details.direction === "out" ? "Outgoing" : "Incoming" }} · {{ details.state }}</p>
            <p v-if="details.direction === 'out'" class="text-sm">
                {{
                    details.heard_repeats == null
                        ? "Repeat tracking unavailable."
                        : `${details.heard_repeats} matching repeats recorded.`
                }}
                Not a unique-repeater count or delivery receipt.
            </p>
            <p v-if="details.reported_hops !== null" class="text-sm">
                Radio reported {{ details.reported_hops }} {{ details.reported_hops === 1 ? "hop" : "hops" }}.
            </p>
            <p v-else-if="details.direct_routing" class="text-sm">
                Direct routing · the message queue did not report its hop list.
            </p>
            <p v-if="details.snr != null || details.rssi != null" class="text-sm">
                Radio receipt<span v-if="details.snr != null"> · SNR {{ details.snr }} dB</span
                ><span v-if="details.rssi != null"> · RSSI {{ details.rssi }} dBm</span>
            </p>
            <p v-if="!details.routes.length" class="text-sm text-sem-fg-muted">
                No full packet path was captured for this message. Saved contact routes are not substituted for the
                route this message took.
            </p>
            <label v-if="details.routes.length > 1" class="block text-sm"
                >Captured packet<select v-model.number="selection" class="block w-full input-field">
                    <option v-for="(captured, index) in details.routes" :key="index" :value="index">
                        Observation {{ index + 1 }} · {{ captured.hops.length }} hop hashes
                    </option>
                </select></label
            >
            <template v-if="route">
                <p v-if="details.direction === 'out' && route.route === 'flood' && route.hops.length" class="text-sm">
                    Last relay claimed in this captured copy:
                    {{
                        route.hops.at(-1).candidate_count === 1
                            ? route.hops.at(-1).matches[0].name
                            : route.hops.at(-1).hash
                    }}
                    · prefix match, not a verified identity.
                </p>
                <p class="text-sm">
                    {{
                        route.route === "flood"
                            ? "Observed flood path"
                            : "Supplied direct path · not proof of traversal"
                    }}
                    · {{ route.hash_bytes }}-byte hashes
                </p>
                <p class="text-xs text-sem-fg-muted">
                    {{ new Date(route.received * 1000).toLocaleString()
                    }}<span v-if="route.rssi != null"> · RSSI {{ route.rssi }} dBm</span
                    ><span v-if="route.snr != null"> · SNR {{ route.snr }} dB</span>
                </p>
                <p v-if="!route.hops.length" class="text-sm">No repeater hashes in this captured packet.</p>
                <ol class="space-y-3 text-sm">
                    <li v-for="(hop, index) in route.hops" :key="index" class="rounded-lg border border-sem-border p-3">
                        <span class="font-mono">{{ index + 1 }} · {{ hop.hash }}</span>
                        <span v-if="hop.candidate_count === 0" class="block text-sem-fg-muted">Unknown node</span>
                        <template v-else
                            ><p>
                                {{
                                    hop.candidate_count === 1
                                        ? "Known prefix match"
                                        : `${hop.candidate_count} possible matches · ambiguous`
                                }}
                            </p>
                            <details
                                v-for="node in hop.matches"
                                :key="node.peer"
                                class="rounded border border-sem-border p-2 mt-2"
                            >
                                <summary class="cursor-pointer break-words min-h-11 py-2">
                                    {{ node.name }} ·
                                    {{
                                        hasReportedPosition(node)
                                            ? "reported location available"
                                            : "no reported location"
                                    }}
                                </summary>
                                <dl class="space-y-2 text-xs break-words">
                                    <div>
                                        <dt>Type</dt>
                                        <dd>{{ nodeKinds[node.kind] || "Node" }}</dd>
                                    </div>
                                    <div>
                                        <dt>Public key</dt>
                                        <dd class="font-mono">{{ node.peer }}</dd>
                                    </div>
                                    <template v-if="hasReportedPosition(node)">
                                        <div>
                                            <dt>Reported position</dt>
                                            <dd>{{ node.latitude.toFixed(6) }}, {{ node.longitude.toFixed(6) }}</dd>
                                        </div>
                                        <div>
                                            <dt>Position report saved</dt>
                                            <dd>{{ positionDate(node.updated) }}</dd>
                                        </div>
                                    </template>
                                </dl>
                                <p class="text-xs text-sem-fg-muted mt-2">
                                    {{
                                        hop.candidate_count > 1
                                            ? "Possible prefix match; this hop is ambiguous."
                                            : "Prefix match, not a verified relay identity."
                                    }}
                                    Reported positions may be old and are not positions at message time.
                                </p>
                                <button
                                    v-if="hasReportedPosition(node)"
                                    type="button"
                                    class="secondary-chip mt-2 min-h-11"
                                    @click="showNode(node)"
                                >
                                    Show on map
                                </button>
                            </details></template
                        >
                    </li>
                </ol>
                <p v-if="route.points.length && hasUnmappedHops" class="text-xs text-sem-fg-muted">
                    Some hops have no reported location or match more than one node. The map shows known positions and
                    leaves gaps between unresolved hops.
                </p>
                <button v-if="route.points.length" type="button" class="primary-chip" @click="showMap(selection)">
                    View captured route on map
                </button>
                <p v-if="!route.points.length" class="text-xs text-sem-fg-muted">
                    {{
                        route.route === "direct"
                            ? "This packet lists a supplied path, not an observed route."
                            : "A route map is not available for this observation."
                    }}
                    Expand a repeater above for its details. Show on map is available when it has a reported location.
                </p>
            </template>
            <button v-if="details.endpoints?.length" type="button" class="secondary-chip" @click="showMap(-1)">
                View reported client locations
            </button>
            <p class="text-xs text-sem-fg-muted">{{ details.note }}</p>
        </template>
    </AppModal>
</template>
<script setup>
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { hasReportedPosition } from "../../js/meshcoreNodeSearch";
import AppModal from "../AppModal.vue";
import { apiPath } from "../../js/constants";
const props = defineProps({
    row: { type: Object, default: null },
    owner: { type: String, default: "" },
    target: { type: String, required: true },
    kind: { type: String, required: true },
});
const emit = defineEmits(["close"]),
    router = useRouter();
const details = ref(null),
    error = ref(""),
    loading = ref(false),
    selection = ref(0);
let generation = 0;
const nodeKinds = { 1: "Client", 2: "Repeater", 3: "Room server", 4: "Sensor" };
function positionDate(stamp) {
    if (!Number.isFinite(stamp) || stamp <= 0) return "Time unavailable";
    const date = new Date(stamp * 1000);
    return Number.isFinite(date.getTime()) ? date.toLocaleString() : "Time unavailable";
}
function showNode(node) {
    if (!hasReportedPosition(node) || !/^[a-f0-9]{64}$/i.test(node.peer || "")) return;
    emit("close");
    void router.push({ name: "map", query: { meshcoreNode: node.peer, meshcoreOwner: props.owner } });
}
const route = computed(() => details.value?.routes?.[selection.value]);
const hasUnmappedHops = computed(() =>
    route.value?.hops?.some((hop) => hop.candidate_count !== 1 || !hasReportedPosition(hop.matches?.[0]))
);
watch(
    () => [props.row?.id, props.owner, props.target, props.kind],
    async () => {
        const current = ++generation;
        details.value = null;
        error.value = "";
        selection.value = 0;
        loading.value = false;
        if (!props.row) return;
        loading.value = true;
        try {
            const { data } = await window.api.get(apiPath("/meshcore/message-details"), {
                params: { owner: props.owner, kind: props.kind, target: props.target, id: props.row.id },
            });
            if (
                data.result?.owner !== props.owner ||
                data.result?.id !== props.row?.id ||
                data.result?.target !== props.target ||
                data.result?.kind !== props.kind ||
                !Array.isArray(data.result?.routes)
            )
                throw new Error("Unsupported message details response");
            if (current === generation) details.value = data.result;
        } catch {
            if (current === generation)
                error.value =
                    "Message path details are unavailable. Check that this build supports them and that the selected MeshCore identity has not changed.";
        } finally {
            if (current === generation) loading.value = false;
        }
    },
    { immediate: true }
);
onBeforeUnmount(() => {
    generation++;
});
function showMap(index) {
    if (index === -1 ? !details.value?.endpoints?.length : !route.value?.points.length) return;
    const query = {
        mcMessage: props.row.id,
        mcOwner: props.owner,
        mcTarget: props.target,
        mcKind: props.kind,
        mcObservation: String(index),
    };
    emit("close");
    void router.push({ name: "map", query });
}
</script>
