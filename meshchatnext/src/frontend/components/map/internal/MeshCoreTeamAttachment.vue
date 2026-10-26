<template>
    <div class="space-y-2 mt-2 border-t border-sem-border pt-2">
        <p class="font-semibold">Tactical attachment · MeshCore Radio2</p>
        <template v-if="composer">
            <MeshCoreVoiceComposer
                :peer="owner"
                :owner="owner"
                :connected="connected"
                attachment
                :channel-id="channelId"
                @prepared="prepared('voice', $event)"
            />
            <MeshCoreImageComposer
                :peer="owner"
                :owner="owner"
                :connected="connected"
                :channel-id="channelId"
                attachment
                @prepared="prepared('photo', $event)"
            />
            <p>
                Attach a previewed photo or recording, then share the pin or report. Preparing a recording sends nothing
                over radio.
            </p>
            <p>
                Sharing makes this attachment available on request to radio listeners who know its reference. Media is
                unencrypted over radio.
            </p>
        </template>
        <template v-else-if="item?.attachment">
            <p>
                {{
                    supported
                        ? item.attachment.mode === 40
                            ? "Photo"
                            : `Voice note · ${item.attachment.extra} seconds`
                        : "Attachment format not yet supported in neXt"
                }}
            </p>
            <template v-if="supported">
                <template v-if="!own">
                    <p v-if="matches.length === 1">From {{ matches[0].name || "MeshCore contact" }} · MeshCore</p>
                    <label v-else-if="matches.length > 1" class="block"
                        >Choose the sender · MeshCore
                        <select v-model="peer" class="input-field w-full">
                            <option value="">Choose a contact</option>
                            <option v-for="contact in matches" :key="contact.peer" :value="contact.peer">
                                {{ contact.name || "MeshCore contact" }} · {{ contact.peer.slice(0, 16) }}
                            </option>
                        </select>
                    </label>
                    <template v-else>
                        <p>Sender not found in your MeshCore contacts.</p>
                        <RouterLink to="/contacts" class="text-sem-accent underline"
                            >Find or add a MeshCore contact</RouterLink
                        >
                    </template>
                    <p class="text-xs text-sem-fg-muted">
                        Matched by short radio alias; this does not verify the sender or link contacts.
                    </p>
                    <details>
                        <summary class="cursor-pointer text-xs">Advanced: use a full public key</summary>
                        <input
                            v-model.trim="manualPeer"
                            aria-label="Author’s full MeshCore public key"
                            class="input-field w-full font-mono"
                            maxlength="64"
                            autocomplete="off"
                            spellcheck="false"
                        />
                    </details>
                </template>
                <button type="button" class="secondary-chip" :disabled="busy" @click="load">
                    {{ busy ? "Receiving attachment…" : url ? "Open saved attachment" : "Download attachment" }}
                </button>
                <img
                    v-if="url && item.attachment.mode === 40"
                    :src="url"
                    alt="Tactical photo attachment"
                    class="max-w-full max-h-96 rounded-lg"
                />
                <audio
                    v-else-if="url"
                    :src="url"
                    controls
                    preload="none"
                    class="w-full h-9"
                    aria-label="Tactical voice attachment"
                />
                <p v-if="progress" role="status">{{ progress }}</p>
            </template>
            <p>
                Media is unencrypted over radio. Downloads start only when requested. Radio2 must be enabled on both
                radios.
            </p>
        </template>
        <p v-if="problem" role="alert" class="text-sem-danger">{{ problem }}</p>
    </div>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Public identity checks and component lifetime guards. */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import MeshCoreImageComposer from "../../meshcore/MeshCoreImageComposer.vue";
