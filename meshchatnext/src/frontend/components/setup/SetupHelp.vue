<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <div class="space-y-2" aria-label="Setup option help">
        <details
            v-for="entry in SETUP_HELP[topic] || []"
            :key="entry[0]"
            class="rounded-xl border border-sem-border bg-sem-surface p-3"
        >
            <summary class="cursor-pointer text-sm font-medium">Help · {{ entry[0] }}</summary>
            <p class="pt-3 text-sm leading-relaxed text-sem-fg-muted">{{ entry[1] }}</p>
        </details>
    </div>
</template>
<script setup>
import { SETUP_HELP } from "../../js/setupHelp";
defineProps({ topic: { type: String, required: true } });
</script>
