<!-- SPDX-License-Identifier: 0BSD -->

<template>
    <div v-click-outside="closeResults" class="relative">
        <div class="flex items-center bg-sem-surface rounded-xl shadow-2xl border-0 ring-0">
            <select
                v-if="nodeSearchEnabled"
                :value="scope"
                aria-label="Map search type"
                class="bg-sem-surface text-sem-fg text-xs min-h-11 max-w-24 rounded-l-xl"
                @change="$emit('update:scope', $event.target.value)"
            >
                <option value="nodes">MeshCore nodes</option>
                <option value="places">Places / coordinates</option>
            </select>
            <input
                ref="inputEl"
                :value="modelValue"
                type="text"
                class="min-w-0 flex-1 px-4 py-2.5 bg-transparent text-sem-fg placeholder-gray-400 focus:outline-hidden focus:ring-0 border-0 text-sm"
                :placeholder="
                    scope === 'nodes' && nodeSearchEnabled
                        ? 'Node name or key prefix'
                        : placeholder || $t('map.search_placeholder')
                "
                @input="onInput"
                @keydown.enter="$emit('search')"
                @focus="$emit('focus')"
            />
            <button
                v-if="modelValue"
                class="p-2 text-sem-fg-muted hover:text-sem-fg transition-colors"
                @click="$emit('clear')"
            >
                <MaterialDesignIcon icon-name="close" class="size-[18px]" />
            </button>
            <button
                class="p-2 mr-1 text-sem-info hover:text-sem-info disabled:text-sem-fg-secondary transition-colors"
                :disabled="!modelValue || searching"
                @click="$emit('search')"
            >
                <MaterialDesignIcon
                    :icon-name="searching ? 'loading' : 'magnify'"
                    :class="['size-5', { 'animate-spin': searching }]"
                />
            </button>
        </div>

        <div v-if="showResults && (results.length > 0 || error)" class="absolute top-full left-0 right-0 mt-2 z-40">
            <div
                class="dropdown-caret pointer-events-none absolute -top-[4px] right-9 border-t border-l border-sem-border"
                aria-hidden="true"
            ></div>
            <div class="bg-sem-surface rounded-xl shadow-2xl border border-sem-border overflow-y-auto max-h-64">
                <div v-if="error" class="p-4 text-sm text-sem-danger flex items-center gap-2">
                    <MaterialDesignIcon icon-name="alert-circle" class="size-4" />
                    {{ error }}
                </div>
                <button
                    v-for="(result, index) in results"
                    :key="index"
                    class="w-full px-4 py-3 text-left hover:bg-sem-surface-muted/50 border-b border-sem-border dark:border-sem-border last:border-b-0 transition-all"
                    @click="$emit('select', result)"
                >
                    <div class="font-bold text-sem-fg text-sm">{{ result.display_name }}</div>
                    <div v-if="result.node" class="font-mono text-xs break-all text-sem-fg-muted">
                        {{ result.node.peer }}
                    </div>
                    <div class="text-[10px] text-sem-fg-muted mt-0.5 font-bold uppercase tracking-wider">
                        {{ result.type }}
                    </div>
                </button>
            </div>
        </div>
    </div>
</template>

<script>
import MaterialDesignIcon from "../../MaterialDesignIcon.vue";

export default {
    name: "MapSearchBar",
    components: { MaterialDesignIcon },
    props: {
        scope: { type: String, default: "places" },
        nodeSearchEnabled: { type: Boolean, default: false },
        modelValue: { type: String, default: "" },
        results: { type: Array, default: () => [] },
        error: { type: String, default: null },
        searching: { type: Boolean, default: false },
        showResults: { type: Boolean, default: false },
        placeholder: { type: String, default: "" },
    },
    emits: ["update:scope", "update:modelValue", "input", "search", "clear", "focus", "blur", "select"],
    methods: {
        closeResults() {
            this.$emit("blur");
        },
        onInput(event) {
            this.$emit("update:modelValue", event.target.value);
            this.$emit("input", event);
        },
    },
};
</script>
