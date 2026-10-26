<template>
    <div class="space-y-4" aria-label="Share MeshCore identity">
        <template v-if="publicKey">
            <div class="text-center">
                <h4 class="font-semibold text-sem-fg">
                    MeshCore · {{ snapshot.profile_name || "Your radio identity" }}
                </h4>
                <p class="text-xs text-sem-fg-muted">
                    {{ snapshot.connected ? "Connected radio" : "Last connected radio identity" }}
                </p>
            </div>
            <div class="flex justify-center">
                <img
                    v-if="qr"
                    :src="qr"
                    alt="MeshCore public key QR"
                    class="w-52 h-52 rounded-xl border border-sem-border bg-white"
                />
                <p v-else class="text-sm text-sem-fg-muted">
                    {{ qrError ? "QR unavailable. You can still copy the public key." : "Preparing QR…" }}
                </p>
            </div>
            <p class="text-xs font-mono break-all text-center text-sem-fg-muted">{{ publicKey }}</p>
            <p class="text-xs text-sem-fg-muted text-center">
                MeshCore public key only. Your private key is not included.
            </p>
            <div class="flex justify-center flex-wrap gap-2">
                <button type="button" class="secondary-chip" @click="copy">Copy public key</button>
                <button type="button" class="primary-chip" @click="share">Share MeshCore identity</button>
            </div>
            <p v-if="notice" role="status" class="text-sm text-center text-sem-accent">{{ notice }}</p>
            <p v-if="error" role="alert" class="text-sm text-center text-sem-danger">{{ error }}</p>
        </template>
        <p v-else class="text-sm text-sem-fg-muted">Connect your MeshCore radio once to read its public identity.</p>
    </div>
</template>
<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue";
import QRCode from "qrcode";
const props = defineProps({ snapshot: { type: Object, required: true } });
const publicKey = computed(() =>
    /^[0-9a-f]{64}$/i.test(props.snapshot.owner || "") ? props.snapshot.owner.toLowerCase() : ""
);
const qr = ref(""),
    qrError = ref(false),
    notice = ref(""),
    error = ref("");
let generation = 0;
watch(
    publicKey,
    async (key) => {
        const revision = ++generation;
        qr.value = "";
        qrError.value = false;
        notice.value = "";
        error.value = "";
        if (!key) return;
        try {
            const result = await QRCode.toDataURL(key, { margin: 1, scale: 6 });
            if (revision === generation && key === publicKey.value) qr.value = result;
        } catch {
            if (revision === generation) qrError.value = true;
        }
    },
    { immediate: true, flush: "sync" }
);
onBeforeUnmount(() => {
    ++generation;
});
async function copy() {
    const key = publicKey.value;
    if (!key) return;
    notice.value = "";
    error.value = "";
    try {
        await navigator.clipboard.writeText(key);
        if (key === publicKey.value) notice.value = "MeshCore public key copied.";
    } catch {
        if (key === publicKey.value) error.value = "Could not copy the public key.";
    }
}
async function share() {
    const key = publicKey.value;
    if (!key) return;
    notice.value = "";
    error.value = "";
    if (!navigator.share) {
        await copy();
        return;
    }
    try {
        await navigator.share({ title: "MeshCore identity", text: key });
    } catch (e) {
        if (e?.name !== "AbortError" && key === publicKey.value)
            error.value = "Could not open sharing. Use Copy public key instead.";
    }
}
</script>
