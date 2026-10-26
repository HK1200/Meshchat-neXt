<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <aside
        v-if="state.call_state !== 'idle' && !($route.path === '/call' && $route.query.network === 'sip')"
        class="fixed bottom-4 right-4 z-50 max-w-sm rounded-xl border border-sem-border bg-sem-surface p-4 shadow-xl space-y-2"
        aria-label="SIP call"
    >
        <p class="font-semibold text-sem-fg">SIP · {{ state.call_state }}</p>
        <p class="text-sm text-sem-fg-muted break-all">{{ state.peer }}</p>
        <div class="flex gap-2">
            <button v-if="state.call_state === 'incoming'" type="button" class="primary-chip" @click="answer">
                Answer
            </button>

            <button
                v-if="state.call_state !== 'incoming'"
                type="button"
                class="primary-chip"
                @click="$router.push({ path: '/call', query: { network: 'sip', tab: 'phone' } })"
            >
                Open SIP call</button
            ><button type="button" class="secondary-chip" @click="hangup">
                {{ state.call_state === "incoming" ? "Decline" : "End call" }}
            </button>
        </div>
        <p v-if="error" role="alert">{{ error }}</p>
    </aside>
</template>
<script setup>
import { useRouter } from "vue-router";
import { onMounted, onBeforeUnmount, ref } from "vue";
import { sipState as state, refreshSip, sipCommand } from "../../js/sip";
const error = ref("");
const router = useRouter();
async function answer() {
    try {
        await sipCommand("answer");
        router.push({ path: "/call", query: { network: "sip", tab: "phone" } });
    } catch (e) {
        error.value = e.message;
    }
}
let timer;
onMounted(() => {
    refreshSip();
    timer = setInterval(refreshSip, 1000);
});
onBeforeUnmount(() => clearInterval(timer));
async function hangup() {
    try {
        await sipCommand("hangup");
    } catch (e) {
        error.value = e.message;
    }
}
</script>
