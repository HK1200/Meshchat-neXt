<template>
    <component
        :is="embedded ? 'div' : 'details'"
        :class="embedded ? '' : 'px-4 py-2 border-t border-sem-border'"
        @toggle="toggle"
    >
        <summary v-if="!embedded" class="text-xs cursor-pointer font-semibold">Voice clip · MeshCore Radio2</summary>
        <div class="mt-2 space-y-2">
            <p class="text-xs text-sem-fg-muted">
                Up to 20 seconds · compatible MediaMesh clients.
                {{
                    channel
                        ? "Media uses the channel key; public channels are not private."
                        : "Audio is unencrypted over radio."
                }}
                Radio2 must be enabled on both radios.
            </p>
            <div class="flex flex-wrap gap-2 items-center">
                <button
                    v-if="!recording && !clip"
                    type="button"
                    class="secondary-chip"
                    :disabled="working || !connected"
                    @click="record"
                >
                    Record voice clip
                </button>
                <button v-if="recording" type="button" class="secondary-chip" @click="stop">
                    Stop · {{ seconds }} / 20 s
                </button>
                <template v-if="clip"
                    ><button type="button" class="secondary-chip" :disabled="working" @click="discard">
                        Discard recording</button
                    ><button type="button" class="primary-chip" :disabled="working || !connected" @click="send">
                        {{ working ? "Sending announcement…" : attachment ? "Attach recording" : "Send voice clip" }}
                    </button></template
                >
                <span v-if="working && !clip" role="status" class="text-xs">{{
                    recordingPhase === "starting" ? "Starting microphone…" : "Preparing recording…"
                }}</span>
            </div>
            <audio
                v-if="url"
                :src="url"
                controls
                preload="none"
                class="w-full h-9"
                aria-label="Preview recorded MeshCore voice clip"
            />
            <p v-if="problem" role="alert" class="text-xs text-sem-danger">{{ problem }}</p>
        </div>
    </component>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Generation counters guard component lifetime; no secret comparisons. */
