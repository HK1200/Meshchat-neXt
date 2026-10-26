<template>
    <div class="min-w-0 flex-1">
        <button
            type="button"
            class="sidebar-nav-link items-center focus-visible:outline-sem-focus"
            :class="[
                collapsed ? 'justify-center rounded-none' : 'rounded-r-full mr-2',
                inSettings ? 'sidebar-nav-link--active' : 'sidebar-nav-link--hover',
            ]"
            :aria-label="label"
            :aria-expanded="expanded"
            :title="label"
            @click="toggle"
        >
            <MaterialDesignIcon :icon-name="icon" class="w-6 h-6 shrink-0 text-sem-fg-secondary" />
            <span v-if="!collapsed" class="flex-1 text-left truncate">{{ label }}</span>
            <MaterialDesignIcon
                v-if="!collapsed"
                :icon-name="expanded ? 'chevron-down' : 'chevron-right'"
                class="size-4 shrink-0 text-sem-fg-muted"
            />
        </button>
        <ul v-if="expanded && !editing" class="space-y-1 py-1" aria-label="Settings networks">
            <li v-for="network in networks" :key="network.name">
                <RouterLink
                    :to="{ name: network.route }"
                    class="flex items-center gap-2 py-2 rounded-lg text-sm text-sem-fg-muted hover:bg-sem-surface-muted"
                    :class="collapsed ? 'justify-center' : 'pl-10 pr-3'"
                    active-class="text-sem-accent bg-sem-surface-muted"
                    :aria-label="`${network.name} settings`"
                    :title="`Settings → ${network.name}`"
                >
                    <MaterialDesignIcon :icon-name="network.icon" class="size-4 shrink-0" /><span v-if="!collapsed">{{
                        network.name
                    }}</span
                    ><span v-else class="text-[9px]">{{ network.short }}</span>
                </RouterLink>
            </li>
        </ul>
    </div>
</template>
<script setup>
import { appFeatures } from "../../js/appFeatures";
import { computed, inject, ref, watch } from "vue";
import { routerKey } from "vue-router";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
const props = defineProps({
    collapsed: Boolean,
    editing: Boolean,
    label: { type: String, default: "Settings" },
    icon: { type: String, default: "cog" },
});
const router = inject(routerKey, null);
const expanded = ref(false);
const inSettings = computed(() =>
    ["settings", "meshcore-settings", "feature-settings", "sip-settings"].includes(router?.currentRoute.value.name)
);
const networks = computed(() =>
    [
        { name: "App features", short: "F", route: "feature-settings", icon: "toggle-switch" },
        { name: "Reticulum", short: "R", route: "settings", icon: "access-point-network" },
        { name: "MeshCore", short: "M", route: "meshcore-settings", icon: "radio-handheld" },
        { name: "SIP", short: "S", route: "sip-settings", icon: "phone" },
    ].filter(
        (network) =>
            network.route === "feature-settings" ||
            (network.route === "settings"
                ? appFeatures.reticulum
                : network.route === "sip-settings"
                  ? appFeatures.sip
                  : appFeatures.meshcore)
    )
);
watch(
    () => router?.currentRoute.value.name,
    () => {
        if (inSettings.value) expanded.value = true;
    },
    { immediate: true }
);
function toggle() {
    if (!props.editing) expanded.value = !expanded.value;
}
</script>
