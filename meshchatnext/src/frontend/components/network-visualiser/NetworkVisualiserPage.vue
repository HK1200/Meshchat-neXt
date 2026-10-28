<!-- SPDX-License-Identifier: 0BSD AND MIT -->
<template>
    <section class="flex-1 min-w-0 h-full flex flex-col overflow-hidden">
        <header
            class="flex items-center gap-3 px-3 py-2 border-b border-sem-border bg-sem-surface text-sem-fg shrink-0"
        >
            <h1 class="font-semibold">Network visualiser</h1>
            <label class="ml-auto text-sm"
                >Network
                <select
                    :value="network"
                    class="bg-sem-surface text-sem-fg border border-sem-border rounded-lg p-2"
                    aria-label="Visualiser network"
                    @change="choose($event.target.value)"
                >
                    <option v-if="appFeatures.reticulum" value="reticulum">Reticulum</option>
                    <option v-if="appFeatures.meshcore" value="meshcore">MeshCore</option>
                </select>
            </label>
        </header>
        <NetworkVisualiser v-if="network === 'reticulum'" class="min-h-0" />
        <MeshCoreNetworkVisualiser v-else-if="network === 'meshcore'" />
        <p v-else class="p-4">Enable Reticulum or MeshCore in App features to view a network.</p>
    </section>
</template>
<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { appFeatures } from "../../js/appFeatures";
import NetworkVisualiser from "./NetworkVisualiser.vue";
import MeshCoreNetworkVisualiser from "./MeshCoreNetworkVisualiser.vue";
const route = useRoute(),
    router = useRouter();
const network = computed(() =>
    route.query.network === "meshcore" && appFeatures.meshcore
        ? "meshcore"
        : appFeatures.reticulum
          ? "reticulum"
          : appFeatures.meshcore
            ? "meshcore"
            : null
);
function choose(value) {
    router.replace({ query: { ...route.query, network: value } });
}
</script>
