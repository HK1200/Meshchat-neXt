<template>
    <section class="space-y-2" aria-label="MeshCore message contacts">
        <p v-if="snapshot.radio_label" class="text-xs text-sem-fg-muted">
            Radio: {{ snapshot.radio_label }}{{ snapshot.connected ? "" : " · Disconnected" }}
        </p>
        <button
            v-if="snapshot.available"
            type="button"
            class="secondary-chip"
            :aria-expanded="showDiscovery"
            @click="showDiscovery = !showDiscovery"
        >
            {{ showDiscovery ? "Saved contacts" : "Discover contacts" }}
        </button>
        <p v-if="error || addError" role="alert" class="text-sm text-sem-danger">{{ addError || error }}</p>
        <p v-if="savedNotice" role="status" class="text-sm text-sem-fg-muted">{{ savedNotice }}</p>
        <template v-if="showDiscovery && snapshot.available">
            <p v-if="!snapshot.connected" class="text-xs text-sem-fg-muted">
                Connect the radio to save a discovered contact.
            </p>
            <DiscoveredContacts
                :meshcore="snapshot"
                :disabled="busy || !snapshot.connected"
                action-label="Add contact"
                @select="addDiscovered"
            />
        </template>
        <template v-else>
            <SearchInput v-model="search" placeholder="Search MeshCore contacts…" />
            <p v-if="!snapshot.available" class="text-sm text-sem-fg-muted">
                Saved contacts appear here when MeshCore is available.
            </p>
            <p v-else-if="!contacts.length" class="text-sm text-sem-fg-muted">
                {{ search.trim() ? "No matching MeshCore contacts." : "No saved MeshCore contacts on this radio." }}
            </p>
            <ul v-else class="max-h-56 overflow-y-auto divide-y divide-sem-border">
                <li v-for="contact in contacts" :key="contact.peer">
                    <RouterLink
                        :to="meshcoreRoute(contact.peer, snapshot.radio_id)"
                        class="block rounded-lg p-2 hover:bg-sem-surface-muted focus-ring-sem"
                        @click="$emit('selected')"
                    >
                        <span class="block font-medium break-words">{{
                            contact.name || contact.peer.slice(0, 12)
                        }}</span>
                        <span class="block text-xs font-mono text-sem-fg-muted break-all">{{ contact.peer }}</span>
                    </RouterLink>
                </li>
            </ul>
        </template>
    </section>
</template>
<script setup>
import { computed, ref } from "vue";
import DiscoveredContacts from "../contacts/DiscoveredContacts.vue";
import SearchInput from "../SearchInput.vue";
import { meshcoreRoute, useMeshCoreUi } from "../../js/meshcoreUi";

defineEmits(["selected"]);
const { snapshot, error, action } = useMeshCoreUi();
const search = ref("");
const showDiscovery = ref(false);
const busy = ref(false);
const addError = ref("");
const savedNotice = ref("");

async function addDiscovered(contact) {
    if (busy.value || !snapshot.value.connected) return;
    busy.value = true;
    addError.value = "";
    savedNotice.value = "";
    try {
        await action("contact-add", { peer: contact.address, name: contact.name });
        savedNotice.value = `${contact.name} added to MeshCore contacts.`;
        search.value = "";
        showDiscovery.value = false;
    } catch {
        addError.value = "Could not add the MeshCore contact. Check the radio connection and try again.";
    } finally {
        busy.value = false;
    }
}
const contacts = computed(() => {
    const query = search.value.trim().toLowerCase();
    if (!snapshot.value.available) return [];
    return snapshot.value.contacts
        .filter(
            (contact) =>
                contact.kind === 1 &&
                contact.active !== 0 &&
                contact.active !== false &&
                /^[0-9a-f]{64}$/i.test(contact.peer || "") &&
                `${contact.name || ""} ${contact.peer}`.toLowerCase().includes(query)
        )
        .sort((a, b) => (a.name || a.peer).localeCompare(b.name || b.peer));
});
</script>
