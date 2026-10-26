<template>
    <div v-if="compact && snapshot.available" class="space-y-1 border-b border-sem-border pb-1">
        <button
            v-for="row in visible"
            :key="row.peer"
            type="button"
            class="w-11 rounded-lg border border-sem-border p-1 text-xs text-sem-fg"
            :title="`${row.name || row.peer} · MeshCore`"
            :aria-label="`${row.name || row.peer} · MeshCore${row.unread ? ' · unread' : ''}`"
            @click="$router.push(meshcoreRoute(row.peer))"
        >
            <span class="block">{{ (row.name || row.peer).slice(0, 2) }}</span
            ><span class="text-[9px]">MC{{ row.unread ? " · " + row.unread : "" }}</span>
        </button>
    </div>
    <section
        v-else-if="snapshot.available"
        class="border-b border-sem-border p-2 space-y-1"
        aria-label="MeshCore conversations"
    >
        <div class="flex items-center justify-between text-xs text-sem-fg-muted">
            <strong>MeshCore</strong><span>{{ snapshot.connected ? "Connected" : "Disconnected" }}</span>
        </div>
        <p v-if="error" role="alert" class="text-xs text-sem-danger">{{ error }}</p>
        <button
            v-for="row in visible"
            :key="row.peer"
            type="button"
            class="w-full text-left rounded-lg p-2 transition-colors text-sem-fg"
            :class="
                $route.query.meshcore === row.peer
                    ? 'bg-sem-surface-muted ring-1 ring-sem-border'
                    : 'hover:bg-sem-surface-muted'
            "
            :aria-current="$route.query.meshcore === row.peer ? 'page' : undefined"
            @click="$router.push(meshcoreRoute(row.peer))"
        >
            <div class="flex gap-2 items-center">
                <LxmfUserIcon icon-class="size-8 shrink-0" />
                <span class="truncate flex-1">{{ row.name || row.peer.slice(0, 12) }}</span
                ><span class="text-[10px] font-medium border border-sem-border rounded-full px-1.5 text-sem-fg-muted"
                    >MeshCore</span
                ><span v-if="row.unread" class="text-xs font-bold text-sem-accent">{{ row.unread }} unread</span>
            </div>
            <p class="text-xs text-sem-fg-muted truncate">{{ voicePreview(row.text) }}</p>
        </button>
        <div class="pt-2 text-xs text-sem-fg-muted font-semibold">Reticulum</div>
    </section>
</template>
<script setup>
import { voicePreview } from "../../js/meshcoreVoice";
import { computed } from "vue";
import LxmfUserIcon from "../LxmfUserIcon.vue";
import { useMeshCoreUi, meshcoreRoute } from "../../js/meshcoreUi";
const props = defineProps({ search: { type: String, default: "" }, unreadOnly: Boolean, compact: Boolean });
const { snapshot, error } = useMeshCoreUi();
const visible = computed(() =>
    snapshot.value.conversations.filter(
        (row) =>
            (!props.unreadOnly || row.unread) &&
            `${row.name} ${row.peer} ${row.text}`.toLowerCase().includes(props.search.toLowerCase())
    )
);
</script>
