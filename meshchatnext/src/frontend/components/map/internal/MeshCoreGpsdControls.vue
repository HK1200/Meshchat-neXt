<template>
    <details v-if="supported" class="border border-sem-border rounded-lg p-2 text-xs">
        <summary class="cursor-pointer">Automatic position sharing · Linux GPS receiver</summary>
        <div class="space-y-2 mt-2">
            <p>
                Optional. Requires a GPS receiver and GPSD running locally on this computer. Wi-Fi and internet access
                do not provide your position.
            </p>
            <p>
                Off by default. Sharing sends current, sufficiently accurate receiver fixes to this private MeshCore
                team. It stops on an error, a changed team, disconnection, app shutdown or the time limit, and never
                restarts automatically.
            </p>
            <label class="block"
                >Send interval<select v-model.number="interval" class="input-field" :disabled="active || busy">
                    <option :value="60">1 minute</option>
                    <option :value="120">2 minutes</option>
                    <option :value="300">5 minutes</option>
                </select></label
            >
            <label class="block"
                >Stop automatically after<select
                    v-model.number="duration"
                    class="input-field"
                    :disabled="active || busy"
                >
                    <option :value="15">15 minutes</option>
                    <option :value="30">30 minutes</option>
                    <option :value="60">1 hour</option>
                </select></label
            >
            <button
                v-if="!active"
                type="button"
                class="secondary-chip"
                :disabled="busy || !connected || !team?.enabled"
                @click="start"
            >
                {{ busy ? "Starting…" : "Start sharing receiver position" }}
            </button>
            <button v-else type="button" class="secondary-chip" @click="stop">Stop sharing receiver position</button>
            <p role="status">{{ active ? "Receiver sharing active" : "Off" }}</p>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </details>
</template>
<script setup>
import { ref, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../../js/constants";
import DialogUtils from "../../../js/DialogUtils";
const props = defineProps({
    owner: { type: String, default: null },
    team: { type: Object, default: null },
    scope: { type: String, default: null },
    connected: Boolean,
});
const supported = window.electron?.getPlatform?.() === "linux";
const active = ref(false),
    busy = ref(false),
    problem = ref(""),
    interval = ref(300),
    duration = ref(15);
let generation = 0,
    polling = false,
    mounted = true;
async function readStatus() {
    if (polling || !props.owner || !props.connected) return;
    polling = true;
    const current = generation;
    try {
        const { data } = await window.api.post(apiPath("/meshcore/team-beacon-status"), {
            expected_owner: props.owner,
        });
        if (mounted && current === generation) {
            active.value = Boolean(data.result.active);
            problem.value = data.result.error || "";
        }
    } catch {
        if (mounted && current === generation) {
            active.value = false;
            problem.value = "Could not check receiver sharing; reconnect to the radio.";
        }
    } finally {
        polling = false;
    }
}
async function stop() {
    generation++;
    busy.value = false;
    active.value = false;
    try {
        await window.api.post(apiPath("/meshcore/team-beacon-stop"), { expected_owner: props.owner });
    } catch {
        problem.value = "Could not confirm sharing stopped. Disconnect the radio to end sharing.";
    }
}
async function start() {
    if (busy.value || !props.connected || !props.team?.enabled) return;
    const current = ++generation;
    const target = {
        expected_owner: props.owner,
        expected_channel_id: props.team.channel_id,
        expected_scope: props.scope,
        interval: interval.value,
        source: "gpsd",
        duration_minutes: duration.value,
    };
    busy.value = true;
    problem.value = "";
    try {
        if (
            !(await DialogUtils.confirm(
                "Use this computer’s local GPS receiver to share your position with the selected private MeshCore team, including while the map is closed? Sharing ends at the chosen time limit. No internet location lookup is used."
            ))
        )
            return;
        if (!mounted || current !== generation) return;
        await window.api.post(apiPath("/meshcore/team-beacon-start"), target);
        if (mounted && current === generation) await readStatus();
    } catch {
        if (mounted && current === generation)
            problem.value =
                "Could not start sharing. Check the local GPSD receiver, private team and radio connection.";
    } finally {
        if (mounted && current === generation) busy.value = false;
    }
}
watch(
    [
        () => props.owner,
        () => props.team?.channel_id,
        () => props.scope,
        () => props.team?.enabled,
        () => props.connected,
    ],
    () => {
        if (supported) void stop();
    }
);
const timer = supported ? setInterval(readStatus, 2000) : null;
if (supported) void readStatus();
onBeforeUnmount(() => {
    mounted = false;
    generation++;
    clearInterval(timer);
}); // Backend consent survives map navigation, never app shutdown.
</script>
