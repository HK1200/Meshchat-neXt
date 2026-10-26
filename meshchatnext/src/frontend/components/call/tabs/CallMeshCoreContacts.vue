<template>
    <section
        class="flex-1 flex flex-col max-w-3xl mx-auto w-full pt-2 space-y-4"
        aria-label="MeshCore telephone contacts"
    >
        <p class="text-sm text-sem-fg-muted">
            MeshCore · {{ snapshot.connected ? "Connected" : "Disconnected · saved contacts" }}. MediaMesh supports
            recorded voice clips. Live MeshCore calls are not available in this app yet.
        </p>
        <div class="flex gap-2">
            <SearchInput v-model="search" class="flex-1" placeholder="Search MeshCore names or public keys…" />
            <button v-if="!discovery" type="button" class="primary-chip" @click="showAdd = !showAdd">
                Add MeshCore contact
            </button>
        </div>
        <form
            v-if="showAdd && !discovery"
            class="space-y-2 border border-sem-border rounded-lg p-3"
            @submit.prevent="addManual"
        >
            <label class="block text-sm"
                >Name<input v-model="name" class="input-field w-full" required aria-label="MeshCore contact name"
            /></label>
            <label class="block text-sm"
                >MeshCore public key<input
                    v-model="key"
                    class="input-field w-full font-mono"
                    required
                    pattern="[0-9a-fA-F]{64}"
                    aria-label="MeshCore contact public key"
            /></label>
            <p class="text-xs text-sem-fg-muted">
                Use the full 64-character MeshCore public key. This creates a separate MeshCore contact.
            </p>
            <button type="submit" class="primary-chip" :disabled="!snapshot.connected || busy">
                Save MeshCore contact
            </button>
        </form>
        <div v-if="!discovery" class="flex gap-2 text-sm" role="group" aria-label="MeshCore contact source">
            <button type="button" class="secondary-chip" :aria-pressed="!showDiscovery" @click="showDiscovery = false">
                Saved contacts
            </button>
            <button type="button" class="secondary-chip" :aria-pressed="showDiscovery" @click="showDiscovery = true">
                Add from announces
            </button>
        </div>
        <p v-if="error || problem" class="text-sm text-sem-danger" role="alert">{{ problem || error }}</p>
        <p v-if="!snapshot.available" class="text-sm text-sem-fg-muted">
            MeshCore is unavailable. Configure your radio in Settings → MeshCore.
        </p>
        <p v-else-if="!rows.length" class="text-sm text-sem-fg-muted">
            {{ discovery || showDiscovery ? "No matching MeshCore user announces." : "No matching MeshCore contacts." }}
        </p>
        <ul class="divide-y divide-sem-border">
            <li v-for="contact in rows" :key="contact.peer" class="py-3 space-y-1">
                <div class="flex items-center gap-2">
                    <strong class="truncate">{{ contact.name || contact.peer.slice(0, 12) }}</strong
                    ><span class="text-[10px] rounded-full border border-sem-border px-1.5 text-sem-fg-muted"
                        >MeshCore</span
                    >
                </div>
                <p class="font-mono text-xs text-sem-fg-muted break-all">{{ contact.peer }}</p>
                <p v-if="contact.heard || contact.advertised" class="text-xs text-sem-fg-muted">
                    Last announced {{ new Date((contact.heard || contact.advertised) * 1000).toLocaleString() }}
                </p>
                <button
                    v-if="!savedKeys.has(contact.peer)"
                    type="button"
                    class="secondary-chip"
                    :disabled="!snapshot.connected || !!busy"
                    @click="add(contact)"
                >
                    {{ busy === contact.peer ? "Adding…" : "Add MeshCore contact" }}
                </button>
                <RouterLink v-else :to="meshcoreRoute(contact.peer)" class="text-sm text-sem-accent"
                    >Message via MeshCore</RouterLink
                >
            </li>
        </ul>
    </section>
</template>
<script setup>
import { computed, ref } from "vue";
import SearchInput from "../../SearchInput.vue";
import { useMeshCoreUi, meshcoreRoute } from "../../../js/meshcoreUi";
const props = defineProps({ discovery: Boolean });
const { snapshot, error, action } = useMeshCoreUi();
const search = ref(""),
    showAdd = ref(false),
    showDiscovery = ref(false),
    name = ref(""),
    key = ref(""),
    busy = ref(""),
    problem = ref("");
const savedKeys = computed(
    () => new Set((snapshot.value.contacts || []).filter((c) => c.active !== 0).map((c) => c.peer))
);
const rows = computed(() =>
    (props.discovery || showDiscovery.value ? snapshot.value.announces || [] : snapshot.value.contacts || []).filter(
        (c) =>
            c.kind === 1 &&
            c.active !== 0 &&
            `${c.name || ""} ${c.peer}`.toLowerCase().includes(search.value.toLowerCase())
    )
);
async function add(contact) {
    if (busy.value || !snapshot.value.connected) return;
    problem.value = "";
    if (
        !/^[0-9a-f]{64}$/i.test(contact.peer || "") ||
        !contact.name?.trim() ||
        new TextEncoder().encode(contact.name.trim()).length > 31
    ) {
        problem.value = "Enter a full MeshCore public key and a name of 1–31 UTF-8 bytes.";
        return;
    }
    busy.value = contact.peer;
    try {
        await action("contact-add", { peer: contact.peer.toLowerCase(), name: contact.name.trim() });
        showAdd.value = false;
        name.value = "";
        key.value = "";
    } catch {
        problem.value = "Could not add the MeshCore contact. Check the connection and try again.";
    } finally {
        busy.value = "";
    }
}
function addManual() {
    return add({ peer: key.value.trim(), name: name.value.trim() });
}
</script>
