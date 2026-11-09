<!-- SPDX-License-Identifier: 0BSD -->

<template>
    <section class="space-y-2 rounded-lg border border-sem-border p-3" aria-label="Discovered contacts">
        <SearchInput v-model="search" placeholder="Search discovered contacts…" compact />
        <p v-if="error" class="text-sm text-sem-danger" role="alert">{{ error }}</p>
        <p v-else-if="loading && !rows.length" class="text-sm text-sem-fg-muted" role="status">Loading discoveries…</p>
        <p v-else-if="!rows.length" class="text-sm text-sem-fg-muted">No matching discovered contacts.</p>
        <ul v-if="rows.length" class="max-h-48 overflow-y-auto divide-y divide-sem-border">
            <li v-for="row in rows" :key="row.address" class="flex items-center gap-2 py-2">
                <div class="min-w-0 flex-1">
                    <p class="truncate text-sm font-medium text-sem-fg">{{ row.name }}</p>
                    <p class="truncate font-mono text-xs text-sem-fg-muted" :title="row.address">{{ row.address }}</p>
                </div>
                <button
                    type="button"
                    class="secondary-chip shrink-0"
                    :disabled="disabled || row.saved"
                    :aria-label="row.saved ? `${row.name} already saved` : `${actionLabel} ${row.name}`"
                    @click="$emit('select', row)"
                >
                    {{ row.saved ? "Saved" : actionLabel }}
                </button>
            </li>
        </ul>
        <div v-if="!meshcore && (hasMore || error)" class="flex gap-2">
            <button v-if="hasMore" type="button" class="secondary-chip" :disabled="loading" @click="loadMore">
                Load more
            </button>
            <button v-if="error" type="button" class="secondary-chip" :disabled="loading" @click="refresh">
                Retry
            </button>
        </div>
    </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import SearchInput from "../SearchInput.vue";
import { listAnnounces } from "../../js/api/announces";

const props = defineProps({
    aspect: { type: String, default: "lxmf.delivery" },
    meshcore: { type: Object, default: null },
    ownAddress: { type: String, default: "" },
    savedAddresses: { type: Array, default: () => [] },
    actionLabel: { type: String, default: "Use contact" },
    disabled: Boolean,
});
defineEmits(["select"]);

const pageSize = 25;
const search = ref("");
const announces = ref([]);
const loading = ref(false);
const hasMore = ref(false);
const error = ref("");
let offset = 0;
let request = null;

const rows = computed(() => {
    const saved = new Set(props.savedAddresses.filter(Boolean));
    const meshcore = props.meshcore;
    const query = search.value.trim().toLowerCase();
    if (meshcore) {
        for (const contact of meshcore.contacts || []) {
            if (contact.kind === 1 && contact.active !== 0 && contact.active !== false) saved.add(contact.peer);
        }
        return (meshcore.announces || [])
            .filter((row) => row.kind === 1 && /^[0-9a-f]{64}$/i.test(row.peer || "") && row.peer !== meshcore.owner)
            .filter((row) => `${row.name || ""} ${row.peer}`.toLowerCase().includes(query))
            .map((row) => ({
                address: row.peer,
                name: meshcoreName(row.name),
                saved: row.saved || saved.has(row.peer),
            }));
    }
    const unique = new Map();
    for (const row of announces.value) {
        const address = row.destination_hash;
        if (!/^[0-9a-f]{32}$/i.test(address || "") || address === props.ownAddress) continue;
        if (props.aspect === "lxst.telephony" && !/^[0-9a-f]{32}$/i.test(row.identity_hash || "")) continue;
        if (!unique.has(address)) {
            unique.set(address, {
                address,
                name: row.display_name?.trim() || `Contact ${address.slice(0, 8)}`,
                identityHash: row.identity_hash,
                lxmfAddress: row.lxmf_destination_hash,
                saved: saved.has(address) || saved.has(row.identity_hash),
            });
        }
    }
    return [...unique.values()];
});

function meshcoreName(value) {
    const encoder = new TextEncoder();
    let name = "";
    for (const character of value?.trim() || "MeshCore contact") {
        if (encoder.encode(name + character).length > 31) break;
        name += character;
    }
    return name.trim() || "MeshCore contact";
}

async function loadMore() {
    if (loading.value || props.meshcore) return;
    const current = new AbortController();
    request = current;
    loading.value = true;
    error.value = "";
    try {
        const { data } = await listAnnounces({
            params: { aspect: props.aspect, limit: pageSize, offset, search: search.value.trim() },
            signal: current.signal,
        });
        if (current.signal.aborted) return;
        const page = data.announces || [];
        announces.value = [...announces.value, ...page];
        offset += page.length;
        hasMore.value = page.length === pageSize;
    } catch {
        if (!current.signal.aborted) error.value = "Could not load discovered contacts.";
    } finally {
        if (!current.signal.aborted) loading.value = false;
    }
}

function refresh() {
    request?.abort();
    announces.value = [];
    offset = 0;
    hasMore.value = false;
    loading.value = false;
    if (!props.meshcore) void loadMore();
}

watch(
    [search, () => props.aspect, () => Boolean(props.meshcore)],
    ([query, , meshcore], _previous, onCleanup) => {
        request?.abort();
        if (meshcore) return;
        const timer = setTimeout(refresh, query ? 200 : 0);
        onCleanup(() => {
            clearTimeout(timer);
            request?.abort();
        });
    },
    { immediate: true }
);
</script>