import MeshCoreVoiceComposer from "../../meshcore/MeshCoreVoiceComposer.vue";
import { apiPath } from "../../../js/constants";
import { attachmentContacts } from "../../../js/meshcoreAttachments";
import { mediaUrl } from "../../../js/meshcoreVoice";
const props = defineProps({
    owner: { type: String, required: true },
    channelId: { type: String, required: true },
    connected: Boolean,
    contacts: { type: Array, default: () => [] },
    composer: Boolean,
    item: { type: Object, default: null },
});
const emit = defineEmits(["prepared"]);
let selectedType;
function prepared(type, meta) {
    if (meta || selectedType === type) {
        selectedType = meta ? type : null;
        emit("prepared", meta);
    }
}
const peer = ref(""),
    manualPeer = ref(""),
    url = ref(""),
    busy = ref(false),
    problem = ref(""),
    progress = ref("");
const matches = computed(() => attachmentContacts(props.contacts, props.item?.alias));
const own = computed(() => props.item?.alias === props.owner.slice(0, 8));
const supported = computed(() => {
    const meta = props.item?.attachment;
    return (
        meta &&
        (meta.mode === 40
            ? meta.extra >= 1 && meta.extra <= 600
            : meta.mode >= 1 && meta.mode <= 6 && meta.extra >= 1 && meta.extra <= 20)
    );
});
let generation = 0,
    timer,
    wake;
function reset() {
    generation++;
    clearTimeout(timer);
    wake?.();
    wake = null;
    if (url.value) URL.revokeObjectURL(url.value);
    url.value = "";
    busy.value = false;
    problem.value = "";
    progress.value = "";
    peer.value = "";
    manualPeer.value = "";
}
async function load() {
    if (busy.value || !supported.value) return;
    const author = own.value
        ? props.owner
        : manualPeer.value.toLowerCase() || (matches.value.length === 1 ? matches.value[0].peer : peer.value);
    if (!/^[0-9a-f]{64}$/.test(author) || author.slice(0, 8) !== props.item.alias) {
        problem.value = "Select the sender’s MeshCore contact or add them before downloading.";
        return;
    }
    busy.value = true;
    problem.value = "";
    const token = generation,
        meta = { ...props.item.attachment },
        body = { peer: author, expected_owner: props.owner, sid: meta.sid, direction: own.value ? "out" : "in" };
    const play = async () => {
        const { data } = await window.api.post(apiPath("/meshcore/voice-play"), body);
        if (token !== generation) return;
        if (url.value) URL.revokeObjectURL(url.value);
        url.value = mediaUrl(data.result);
        progress.value = "Saved on this device · ready to play";
    };
    try {
        try {
            await play();
            return;
        } catch (error) {
            if (own.value || !props.connected || error?.response?.status !== 400 || token !== generation) throw error;
        }
        await window.api.post(apiPath("/meshcore/team-attachment-fetch"), {
            peer: author,
            kind: props.item.kind,
            item_id: props.item.id,
            alias: props.item.alias,
            expected_owner: props.owner,
            expected_channel_id: props.channelId,
        });
        for (let i = 0; i < 90 && token === generation; i++) {
            await new Promise((resolve) => {
                wake = resolve;
                timer = setTimeout(resolve, 1500);
            });
            wake = null;
            if (token !== generation) return;
            const { data } = await window.api.get(apiPath("/meshcore/ui"));
            if (token !== generation) return;
            const job = data.result?.voice_jobs?.[author + ":" + meta.sid];
            progress.value = job ? `Receiving ${job.received}/${job.total} parts` : "Waiting for sender…";
            if (job?.state === "complete") {
                await play();
                return;
            }
            if (["failed", "cancelled"].includes(job?.state))
                throw new Error("Attachment download incomplete. Check Radio2 and the sender, then retry.");
        }
        if (token === generation)
            throw new Error("Download is taking longer than expected. Check the connection and try again.");
    } catch (error) {
        if (token === generation)
            problem.value = error?.response?.data?.message || error.message || "Attachment could not be loaded.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
watch(
    () => [
        props.owner,
        props.channelId,
        props.connected,
        props.item?.alias,
        props.item?.id,
        props.item?.attachment?.sid,
    ],
    reset
);
onBeforeUnmount(reset);
</script>
