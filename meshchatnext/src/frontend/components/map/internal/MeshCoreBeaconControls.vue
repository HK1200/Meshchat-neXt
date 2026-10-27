<template>
    <MeshCoreGpsdControls v-bind="props" />
    <details v-if="supported" class="border border-sem-border rounded-lg p-2 text-xs">
        <summary class="cursor-pointer">Automatic position sharing · Android</summary>
        <div class="space-y-2 mt-2">
            <p>
                Off by default. When started, your current phone position is sent to this private MeshCore team while
                the app is in the background. Android shows a Stop sharing notification. This uses GPS and battery.
            </p>
            <p>
                GPS stays active while sharing. Only current fixes with adequate accuracy are sent; weak reception can
                delay updates. The send interval limits radio transmissions.
            </p>
            <p>
                Stops on a connection error, changed team settings, app shutdown or restart. It does not restart
                automatically.
            </p>
            <label class="block"
                >Send interval
                <select v-model.number="interval" class="input-field" :disabled="active || busy">
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
                    <option :value="0">Until I stop sharing</option>
                    <option :value="15">15 minutes</option>
                    <option :value="30">30 minutes</option>
                    <option :value="60">1 hour</option>
                </select></label
            >
            <p v-if="active">
                {{ submitted }} positions submitted<span v-if="lastAge >= 0"> · last {{ lastAge }} seconds ago</span>
            </p>
            <button
                v-if="!active"
                type="button"
                class="secondary-chip"
                :disabled="busy || !connected || !team?.enabled"
                @click="start"
            >
                {{ busy ? "Starting…" : "Start sharing my position" }}
            </button>
            <button v-else type="button" class="secondary-chip" @click="stop">Stop sharing my position</button>
            <p role="status">{{ status }}</p>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Lifetime counters are public. */
import { ref, watch, onBeforeUnmount } from "vue";
import MeshCoreGpsdControls from "./MeshCoreGpsdControls.vue";
import { getAndroidPosition } from "../../../js/androidLocation";
import { getCsrfToken } from "../../../js/csrfToken";
import { apiPath } from "../../../js/constants";
import DialogUtils from "../../../js/DialogUtils";
const props = defineProps({
    owner: { type: String, default: null },
    team: { type: Object, default: null },
    scope: { type: String, default: null },
    connected: Boolean,
});
const native = window.MeshchatNextAndroid;
const supported = typeof native?.startMeshCoreBeacons === "function";
const interval = ref(300),
    active = ref(false),
    busy = ref(false),
    status = ref("Off"),
    problem = ref("");
const duration = ref(0),
    submitted = ref(0),
    lastAge = ref(-1);
let generation = 0;
function readStatus() {
    try {
        const result = JSON.parse(native.meshCoreBeaconStatus());
        active.value = Boolean(result.active);
        status.value = result.status || "Off";
        submitted.value = result.submitted || 0;
        lastAge.value = result.secondsSinceSubmitted ?? -1;
    } catch {
        active.value = false;
    }
}
async function stop() {
    generation++;
    busy.value = false;
    native?.stopMeshCoreBeacons?.();
    active.value = false;
    status.value = "Off";
    try {
        await window.api.post(apiPath("/meshcore/team-beacon-stop"), { expected_owner: props.owner });
    } catch {
        /* Disconnected sessions already lost consent. */
    }
}
async function start() {
    if (busy.value || !props.connected || !props.team?.enabled) return;
    const token = ++generation;
    const target = { owner: props.owner, channel: props.team.channel_id, scope: props.scope, interval: interval.value };
    busy.value = true;
    problem.value = "";
    try {
        if (
            !(await DialogUtils.confirm(
                "Share this phone’s location automatically with the selected private MeshCore team, including while the app is in the background? You can stop from the Android notification."
            ))
        )
            return;
        if (token !== generation) return;
        await getAndroidPosition(); // Permission and initial local fix only; no transmission here.
        if (token !== generation) return;
        const { data } = await window.api.post(apiPath("/meshcore/team-beacon-start"), {
            expected_owner: target.owner,
            expected_channel_id: target.channel,
            expected_scope: target.scope,
            interval: target.interval,
        });
        if (token !== generation) return;
        if (typeof native.startTimedMeshCoreBeacons === "function")
            native.startTimedMeshCoreBeacons(
                target.owner,
                data.result.token,
                target.interval,
                getCsrfToken(),
                duration.value
            );
        else native.startMeshCoreBeacons(target.owner, data.result.token, target.interval, getCsrfToken());
        status.value = "Starting Android location sharing…";
    } catch {
        if (token === generation)
            problem.value =
                "Could not start sharing. Check location permission, notifications and the radio connection.";
    } finally {
        if (token === generation) busy.value = false;
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
const timer = supported ? setInterval(readStatus, 1000) : null;
if (supported) readStatus();
onBeforeUnmount(() => {
    generation++;
    clearInterval(timer);
}); // User-enabled foreground service survives map navigation.
</script>
