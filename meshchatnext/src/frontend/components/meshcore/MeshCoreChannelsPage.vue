<template>
    <section class="flex flex-col flex-1 min-w-0 h-full bg-sem-canvas text-sem-fg" aria-label="MeshCore channels">
        <header class="px-3 py-2 border-b border-sem-border flex items-center gap-2 shrink-0">
            <button
                v-if="channelId"
                type="button"
                class="p-2 rounded-lg text-sem-fg-muted hover:bg-sem-surface-muted"
                data-app-back
                aria-label="Back to MeshCore channels"
                @click="$router.push({ name: 'meshcore-channels' })"
            >
                <MaterialDesignIcon icon-name="arrow-left" class="size-5" />
            </button>
            <div class="min-w-0 flex-1">
                <h1 class="text-base font-semibold truncate">{{ selected?.name || "MeshCore Channels" }}</h1>
                <p class="text-xs text-sem-fg-muted truncate">
                    MeshCore · {{ snapshot.connected ? "Connected" : "Disconnected · saved history"
                    }}<span v-if="selected">
                        · {{ selected.kind === "private" ? "Private channel" : "Public channel" }}</span
                    >
                </p>
            </div>
            <label v-if="selected" class="text-xs shrink-0">
                <span class="sr-only">Notifications</span>
                <select
                    aria-label="Channel notifications"
                    class="rounded-lg border border-sem-border bg-sem-surface text-sem-fg px-2 py-2 text-xs max-w-28"
                    :disabled="busy"
                    :value="selected.muted ? 'muted' : selected.mentions_only ? 'mentions' : 'all'"
                    @change="setNotifications($event.target.value)"
                >
                    <option value="all">All messages</option>
                    <option value="mentions">Mentions only</option>
                    <option value="muted">Muted</option>
                </select>
            </label>
        </header>
        <p v-if="positionError" role="alert" class="px-4 py-2 text-sm text-sem-danger">{{ positionError }}</p>
        <p v-if="error" role="alert" class="px-4 py-2 text-sm text-sem-danger">{{ error }}</p>
        <div v-if="!channelId" class="overflow-y-auto p-4 md:p-6 space-y-6">
            <div class="max-w-3xl mx-auto space-y-4">
                <h2 class="font-semibold">Your channels</h2>
                <RouterLink
                    :to="{ name: 'meshcore-tools', params: { tool: 'regions' } }"
                    class="text-sm text-sem-accent"
                    >Manage channel regions</RouterLink
                >
                <p class="text-sm text-sem-fg-muted">Use the arrows to change channel order in the sidebar.</p>
                <div
                    v-for="(channel, index) in snapshot.channels || []"
                    :key="channel.channel_id + ':' + channel.slot"
                    class="flex flex-wrap items-center gap-2 border-b border-sem-border"
                >
                    <RouterLink
                        :to="meshcoreChannelRoute(channel.channel_id)"
                        class="flex flex-1 basis-full sm:basis-auto min-w-0 items-center gap-3 py-3 hover:bg-sem-surface-muted"
                    >
                        <MaterialDesignIcon
                            :icon-name="channel.kind === 'private' ? 'lock-outline' : 'pound'"
                            class="size-5"
                        />
                        <span class="flex-1 truncate"
                            >{{ channel.name
                            }}<span class="block text-xs text-sem-fg-muted">MeshCore · {{ channel.kind }}</span></span
                        >
                        <span v-if="channel.unread" class="text-xs text-sem-accent">{{ channel.unread }} unread</span>
                        <MaterialDesignIcon v-if="channel.muted" icon-name="bell-off-outline" class="size-4" />
                    </RouterLink>
                    <MeshCoreChannelScope
                        :channel="channel"
                        :regions="snapshot.regions || []"
                        :default-scope="snapshot.channel_default_scope || ''"
                        :disabled="busy"
                        @change="(scope) => setChannelScope(channel, scope)"
                    />
                    <button
                        type="button"
                        class="p-2 disabled:opacity-30"
                        :disabled="busy || index === 0"
                        :aria-label="`Move ${channel.name} up`"
                        @click="moveChannel(index, index - 1)"
                    >
                        <MaterialDesignIcon icon-name="chevron-up" class="size-5" />
                    </button>
                    <button
                        type="button"
                        class="p-2 disabled:opacity-30"
                        :disabled="busy || index === snapshot.channels.length - 1"
                        :aria-label="`Move ${channel.name} down`"
                        @click="moveChannel(index, index + 1)"
                    >
                        <MaterialDesignIcon icon-name="chevron-down" class="size-5" />
                    </button>
                    <button
                        type="button"
                        class="secondary-chip text-xs"
                        :disabled="busy"
                        :aria-label="`${channel.hidden ? 'Show' : 'Hide'} ${channel.name}`"
                        @click="visibility(channel)"
                    >
                        {{ channel.hidden ? "Show" : "Hide" }}
                    </button>
                    <button
                        v-if="channel.slot !== 0"
                        type="button"
                        class="secondary-chip text-xs text-sem-danger"
                        :disabled="busy || !snapshot.connected"
                        :aria-label="`Delete ${channel.name}`"
                        @click="removeChannel(channel)"
                    >
                        Delete
                    </button>
                    <span v-else class="text-xs text-sem-fg-muted">Default · can be hidden</span>
                    <p
                        v-if="channel.kind === 'public' && channel.name !== channel.name.toLowerCase()"
                        class="w-full text-xs text-sem-fg-muted pb-2"
                    >
                        Existing mixed-case hashtag: other clients need the same channel key. Re-add it in lowercase to
                        use lowercase name-based joins; its existing key is unchanged.
                    </p>
                    <p v-if="channel.hidden" class="w-full text-xs text-sem-fg-muted pb-2">
                        Hidden from sidebar · notifications off
                    </p>
                </div>
                <p v-if="!snapshot.channels?.length" class="text-sm text-sem-fg-muted">
                    No MeshCore channels are configured.
                </p>
                <form class="space-y-3 border-t border-sem-border pt-4" @submit.prevent="add">
                    <h2 class="font-semibold">Add a MeshCore channel</h2>
                    <label class="block text-sm"
                        >Hashtag name<input
                            v-model="name"
                            class="input-field mt-1"
                            :placeholder="privateChannel ? 'Private channel name' : '#channel'"
                            required
                            :disabled="busy"
                            autocomplete="off"
                    /></label>
                    <p v-if="!privateChannel" class="text-xs text-sem-fg-muted">
                        Public hashtag names are saved in lowercase so other clients can join by name.
                    </p>
                    <label class="flex items-center gap-2 text-sm"
                        ><input v-model="privateChannel" type="checkbox" :disabled="busy" />Private channel</label
                    >
                    <label v-if="privateChannel" class="block text-sm"
                        >Shared key (32 hex characters)<input
                            v-model="key"
                            type="password"
                            class="input-field mt-1"
                            autocomplete="off"
                            :disabled="busy"
                        /><span class="text-xs text-sem-fg-muted"
                            >Enter the shared key to join, or leave blank to create a new private channel. Private
                            channel names use a plain label without # for compatibility with other clients.</span
                        ></label
                    >
                    <button class="primary-chip" :disabled="!snapshot.connected || busy || !name.trim()">
                        {{ busy ? "Adding…" : "Add channel" }}
                    </button>
                </form>
            </div>
        </div>
        <template v-else-if="selected">
            <div
                ref="list"
                class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3"
                aria-label="Channel messages"
                @scroll.passive="onScroll"
            >
                <p v-if="!rows.length" class="text-sm text-sem-fg-muted">No messages in this MeshCore channel yet.</p>
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
                    <p v-if="row.id === firstUnreadId" class="text-xs font-semibold text-sem-accent mb-2">
                        New messages
                    </p>
                    <p v-if="channelMediaEnvelope(row) && row.sender" class="text-xs font-semibold">
                        {{ row.sender }} · MeshCore
                    </p>
                    <MeshCoreVoiceMessage
                        v-if="channelMediaEnvelope(row)"
                        :row="row"
                        :peer="channelId"
                        :channel-id="channelId"
                        :scope="mediaScope"
                        :meta="channelMediaEnvelope(row)"
                        :snapshot="snapshot"
                        @changed="refresh"
                    />
                    <p v-else class="whitespace-pre-wrap break-words">{{ row.text }}</p>
                    <p class="text-xs text-sem-fg-muted mt-1">
                        {{ new Date(row.created * 1000).toLocaleString() }} ·
                        {{ row.direction === "in" ? "Received via MeshCore" : states[row.state] || row.state }}
                        <span
                            v-if="row.direction === 'out' && Number.isInteger(row.heard_repeats)"
                            title="Overheard matching retransmissions; not unique repeaters or proof of delivery"
                        >
                            · {{ row.heard_repeats }}
                            {{ row.heard_repeats === 1 ? "repeat heard" : "repeats heard" }}</span
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
                    <button
                        v-if="row.direction === 'in' && row.sender"
                        type="button"
                        class="inline-flex p-1 rounded-lg text-sem-fg-muted hover:bg-sem-surface-muted mt-1"
                        :aria-label="`Message actions for ${row.sender}`"
                        :disabled="busy"
                        @click.stop="openMenu($event, row)"
                    >
                        <MaterialDesignIcon icon-name="dots-vertical" class="size-4" />
                    </button>
                </article>
            </div>
            <button v-if="hasNewer" class="secondary-chip m-2" :disabled="loading" @click="loadNewer">
                Show newer messages
            </button>
            <MeshCoreAttachments
                :owner="snapshot.owner"
                :peer="channelId"
                :connected="snapshot.connected"
                :channel-id="channelId"
                :scope="mediaScope"
                @sent="refresh"
            />
            <form class="p-4 border-t border-sem-border space-y-2" @submit.prevent="send">
                <label for="meshcore-channel-compose" class="text-xs font-semibold"
                    >Message {{ selected.name }} via MeshCore</label
                >
                <textarea
                    id="meshcore-channel-compose"
                    ref="composer"
                    v-model="draft"
                    class="input-field resize-none"
                    rows="3"
                    :disabled="busy"
                    placeholder="Write a channel message"
                />
                <div class="flex items-center justify-between">
                    <span class="text-xs text-sem-fg-muted">{{ bytes }}/{{ maximum }} bytes</span
                    ><button
                        class="primary-chip"
                        :disabled="!snapshot.connected || busy || !draft.trim() || bytes > maximum"
                    >
                        {{ busy ? "Submitting…" : "Send via MeshCore" }}
                    </button>
                </div>
                <p v-if="uncertain" class="text-xs text-sem-fg-muted">
                    The result is uncertain. Check this channel before sending again.
                </p>
            </form>
        </template>
        <p v-else class="p-4 text-sm text-sem-fg-muted">
            This channel is unavailable for the selected MeshCore identity.
        </p>
        <ContextMenuPanel v-click-outside="closeMenu" :show="!!context.row" :x="context.x" :y="context.y">
            <ContextMenuItem :disabled="busy || !snapshot.connected" @click="reply(context.row)"
                >Reply to sender</ContextMenuItem
            >
            <ContextMenuItem :disabled="busy" @click="banish(context.row)">Banish sender name…</ContextMenuItem>
        </ContextMenuPanel>
        <MeshCoreMessageDetails
            :row="detailRow"
            :owner="snapshot.owner"
            :target="channelId"
            kind="channel"
            @close="detailRow = null"
        />
    </section>
