<template>
    <details class="border-t border-sem-border pt-4" @toggle="opened">
        <summary class="cursor-pointer text-sm font-semibold">Radio2 · MediaMesh</summary>
        <div class="space-y-3 pt-3">
            <p class="text-xs text-sem-fg-muted">
                Optional second LoRa profile for MediaMesh. One transceiver alternates between the two profiles. TX
                power is shared with your primary profile.
            </p>
            <p v-if="problem" role="alert" class="text-sm text-sem-danger">{{ problem }}</p>
            <p v-if="notice" role="status" class="text-sm text-sem-accent">{{ notice }}</p>
            <p v-if="baseline && !baseline.supported" class="text-sm text-sem-fg-muted">
                This radio firmware does not support Radio2.
            </p>
            <form v-if="baseline?.supported" class="space-y-3" @submit.prevent="apply">
                <fieldset :disabled="disabled || busy || needsRead || !snapshot.connected" class="space-y-3">
                    <label class="flex items-center gap-2 text-sm"
                        ><input v-model="enabled" type="checkbox" />Enable Radio2</label
                    >
                    <div v-if="enabled" class="grid gap-3 sm:grid-cols-2">
                        <label class="text-sm"
                            >Frequency (MHz)<input
                                v-model.number="draft.frequency_mhz"
                                class="input-field"
                                type="number"
                                step="0.001"
                                required
                        /></label>
                        <label class="text-sm"
                            >Bandwidth (kHz)<input
                                v-model.number="draft.bandwidth_khz"
                                class="input-field"
                                type="number"
                                step="0.001"
                                required
                        /></label>
                        <label class="text-sm"
                            >Spreading factor<select v-model.number="draft.sf" class="input-field">
                                <option v-for="sf in 8" :key="sf" :value="sf + 4">SF{{ sf + 4 }}</option>
                            </select></label
                        >
                        <label class="text-sm"
                            >Coding rate<select v-model.number="draft.cr" class="input-field">
                                <option v-for="cr in [5, 6, 7, 8]" :key="cr" :value="cr">4/{{ cr }}</option>
                            </select></label
                        >
                    </div>
                    <p class="text-xs text-sem-fg-muted">
                        New profiles default to MediaMesh: 911.150 MHz, 250 kHz, SF7, CR4/5. Saving an enabled profile
                        uses automatic preamble, disables cross-profile forwarding, and requires media to use Radio2.
                        Existing radio values are loaded first.
                    </p>
                    <button class="primary-chip" :disabled="!dirty">Apply and verify Radio2</button>
                </fieldset>
            </form>
            <p v-if="baseline?.timing_pending" class="text-xs text-sem-fg-muted">
                The radio is measuring switching timing. Its automatic preamble may adjust during this check.
            </p>
            <button
                type="button"
                class="secondary-chip"
                :disabled="disabled || busy || !snapshot.connected"
                @click="read"
            >
                {{ busy ? "Working…" : "Read Radio2 from radio" }}
            </button>
            <p class="text-xs text-sem-fg-muted">
                These controls prepare the radio. Photo and voice messaging support is still being added to the app.
            </p>
        </div>
    </details>
</template>
<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
const lifetime = new AbortController();
const props = defineProps({ snapshot: { type: Object, required: true }, disabled: Boolean });
const emit = defineEmits(["busy"]);
const baseline = ref(null),
    enabled = ref(false),
    draft = ref({}),
    busy = ref(false),
    needsRead = ref(false),
    problem = ref(""),
    notice = ref("");
let generation = 0,
    stopped = false;
const dirty = computed(
    () =>
        baseline.value?.supported &&
        (enabled.value !== baseline.value.enabled ||
            (enabled.value &&
                ["frequency_mhz", "bandwidth_khz", "sf", "cr"].some(
                    (key) => draft.value[key] !== baseline.value.profile?.[key]
                )))
);
function accept(value) {
    baseline.value = value;
    enabled.value = Boolean(value.enabled);
    draft.value = { ...(value.profile || value.defaults) };
    needsRead.value = false;
}
async function run(write) {
    if (props.disabled || busy.value || !props.snapshot.connected || (write && needsRead.value)) return;
    const owner = props.snapshot.owner,
        token = ++generation;
    busy.value = true;
    emit("busy", true);
    problem.value = "";
    notice.value = "";
    try {
        const { data } = write
            ? await window.api.post(apiPath("/meshcore/radio2"), {
                  enabled: enabled.value,
                  ...(enabled.value ? draft.value : {}),
                  expected_owner: owner,
              })
            : await window.api.get(apiPath("/meshcore/radio2"), { signal: lifetime.signal });
        if (!stopped && token === generation && owner === props.snapshot.owner && props.snapshot.connected) {
            accept(data.result);
            if (write) notice.value = "Radio2 settings saved and verified.";
        }
    } catch {
        if (!stopped && token === generation) {
            needsRead.value = write;
            problem.value = write
                ? "Radio2 changes could not be fully verified. Reconnect and read the radio before trying again."
                : "Could not read Radio2. Check the connection and try again.";
        }
    } finally {
        busy.value = false;
        emit("busy", false);
    }
}
function read() {
    return run(false);
}
function apply() {
    return run(true);
}
function opened(event) {
    if (event.target.open && !baseline.value) read();
}
watch([() => props.snapshot.owner, () => props.snapshot.connected], () => {
    ++generation;
    baseline.value = null;
    draft.value = {};
    problem.value = "";
    notice.value = "";
    needsRead.value = false;
});

onBeforeUnmount(() => {
    lifetime.abort();
    stopped = true;
    ++generation;
    emit("busy", false);
});
</script>
<style scoped>
@reference "../../style.css";
.input-field {
    @apply bg-sem-surface-muted border border-sem-border text-sm rounded-2xl block w-full p-2.5 text-sem-fg;
}
button {
    @apply disabled:opacity-50 disabled:cursor-not-allowed;
}
</style>
