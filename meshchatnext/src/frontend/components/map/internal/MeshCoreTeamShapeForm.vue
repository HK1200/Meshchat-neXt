<template>
    <details class="border border-sem-border rounded-lg p-2" @toggle="readDrawings">
        <summary class="cursor-pointer">Share a drawing · route / boundary</summary>
        <div class="space-y-2 mt-2">
            <p>
                Draw a line, polygon or circle with the existing map tools, then select it here. Sharing sends a copy to
                your private MeshCore team channel.
            </p>
            <label class="block"
                >Drawing<select v-model="selected" class="input-field w-full">
                    <option value="">Choose a drawing</option>
                    <option v-for="row in drawings" :key="row.id" :value="row.id">{{ row.label }}</option>
                </select></label
            >
            <button type="button" class="secondary-chip" @click="readDrawings">Refresh drawing list</button>
            <p v-if="!drawings.length">No supported drawings yet. Close this panel to use the map drawing tools.</p>
            <template v-if="selected">
                <label class="block"
                    >Label · 24 UTF-8 bytes<input v-model="label" maxlength="24" class="input-field w-full"
                /></label>
                <label v-if="selectedType === 'LineString'" class="flex gap-2"
                    ><input v-model="route" type="checkbox" /> Share as a route</label
                >
                <label v-if="route && selectedType === 'LineString'" class="block"
                    >Travel method<select v-model.number="method" class="input-field w-full">
                        <option v-for="(name, i) in team.route_methods || []" :key="i" :value="i">{{ name }}</option>
                    </select></label
                >
                <label v-if="['Polygon', 'Circle'].includes(selectedType)" class="block"
                    >Geofence definition<select v-model.number="geofence" class="input-field w-full">
                        <option v-for="(name, i) in team.geofences || []" :key="i" :value="i">{{ name }}</option>
                    </select></label
                >
                <p v-if="geofence && ['Polygon', 'Circle'].includes(selectedType)">
                    Shares the boundary and crossing rule. Enable local crossing alerts in Team settings. Compatible
                    clients apply their own monitoring settings.
                </p>
                <p>
                    One radio packet per drawing · coordinates rounded to approximately one metre. Detailed drawings
                    must be simplified or split; nothing is removed automatically.
                </p>
                <button type="button" class="secondary-chip" :disabled="busy || !canSend" @click="preview">
                    Check size
                </button>
                <p v-if="checked" role="status">
                    {{ checked.vertices }} vertices · {{ checked.bytes }} / {{ checked.limit }} bytes
                </p>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || !canSend || !currentChecked"
                    @click="share"
                >
                    Share drawing
                </button>
            </template>
            <p v-if="problem || buildProblem" role="alert" class="text-sem-danger">{{ problem || buildProblem }}</p>
        </div>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Public drawing IDs, coordinates and lifetime counters are not secrets. */
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { unByKey } from "ol/Observable";
import { drawingShape } from "../../../js/meshcoreShapes";
import { apiPath } from "../../../js/constants";
const props = defineProps({
    owner: { type: String, required: true },
    team: { type: Object, required: true },
    source: { type: Object, default: null },
    canSend: Boolean,
});
const emit = defineEmits(["send"]);
const drawings = ref([]),
    selected = ref(""),
    label = ref(""),
    route = ref(false),
    method = ref(0),
    geofence = ref(0),
    checked = ref(null),
    problem = ref(""),
    busy = ref(false),
    revision = ref(0);
let keys = [],
    generation = 0;
const references = new Map(),
    featureIds = new WeakMap();
function readDrawings() {
    const rows = [];
    references.clear();
    for (const [index, feature] of (props.source?.getFeatures?.() || []).entries()) {
        const type = feature.getGeometry?.()?.getType?.();
        if (!["LineString", "Polygon", "Circle"].includes(type)) continue;
        if (!featureIds.has(feature)) featureIds.set(feature, crypto.randomUUID());
        const id = featureIds.get(feature);
        references.set(id, feature);
        rows.push({ id, label: String(feature.get("name") || feature.get("label") || `${type} ${index + 1}`), type });
    }
    drawings.value = rows;
    revision.value++;
    if (!references.has(selected.value)) selected.value = "";
}
const selectedType = computed(() => drawings.value.find((r) => r.id === selected.value)?.type);
const built = computed(() => {
    revision.value;
    try {
        const feature = references.get(selected.value);
        if (!feature) return { record: null, error: "" };
        const shape = drawingShape(feature, route.value);
        return {
            record: {
                ...shape,
                label: label.value,
                color: props.team.color || 0,
                geofence: [2, 4].includes(shape.shape_kind) ? geofence.value : 0,
                route_method: shape.shape_kind === 5 ? method.value : 0,
            },
            error: "",
        };
    } catch (error) {
        return { record: null, error: error.message };
    }
});
const buildProblem = computed(() => built.value.error);
const signature = computed(() => JSON.stringify(built.value.record));
const currentChecked = computed(() => checked.value?.signature === signature.value);
watch(signature, () => {
    checked.value = null;
    problem.value = "";
    generation++;
    busy.value = false;
});
watch([() => props.owner, () => props.team.channel_id], () => {
    generation++;
    checked.value = null;
    busy.value = false;
});
watch(selected, () => {
    label.value = drawings.value.find((r) => r.id === selected.value)?.label || "";
    route.value = false;
    geofence.value = 0;
});
watch(
    () => props.source,
    (source) => {
        keys.forEach(unByKey);
        keys = [];
        readDrawings();
        if (source?.on)
            keys = ["addfeature", "removefeature", "changefeature"].map((type) => source.on(type, readDrawings));
    },
    { immediate: true }
);
async function preview() {
    if (busy.value || !props.canSend || !built.value.record) return;
    const token = generation,
        owner = props.owner,
        body = built.value.record,
        sig = signature.value;
    busy.value = true;
    problem.value = "";
    try {
        const { data } = await window.api.post(apiPath("/meshcore/team-shape-preview"), {
            record: body,
            expected_owner: owner,
        });
        if (
            !Number.isInteger(data.result?.bytes) ||
            data.result.bytes < 1 ||
            data.result.bytes > 163 ||
            data.result.limit !== 163 ||
            data.result.vertices !== body.points.length
        )
            throw new Error("Invalid size preview");
        if (token === generation) checked.value = { ...data.result, signature: sig };
    } catch (error) {
        if (token === generation)
            problem.value =
                error?.response?.data?.error ||
                "This drawing could not fit one packet. Simplify or split it and check again.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
function share() {
    if (props.canSend && !busy.value && currentChecked.value && built.value.record)
        emit("send", JSON.parse(signature.value));
}
onBeforeUnmount(() => {
    generation++;
    keys.forEach(unByKey);
});
</script>
