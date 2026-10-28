<template>
    <div v-if="snapshot.available" class="mt-1 space-y-1 text-xs">
        <div v-if="contact.meshcore_key" class="space-y-1">
            <div class="flex items-center gap-1.5 min-w-0 text-sem-fg-muted">
                <MaterialDesignIcon icon-name="radio-handheld" class="size-4 text-sem-info shrink-0" />
                <span class="shrink-0">MeshCore</span>
                <span class="font-mono truncate" :title="contact.meshcore_key">{{ contact.meshcore_key }}</span>
            </div>
            <button
                type="button"
                class="text-sem-accent"
                @click="$router.push(meshcoreRoute(contact.meshcore_key, snapshot.radio_id))"
            >
                Message via MeshCore
            </button>
        </div>
        <details v-if="appFeatures.reticulum && !contact.meshcore_only" class="text-sem-fg-muted">
            <summary class="cursor-pointer">
                {{ contact.meshcore_key ? "Manage MeshCore link" : "Link a MeshCore contact…" }}
            </summary>
            <p class="py-1">Only link these addresses if you know they belong to the same person.</p>
            <label class="block"
                >MeshCore contact<select v-model="selected" class="input-field">
                    <option value="">Choose a contact</option>
                    <option v-for="peer in choices" :key="peer.peer" :value="peer.peer">
                        {{ peer.name }} · {{ peer.peer.slice(0, 12) }}…
                    </option>
                </select></label
            >
            <div class="flex gap-2 pt-1">
                <button type="button" class="secondary-chip" :disabled="!selected || busy" @click="link(selected)">
                    Link selected contact</button
                ><button
                    v-if="contact.meshcore_key"
                    type="button"
                    class="secondary-chip"
                    :disabled="busy"
                    @click="link(null)"
                >
                    Unlink
                </button>
            </div>
        </details>
        <button
            v-if="appFeatures.reticulum && contact.meshcore_only && linkedContact"
            type="button"
            class="text-sem-fg-muted"
            :disabled="busy"
            @click="link(null, linkedContact.contact)"
        >
            Unlink Reticulum contact
        </button>
        <p v-if="error" role="alert" class="text-sem-danger">{{ error }}</p>
    </div>
</template>
<script setup>
import { appFeatures } from "../../js/appFeatures";
import { computed, ref, watch } from "vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import { meshcoreRoute } from "../../js/meshcoreUi";
import { apiPath } from "../../js/constants";
const props = defineProps({ contact: { type: Object, required: true }, snapshot: { type: Object, required: true } });
const emit = defineEmits(["changed"]);
const selected = ref(""),
    busy = ref(false),
    error = ref("");
const choices = computed(() =>
    props.snapshot.contacts.filter(
        (peer) => !props.snapshot.links.some((link) => link.peer === peer.peer && link.contact !== props.contact.id)
    )
);
const linkedContact = computed(() => props.snapshot.links.find((link) => link.peer === props.contact.meshcore_key));
watch([() => props.snapshot.owner, () => props.snapshot.account], () => {
    selected.value = "";
    error.value = "";
});
async function link(peer, contactId = props.contact.id) {
    busy.value = true;
    error.value = "";
    try {
        await window.api.post(apiPath("/meshcore/contact-link"), {
            contact: contactId,
            peer,
            expected_owner: props.snapshot.owner,
        });
        emit("changed");
        selected.value = "";
    } catch {
        error.value = "The contact could not be linked. Refresh and try again.";
    } finally {
        busy.value = false;
    }
}
</script>