</template>
<script setup>
import MeshCoreMessageDetails from "./MeshCoreMessageDetails.vue";
import MeshCoreAttachments from "./MeshCoreAttachments.vue";
import MeshCoreVoiceMessage from "./MeshCoreVoiceMessage.vue";
import { channelMediaEnvelope } from "../../js/meshcoreVoice";
import MeshCoreChannelScope from "./MeshCoreChannelScope.vue";
import { useMeshCoreMessagePosition } from "../../js/meshcoreMessagePosition";
import { useMeshCoreNotificationContext } from "../../js/meshcoreNotifications";
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import ContextMenuPanel from "../contextmenu/ContextMenuPanel.vue";
import ContextMenuItem from "../contextmenu/ContextMenuItem.vue";
import MaterialDesignIcon from "../MaterialDesignIcon.vue";
import DialogUtils from "../../js/DialogUtils";
import { apiPath } from "../../js/constants";
import { useMeshCoreUi, meshcoreChannelRoute } from "../../js/meshcoreUi";
const detailRow = ref(null);
const props = defineProps({ channelId: { type: String, default: "" }, visit: { type: String, default: "" } });
const { snapshot, error, action, refresh } = useMeshCoreUi(
    () => null,
    () => true,
    () => props.channelId || null,
    () => props.visit
);
useMeshCoreNotificationContext(() => snapshot.value.active_notification_key);
const selected = computed(() => (snapshot.value.channels || []).find((row) => row.channel_id === props.channelId));
watch([() => snapshot.value.owner, () => props.channelId], () => {
    detailRow.value = null;
});
const rawRows = computed(() => [...(snapshot.value.channel_messages || [])].sort((a, b) => a.created - b.created));
const composer = ref(null);
const list = ref(null),
    draft = ref(""),
    name = ref(""),
    key = ref(""),
    privateChannel = ref(false),
    busy = ref(false),
    uncertain = ref(false);
