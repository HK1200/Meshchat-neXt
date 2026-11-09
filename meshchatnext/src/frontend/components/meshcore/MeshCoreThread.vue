<template>
    <section
        data-meshcore-chat
        class="flex flex-col flex-1 min-h-0 min-w-0 h-full bg-sem-canvas text-sem-fg"
        aria-label="MeshCore direct messages"
    >
        <header
            class="relative z-20 flex items-center gap-2 px-3 sm:px-4 py-2 border-b border-sem-border bg-sem-canvas"
        >
            <button
                type="button"
                class="p-2 rounded-lg text-sem-fg-muted hover:bg-sem-surface-muted"
                data-app-back
                aria-label="Back to conversations"
                @click="navigateAppUp(router, { name: 'messages' })"
            >
                <MaterialDesignIcon icon-name="arrow-left" class="size-5" />
            </button>
            <LxmfUserIcon icon-class="size-10 shrink-0" />
            <div class="min-w-0 flex-1">
                <h2 class="font-semibold truncate text-base">
                    {{ name }}
                    <span
                        class="text-[10px] font-medium border border-sem-border px-1.5 py-0.5 rounded-full text-sem-fg-muted"
                        >MeshCore</span
                    >
                </h2>
                <p class="text-xs font-mono text-sem-fg-muted truncate mt-0.5" :title="peer">
                    <span v-if="!snapshot.connected" class="meshcore-short-status hidden text-sem-warning"
                        >Disconnected · </span
                    >{{ peer }}
                </p>
            </div>
            <button v-if="snapshot.owner" type="button" class="secondary-chip shrink-0" @click="viewContactOnMap">
                View on map
            </button>
        </header>
        <MeshCorePrivateLocation
            v-if="snapshot.contacts.some((c) => c.peer === peer && c.kind === 1 && c.active) && snapshot.owner"
            :owner="snapshot.owner"
            :peer="peer"
            :name="name"
            :radio-id="snapshot.radio_id"
            :context-key="$route.query.meshcoreRadio || null"
            :connected="snapshot.connected"
        />
        <p class="meshcore-connection-hint px-4 py-2 text-xs text-sem-fg-muted">
            {{
                snapshot.connected
                    ? "Direct message over MeshCore"
                    : "MeshCore disconnected — saved messages remain available"
            }}
        </p>
        <label v-if="snapshot.radios?.length > 1" class="px-4 py-2 text-xs text-sem-fg-muted">
            Radio for this conversation
            <select
                class="input-field"
                aria-label="Sending MeshCore radio"
                :value="snapshot.radio_id"
                :disabled="busy"
                @change="
                    router.replace({
                        query: { ...router.currentRoute.value.query, meshcoreRadio: $event.target.value },
                    })
                "
            >
                <option v-for="radio in snapshot.radios" :key="radio.id" :value="radio.id">
                    {{ radio.label }} ·
                    {{ radio.connected ? "Connected" : radio.auto_reconnect ? "Reconnecting" : "Disconnected" }}
                </option>
            </select>
        </label>
        <p v-if="positionError" role="alert" class="px-4 py-2 text-sm text-sem-danger">{{ positionError }}</p>
        <p v-if="error" role="alert" class="px-4 text-sm text-sem-danger">{{ error }}</p>
        <div
            ref="list"
            class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3"
            aria-label="Messages"
            @scroll.passive="onScroll"
        >
            <p v-if="!rows.length" class="text-sm text-sem-fg-muted">No MeshCore messages yet.</p>
            <article
                v-for="row in rows"
                :key="row.id"
                :data-message-id="row.id"
                class="w-fit max-w-[85%] px-4 py-2.5 rounded-2xl border shadow-xs"
                :class="
                    row.direction === 'out'
                        ? 'ml-auto bg-sem-bubble-outbound/10 border-sem-bubble-outbound/25 dark:bg-sem-bubble-outbound/15'
                        : 'bg-sem-surface border-sem-border'
                "
            >
                <p v-if="row.id === firstUnreadId" class="text-xs font-semibold text-sem-accent mb-2">New messages</p>
                <MeshCoreVoiceMessage
                    v-if="voiceEnvelope(row.text)"
                    :row="row"
                    :peer="peer"
                    :meta="voiceEnvelope(row.text)"
                    :snapshot="snapshot"
                    @changed="refresh"
                />
                <p v-else class="whitespace-pre-wrap break-words">{{ row.text }}</p>
                <p class="text-xs text-sem-fg-muted mt-1">
                    {{ new Date(row.created * 1000).toLocaleString() }} ·
                    {{ row.direction === "in" ? "Received via MeshCore" : labels[row.state] || row.state }}
                    <span v-if="row.direction === 'out' && row.sent_route">
                        ·
                        {{
                            row.sent_route === "direct_then_flood"
                                ? "Flood retry"
                                : row.sent_route === "direct"
                                  ? "Direct"
                                  : "Flood"
                        }}
                    </span>
                    <span
                        v-if="row.direction === 'out' && Number.isInteger(row.heard_repeats)"
                        title="Overheard matching retransmissions; not unique repeaters or proof of delivery"
                    >
                        · {{ row.heard_repeats }} {{ row.heard_repeats === 1 ? "repeat heard" : "repeats heard" }}</span
                    >
                    <button
                        type="button"
                        class="ml-2 underline underline-offset-2"
                        aria-label="Show message path details"
                        @click.stop="detailRow = row"
                    >
                        Details
                    </button>
                </p>
            </article>
        </div>
        <button v-if="hasNewer" class="secondary-chip m-2" :disabled="loading" @click="loadNewer">
            Show newer messages
        </button>
        <MeshCoreAttachments :owner="snapshot.owner" :peer="peer" :connected="snapshot.connected" @sent="refresh" />
        <form data-meshcore-compose class="p-4 border-t border-sem-border space-y-2" @submit.prevent="send">
            <label class="text-xs font-semibold" for="meshcore-compose">Message via MeshCore</label>
            <textarea
                id="meshcore-compose"
                v-model="draft"
                class="input-field resize-none"
                rows="3"
                :disabled="busy"
                placeholder="Write a MeshCore message"
            />
            <div class="flex items-center justify-between gap-2">
                <span class="text-xs text-sem-fg-muted">
                    {{ bytes }} of {{ REPEAT_TEXT_BYTES }} bytes per message
                    <span v-if="parts.length > 1"> · {{ parts.length }} messages</span>
                </span>
                <button class="primary-chip" :disabled="!canSend">
                    {{ busy ? "Submitting…" : "Send via MeshCore" }}
                </button>
            </div>
            <p v-if="sendStatus" role="status" class="text-xs text-sem-fg-muted">{{ sendStatus }}</p>
        </form>
        <MeshCoreMessageDetails
            :row="detailRow"
            :owner="snapshot.owner"
            :target="peer"
            kind="direct"
            @close="detailRow = null"
        />
    </section>
