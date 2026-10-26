<template>
    <details class="border border-sem-border rounded-lg p-2">
        <summary class="cursor-pointer">Share CASEVAC · nine-line report</summary>
        <form class="space-y-2 mt-2 text-xs" @submit.prevent="submit">
            <p>
                This shares a report with your private MeshCore team. It does not contact emergency services or arrange
                evacuation.
            </p>
            <fieldset class="space-y-2">
                <legend class="font-semibold">1 · Pickup location</legend>
                <label class="block"
                    >Latitude<input
                        v-model.number="draft.latitude"
                        aria-label="CASEVAC latitude"
                        type="number"
                        min="-90"
                        max="90"
                        step="any"
                        required
                        class="input-field w-full"
                /></label>
                <label class="block"
                    >Longitude<input
                        v-model.number="draft.longitude"
                        aria-label="CASEVAC longitude"
                        type="number"
                        min="-180"
                        max="180"
                        step="any"
                        required
                        class="input-field w-full"
                /></label>
                <label class="block"
                    >Place · 20 bytes<input v-model="draft.place" maxlength="20" class="input-field w-full"
                /></label>
                <button type="button" class="secondary-chip" @click="center">Use map centre for pickup</button>
            </fieldset>
            <fieldset>
                <legend class="font-semibold">2 · Contact</legend>
                <label class="block"
                    >Frequency · 12 bytes<input v-model="draft.frequency" maxlength="12" class="input-field w-full"
                /></label>
                <label class="block"
                    >Callsign · 12 bytes<input v-model="draft.callsign" maxlength="12" class="input-field w-full"
                /></label>
            </fieldset>
            <fieldset>
                <legend class="font-semibold">3 · Patients by precedence</legend>
                <div class="grid grid-cols-2 gap-2">
                    <label v-for="[key, label] in precedence" :key="key"
                        >{{ label
                        }}<input
                            v-model.number="draft[key]"
                            :aria-label="label"
                            type="number"
                            min="0"
                            max="255"
                            step="1"
                            class="input-field w-full"
                    /></label>
                </div>
            </fieldset>
            <fieldset>
                <legend class="font-semibold">4 · Special equipment</legend>
                <label v-for="(label, i) in equipment" :key="label" class="flex gap-2"
                    ><input v-model="equipmentBits" type="checkbox" :value="i" />{{ label }}</label
                >
            </fieldset>
            <fieldset>
                <legend class="font-semibold">5 · Patients by type</legend>
                <div class="grid grid-cols-2 gap-2">
                    <label
                        >Litter<input
                            v-model.number="draft.litter"
                            type="number"
                            min="0"
                            max="255"
                            step="1"
                            class="input-field w-full" /></label
                    ><label
                        >Ambulatory<input
                            v-model.number="draft.ambulatory"
                            type="number"
                            min="0"
                            max="255"
                            step="1"
                            class="input-field w-full"
                    /></label>
                </div>
            </fieldset>
            <label class="block"
                >6 · Pickup-site security<select v-model.number="draft.security" class="input-field w-full">
                    <option v-for="(label, i) in security" :key="label" :value="i">{{ label }}</option>
                </select></label
            >
            <label class="block"
                >7 · Pickup-site marking<select v-model.number="draft.marking" class="input-field w-full">
                    <option v-for="(label, i) in marking" :key="label" :value="i">{{ label }}</option>
                </select></label
            >
            <label class="block"
                >Marking detail · 12 bytes<input
                    v-model="draft.marking_detail"
                    maxlength="12"
                    class="input-field w-full"
            /></label>
            <fieldset>
                <legend class="font-semibold">8 · Patients by nationality/status</legend>
                <div class="grid grid-cols-2 gap-2">
                    <label v-for="[key, label] in nationality" :key="key"
                        >{{ label
                        }}<input
                            v-model.number="draft[key]"
                            type="number"
                            min="0"
                            max="255"
                            step="1"
                            class="input-field w-full"
                    /></label>
                </div>
            </fieldset>
            <fieldset>
                <legend class="font-semibold">9 · Terrain and contamination</legend>
                <label v-for="(label, i) in terrain" :key="label" class="flex gap-2"
                    ><input v-model="terrainBits" type="checkbox" :value="i" />{{ label }}</label
                >
                <label class="block"
                    >NBC<select v-model.number="draft.nbc" class="input-field w-full">
                        <option v-for="(label, i) in nbc" :key="label" :value="i">{{ label }}</option>
                    </select></label
                >
            </fieldset>
            <label class="block"
                >Remarks · 40 bytes<input v-model="draft.remarks" maxlength="40" class="input-field w-full"
            /></label>
            <p v-if="totalsWarning">Patient totals differ between sections. Review before sharing.</p>
            <button type="submit" class="secondary-chip" :disabled="!canSend || confirming">
                Review and share CASEVAC…
            </button>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </form>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- UI lifetime counters are public, not secret comparisons. */
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { toLonLat } from "ol/proj";
import DialogUtils from "../../../js/DialogUtils";
import {
    precedence,
    nationality,
    equipment,
    security,
    marking,
    terrain,
    nbc,
    countFields,
    casevacLines,
} from "../../../js/meshcoreCasevac";
const props = defineProps({
    map: { type: Object, default: null },
    team: { type: Object, required: true },
    canSend: Boolean,
});
const emit = defineEmits(["send"]);
const draft = ref({
    kind: "casevac",
    latitude: "",
    longitude: "",
    place: "",
    frequency: "",
    callsign: "",
    marking_detail: "",
    remarks: "",
    security: 0,
    marking: 3,
    nbc: 0,
    ...Object.fromEntries(countFields.map(([key]) => [key, 0])),
});
const equipmentBits = ref([]),
    terrainBits = ref([]),
    problem = ref(""),
    confirming = ref(false);
