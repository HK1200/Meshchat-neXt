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
        <details class="rounded-lg border border-sem-border p-3">
            <summary class="cursor-pointer font-semibold text-sm">HOIP live phonebook · online directory</summary>
            <div class="pt-3 space-y-2 text-sm">
                <p>Find HOIP extensions by callsign, name or location, and check their advertised availability.</p>
                <a
                    href="https://helpdesk.hamsoverip.com/phonebook/"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="primary-chip inline-flex"
                    >Open HOIP phonebook</a
                >
                <p class="text-xs text-sem-fg-muted">
                    Opens in your browser using its connection. Wi-Fi or mobile internet is required. I2P-only access
                    requires a browser configured with an HTTPS outproxy; this is a public internet website.
                </p>
                <p class="text-xs text-sem-fg-muted">
                    To keep an entry here, copy its extension, then choose Add SIP contact. Calls use your selected SIP
                    account; Reticulum and MeshCore contacts remain separate.
                </p>
            </div>
        </details>
        <input
            v-model="search"
            class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent"
            aria-label="Search SIP contacts"
            placeholder="Search SIP contacts"
        />
        <div class="flex items-center justify-between gap-2 text-xs text-sem-fg-muted" role="status">
            <span>Showing {{ filtered.length }} of {{ sipContacts.length }} SIP contacts</span>
            <button v-if="search" type="button" class="secondary-chip" @click="search = ''">Clear SIP search</button>
        </div>
        <div
            v-for="contact in filtered"
            :key="contact.id"
            class="flex items-center gap-2 border-b border-sem-border py-2"
        >
            <div class="min-w-0 flex-1">
                <div class="font-medium text-sem-fg">
                    {{ contact.name }} <span class="text-xs text-sem-fg-muted">SIP</span>
                </div>
                <div
                    v-for="(number, index) in sipContactNumbers(contact)"
                    :key="index"
                    class="flex items-center gap-2 py-1"
                >
                    <span class="text-xs text-sem-fg-muted break-all flex-1"
                        >{{ number.label }} · {{ number.address }}</span
                    >
                    <button
                        type="button"
                        class="secondary-chip min-h-11"
                        :aria-label="`Call ${contact.name} ${number.label} ${number.address}`"
                        @click="$router.push(sipCallRoute(number.address))"
                    >
                        Call via SIP
                    </button>
                </div>
            </div>
            <button type="button" class="secondary-chip" :aria-label="`Edit ${contact.name}`" @click="edit(contact)">
                Edit
            </button>
        </div>
        <p v-if="!filtered.length" class="text-sm text-sem-fg-muted">
            {{
                sipContacts.length
                    ? "No SIP contacts match this search. Clear the search to show all saved entries."
                    : "No SIP contacts yet."
            }}
        </p>
        <SipContactEditor :contact="form" @close="form = null" @saved="form = null" />
    </section>
</template>
<script setup>
import { computed, ref } from "vue";
import SipContactEditor from "./SipContactEditor.vue";
import { sipContacts, sipContactNumbers, sipCallRoute } from "../../js/sip";
const search = ref(""),
    form = ref(null);
const filtered = computed(() =>
    [...sipContacts]
        .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id))
        .filter((c) =>
            `${c.name} ${sipContactNumbers(c)
                .map((n) => `${n.label} ${n.address}`)
                .join(" ")}`
                .toLowerCase()
                .includes(search.value.toLowerCase())
        )
);
function edit(c) {
    form.value = c ? { ...c, numbers: sipContactNumbers(c) } : { name: "", numbers: [{ label: "Home", address: "" }] };
}
</script>
