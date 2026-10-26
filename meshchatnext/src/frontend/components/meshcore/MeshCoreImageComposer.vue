<template>
    <component :is="embedded ? 'div' : 'details'" :class="embedded ? '' : 'px-4 py-2 border-t border-sem-border'">
        <summary v-if="!embedded" class="text-xs cursor-pointer font-semibold">Photo · MeshCore Radio2</summary>
        <div class="space-y-2 mt-2 text-xs">
            <p>
                Preview the compressed photo before sending. Source location and camera metadata are removed. Download
                starts only when requested.
            </p>
            <p>
                {{
                    channelId && !attachment
                        ? "Media uses the channel key; public channels are not private."
                        : "Photos are unencrypted over radio."
                }}
                Radio2 must be enabled on both radios.
            </p>
            <label v-if="!clip" class="block"
                >Choose a photo · JPEG, PNG or WebP, up to 10 MB / 40 MP
                <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    :disabled="working || !connected"
                    @change="choose"
                />
            </label>
            <p v-if="working" role="status">
                {{ clip ? "Submitting photo announcement…" : "Preparing photo preview…" }}
            </p>
            <template v-if="clip">
                <img :src="url" alt="Preview of the compressed MeshCore photo" class="max-w-full max-h-64 rounded-lg" />
                <p>
                    {{ clip.width }} × {{ clip.height }} pixels · {{ clip.bytes || "cached" }} bytes ·
                    {{ clip.total }} radio packets
                </p>
                <p>
                    Fine text and small details may be lost. Review this preview before sending. Transfer time depends
                    on radio settings, route and retries.
                </p>
                <button type="button" class="secondary-chip" :disabled="working" @click="discard">Discard photo</button>
                <button type="button" class="primary-chip" :disabled="working || !connected" @click="send">
                    {{ attachment ? "Attach photo" : "Send photo" }}
                </button>
            </template>
            <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
        </div>
    </component>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Component lifetime guards, not secret comparisons. */
import { onBeforeUnmount, ref, watch } from "vue";
import { apiPath } from "../../js/constants";
import { checkPhoto } from "../../js/meshcorePhotos";
import { imageUrl } from "../../js/meshcoreVoice";
const props = defineProps({
    peer: { type: String, required: true },
    owner: { type: String, default: "" },
    connected: Boolean,
    embedded: Boolean,
    attachment: Boolean,
    channelId: { type: String, default: "" },
    scope: { type: String, default: null },
});
const emit = defineEmits(["sent", "prepared"]);
const clip = ref(null),
    url = ref(""),
    working = ref(false),
    problem = ref("");
let generation = 0,
    sendId;
function reset() {
    generation++;
    if (url.value) URL.revokeObjectURL(url.value);
    url.value = "";
    clip.value = null;
    working.value = false;
    problem.value = "";
    sendId = null;
}
async function choose(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || working.value || !props.connected) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) {
        problem.value = "Choose a JPEG, PNG or WebP photo up to 10 MB / 40 MP.";
        return;
    }
    working.value = true;
    problem.value = "";
    const token = generation;
    let bitmap;
    try {
        await checkPhoto(file);
        if (token !== generation) return;
        bitmap = await createImageBitmap(file, { resizeWidth: 512, resizeQuality: "high" });
        if (token !== generation) return;
        const scale = Math.min(1, 512 / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(bitmap.width * scale));
        canvas.height = Math.max(1, Math.round(bitmap.height * scale));
        const context = canvas.getContext("2d", { willReadFrequently: true });
        context.fillStyle = "white";
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data,
            rgb = new Uint8Array(canvas.width * canvas.height * 3);
        for (let i = 0, j = 0; i < rgba.length; i += 4) {
            rgb[j++] = rgba[i];
            rgb[j++] = rgba[i + 1];
            rgb[j++] = rgba[i + 2];
        }
        let binary = "";
        for (let i = 0; i < rgb.length; i += 8192) binary += String.fromCharCode(...rgb.subarray(i, i + 8192));
        const { data } = await window.api.post(
            apiPath("/meshcore/image-prepare"),
            {
                peer: props.peer,
                expected_owner: props.owner,
                rgb_base64: btoa(binary),
                width: canvas.width,
                height: canvas.height,
                request_id: crypto.randomUUID(),
            },
            { timeout: 120000 }
        );
        if (token !== generation) return;
        clip.value = data.result;
        url.value = imageUrl(data.result.png_base64);
        sendId = crypto.randomUUID();
    } catch (error) {
        if (token === generation)
            problem.value =
                error?.response?.data?.message || error.message || "Photo could not be prepared. Try a smaller photo.";
    } finally {
        bitmap?.close();
        if (token === generation) working.value = false;
    }
}
async function discard() {
    const old = clip.value;
    if (props.attachment) emit("prepared", null);
    reset();
    if (old)
        try {
            await window.api.post(apiPath("/meshcore/voice-discard"), {
                peer: props.peer,
                expected_owner: props.owner,
                sid: old.sid,
            });
        } catch {
            /* Bounded drafts expire locally. */
        }
}
async function send() {
    if (!clip.value || working.value || !props.connected) return;
    if (props.attachment) {
        emit("prepared", { mode: 40, sid: clip.value.sid, packets: clip.value.total, extra: clip.value.seconds });
        return;
    }
    const token = generation;
    working.value = true;
    problem.value = "";
    try {
        const { data } = await window.api.post(
            apiPath(props.channelId ? "/meshcore/media-channel-send" : "/meshcore/voice-send"),
            {
                ...(props.channelId
                    ? { channel_id: props.channelId, expected_scope: props.scope }
                    : { peer: props.peer }),
                sid: clip.value.sid,
                expected_owner: props.owner,
                request_id: sendId,
            },
            { timeout: 60000 }
        );
        if (token !== generation) return;
        if (data.result.state === "rejected") {
            sendId = crypto.randomUUID();
            problem.value = "Radio rejected the announcement. The preview is kept for retry.";
            return;
        }
        if (["unknown", "submitting"].includes(data.result.state)) {
            problem.value =
                "Submission is uncertain. Check the conversation before retrying; the same request will not be sent twice.";
            return;
        }
        reset();
        emit("sent");
    } catch (error) {
        if (token === generation)
            problem.value =
                error?.response?.data?.message ||
                "Submission could not be confirmed. Check the conversation before retrying.";
    } finally {
        if (token === generation) working.value = false;
    }
}
watch(() => [props.peer, props.owner, props.connected, props.channelId, props.scope], reset);
onBeforeUnmount(reset);
</script>
