<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <div class="text-xs mt-1" @click.stop>
        <div v-for="row in linked" :key="row.id" class="space-y-1">
            <div
                v-for="(number, index) in sipContactNumbers(row)"
                :key="index"
                class="flex flex-wrap gap-2 items-center"
            >
                <span class="text-sem-fg-muted">SIP · {{ number.label }} · {{ number.address }}</span>
                <button class="text-sem-accent" type="button" @click="$router.push(sipCallRoute(number.address))">
                    Call via SIP
                </button>
            </div>
            <button v-if="editable" type="button" class="text-sem-fg-muted" @click="unlink(row)">Unlink SIP</button>
        </div>
        <template v-if="editable">
            <button type="button" class="secondary-chip min-h-11 mt-2" @click="addExtension">Add SIP extension</button>
            <SipContactEditor
                :contact="extensionForm"
                title="Add SIP extension"
                :allow-delete="false"
                @close="extensionForm = null"
                @saved="extensionForm = null"
            />
        </template>
        <template v-if="editable">
            <button
                v-if="!choosing"
                type="button"
                class="text-sem-fg-muted hover:text-sem-accent"
                @click="choosing = true"
            >
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
                        {{ row.name }} ·
                        {{
                            sipContactNumbers(row)
                                .map((n) => n.label + ": " + n.address)
                                .join(" · ")
                        }}
                    </option></select
                ><button type="submit" :disabled="!selected" class="secondary-chip">Link</button
                ><button type="button" @click="choosing = false">Cancel</button
                ><span v-if="!unlinked.length" class="text-sem-fg-muted">Add a SIP contact above first.</span
                ><span v-if="error" role="alert">{{ error }}</span>
            </form>
        </template>
    </div>
</template>
<script setup>
import { computed, ref } from "vue";
import SipContactEditor from "./SipContactEditor.vue";
import { sipContacts, sipContactNumbers, sipContactKey, saveSipContact, sipCallRoute } from "../../js/sip";
const props = defineProps({ contact: { type: Object, required: true }, editable: { type: Boolean, default: true } });
const choosing = ref(false),
    selected = ref(""),
    error = ref("");
const extensionForm = ref(null);
function addExtension() {
    error.value = "";
    if (linked.value.length === 1) {
        const existing = linked.value[0];
        if (sipContactNumbers(existing).length >= 12) {
            error.value = "This SIP contact already has 12 numbers. Edit its numbers in the SIP phonebook.";
            return;
        }
        extensionForm.value = {
            ...existing,
            numbers: [...sipContactNumbers(existing), { label: "Other", address: "" }],
        };
    } else {
        extensionForm.value = {
            name: props.contact.name || "",
            linked_contact: key.value,
            numbers: [{ label: "Home", address: "" }],
        };
    }
}
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