import { ref, watch, onMounted, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
import { pcmBase64, audioUrl } from "../../js/meshcoreVoice";
const props = defineProps({
    peer: { type: String, required: true },
    owner: { type: String, default: "" },
    connected: Boolean,
    embedded: Boolean,
    attachment: Boolean,
    channel: Boolean,
    scope: { type: String, default: null },
    channelId: { type: String, default: "" },
});
const emit = defineEmits(["sent", "prepared"]);
const recording = ref(false),
    working = ref(false),
    seconds = ref(0),
    clip = ref(null),
    url = ref(""),
    problem = ref(""),
    recordingPhase = ref("idle");
let context,
    stream,
    processor,
    timer,
    chunks = [],
    capturedSamples = 0,
    generation = 0,
    sendId = null;
function release() {
    clearInterval(timer);
    processor?.disconnect();
    processor = null;
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    const old = context;
    context = null;
    old?.close().catch(() => {});
    recording.value = false;
}
function clearUrl() {
    if (url.value) URL.revokeObjectURL(url.value);
    url.value = "";
}
async function record() {
    if (working.value || recording.value || !props.connected) return;
    const token = generation;
    problem.value = "";
    working.value = true;
    recordingPhase.value = "starting";
    try {
        const next = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, echoCancellation: true },
            video: false,
        });
        if (token !== generation) {
            next.getTracks().forEach((track) => track.stop());
            return;
        }
        stream = next;
        context = new AudioContext();
        await context.audioWorklet.addModule("assets/js/telephone-pcm-capture.worklet.js");
        if (token !== generation) return;
        processor = new AudioWorkletNode(context, "telephone-pcm-capture");
        chunks = [];
        capturedSamples = 0;
        processor.port.onmessage = (event) => {
            if (!recording.value) return;
            const remaining = Math.max(0, Math.floor(context.sampleRate * 20) - capturedSamples);
            const chunk = new Int16Array(event.data).subarray(0, remaining);
            if (chunk.length) {
                chunks.push(chunk);
                capturedSamples += chunk.length;
            }
            if (capturedSamples >= context.sampleRate * 20) void stop();
        };
        const source = context.createMediaStreamSource(stream),
            mute = context.createGain();
        mute.gain.value = 0;
        source.connect(processor);
        processor.connect(mute);
        mute.connect(context.destination);
        await context.resume();
        seconds.value = 0;
        recording.value = true;
        recordingPhase.value = "recording";
        timer = setInterval(() => {
            seconds.value++;
            if (seconds.value >= 20) stop();
        }, 1000);
    } catch {
        if (token === generation) {
            release();
            problem.value = "Could not start the microphone. Check microphone access and try again.";
        }
    } finally {
        if (token === generation) working.value = false;
    }
}
async function stop() {
    if (!recording.value) return;
    const rate = context.sampleRate,
        captured = chunks;
    chunks = [];
    release();
    working.value = true;
    recordingPhase.value = "preparing";
    const token = generation;
    try {
        const { data } = await window.api.post(
            apiPath(props.attachment ? "/meshcore/team-attachment-prepare" : "/meshcore/voice-prepare"),
            {
                ...(props.attachment ? { expected_channel_id: props.channelId } : { peer: props.peer }),
                expected_owner: props.owner,
                pcm_base64: pcmBase64(captured, rate),
                request_id: crypto.randomUUID(),
            }
        );
        if (token !== generation) return;
        clip.value = data.result;
        sendId = crypto.randomUUID();
        clearUrl();
        url.value = audioUrl(data.result.wav_base64);
    } catch (error) {
        if (token === generation)
            problem.value = error?.response?.data?.message || error.message || "Recording could not be prepared.";
    } finally {
        if (token === generation) working.value = false;
    }
}
async function discard() {
    const old = clip.value;
    if (props.attachment) emit("prepared", null);
    clip.value = null;
    clearUrl();
    sendId = null;
    if (old) {
        try {
            await window.api.post(apiPath("/meshcore/voice-discard"), {
                peer: props.peer,
                expected_owner: props.owner,
                sid: old.sid,
            });
        } catch {
            /* Local drafts expire from the bounded cache. */
        }
    }
}
async function send() {
    if (!clip.value || working.value || !props.connected) return;
    if (props.attachment) {
        emit("prepared", clip.value.attachment);
        return;
    }
    working.value = true;
    problem.value = "";
    const token = generation;
    try {
        const { data } = await window.api.post(
            apiPath(props.channel ? "/meshcore/media-channel-send" : "/meshcore/voice-send"),
            {
                ...(props.channel
                    ? { channel_id: props.channelId, expected_scope: props.scope }
                    : { peer: props.peer }),
                expected_owner: props.owner,
                sid: clip.value.sid,
                request_id: sendId,
            },
            { timeout: 60000 }
        );
        if (token !== generation) return;
        if (data.result.state === "rejected") {
            sendId = crypto.randomUUID();
            problem.value =
                "The radio rejected the voice announcement. Your recording is kept; you can try sending it again.";
            return;
        }
        clip.value = null;
        clearUrl();
        sendId = null;
        emit("sent");
    } catch (error) {
        if (token === generation)
            problem.value =
                error?.response?.data?.message ||
                "Voice submission could not be confirmed. Check the conversation before retrying.";
    } finally {
        if (token === generation) working.value = false;
    }
}
function reset() {
    generation++;
    release();
    chunks = [];
    clip.value = null;
    working.value = false;
    sendId = null;
    clearUrl();
    problem.value = "";
}
function toggle(event) {
    if (!event.target.open && recording.value) reset();
}
watch(() => [props.owner, props.peer, props.connected, props.channelId, props.scope], reset);
function visibilityChanged() {
    if (document.hidden && (recording.value || (working.value && !clip.value))) {
        reset();
        problem.value = "Recording stopped when the app went into the background. Record again when ready.";
    }
}
onMounted(() => document.addEventListener("visibilitychange", visibilityChanged));
onBeforeUnmount(() => {
    document.removeEventListener("visibilitychange", visibilityChanged);
    reset();
});
</script>
