<template>
    <div v-if="compact && snapshot.available" class="space-y-1 border-b border-sem-border pb-1">
        <button
            v-for="row in visible"
            :key="`${row.radio_id || 'default'}:${row.peer}`"
            type="button"
            class="w-11 rounded-lg border border-sem-border p-1 text-xs text-sem-fg"
            :title="`${row.name || row.peer} · MeshCore${row.radio_label ? ' · ' + row.radio_label : ''}`"
            :aria-label="`${row.name || row.peer} · MeshCore${row.radio_label ? ' · ' + row.radio_label : ''}${row.unread ? ' · unread' : ''}`"
            @click="$router.push(meshcoreRoute(row.peer, row.radio_id))"
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
            <strong>MeshCore</strong
            ><span>{{
                snapshot.radios?.length > 1
                    ? `Connected radios: ${snapshot.radios.filter((radio) => radio.connected).length}`
                    : snapshot.connected
                      ? "Connected"
                      : "Disconnected"
            }}</span>
        </div>
        <label
            v-if="snapshot.inbox_mode === 'separate' && snapshot.radios?.length > 1"
            class="block text-xs text-sem-fg-muted"
        >
            Radio view
            <select
                class="input-field"
                aria-label="MeshCore radio view"
                :value="snapshot.radio_id"
                @change="action('radio-configure', { active: $event.target.value })"
            >
                <option v-for="radio in snapshot.radios" :key="radio.id" :value="radio.id">{{ radio.label }}</option>
            </select>
        </label>
        <p v-if="error" role="alert" class="text-xs text-sem-danger">{{ error }}</p>
        <button
            v-for="row in visible"
            :key="`${row.radio_id || 'default'}:${row.peer}`"
            type="button"
            class="w-full text-left rounded-lg p-2 transition-colors text-sem-fg"
            :class="
                $route.query.meshcore === row.peer &&
                (!row.radio_id || ($route.query.meshcoreRadio || snapshot.radio_id) === row.radio_id)
                    ? 'bg-sem-surface-muted ring-1 ring-sem-border'
                    : 'hover:bg-sem-surface-muted'
            "
            :aria-current="
                $route.query.meshcore === row.peer &&
                (!row.radio_id || ($route.query.meshcoreRadio || snapshot.radio_id) === row.radio_id)
                    ? 'page'
                    : undefined
            "
            @click="$router.push(meshcoreRoute(row.peer, row.radio_id))"
        >
            <div class="flex gap-2 items-center">
                <LxmfUserIcon icon-class="size-8 shrink-0" />
                <span class="truncate flex-1"
                    >{{ row.name || row.peer.slice(0, 12) }}
                    <small v-if="snapshot.radios?.length > 1" class="block text-xs text-sem-fg-muted">{{
                        row.radio_label
                    }}</small></span
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
const { snapshot, error, action } = useMeshCoreUi();
const visible = computed(() =>
    snapshot.value.conversations.filter(
        (row) =>
            (!props.unreadOnly || row.unread) &&
            `${row.name} ${row.peer} ${row.text}`.toLowerCase().includes(props.search.toLowerCase())
    )
);
</script>