const bytes = computed(() => new TextEncoder().encode(draft.value).length);
const maximum = computed(() => Math.max(0, 158 - new TextEncoder().encode(snapshot.value.profile_name || "").length));
const mediaScope = computed(() => selected.value?.scope ?? snapshot.value.channel_default_scope ?? null);
const states = {
    submitted: "Accepted by radio",
    rejected: "Rejected by radio",
    unknown: "Result uncertain",
    submitting: "Submitting",
};
const context = ref({ row: null, x: 0, y: 0 });
function closeMenu() {
    context.value.row = null;
}
function openMenu(event, row) {
    const rect = event.currentTarget.getBoundingClientRect();
    context.value = { row, x: event.clientX || rect.right, y: event.clientY || rect.bottom };
}
async function reply(row) {
    if (!row?.sender || busy.value || !snapshot.value.connected) return;
    if (/[\]\r\n]/.test(row.sender)) {
        error.value = "This sender name cannot be used in a MeshCore mention.";
        closeMenu();
        return;
    }
    const mention = `@[${row.sender}] `;
    if (!draft.value.startsWith(mention)) draft.value = mention + draft.value;
    closeMenu();
    await nextTick();
    composer.value?.focus();
}
function escapeMenu(event) {
    if (event.key === "Escape") closeMenu();
}
onMounted(() => document.addEventListener("keydown", escapeMenu));
onBeforeUnmount(() => document.removeEventListener("keydown", escapeMenu));
let pending = null,
    privateKey = null;
