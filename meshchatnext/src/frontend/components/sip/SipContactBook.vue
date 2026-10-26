<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <section class="py-3 space-y-3" aria-label="SIP contacts">
        <div class="flex items-center justify-between gap-2">
            <h2 class="font-semibold text-sem-fg">SIP contacts</h2>
            <button type="button" class="secondary-chip" @click="edit(null)">Add SIP contact</button>
        </div>
        <p class="text-xs text-sem-fg-muted">
            Extensions and SIP addresses · contacts are linked only when you choose.
        </p>
        <input
            v-model="search"
            class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent"
            aria-label="Search SIP contacts"
            placeholder="Search SIP contacts"
        />
        <div
            v-for="contact in filtered"
            :key="contact.id"
            class="flex items-center gap-2 border-b border-sem-border py-2"
        >
            <div class="min-w-0 flex-1">
                <div class="font-medium text-sem-fg">
                    {{ contact.name }} <span class="text-xs text-sem-fg-muted">SIP</span>
                </div>
                <div class="text-xs text-sem-fg-muted break-all">{{ contact.address }}</div>
            </div>
            <button type="button" class="secondary-chip" @click="$router.push(sipCallRoute(contact.address))">
                Call via SIP
            </button>
            <button type="button" class="secondary-chip" :aria-label="`Edit ${contact.name}`" @click="edit(contact)">
                Edit
            </button>
        </div>
        <p v-if="!filtered.length" class="text-sm text-sem-fg-muted">No SIP contacts yet.</p>
        <form v-if="form" class="border border-sem-border rounded-lg p-3 space-y-3" @submit.prevent="save">
            <label class="block text-sm"
                >Name<input
                    v-model="form.name"
                    class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                    maxlength="100"
                    required
            /></label>
            <label class="block text-sm"
                >SIP extension or address<input
                    v-model="form.address"
                    class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                    placeholder="Extension or sip:user@server"
                    required
            /></label>
            <p v-if="error" role="alert" class="text-sem-danger text-sm">{{ error }}</p>
            <div class="flex gap-2 flex-wrap">
                <button class="primary-chip" type="submit">Save contact</button
                ><button class="secondary-chip" type="button" @click="form = null">Cancel</button
                ><button v-if="form.id" class="secondary-chip text-sem-danger" type="button" @click="remove">
                    Delete SIP contact
                </button>
            </div>
        </form>
    </section>
</template>
<script setup>
import { computed, ref } from "vue";
import { sipContacts, saveSipContact, deleteSipContact, sipCallRoute } from "../../js/sip";
const search = ref(""),
    form = ref(null),
    error = ref("");
const filtered = computed(() =>
    sipContacts.filter((c) => `${c.name} ${c.address}`.toLowerCase().includes(search.value.toLowerCase()))
);
function edit(c) {
    error.value = "";
    form.value = c ? { ...c } : { name: "", address: "" };
}
function save() {
    try {
        saveSipContact(form.value);
        form.value = null;
    } catch (e) {
        error.value = e.message;
    }
}
function remove() {
    deleteSipContact(form.value.id);
    form.value = null;
}
</script>