let generation = 0;
watch(
    () => props.team.channel_id,
    () => {
        generation++;
        confirming.value = false;
    }
);
onBeforeUnmount(() => {
    generation++;
});
const total = (list) => list.reduce((n, [key]) => n + (draft.value[key] || 0), 0);
const totalsWarning = computed(
    () =>
        total(precedence) !== draft.value.litter + draft.value.ambulatory ||
        (total(nationality) > 0 && total(nationality) !== total(precedence))
);
function center() {
    const p = props.map?.getView?.().getCenter();
    if (p) {
        const [lon, lat] = toLonLat(p);
        draft.value.latitude = +lat.toFixed(7);
        draft.value.longitude = +lon.toFixed(7);
    }
}
async function submit() {
    if (!props.canSend || confirming.value) return;
    problem.value = "";
    const record = {
        ...draft.value,
        equipment_flags: equipmentBits.value.reduce((a, b) => a | (1 << b), 0),
        terrain_flags: terrainBits.value.reduce((a, b) => a | (1 << b), 0),
    };
    if (
        !Number.isFinite(record.latitude) ||
        Math.abs(record.latitude) > 90 ||
        !Number.isFinite(record.longitude) ||
        Math.abs(record.longitude) > 180
    ) {
        problem.value = "Enter valid pickup coordinates or use the map centre.";
        return;
    }
    if (countFields.some(([key]) => !Number.isInteger(record[key]) || record[key] < 0 || record[key] > 255)) {
        problem.value = "Patient counts must be whole numbers from 0 to 255.";
        return;
    }
    if (
        (equipmentBits.value.includes(0) && equipmentBits.value.length > 1) ||
        (terrainBits.value.includes(0) && terrainBits.value.length > 1)
    ) {
        problem.value = "Choose None / Flat on its own, or select the applicable alternatives.";
        return;
    }
    if (!total(precedence)) {
        problem.value = "Enter at least one patient by precedence.";
        return;
    }
    const limits = { frequency: 12, callsign: 12, marking_detail: 12, place: 20, remarks: 40 };
    if (Object.entries(limits).some(([key, limit]) => new TextEncoder().encode(record[key]).length > limit)) {
        problem.value = "A text field exceeds its UTF-8 byte limit.";
        return;
    }
    const token = generation;
    confirming.value = true;
    try {
        const accepted = await DialogUtils.confirm(
            [
                ...casevacLines(record),
                record.remarks,
                totalsWarning.value ? "Patient totals differ; verify them." : "",
                "Share with your private team only. No emergency service will be contacted.",
            ]
                .filter(Boolean)
                .join("\n"),
            "Review CASEVAC report"
        );
        if (accepted && token === generation && props.canSend) emit("send", record);
    } finally {
        if (token === generation) confirming.value = false;
    }
}
</script>
