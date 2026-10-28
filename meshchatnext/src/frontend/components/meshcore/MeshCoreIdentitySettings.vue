<template>
    <section class="border-t border-sem-border pt-4 space-y-3" aria-label="MeshCore identity settings">
        <h3 class="font-semibold">MeshCore identity</h3>
        <p v-if="snapshot.owner" class="text-xs text-sem-fg-muted">
            {{ snapshot.connected ? "Public address" : "Last connected public address" }}
        </p>
        <p v-if="snapshot.owner" class="font-mono text-xs break-all text-sem-fg-muted">{{ snapshot.owner }}</p>
        <p v-else class="text-sm text-sem-fg-muted">Connect a MeshCore radio to read its identity.</p>
        <p v-if="problem" role="alert" class="text-sm text-sem-danger">{{ problem }}</p>
        <p v-if="notice" role="status" class="text-sm text-sem-accent">{{ notice }}</p>
        <form class="space-y-3" @submit.prevent="save">
            <label class="block text-sm"
                >MeshCore display name
                <input
                    v-model="name"
                    class="input-field"
                    :disabled="busy || disabled || !snapshot.connected || original === null || needsRead"
                    autocomplete="off"
                    required
                />
            </label>
            <p class="text-xs" :class="bytes > 31 ? 'text-sem-danger' : 'text-sem-fg-muted'">
                {{ bytes }}/31 bytes · This changes the name on your MeshCore radio.
            </p>
            <div class="flex flex-wrap gap-2">
                <button
                    class="primary-chip"
                    :disabled="
                        busy ||
                        disabled ||
                        !snapshot.connected ||
                        original === null ||
                        needsRead ||
                        !valid ||
                        name === original
                    "
                >
                    {{ busy ? "Working…" : "Save MeshCore name" }}
                </button>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || disabled || !snapshot.connected"
                    @click="read"
                >
                    Read identity
                </button>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || disabled || original === null || name === original"
                    @click="name = original"
                >
                    Discard name change
                </button>
            </div>
        </form>
    </section>
</template>
<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
const lifetime = new AbortController();
const props = defineProps({
    snapshot: { type: Object, required: true },
    disabled: Boolean,
    refreshKey: { type: Number, default: 0 },
});
const emit = defineEmits(["saved", "busy"]);
const name = ref(""),
    original = ref(null),
    busy = ref(false),
    needsRead = ref(false),
    problem = ref(""),
    notice = ref("");
const bytes = computed(() => new TextEncoder().encode(name.value).length);
const valid = computed(() => name.value.trim() && !name.value.includes("\0") && bytes.value <= 31);
let revision = 0,
    stopped = false,
    pendingRead = false;
async function read() {
    if (busy.value || props.disabled || !props.snapshot.connected || !props.snapshot.owner) return;
    pendingRead = false;
    const owner = props.snapshot.owner,
        current = ++revision;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        const { data } = await window.api.get(apiPath("/meshcore/identity"), {
            signal: lifetime.signal,
            params: { radio: props.snapshot.radio_id },
        });
        if (stopped || current !== revision || owner !== props.snapshot.owner || !props.snapshot.connected) return;
        if (data.result?.public_key !== owner || typeof data.result?.name !== "string")
            throw new Error("Identity changed");
        name.value = data.result.name;
        original.value = data.result.name;
        needsRead.value = false;
    } catch {
        if (!stopped && current === revision) {
            original.value = null;
            name.value = "";
            problem.value = "Could not read the selected radio identity. Check the connection and read again.";
        }
    } finally {
        busy.value = false;
    }
}
async function save() {
    if (
        busy.value ||
        props.disabled ||
        !props.snapshot.connected ||
        original.value === null ||
        needsRead.value ||
        !valid.value ||
        name.value === original.value
    )
        return;
    const owner = props.snapshot.owner,
        requested = name.value,
        current = ++revision;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        const { data } = await window.api.post(apiPath("/meshcore/name"), { name: requested, expected_owner: owner });
        if (stopped || current !== revision || owner !== props.snapshot.owner) return;
        if (data.result?.public_key !== owner || data.result?.name !== requested) throw new Error("Unverified name");
        original.value = requested;
        notice.value = "MeshCore name saved and verified.";
        emit("saved");
    } catch {
        if (!stopped && current === revision) {
            needsRead.value = true;
            problem.value =
                "The name update could not be verified. It may have changed on the radio. Read identity before trying again.";
        }
    } finally {
        busy.value = false;
    }
}
watch(
    [() => props.snapshot.owner, () => props.snapshot.connected, () => props.refreshKey],
    () => {
        ++revision;
        name.value = "";
        original.value = null;
        needsRead.value = false;
        problem.value = "";
        notice.value = "";
        pendingRead = Boolean(props.snapshot.connected && props.snapshot.owner);
        if (pendingRead && !busy.value) read();
    },
    { immediate: true }
);
watch(
    () => props.disabled,
    (value) => {
        if (!value && pendingRead && !busy.value && !stopped) read();
    }
);
watch(busy, (value) => {
    emit("busy", value);
    if (!value && pendingRead && !stopped) read();
});
onBeforeUnmount(() => {
    lifetime.abort();
    stopped = true;
    emit("busy", false);
    ++revision;
});
</script>
<style scoped>
@reference "../../style.css";
.input-field {
    @apply bg-sem-surface-muted border border-sem-border text-sm rounded-2xl focus:ring-2 focus:ring-sem-focus focus:border-sem-focus-border block w-full p-2.5 text-sem-fg transition;
}
button {
    @apply disabled:opacity-50 disabled:cursor-not-allowed;
}
</style>