</template>
<script setup>
import { navigateAppUp } from "../../js/androidBackNavigation";
import { useRouter } from "vue-router";
const router = useRouter();
import MeshCoreMessageDetails from "./MeshCoreMessageDetails.vue";
import MeshCorePrivateLocation from "./MeshCorePrivateLocation.vue";
import MeshCoreAttachments from "./MeshCoreAttachments.vue";
import MeshCoreVoiceMessage from "./MeshCoreVoiceMessage.vue";
import { voiceEnvelope } from "../../js/meshcoreVoice";
import { useMeshCoreMessagePosition } from "../../js/meshcoreMessagePosition";
import { useMeshCoreNotificationContext } from "../../js/meshcoreNotifications";
import { computed, ref, watch } from "vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import LxmfUserIcon from "../LxmfUserIcon.vue";
import { useMeshCoreUi } from "../../js/meshcoreUi";
import { REPEAT_TEXT_BYTES, useMeshCoreTextSend } from "../../js/meshcoreTextSend";
import { apiPath } from "../../js/constants";
const detailRow = ref(null);
const props = defineProps({ peer: { type: String, required: true } });
const { snapshot, error, action } = useMeshCoreUi(() => props.peer);
useMeshCoreNotificationContext(() => snapshot.value.active_notification_key);
const draft = ref(""),
    busy = ref(false),
    list = ref(null);
const labels = {
    submitting: "Submitting",
    accepted: "Accepted by radio",
    delivered: "Delivered",
    unconfirmed: "Delivery unconfirmed",
    unknown: "Result uncertain — not retried",
    rejected: "Rejected by radio",
};
watch([() => snapshot.value.owner, () => props.peer], () => {
    detailRow.value = null;
});
const rawRows = computed(() => [...(snapshot.value.messages || [])].sort((a, b) => a.created - b.created));
const name = computed(() => snapshot.value.contacts.find((c) => c.peer === props.peer)?.name || "MeshCore contact");
function viewContactOnMap() {
    const { owner, radio_id: radio } = snapshot.value;
    if (!owner) return;
    void router.push({
        name: "map",
        query: { meshcoreNode: props.peer, meshcoreOwner: owner, ...(radio ? { meshcoreRadio: radio } : {}) },
    });
}

const {
    bytes,
    parts,
    status: sendStatus,
    canSend,
    send,
} = useMeshCoreTextSend({
    draft,
    busy,
    maximum: () => REPEAT_TEXT_BYTES,
    ready: () => snapshot.value.connected,
    context: () => [props.peer, snapshot.value.owner, snapshot.value.radio_id].join(":"),
    history: () => snapshot.value.messages,
    submit: (frame) => action("message", { ...frame, peer: props.peer }),
});
watch(
    () => props.peer,
    () => {
        draft.value = "";
    }
);
watch(
    () => [snapshot.value.owner, snapshot.value.radio_id],
    ([owner, radioId], [previous, previousRadio]) => {
        if (previous && owner !== previous) {
            if (radioId && previousRadio && radioId !== previousRadio) {
                error.value = ""; // An explicit sending-radio choice keeps the unsent draft.
            } else {
                draft.value = "";
                error.value = "MeshCore identity changed. Start a new message.";
            }
        }
    }
);
const {
    visibleRows: rows,
    firstUnreadId,
    hasNewer,
    loadNewer,
    loading,
    onScroll,
    positionError,
} = useMeshCoreMessagePosition({
    snapshot,
    target: () => props.peer,
    kind: "direct",
    list,
    rows: rawRows,
    markRead: (through) =>
        window.api.post(apiPath("/meshcore/read"), { peer: props.peer, through, expected_owner: snapshot.value.owner }),
});
</script>