onBeforeUnmount(() => {
    key.value = "";
    privateKey = null;
});
watch([() => props.channelId, () => snapshot.value.owner], () => {
    draft.value = "";
    closeMenu();
    pending = null;
    uncertain.value = false;
    key.value = "";
    privateKey = null;
});
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
    target: () => props.channelId,
    kind: "channel",
    list,
    rows: rawRows,
    visit: () => props.visit,
    markRead: (through) =>
        window.api.post(apiPath("/meshcore/channel-read"), {
            channel: props.channelId,
            through,
            expected_owner: snapshot.value.owner,
        }),
});
async function visibility(channel) {
    if (busy.value) return;
    busy.value = true;
    try {
        await action("channel-visibility", { channel: channel.channel_id, hidden: !channel.hidden });
    } catch {
        error.value = "Could not change channel visibility.";
    } finally {
        busy.value = false;
    }
}
async function removeChannel(channel) {
    if (busy.value || !snapshot.value.connected || channel.slot === 0) return;
    const owner = snapshot.value.owner,
        id = channel.channel_id,
        slot = channel.slot;
    if (
        !(await DialogUtils.confirm(
            `Delete “${channel.name}” from this MeshCore radio? Saved messages stay on this device. You can re-add the channel later using its name or shared key.`,
            "Delete MeshCore channel"
        ))
    )
        return;
    if (
        owner !== snapshot.value.owner ||
        busy.value ||
        !snapshot.value.channels.some((row) => row.channel_id === id && row.slot === slot)
    )
        return;
    busy.value = true;
    try {
        await action("channel-remove", { slot, expected_channel_id: id });
    } catch {
        error.value = "Channel deletion was not confirmed. Refresh before trying again.";
    } finally {
        busy.value = false;
    }
}
async function moveChannel(from, to) {
    const channels = [...(snapshot.value.channels || [])];
    if (busy.value || from < 0 || to < 0 || from >= channels.length || to >= channels.length || from === to) return;
    const [moved] = channels.splice(from, 1);
    channels.splice(to, 0, moved);
    busy.value = true;
    error.value = "";
    try {
        await action("channel-order", { channels: [...new Set(channels.map((row) => row.channel_id))] });
    } catch {
        error.value = "Could not save channel order. Refresh and try again.";
    } finally {
        busy.value = false;
    }
}
async function setChannelScope(channel, scope) {
    if (!channel || busy.value) return;
    busy.value = true;
    try {
        await action("channel-scope", { channel: channel.channel_id, scope });
    } catch {
        error.value = "Could not save this channel scope.";
    } finally {
        busy.value = false;
    }
}

