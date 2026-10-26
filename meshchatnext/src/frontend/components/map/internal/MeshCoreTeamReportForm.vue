<template>
    <details class="border border-sem-border rounded-lg p-2">
        <summary class="cursor-pointer">Share a report · SALUTE / general</summary>
        <form class="space-y-2 mt-2" @submit.prevent="submit">
            <label class="block"
                >Report type<select v-model.number="draft.report_kind" class="input-field w-full">
                    <option :value="0">SALUTE</option>
                    <option :value="1">General report</option>
                </select></label
            >
            <label class="block"
                >Urgency<select v-model.number="draft.urgency" class="input-field w-full">
                    <option v-for="(name, i) in team.urgencies || []" :key="i" :value="i">{{ name }}</option>
                </select></label
            >
            <label v-if="!draft.report_kind" class="block"
                >Affiliation<select v-model.number="draft.affiliation" class="input-field w-full">
                    <option v-for="(name, i) in team.affiliations || []" :key="i" :value="i">{{ name }}</option>
                </select></label
            >
            <label class="block"
                >{{ draft.report_kind ? "Report text · 100 bytes" : "Activity · 32 bytes"
                }}<input
                    v-model="draft.activity"
                    :maxlength="draft.report_kind ? 100 : 32"
                    class="input-field w-full"
                    required
            /></label>
            <template v-if="!draft.report_kind">
                <div class="grid grid-cols-2 gap-2">
                    <label
                        >Vehicles<input
                            v-model.number="draft.vehicles"
                            type="number"
                            min="0"
                            max="255"
                            class="input-field w-full" /></label
                    ><label
                        >People<input
                            v-model.number="draft.people"
                            type="number"
                            min="0"
                            max="255"
                            class="input-field w-full"
                    /></label>
                </div>
                <label class="block"
                    >Size note · 12 bytes<input v-model="draft.size" maxlength="12" class="input-field w-full"
                /></label>
                <label class="block"
                    >Unit / uniform · 24 bytes<input v-model="draft.unit" maxlength="24" class="input-field w-full"
                /></label>
                <label class="block"
                    >Equipment · 28 bytes<input v-model="draft.equipment" maxlength="28" class="input-field w-full"
                /></label>
            </template>
            <label class="block"
                >Place · 24 bytes<input v-model="draft.place" maxlength="24" class="input-field w-full"
            /></label>
            <label class="block"
                >Latitude<input
                    v-model.number="draft.latitude"
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
                    type="number"
                    min="-180"
                    max="180"
                    step="any"
                    required
                    class="input-field w-full"
            /></label>
            <label class="block"
                >Observed time<input v-model="observed" type="datetime-local" class="input-field w-full"
            /></label>
            <p>Leave the time blank to use the send time. Coordinates must describe the reported location.</p>
            <MeshCoreTeamAttachment
                :owner="owner"
                :channel-id="team.channel_id"
                :connected="connected"
                composer
                @prepared="draft.attachment = $event"
            />
            <p v-if="draft.attachment">
                {{
                    draft.attachment.mode === 40
                        ? "Photo attached"
                        : `Recording attached · ${draft.attachment.extra} seconds`
                }}
            </p>
            <button type="button" class="secondary-chip" @click="center">Use map centre</button>
            <button type="submit" class="secondary-chip" :disabled="!canSend">Share report</button>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </form>
    </details>
</template>
<script setup>
import { ref } from "vue";
import MeshCoreTeamAttachment from "./MeshCoreTeamAttachment.vue";
import { toLonLat } from "ol/proj";
const props = defineProps({
    team: { type: Object, required: true },
    map: { type: Object, default: null },
    canSend: Boolean,
    owner: { type: String, default: "" },
    connected: Boolean,
});
const emit = defineEmits(["send"]);
const draft = ref({
        kind: "report",
        report_kind: 0,
        urgency: 1,
        affiliation: 0,
        vehicles: 0,
        people: 0,
        activity: "",
        size: "",
        unit: "",
        equipment: "",
        place: "",
        latitude: "",
        longitude: "",
    }),
    observed = ref(""),
    problem = ref("");
function center() {
    const p = props.map?.getView?.().getCenter();
    if (p) {
        const [lon, lat] = toLonLat(p);
        draft.value.longitude = +lon.toFixed(7);
        draft.value.latitude = +lat.toFixed(7);
    }
}
function submit() {
    if (!props.canSend) return;
    problem.value = "";
    const record = { ...draft.value };
    if (!Number.isFinite(record.latitude) || !Number.isFinite(record.longitude)) {
        problem.value = "Enter the report coordinates or use the map centre.";
        return;
    }
    if (observed.value) {
        const stamp = Date.parse(observed.value);
        if (!Number.isFinite(stamp)) {
            problem.value = "Enter a valid observed time.";
            return;
        }
        record.timestamp = Math.floor(stamp / 1000);
    }
    if (record.report_kind)
        Object.assign(record, { size: "", unit: "", equipment: "", people: 0, vehicles: 0, affiliation: 0 });
    emit("send", record);
}
</script>
