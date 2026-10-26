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
                            <p v-for="node in hop.matches" :key="node.peer" class="break-words">
                                {{ node.name
                                }}<span class="text-sem-fg-muted">
                                    ·
                                    {{
                                        node.latitude != null ? "reported location available" : "no reported location"
                                    }}</span
                                >
                            </p></template
                        >
                    </li>
                </ol>
                <button v-if="route.points.length" type="button" class="primary-chip" @click="showMap(selection)">
                    View captured route on map
                </button>
                <p v-if="!route.points.length" class="text-xs text-sem-fg-muted">
                    {{
                        route.route === "direct"
                            ? "Map unavailable: this is a supplied direct path, not a captured traversal."
                            : "Map unavailable: no nodes in this captured packet have unambiguous reported locations."
                    }}
                    <span v-if="details.direction === 'out'">
                        Sent messages need a matching received copy with usable locations to show a captured route.
                    </span>
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
const route = computed(() => details.value?.routes?.[selection.value]);
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