async function setNotifications(mode) {
    if (busy.value) return;
    busy.value = true;
    try {
        await action("channel-mute", {
            channel: props.channelId,
            muted: mode === "muted",
            mentions_only: mode === "mentions",
        });
    } catch {
        error.value = "Could not update this channel preference.";
    } finally {
        busy.value = false;
    }
}
async function add() {
    if (busy.value || !snapshot.value.connected) return;
    busy.value = true;
    error.value = "";
    try {
        const body = {
            name: privateChannel.value ? name.value.trim() : name.value.trim().toLowerCase(),
            private: privateChannel.value,
        };
        if (privateChannel.value) {
            if (key.value.trim()) body.key_hex = key.value.trim();
            else {
                if (!privateKey)
                    privateKey = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
                        b.toString(16).padStart(2, "0")
                    ).join("");
                body.key_hex = privateKey;
            }
        }
        await action("channel-add", body);
        name.value = "";
        key.value = "";
        privateKey = null;
    } catch {
        error.value =
            "Could not verify the channel change. Check the radio connection and channel list before trying again.";
    } finally {
        busy.value = false;
    }
}
async function send() {
    if (
        busy.value ||
        !selected.value ||
        !snapshot.value.connected ||
        !draft.value.trim() ||
        bytes.value > maximum.value
    )
        return;
    const channel = props.channelId,
        owner = snapshot.value.owner,
        text = draft.value;
    if (!pending || pending.text !== text || pending.expected_channel_id !== channel)
        pending = { slot: selected.value.slot, text, expected_channel_id: channel, request_id: crypto.randomUUID() };
    busy.value = true;
    uncertain.value = false;
    try {
        const result = await action("channel-message", pending);
        if (channel === props.channelId && owner === snapshot.value.owner) {
            draft.value = "";
            pending = null;
            uncertain.value = result.state === "unknown";
        }
    } catch {
        if (channel === props.channelId && owner === snapshot.value.owner) {
            error.value = "MeshCore did not return a result. Check the saved message before trying again.";
            uncertain.value = true;
        }
    } finally {
        busy.value = false;
    }
}
async function banish(row) {
    closeMenu();
    const channel = props.channelId,
        owner = snapshot.value.owner;
    if (
        !(await DialogUtils.confirm(
            `Hide messages from the displayed name “${row.sender}” in ${selected.value.name} on this device? Sender names are not verified identities. This does not remove anyone from the mesh.`
        ))
    )
        return;
    if (channel !== props.channelId || owner !== snapshot.value.owner) return;
    busy.value = true;
    try {
        await action("channel-banish", { channel, message: row.id });
        await refresh();
    } catch {
        error.value = "Could not banish this sender name.";
    } finally {
        busy.value = false;
    }
}
</script>
