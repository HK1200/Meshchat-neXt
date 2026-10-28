<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <section
        role="dialog"
        aria-label="Map node details"
        data-map-node-details
        data-app-back-scope
        class="absolute bottom-3 left-3 right-3 z-50 sm:right-auto sm:w-96 max-w-[calc(100%_-_1.5rem)] max-h-[min(32rem,calc(100dvh_-_9rem))] min-h-0 flex flex-col overflow-hidden rounded-xl border-2 border-sem-border bg-sem-surface text-sem-fg shadow-2xl"
        @app-back.stop="$emit('close')"
        @keydown.esc.stop.prevent="$emit('close')"
        @pointerdown.stop
        @contextmenu.stop
    >
        <header class="flex items-start justify-between gap-3 p-3 border-b border-sem-border shrink-0">
            <div class="min-w-0">
                <h3 class="font-semibold break-words">{{ current.title }}</h3>
                <p class="text-xs text-sem-fg-muted">{{ current.source }} · reported information</p>
            </div>
            <button
                ref="closeButton"
                type="button"
                class="secondary-chip shrink-0 min-h-11 min-w-11"
                aria-label="Close node details"
                @click="$emit('close')"
            >
                Close
            </button>
        </header>
        <div class="min-h-0 overflow-y-auto overscroll-contain p-3 space-y-3">
            <label v-if="items.length > 1" class="block text-sm">
                Nodes at this point ({{ items.length }})
                <select v-model.number="selected" class="input-field mt-1">
                    <option v-for="(item, index) in items" :key="index" :value="index">
                        {{ item.title }} · {{ item.source }}
                    </option>
                </select>
            </label>
            <dl class="space-y-2 text-sm">
                <div v-for="row in current.rows" :key="row.label">
                    <dt class="text-xs text-sem-fg-muted">{{ row.label }}</dt>
                    <dd class="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">{{ row.value }}</dd>
                </div>
            </dl>
            <p v-if="!current.rows.length" class="text-sm text-sem-fg-muted">
                No additional information has been reported for this point.
            </p>
        </div>
    </section>
</template>
<script setup>
import { computed, ref, onMounted, watch } from "vue";
const props = defineProps({ items: { type: Array, required: true } });
defineEmits(["close"]);
const selected = ref(0),
    closeButton = ref(null);
const current = computed(
    () => props.items[selected.value] || props.items[0] || { title: "Map point", source: "Map", rows: [] }
);
watch(
    () => props.items,
    () => {
        selected.value = 0;
    }
);
onMounted(() => closeButton.value?.focus({ preventScroll: true }));
</script>
