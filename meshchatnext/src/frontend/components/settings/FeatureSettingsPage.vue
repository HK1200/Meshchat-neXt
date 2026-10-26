<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <div class="flex-1 overflow-y-auto bg-sem-canvas text-sem-fg p-4 md:p-6">
        <div class="max-w-3xl mx-auto space-y-4">
            <h1 class="text-2xl font-bold">App features</h1>
            <RouterLink :to="{ name: 'tutorial' }" class="inline-flex secondary-chip">Run setup guide</RouterLink>
            <p class="text-sm text-sem-fg-muted">
                Choose which networks appear in neXt on this device. Turning a feature off hides its menus, contacts and
                messaging or calling controls. Your saved accounts, contacts and messages are kept.
            </p>
            <div class="rounded-xl border border-sem-border bg-sem-surface divide-y divide-sem-border">
                <label v-for="feature in features" :key="feature.id" class="flex items-center gap-4 p-4 cursor-pointer">
                    <div class="flex-1">
                        <span class="font-semibold">{{ feature.label }}</span>
                        <p class="text-sm text-sem-fg-muted">{{ feature.description }}</p>
                    </div>
                    <input
                        type="checkbox"
                        role="switch"
                        :aria-label="feature.label"
                        :checked="appFeatures[feature.id]"
                        class="size-5 accent-sem-accent"
                        @change="change(feature.id, $event.target.checked)"
                    />
                </label>
            </div>
            <p class="text-xs text-sem-fg-muted">
                These choices control the app layout. Radio connections and background services have their own
                connection controls.
            </p>
            <div id="app-updates"><UpdatesSettingsSection /></div>
            <p v-if="error" role="alert" class="text-sem-danger">{{ error }}</p>
            <p v-else role="status" class="text-sm text-sem-fg-muted">{{ saved }}</p>
        </div>
    </div>
</template>
<script setup>
import { ref, nextTick, onMounted } from "vue";
import { useRoute } from "vue-router";
import UpdatesSettingsSection from "./sections/UpdatesSettingsSection.vue";
const route = useRoute();
onMounted(async () => {
    if (route?.query?.section === "updates") {
        await nextTick();
        document.getElementById("app-updates")?.scrollIntoView?.({ block: "start" });
    }
});
import { appFeatures, setAppFeature } from "../../js/appFeatures";
const error = ref(""),
    saved = ref("");
const features = [
    {
        id: "reticulum",
        label: "Reticulum",
        description: "Reticulum messages, LXST calls, announces, interfaces and tools.",
    },
    {
        id: "meshcore",
        label: "MeshCore",
        description: "MeshCore direct messages, channels, nodes, Radio2 and tactical tools.",
    },
    { id: "sip", label: "SIP", description: "SIP accounts, extension contacts and calls." },
];
function change(name, enabled) {
    try {
        setAppFeature(name, enabled);
        error.value = "";
        saved.value = "Saved";
    } catch {
        error.value = "Could not save this choice. Please try again.";
    }
}
</script>
