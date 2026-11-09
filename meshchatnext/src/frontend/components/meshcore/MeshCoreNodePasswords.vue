<template>
    <details class="border-t border-sem-border pt-3" @toggle="opened">
        <summary class="cursor-pointer text-sm font-medium">Saved passwords</summary>
        <div class="mt-3 max-w-md space-y-3 text-sm">
            <p v-if="loaded && !status.available" class="text-sem-fg-muted">
                Secure password storage is unavailable on this device.
            </p>
            <template v-if="status.available">
                <label class="flex flex-wrap items-center gap-2">
                    Password type
                    <select v-model="role" class="input-field">
                        <option value="member">Member / guest</option>
                        <option value="admin">Administrator</option>
                    </select>
                </label>
                <p class="text-xs text-sem-fg-muted">{{ saved ? "Saved on this device" : "No saved password" }}</p>
                <div v-if="!editing" class="flex flex-wrap gap-2">
                    <button
                        v-if="saved && canLogin"
                        type="button"
                        class="primary-chip"
                        :disabled="busy || disabled"
                        @click="$emit('use-saved', role)"
                    >
                        Use saved password
                    </button>
                    <button type="button" class="secondary-chip" :disabled="busy || disabled" @click="editing = true">
                        {{ saved ? "Replace" : "Save a password" }}
                    </button>
                    <button
                        v-if="saved"
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || disabled"
                        @click="perform('forget')"
                    >
                        Forget
                    </button>
                </div>
                <div v-else class="space-y-2">
                    <label class="block">
                        New saved password
                        <input
                            v-model="password"
                            type="password"
                            autocomplete="off"
                            aria-label="Password to save securely"
                            class="input-field mt-1 w-full"
                            :disabled="busy || disabled"
                        />
                    </label>
                    <div class="flex flex-wrap gap-2">
                        <button
                            type="button"
                            class="primary-chip"
                            :disabled="busy || disabled || !password || bytes > 64"
                            @click="perform('save')"
                        >
                            Save securely
                        </button>
                        <button type="button" class="secondary-chip" :disabled="busy" @click="closeEditor">
                            Cancel
                        </button>
                    </div>
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
    radioId: { type: String, default: "" },
    defaultRole: { type: String, default: "member" },
    disabled: Boolean,
    canLogin: Boolean,
    refreshKey: { type: Number, default: 0 },
});
const emit = defineEmits(["use-saved", "available"]);
const role = ref(props.defaultRole),
    password = ref(""),
    editing = ref(false),
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
    try {
        const options = props.radioId ? [{ params: { radio: props.radioId } }] : [];
        const { data } = await window.api.post(apiPath(`/meshcore/node-password-${action}`), body, ...options);
        if (token !== generation) return;
        status.value = data.result;
        loaded.value = true;
        if (action === "save") closeEditor();
        emit("available", status.value.available);
    } catch {
        if (token === generation) problem.value = "Secure password storage could not complete this request.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
function closeEditor() {
    password.value = "";
    editing.value = false;
}
watch(role, closeEditor);
function opened(event) {
    expanded = event.target.open;
    if (expanded) perform();
    else closeEditor();
}
watch(
    () => props.refreshKey,
    () => {
        if (expanded) perform();
    }
);
watch(
    () => [props.owner, props.peer, props.radioId, props.defaultRole],
    () => {
        generation++;
        role.value = props.defaultRole;
        closeEditor();
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
