<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <div class="text-xs mt-1" @click.stop>
        <div v-for="row in linked" :key="row.id" class="flex flex-wrap gap-2 items-center">
            <span class="text-sem-fg-muted">SIP · {{ row.address }}</span
            ><button class="text-sem-accent" type="button" @click="$router.push(sipCallRoute(row.address))">
                Call via SIP</button
            ><button type="button" class="text-sem-fg-muted" @click="unlink(row)">Unlink SIP</button>
        </div>
        <button v-if="!choosing" type="button" class="text-sem-fg-muted hover:text-sem-accent" @click="choosing = true">
            Link SIP contact…
        </button>
        <form v-else class="flex flex-wrap gap-2" @submit.prevent="link">
            <select
                v-model="selected"
                class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent"
                aria-label="SIP contact to link"
            >
                <option value="">Choose SIP contact</option>
                <option v-for="row in unlinked" :key="row.id" :value="row.id">
                    {{ row.name }} · {{ row.address }}
                </option></select
            ><button type="submit" :disabled="!selected" class="secondary-chip">Link</button
            ><button type="button" @click="choosing = false">Cancel</button
            ><span v-if="!unlinked.length" class="text-sem-fg-muted">Add a SIP contact above first.</span
            ><span v-if="error" role="alert">{{ error }}</span>
        </form>
    </div>
</template>
<script setup>
import { computed, ref } from "vue";
import { sipContacts, sipContactKey, saveSipContact, sipCallRoute } from "../../js/sip";
const props = defineProps({ contact: { type: Object, required: true } });
const choosing = ref(false),
    selected = ref(""),
    error = ref("");
const key = computed(() => sipContactKey(props.contact));
const linked = computed(() => sipContacts.filter((c) => c.linked_contact === key.value));
const unlinked = computed(() => sipContacts.filter((c) => !c.linked_contact));
function link() {
    try {
        const row = unlinked.value.find((c) => c.id === selected.value);
        if (row) saveSipContact({ ...row, linked_contact: key.value });
        choosing.value = false;
    } catch (e) {
        error.value = e.message;
    }
}
function unlink(row) {
    try {
        saveSipContact({ ...row, linked_contact: "" });
    } catch (e) {
        error.value = e.message;
    }
}
</script>
