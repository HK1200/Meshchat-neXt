<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <section class="space-y-3" aria-label="Meshchat neXt support">
        <h3 class="font-semibold">Meshchat neXt Relay</h3>
        <p class="text-sm text-sem-fg-muted">
            Report bugs, suggest features or chat with the community over Reticulum. Opening a room connects to the
            relay; it does not send a message.
        </p>
        <div v-for="entry in SUPPORT_ROOMS" :key="entry.room" class="flex flex-wrap items-center gap-2">
            <button
                type="button"
                class="secondary-chip"
                :disabled="busy || !appFeatures.reticulum"
                @click="openRoom(entry.room)"
            >
                {{ entry.label }}
            </button>
            <button
                type="button"
                class="text-sm text-sem-accent"
                :disabled="busy"
                :aria-label="`Copy ${entry.label} relay link`"
                @click="copyRoom(entry.room)"
            >
                Copy link
            </button>
        </div>
        <p v-if="!appFeatures.reticulum" class="text-sm text-sem-fg-muted">
            Enable Reticulum in Settings → App features to open relay rooms.
        </p>
        <p class="break-all font-mono text-xs text-sem-fg-muted">{{ SUPPORT_HUB }}</p>
        <a
            v-if="githubUrl"
            :href="githubUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="block text-sm text-sem-accent"
            >Report on GitHub</a
        >
        <p v-if="message" role="status" class="text-sm text-sem-fg-muted">{{ message }}</p>
    </section>
</template>
<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { appFeatures } from "../js/appFeatures";
import { SUPPORT_HUB, SUPPORT_NAME, SUPPORT_ROOMS } from "../js/supportChannels";
import { applyRelayShareLink, buildMeshchatRelayUri } from "../js/relayLinkUtils";
const props = defineProps({ reportUrl: { type: String, default: "" } });
const router = useRouter();
const busy = ref(false),
    message = ref("");
const githubUrl = computed(() => {
    try {
        const url = new URL(props.reportUrl);
        return url.protocol === "https:" && url.hostname === "github.com" ? url.href : "";
    } catch {
        return "";
    }
});
async function openRoom(room) {
    if (busy.value || !appFeatures.reticulum) return;
    busy.value = true;
    message.value = "";
    try {
        await applyRelayShareLink({ hub: SUPPORT_HUB, name: SUPPORT_NAME, room, aspect: "rrc.hub" });
        await router.push({ name: "relay-chat", query: { hub: SUPPORT_HUB, room } });
    } catch {
        message.value = "Could not open the relay. Check your Reticulum connection and try again.";
    } finally {
        busy.value = false;
    }
}
async function copyRoom(room) {
    try {
        await navigator.clipboard.writeText(buildMeshchatRelayUri({ hub: SUPPORT_HUB, name: SUPPORT_NAME, room }));
        message.value = "Relay link copied.";
    } catch {
        message.value = "Could not copy the relay link.";
    }
}
</script>
