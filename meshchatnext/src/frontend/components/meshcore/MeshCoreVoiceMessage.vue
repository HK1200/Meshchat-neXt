<template>
    <div class="space-y-2 min-w-0">
        <p>
            {{ meta.image ? "Photo" : `Voice clip · ${meta.seconds} seconds` }}
            <span class="text-xs text-sem-fg-muted">MeshCore Radio2</span>
        </p>
        <img v-if="url && meta.image" :src="url" alt="Received MeshCore photo" class="max-w-full max-h-96 rounded-lg" />
        <audio
            v-else-if="url"
            :src="url"
            controls
            preload="none"
            class="max-w-full h-9"
            aria-label="MeshCore voice clip"
        />
        <p v-if="job?.state === 'downloading'" role="status" aria-live="polite" class="text-xs text-sem-fg-muted">
            Receiving attachment · {{ job.received }}/{{ job.total }} parts
        </p>
        <progress
            v-if="job?.state === 'downloading'"
            :value="job.received"
            :max="job.total"
            class="w-full"
            aria-label="Attachment download progress"
        />
        <button
            v-else-if="!url"
            type="button"
            class="secondary-chip text-xs"
            :disabled="busy || job?.state === 'downloading'"
            @click="load"
        >
            {{
                job?.state === "downloading"
                    ? `Receiving ${job.received}/${job.total}`
                    : busy
                      ? "Loading…"
                      : row.direction === "out" || job?.state === "complete"
                        ? "Open saved attachment"
                        : retryable
                          ? meta.image
                              ? "Retry photo download"
                              : "Retry voice download"
                          : "Download attachment"
            }}
        </button>
        <p v-if="url" role="status" class="text-xs text-sem-fg-muted">Ready to play · saved on this device</p>
        <p v-if="!snapshot.connected && !url" class="text-xs text-sem-fg-muted">
            Offline · cached clips can still be played. Reconnect the MeshCore radio to download missing audio.
        </p>
        <p class="text-xs text-sem-fg-muted">
            {{
                channelId
                    ? "Media uses the channel key; public channels are not private."
                    : "Media is unencrypted over radio."
            }}
        </p>
        <p v-if="problem || job?.state === 'failed'" role="alert" class="text-xs text-sem-danger">
            {{ problem || job.error }}
        </p>
    </div>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Generation counters guard component lifetime; no secret comparisons. */
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
import { mediaUrl } from "../../js/meshcoreVoice";
const props = defineProps({
    row: { type: Object, required: true },
    channelId: { type: String, default: "" },
    scope: { type: String, default: null },
    peer: { type: String, required: true },
    meta: { type: Object, required: true },
    snapshot: { type: Object, required: true },
});
const emit = defineEmits(["changed"]);
const url = ref(""),
    busy = ref(false),
    problem = ref("");
let generation = 0,
    requested = false;
const job = computed(
    () => props.snapshot.voice_jobs?.[(props.channelId ? "channel:" : "") + props.peer + ":" + props.meta.sid]
);
const retryable = computed(() => ["failed", "cancelled"].includes(job.value?.state));
async function load() {
    if (busy.value) return;
    busy.value = true;
    problem.value = "";
    const token = generation;
    const body = { peer: props.peer, expected_owner: props.snapshot.owner };
    try {
        try {
            const { data } = await window.api.post(apiPath("/meshcore/voice-play"), {
                ...body,
                sid: props.meta.sid,
                direction: props.row.direction,
            });
            if (token === generation) {
                url.value = mediaUrl(data.result);
                requested = false;
            }
        } catch (error) {
            if (
                !props.snapshot.connected ||
                props.row.direction !== "in" ||
                error?.response?.status !== 400 ||
                token !== generation
            )
                throw error;
            requested = true;
            await window.api.post(
                apiPath(props.channelId ? "/meshcore/media-channel-fetch" : "/meshcore/voice-fetch"),
                {
                    ...(props.channelId
                        ? {
                              channel_id: props.channelId,
                              expected_owner: props.snapshot.owner,
                              expected_scope: props.scope,
                          }
                        : body),
                    message_id: props.row.id,
                }
            );
            if (token === generation) emit("changed");
        }
    } catch (error) {
        if (token === generation)
            problem.value = !props.snapshot.connected
                ? "This attachment is not available offline. Reconnect the MeshCore radio and try again."
                : error?.response?.data?.message || "Attachment could not be loaded. Try again.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
function reset() {
    generation++;
    requested = false;
    if (url.value) URL.revokeObjectURL(url.value);
    url.value = "";
    busy.value = false;
    problem.value = "";
}
watch([() => props.peer, () => props.snapshot.owner, () => props.row.id, () => props.scope], reset);
watch(
    () => job.value?.state,
    (state, previous) => {
        if (state === "complete" && (previous === "downloading" || requested) && !url.value && !busy.value) void load();
    }
);
onBeforeUnmount(reset);
</script>
