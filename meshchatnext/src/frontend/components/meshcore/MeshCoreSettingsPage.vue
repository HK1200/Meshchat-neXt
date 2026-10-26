<template>
    <section
        class="flex-1 min-w-0 h-full overflow-y-auto bg-sem-canvas text-sem-fg p-4 md:p-6"
        aria-label="MeshCore settings"
    >
        <div class="max-w-4xl mx-auto space-y-5">
            <header class="border-b border-sem-border pb-4">
                <RouterLink
                    data-app-back
                    :to="{ name: 'settings' }"
                    class="text-xs text-sem-fg-muted hover:text-sem-accent"
                    >Settings</RouterLink
                >
                <h1 class="text-2xl font-bold mt-2">MeshCore settings</h1>
                <p class="text-sm text-sem-fg-muted">MeshCore radio, identity, and backups</p>
            </header>
            <MeshCoreSettings />
        </div>
    </section>
</template>
<script setup>
import { nextTick, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import MeshCoreSettings from "./MeshCoreSettings.vue";
const route = useRoute();
async function focusSection() {
    if (!["radio2", "backups"].includes(route.query.section)) return;
    await nextTick();
    const element = document.getElementById(`meshcore-${route.query.section}`);
    if (element?.tagName === "DETAILS") element.open = true;
    element?.scrollIntoView({ block: "start" });
}
onMounted(focusSection);
watch(() => route.query.section, focusSection);
</script>
