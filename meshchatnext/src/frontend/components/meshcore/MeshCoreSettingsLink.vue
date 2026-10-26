<template>
    <RouterLink
        :to="{ name: 'meshcore-settings' }"
        class="flex items-center gap-2 py-2 rounded-lg text-sm text-sem-fg-muted hover:bg-sem-surface-muted"
        :class="collapsed ? 'justify-center' : 'pl-10 pr-3'"
        active-class="text-sem-accent bg-sem-surface-muted"
        title="Settings → MeshCore"
        aria-label="MeshCore settings"
    >
        <MaterialDesignIcon icon-name="radio-handheld" class="size-4 shrink-0" /><span v-if="!collapsed">MeshCore</span>
    </RouterLink>
</template>
<script setup>
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
defineProps({ collapsed: Boolean });
</script>
