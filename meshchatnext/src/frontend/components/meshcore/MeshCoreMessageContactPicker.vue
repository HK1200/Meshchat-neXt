<template>
    <section class="space-y-2" aria-label="MeshCore message contacts">
        <p v-if="snapshot.radio_label" class="text-xs text-sem-fg-muted">
            Radio: {{ snapshot.radio_label }}{{ snapshot.connected ? "" : " · Disconnected" }}
        </p>
        <SearchInput v-model="search" placeholder="Search MeshCore contacts…" />
        <p v-if="error" role="alert" class="text-sm text-sem-danger">{{ error }}</p>
        <p v-else-if="!snapshot.available" class="text-sm text-sem-fg-muted">
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
                    <span class="block font-medium break-words">{{ contact.name || contact.peer.slice(0, 12) }}</span>
                    <span class="block text-xs font-mono text-sem-fg-muted break-all">{{ contact.peer }}</span>
                </RouterLink>
            </li>
        </ul>
    </section>
</template>
<script setup>
import { computed, ref } from "vue";
import SearchInput from "../SearchInput.vue";
import { meshcoreRoute, useMeshCoreUi } from "../../js/meshcoreUi";

defineEmits(["selected"]);
const { snapshot, error } = useMeshCoreUi();
const search = ref("");
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
