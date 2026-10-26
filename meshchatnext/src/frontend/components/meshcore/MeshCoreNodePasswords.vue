<template>
    <details class="border-t border-sem-border pt-3" @toggle="opened">
        <summary class="text-sm cursor-pointer">Saved server passwords</summary>
        <div class="space-y-2 mt-3 text-sm">
            <p class="text-xs text-sem-fg-muted">
                Optional · encrypted on this Android device. Excluded from app exports. Saved separately for each
                MeshCore identity, node and role.
            </p>
            <p v-if="loaded && !status.available">Secure password storage is unavailable on this device.</p>
            <template v-if="status.available">
                <label
                    >Access
                    <select
                        v-model="role"
                        class="bg-sem-surface-muted text-sem-fg border border-sem-border rounded-lg p-2 ml-2"
                    >
                        <option value="member">Member / guest</option>
                        <option value="admin">Administrator</option>
                    </select></label
                >
                <p>{{ saved ? "Password saved on this device" : "No saved password for this access level" }}</p>
                <div v-if="saved" class="flex flex-wrap gap-2">
                    <button
                        v-if="canLogin"
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || disabled"
                        @click="$emit('use-saved', role)"
                    >
                        Log in with saved password
                    </button>
                    <button
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || disabled"
                        @click="perform('forget')"
                    >
                        Forget saved password
                    </button>
                </div>
                <label class="block"
                    >{{ saved ? "Replace saved password" : "Password to save"
                    }}<input
                        v-model="password"
                        :type="show ? 'text' : 'password'"
                        autocomplete="off"
                        aria-label="Password to save securely"
                        class="block w-full bg-sem-surface-muted border border-sem-border rounded-lg p-2 mt-1"
                        :disabled="busy || disabled"
                /></label>
                <div class="flex gap-2">
                    <button type="button" class="secondary-chip" :disabled="busy || disabled" @click="show = !show">
                        {{ show ? "Hide" : "Show" }}</button
                    ><button
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || disabled || !password || bytes > 64"
                        @click="perform('save')"
                    >
                        Save securely
                    </button>
                </div>
            </template>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </details>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Generation counters guard component lifetime; no secret comparisons. */
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
const props = defineProps({
    owner: { type: String, default: "" },
    peer: { type: String, required: true },
    disabled: Boolean,
    canLogin: Boolean,
    refreshKey: { type: Number, default: 0 },
});
const emit = defineEmits(["use-saved", "available"]);
const role = ref("member"),
    password = ref(""),
    show = ref(false),
    busy = ref(false),
    loaded = ref(false),
    problem = ref("");
const status = ref({ available: false, saved_roles: [] });
const saved = computed(() => status.value.saved_roles.includes(role.value));
const bytes = computed(() => new TextEncoder().encode(password.value).length);
let generation = 0,
    expanded = false;
async function perform(action = "status") {
    if (busy.value || !props.owner || !props.peer) return;
    const token = generation;
    busy.value = true;
    problem.value = "";
    const body = { expected_owner: props.owner, peer: props.peer };
    if (action !== "status") body.role = role.value;
    if (action === "save") body.password = password.value;
    password.value = "";
    show.value = false;
    try {
        const { data } = await window.api.post(apiPath(`/meshcore/node-password-${action}`), body);
        if (token !== generation) return;
        status.value = data.result;
        loaded.value = true;
        emit("available", status.value.available);
    } catch {
        if (token === generation) problem.value = "Secure password storage could not complete this request.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
function opened(event) {
    expanded = event.target.open;
    if (expanded) perform();
    else {
        password.value = "";
        show.value = false;
    }
}
watch(
    () => props.refreshKey,
    () => {
        if (expanded) perform();
    }
);
watch(
    () => [props.owner, props.peer],
    () => {
        generation++;
        password.value = "";
        show.value = false;
        busy.value = false;
        loaded.value = false;
        status.value = { available: false, saved_roles: [] };
        if (expanded) perform();
    }
);
onBeforeUnmount(() => {
    generation++;
    password.value = "";
});
</script>
