<template>
    <label class="text-xs block"
        >Channel scope
        <select
            class="input-field"
            aria-label="MeshCore channel scope"
            :value="channel.scope ?? 'default'"
            :disabled="disabled"
            @change="$emit('change', $event.target.value === 'default' ? null : $event.target.value)"
        >
            <option value="default">{{ defaultScope ? `Channel default · ${defaultScope}` : "Radio default" }}</option>
            <option value="*">Unscoped</option>
            <option v-for="region in choices" :key="region" :value="region">{{ region }}</option>
        </select>
        <RouterLink
            class="block mt-1 text-sem-accent"
            :to="{
                name: 'meshcore-tools',
                params: { tool: 'regions' },
                query: { scan: '1', channel: channel.channel_id },
            }"
            >Find regions</RouterLink
        >
    </label>
</template>
<script setup>
import { computed } from "vue";
const props = defineProps({
    channel: { type: Object, required: true },
    regions: { type: Array, default: () => [] },
    defaultScope: { type: String, default: "" },
    disabled: Boolean,
});
defineEmits(["change"]);
const choices = computed(() => [
    ...new Set([
        ...props.regions,
        ...(props.channel.scope && props.channel.scope !== "*" ? [props.channel.scope] : []),
    ]),
]);
</script>
