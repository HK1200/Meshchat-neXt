<template>
    <div class="space-y-4 border-t border-sem-border pt-4">
        <p class="text-sm text-sem-fg-muted">
            {{ snapshot.connected ? "MeshCore radio connected" : "Disconnected · saved history" }} ·
            {{ administrator ? "Administrator login verified" : verified ? "Member login verified" : "Not logged in" }}
        </p>
        <nav class="flex flex-wrap gap-2 border-b border-sem-border pb-3" aria-label="Node sections">
            <button
                v-for="item in nodeTabs"
                :key="item.id"
                type="button"
                :class="activeTab === item.id ? 'primary-chip' : 'secondary-chip'"
                :aria-pressed="activeTab === item.id"
                :aria-controls="panelId(item.id)"
                @click="activeTab = item.id"
            >
                {{ item.label }}
            </button>
        </nav>
        <section v-show="activeTab === 'access'" :id="panelId('access')" class="space-y-4" aria-label="Node access">
            <h3 class="font-semibold">Access</h3>
            <form class="max-w-md space-y-3" @submit.prevent="login">
                <template v-if="!verified">
                    <label class="block text-sm font-medium" for="meshcore-server-password">Server password</label>
                    <div class="flex items-center gap-2">
                        <input
                            id="meshcore-server-password"
                            v-model="password"
                            :type="showPassword ? 'text' : 'password'"
                            autocomplete="off"
                            class="input-field min-w-0 flex-1"
                            :disabled="busy || needsRecovery || !snapshot.connected"
                            aria-label="MeshCore server password"
                        />
                        <button
                            type="button"
                            class="secondary-chip shrink-0"
                            :aria-pressed="showPassword"
                            :disabled="busy || needsRecovery || !snapshot.connected"
                            @click="showPassword = !showPassword"
                        >
                            {{ showPassword ? "Hide password" : "Show password" }}
                        </button>
                    </div>
                    <label v-if="vaultAvailable !== false" class="flex items-center gap-2 text-sm">
                        <input v-model="rememberPassword" type="checkbox" :disabled="busy || !snapshot.connected" />
                        Remember password on this device
                    </label>
                    <button class="primary-chip" :disabled="busy || needsRecovery || !snapshot.connected">
                        {{ busy ? "Working…" : "Log in" }}
                    </button>
                </template>
                <button
                    v-else
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || needsRecovery || !snapshot.connected"
                    @click="logout"
                >
                    Log out
                </button>
            </form>
            <MeshCoreNodePasswords
                :owner="snapshot.owner"
                :peer="node.peer"
                :radio-id="snapshot.radio_id"
                :default-role="node.kind === 2 ? 'admin' : 'member'"
                :disabled="busy || !snapshot.connected"
                :can-login="!verified && !needsRecovery"
                :refresh-key="passwordRefresh"
                @use-saved="operate('node-login', { use_saved_role: $event })"
                @available="vaultAvailable = $event"
            />
            <label v-if="autoLoginScope" class="flex items-center gap-2 text-sm">
                <input
                    type="checkbox"
                    :checked="autoLoginEnabled"
                    :disabled="busy"
                    @change="setAutoLogin($event.target.checked)"
                />
                Automatically log in with saved member password
            </label>
            <p v-if="node.kind === 2" class="text-xs text-sem-fg-muted">
                Opening this repeater uses its saved administrator password first, if available.
            </p>
        </section>
        <p v-if="notice" role="status" class="text-sm text-sem-fg-muted">{{ notice }}</p>
        <p v-if="!needsRecovery && snapshot.node_operations?.[node.peer]" class="text-xs text-sem-fg-muted">
            Last request: {{ operationLabel(snapshot.node_operations[node.peer].stage) }}
        </p>
        <p v-if="busy" role="status" class="text-sm text-sem-fg-muted">
            Waiting for this server… Please wait before sending another request.
        </p>
        <div v-if="problem || needsRecovery" class="space-y-2">
            <p role="alert" class="text-sm text-sem-danger">
                {{
                    needsRecovery
                        ? "No confirmed server response. Reconnect MeshCore, then log in again. The previous action may have run."
                        : problem
                }}
            </p>
            <button v-if="needsRecovery" type="button" class="secondary-chip" :disabled="busy" @click="recover">
                Reconnect MeshCore
            </button>
        </div>
        <section v-show="activeTab === 'status'" :id="panelId('status')" class="space-y-4" aria-label="Node status">
            <h3 class="font-semibold">Last reported status</h3>
            <p class="text-sm text-sem-fg-muted">
                {{
                    status
                        ? "Received during this visit. A previous report does not confirm current reachability."
                        : "No status requested during this visit."
                }}
            </p>
            <p v-if="!verified" class="text-sm text-sem-fg-muted">
                Log in under Access to request status. {{ node.kind === 2 ? "Pinging" : "Checking the route" }} needs no
                password.
            </p>
            <button
                class="secondary-chip"
                :disabled="busy || needsRecovery || !snapshot.connected || !verified"
                @click="operate('node-status')"
            >
                Request status
            </button>
            <button
                class="secondary-chip"
                type="button"
                :disabled="busy || !snapshot.connected"
                @click="operate('node-route')"
            >
                {{ node.kind === 2 ? "Ping repeater" : "Check route" }}
            </button>
            <dl v-if="status" class="grid grid-cols-2 gap-2 text-sm">
                <template v-for="(value, key) in status.values" :key="key"
                    ><dt class="text-sem-fg-muted">{{ label(key) }}</dt>
                    <dd>{{ value }}</dd></template
                >
            </dl>
        </section>
        <section v-show="activeTab === 'manage'" :id="panelId('manage')" class="space-y-4" aria-label="Manage node">
            <template v-if="!administrator">
                <h3 class="font-semibold">Administrator access required</h3>
                <p class="text-sm text-sem-fg-muted">
                    Log in with this node’s administrator password under Access to manage settings.
                </p>
                <button type="button" class="primary-chip" @click="activeTab = 'access'">Open Access</button>
            </template>
            <section v-if="administrator" class="space-y-3" aria-label="MeshCore administrator controls">
                <h3 class="font-semibold">Administrator · MeshCore</h3>
                <p class="text-xs text-sem-fg-muted">Manage this server using your verified administrator login.</p>
                <div class="space-y-2" aria-label="Administrator settings">
                    <details v-for="group in adminGroups" :key="group.label" class="border-b border-sem-border py-3">
                        <summary class="cursor-pointer text-sm font-semibold">{{ group.label }}</summary>
                        <div class="flex flex-wrap gap-2 pt-3">
                            <button
                                v-for="item in group.options"
                                :key="item[0]"
                                type="button"
                                class="secondary-chip"
                                :aria-pressed="adminAction === item[0]"
                                :disabled="busy || needsRecovery"
                                @click="chooseAdminAction(item[0])"
                            >
                                {{ item[1] }}
                            </button>
                        </div>
                        <div v-if="group.options.some(([action]) => action === adminAction)" class="mt-3 space-y-2">
                            <form
                                v-if="adminNeedsValue || adminDisruptive"
                                class="space-y-3 rounded-lg bg-sem-surface-muted/50 p-3"
                                @submit.prevent="administer"
                            >
                                <h4 class="font-semibold">
                                    {{ adminOptions.find(([action]) => action === adminAction)?.[1] }}
                                </h4>
                                <label v-if="adminNeedsValue" class="block text-sm"
                                    >{{ adminValueLabel }}
                                    <select
                                        v-if="adminAction === 'set-read-only'"
                                        v-model="adminValue"
                                        aria-label="Room read-only guest access"
                                        class="block w-full bg-sem-surface-muted text-sem-fg border border-sem-border rounded-2xl p-2.5 mt-1"
                                        :disabled="busy || needsRecovery"
                                    >
                                        <option value="">Choose access</option>
                                        <option value="on">Allow read-only guests</option>
                                        <option value="off">Require the member password</option>
                                    </select>
                                    <select
                                        v-else-if="adminAction === 'set-repeat'"
                                        v-model="adminValue"
                                        aria-label="Repeater forwarding"
                                        class="input-field mt-1 w-full"
                                        :disabled="busy || needsRecovery"
                                    >
                                        <option value="">Choose on or off</option>
                                        <option value="on">On</option>
                                        <option value="off">Off</option>
                                    </select>
                                    <input
                                        v-else
                                        v-model="adminValue"
                                        :type="adminSecret && !showAdminPassword ? 'password' : 'text'"
                                        autocomplete="off"
                                        aria-label="Administrator setting value"
                                        class="block w-full bg-sem-surface-muted text-sem-fg border border-sem-border rounded-2xl p-2.5 mt-1"
                                        :disabled="busy || needsRecovery"
                                    />
                                </label>
                                <template v-if="adminSecret">
                                    <p class="text-xs text-sem-fg-muted">
                                        This password is for member logins. The administrator password is separate.
                                        Maximum 15 UTF-8 bytes.
                                    </p>
                                    <label class="block text-sm"
                                        >Confirm new room password
                                        <input
                                            v-model="adminPasswordConfirm"
                                            :type="showAdminPassword ? 'text' : 'password'"
                                            autocomplete="off"
                                            aria-label="Confirm room password"
                                            class="block w-full bg-sem-surface-muted text-sem-fg border border-sem-border rounded-2xl p-2.5 mt-1"
                                            :disabled="busy || needsRecovery"
                                        />
                                    </label>
                                    <button
                                        type="button"
                                        class="secondary-chip"
                                        :disabled="busy || needsRecovery"
                                        :aria-pressed="showAdminPassword"
                                        @click="showAdminPassword = !showAdminPassword"
                                    >
                                        {{ showAdminPassword ? "Hide new password" : "Show new password" }}
                                    </button>
                                </template>
                                <label v-if="adminDisruptive" class="flex items-start gap-2 text-sm">
                                    <input v-model="adminConfirmed" type="checkbox" class="mt-1" />
                                    {{
                                        adminSecret
                                            ? "Change the room member password."
                                            : adminAction === "reboot"
                                              ? "Restart this server and disconnect its users."
                                              : "Changing the radio profile can make this server unreachable. A restart is needed to apply it."
                                    }}
                                </label>
                                <p v-if="adminAction === 'sync-clock'" class="text-xs text-sem-fg-muted">
                                    Uses the connected MeshCore radio’s clock. The server will refuse to move its clock
                                    backwards.
                                </p>
                                <p
                                    v-if="['set-latitude', 'set-longitude'].includes(adminAction)"
                                    class="text-xs text-sem-fg-muted"
                                >
                                    Updates the server’s saved position. Its firmware and location-sharing settings
                                    control which position appears in adverts.
                                </p>
                                <p v-if="adminAction === 'set-read-only'" class="text-xs text-sem-fg-muted">
                                    When enabled, guests without the member password may read room posts.
                                </p>
                                <p v-if="adminAction === 'set-hash'" class="text-xs text-sem-fg-muted">
                                    Enter 1, 2, or 3 bytes. The app converts this to the firmware mode.
                                </p>
                                <button
                                    class="secondary-chip"
                                    :disabled="
                                        busy ||
                                        needsRecovery ||
                                        (adminNeedsValue && !adminValue.trim()) ||
                                        (adminDisruptive && !adminConfirmed) ||
                                        (adminSecret && (!adminPasswordValid || adminPasswordConfirm !== adminValue))
                                    "
                                >
                                    {{ adminSubmitLabel }}
                                </button>
                            </form>
                            <p v-if="adminPending" role="status" class="text-sm text-sem-fg-muted">
                                Waiting for this server…
                            </p>
                            <p v-else-if="adminResult" role="status" class="whitespace-pre-wrap break-words text-sm">
                                {{ adminResult }}
                            </p>
                        </div>
                    </details>
                </div>
                <MeshCoreRepeaterConsole
                    :key="`${snapshot.owner}:${snapshot.radio_id}:${snapshot.connection_id}:${node.peer}`"
                    :request="repeaterRequest"
                    :disabled="busy || needsRecovery || !snapshot.connected"
                />
            </section>
        </section>
        <section
            v-if="node.kind === 3"
            v-show="activeTab === 'messages'"
            :id="panelId('messages')"
            class="space-y-4"
            aria-label="Room conversation"
        >
            <h3 class="font-semibold">Room messages · MeshCore</h3>
            <button v-if="!verified" type="button" class="primary-chip" @click="activeTab = 'access'">
                Log in to post
            </button>
            <p v-if="roomPositionError" role="alert" class="text-sm text-sem-danger">{{ roomPositionError }}</p>
            <p class="text-xs text-sem-fg-muted">Shared with room members.</p>
            <details class="text-xs text-sem-fg-muted">
                <summary class="cursor-pointer">About author names</summary>
                <p class="mt-2">
                    The server supplies a short author key prefix. A unique saved MeshCore contact match shows its name.
                    This is a display hint, not verified identity; ambiguous matches keep the prefix.
                </p>
            </details>
            <div
                ref="roomList"
                class="space-y-3 max-h-96 overflow-y-auto"
                aria-label="MeshCore room messages"
                @scroll.passive="onRoomScroll"
            >
                <p v-if="!rows.length" class="text-sm text-sem-fg-muted">
                    No saved room posts yet. Log in to receive available posts.
                </p>
                <article
                    v-for="row in roomRows"
                    :key="row.id"
                    :data-message-id="row.id"
                    class="border border-sem-border rounded-2xl p-3"
                    :class="row.direction === 'out' ? 'ml-6 bg-sem-bubble-outbound/10' : 'mr-6 bg-sem-surface'"
                >
                    <p class="text-xs text-sem-fg-muted">
                        {{ row.direction === "out" ? "You" : author(row).label }}
                        <span v-if="row.direction !== 'out' && author(row).matched">
                            · {{ author(row).prefix }} · contact match</span
                        >
                    </p>
                    <p v-if="row.id === roomFirstUnreadId" class="text-xs font-semibold text-sem-accent mb-2">
                        New messages
                    </p>
                    <p class="whitespace-pre-wrap break-words">{{ row.text }}</p>
                    <p class="text-xs text-sem-fg-muted">
                        {{ new Date(row.created * 1000).toLocaleString() }} ·
                        {{ row.direction === "in" ? "Received via room server" : states[row.state] || row.state }}
                    </p>
                    <button
                        v-if="row.direction === 'in'"
                        type="button"
                        class="secondary-chip mt-2"
                        :disabled="busy || needsRecovery || !verified"
                        @click="reply(row)"
                    >
                        Reply
                    </button>
                </article>
            </div>
            <button v-if="roomHasNewer" class="secondary-chip" :disabled="roomLoading" @click="loadRoomNewer">
                Show newer messages
            </button>
            <p v-if="verified" class="text-xs text-sem-fg-muted">
                Room stopped responding after a server restart?
                <button type="button" class="underline" @click="activeTab = 'access'">Open login controls</button>
                to log out and log in again. Check previous post receipts before repeating a post.
            </p>
            <form class="space-y-2" @submit.prevent="send">
                <div v-if="replyTo" class="border-l-2 border-sem-accent pl-3 text-sm" role="status">
                    <p>Replying to {{ replyTo.label }} · visible to everyone in this room</p>
                    <p class="whitespace-pre-wrap break-words text-sem-fg-muted">{{ replyTo.header }}</p>
                    <button type="button" class="secondary-chip" @click="replyTo = null">Cancel reply</button>
                </div>
                <label class="text-sm"
                    >Post to {{ node.name
                    }}<textarea
                        ref="composer"
                        v-model="draft"
                        rows="3"
                        class="bg-sem-surface-muted border border-sem-border text-sm rounded-2xl focus:ring-2 focus:ring-sem-focus block w-full p-2.5 text-sem-fg mt-1"
                        :disabled="busy || needsRecovery || !snapshot.connected || !verified"
                    />
                </label>
                <div class="flex items-center justify-between">
                    <span class="text-xs text-sem-fg-muted">{{ bytes }}/160 bytes</span
                    ><button
                        class="primary-chip"
                        :disabled="
                            busy || needsRecovery || !verified || !snapshot.connected || !draft.trim() || bytes > 160
                        "
                    >
                        Send to room
                    </button>
                </div>
            </form>
        </section>
    </div>
</template>
<script setup>
import MeshCoreRepeaterConsole from "./MeshCoreRepeaterConsole.vue";
import { roomReply, roomPostText } from "../../js/meshcoreRoomReply";
import { roomAuthor } from "../../js/meshcoreRoomAuthor";
import { useMeshCoreMessagePosition } from "../../js/meshcoreMessagePosition";
import { computed, nextTick, ref, watch, onBeforeUnmount } from "vue";
import MeshCoreNodePasswords from "./MeshCoreNodePasswords.vue";
const vaultAvailable = ref(null),
    rememberPassword = ref(false),
    passwordRefresh = ref(0);
import { apiPath } from "../../js/constants";
const props = defineProps({
    node: { type: Object, required: true },
    snapshot: { type: Object, required: true },
    visit: { type: String, default: "" },
});
const emit = defineEmits(["changed", "busy"]);
const activeTab = ref(props.node.kind === 3 ? "messages" : "status");
const nodeTabs = computed(() => [
    ...(props.node.kind === 3 ? [{ id: "messages", label: "Messages" }] : []),
    { id: "status", label: props.node.kind === 3 ? "Status" : "Overview" },
    { id: "access", label: "Access" },
    { id: "manage", label: "Manage" },
]);
const panelId = (tab) => `meshcore-node-${props.node.peer}-${tab}`;
watch([() => props.node.peer, () => props.node.kind, () => props.snapshot.owner, () => props.snapshot.radio_id], () => {
    activeTab.value = props.node.kind === 3 ? "messages" : "status";
});
const showPassword = ref(false);
const adminAction = ref(""),
    adminValue = ref(""),
    adminConfirmed = ref(false),
    adminResult = ref(""),
    adminPending = ref(false);
const adminPasswordConfirm = ref(""),
    showAdminPassword = ref(false);
const adminSecret = computed(() => adminAction.value === "set-room-password");
const adminPasswordValid = computed(
    () =>
        adminValue.value.length > 0 &&
        adminValue.value === adminValue.value.trim() &&
        new TextEncoder().encode(adminValue.value).length <= 15 &&
        !/[\0\r\n]/.test(adminValue.value)
);
const adminOptions = computed(() => [
    ["version", "View firmware version"],
    ["board", "View hardware"],
    ["name", "View server name"],
    ["radio", "View radio profile"],
    ["tx", "View TX power"],
    ["hash", "View path hash size"],
    ["set-name", "Change server name"],
    ["set-radio", "Change radio profile"],
    ["set-tx", "Change TX power"],
    ["set-hash", "Change path hash size"],
    ...(props.node.kind === 2
        ? [
              ["repeat", "View repeat setting"],
              ["set-repeat", "Change repeat setting"],
          ]
        : []),
    ["clock", "View server clock"],
    ["sync-clock", "Sync server clock to radio"],
    ["latitude", "View saved latitude"],
    ["longitude", "View saved longitude"],
    ["set-latitude", "Change saved latitude"],
    ["set-longitude", "Change saved longitude"],
    ["local-interval", "View local advert interval"],
    ["set-local-interval", "Change local advert interval"],
    ["flood-interval", "View flood advert interval"],
    ["set-flood-interval", "Change flood advert interval"],
    ["advert", "Send server advert"],
    ...(props.node.kind === 3
        ? [
              ["room-post", "Post as room server"],
              ["set-room-password", "Change room password (non-administrator)"],
              ["room-access", "View read-only guest access"],
              ["set-read-only", "Change read-only guest access"],
          ]
        : []),
    ["reboot", "Restart server"],
]);
const adminGroups = computed(() =>
    [
        {
            label: "Identity & location",
            actions: ["version", "board", "name", "set-name", "latitude", "longitude", "set-latitude", "set-longitude"],
        },
        {
            label: "Radio & routing",
            actions: ["radio", "tx", "hash", "set-radio", "set-tx", "set-hash", "repeat", "set-repeat"],
        },
        {
            label: "Advertisements & clock",
            actions: [
                "clock",
                "sync-clock",
                "local-interval",
                "set-local-interval",
                "flood-interval",
                "set-flood-interval",
                "advert",
            ],
        },
        {
            label: "Room access & announcements",
            actions: ["room-post", "set-room-password", "room-access", "set-read-only"],
        },
        { label: "Restart", actions: ["reboot"] },
    ]
        .map((group) => ({
            label: group.label,
            options: adminOptions.value.filter(([action]) => group.actions.includes(action)),
        }))
        .filter((group) => group.options.length)
);
const adminNeedsValue = computed(() => adminAction.value.startsWith("set-") || adminAction.value === "room-post");
const adminDisruptive = computed(() => ["set-radio", "reboot", "set-room-password"].includes(adminAction.value));
const adminSubmitLabel = computed(
    () =>
        ({
            "set-repeat": "Save repeat setting",
            "set-room-password": "Save room password",
            "room-post": "Post announcement",
            reboot: "Confirm restart",
        })[adminAction.value] || "Save setting"
);
const adminValueLabel = computed(
    () =>
        ({
            "set-latitude": "Latitude (-90 to 90 degrees)",
            "set-longitude": "Longitude (-180 to 180 degrees)",
            "set-local-interval": "Local adverts: minutes (0 off; 60–240 in two-minute steps)",
            "set-flood-interval": "Flood adverts: hours (0 off; 3–168)",
            "set-room-password": "New room member password",
            "set-read-only": "Read-only guest access",
            "set-name": "Server name (31 UTF-8 bytes maximum)",
            "set-radio": "Frequency MHz, bandwidth kHz, SF, CR (5–8)",
            "set-tx": "TX power in dBm (1–22)",
            "set-hash": "Path hash size in bytes",
            "set-repeat": "Repeater forwarding",
            "room-post": "Server announcement (140 UTF-8 bytes maximum)",
        })[adminAction.value] || "Value"
);
function clearAdminPassword() {
    adminValue.value = "";
    adminPasswordConfirm.value = "";
    showAdminPassword.value = false;
}
watch(activeTab, (tab, previous) => {
    if (previous === "access") {
        password.value = "";
        showPassword.value = false;
    }
    if (previous === "manage" && adminSecret.value) clearAdminPassword();
});
watch(adminAction, () => {
    clearAdminPassword();
    adminConfirmed.value = false;
    adminResult.value = "";
});
const password = ref(""),
    draft = ref(""),
    busy = ref(false),
    notice = ref(""),
    problem = ref(""),
    status = ref(null),
    uncertain = ref(false);
let generation = 0,
    stopped = false;
const verified = computed(
    () => props.snapshot.connected && props.snapshot.node_sessions?.[props.node.peer]?.state === "verified"
);
watch(verified, (loggedIn) => {
    if (loggedIn) {
        password.value = "";
        showPassword.value = false;
    }
});
const needsRecovery = computed(
    () =>
        uncertain.value ||
        (!["route", "admin"].includes(props.snapshot.node_operations?.[props.node.peer]?.operation) &&
            ["server_timeout", "radio_unconfirmed", "retry_blocked"].includes(
                props.snapshot.node_operations?.[props.node.peer]?.stage
            ))
);
const administrator = computed(
    () => verified.value && props.snapshot.node_sessions?.[props.node.peer]?.is_admin === true
);
watch(administrator, () => clearAdminPassword());
const rows = computed(() =>
    [...(props.snapshot.messages || [])]
        .filter((row) => row.peer === props.node.peer && (row.direction === "out" || payload(row).txt_type === 2))
        .sort((a, b) => a.created - b.created)
);
const roomList = ref(null);
const {
    visibleRows: roomRows,
    firstUnreadId: roomFirstUnreadId,
    hasNewer: roomHasNewer,
    loadNewer: loadRoomNewer,
    loading: roomLoading,
    onScroll: onRoomScroll,
    positionError: roomPositionError,
} = useMeshCoreMessagePosition({
    snapshot: computed(() => props.snapshot),
    target: () => (props.node.kind === 3 ? props.node.peer : ""),
    kind: "direct",
    list: roomList,
    rows,
    visit: () => props.visit,
    markRead: (through) =>
        window.api.post(apiPath("/meshcore/read"), {
            peer: props.node.peer,
            through,
            expected_owner: props.snapshot.owner,
        }),
});
const pendingPostId = ref(null);
const replyTo = ref(null),
    composer = ref(null);
const postText = computed(() => roomPostText(draft.value, replyTo.value));
const bytes = computed(() => new TextEncoder().encode(postText.value).length);
function reply(row) {
    replyTo.value = roomReply(row, author(row));
    composer.value?.focus();
}
watch([() => props.snapshot.messages, uncertain], ([messages]) => {
    if (!uncertain.value || !pendingPostId.value) return;
    const row = (messages || []).find(
        (item) => item.id === pendingPostId.value && item.peer === props.node.peer && item.direction === "out"
    );
    if (!row || !["accepted", "delivered", "unconfirmed", "rejected"].includes(row.state)) return;
    uncertain.value = false;
    pendingPostId.value = null;
    problem.value = "";
    if (row.state === "rejected") {
        notice.value = "The radio rejected the previous post. Your draft is preserved.";
    } else {
        draft.value = "";
        replyTo.value = null;
        notice.value = "The previous post is recorded in room history. It was not sent again.";
    }
});
const states = {
    accepted: "Accepted by radio · awaiting room receipt",
    delivered: "Acknowledged by room server",
    unconfirmed: "No room receipt",
    submitting: "Submitting",
    unknown: "Result uncertain",
    rejected: "Rejected by radio",
};
function payload(row) {
    try {
        return JSON.parse(row.payload || "{}").event || {};
    } catch {
        return {};
    }
}
function author(row) {
    return roomAuthor(payload(row).signature, props.snapshot.contacts);
}
function operationLabel(stage) {
    return (
        {
            sending: "Sending to radio",
            waiting_for_clock: "Waiting for radio clock before sending",
            admin_response: "Administrator response received",
            restart_submitted: "Restart submitted",
            waiting_for_server: "Waiting for this server",
            radio_rejected: "Radio rejected request",
            radio_unconfirmed: "Radio did not confirm transmission",
            server_timeout: "No matching server response before timeout",
            admin_unverified_response: "Reply could not be matched to a command",
            server_denied: "Server denied login",
            login_verified: "Login verified",
            status_received: "Status received",
            route_received: "Route response received",
            local_error: "Local request failed",
            contact_check_failed: "Contact validation failed",
            retry_blocked: "Reconnect required after an uncertain request",
        }[stage] || "Unknown"
    );
}
function label(key) {
    return (
        {
            bat: "Battery (mV)",
            battery_millivolts: "Battery (mV)",
            battery_mv: "Battery (mV)",
            tx_queue_len: "Queued transmissions",
            noise_floor: "Noise floor (dBm)",
            last_rssi: "Last signal (dBm)",
            nb_recv: "Received packets",
            nb_sent: "Sent packets",
            airtime: "Transmit airtime (seconds)",
            uptime: "Uptime (seconds)",
            uptime_seconds: "Uptime (seconds)",
            last_snr: "Last SNR (dB)",
            full_evts: "Error flags",
            rx_airtime: "Receive airtime (seconds)",
        }[key] || key.replaceAll("_", " ")
    );
}
const autoLoginEnabled = ref(false);
const autoLoginScope = computed(() => {
    const { owner, radio_id: radioId } = props.snapshot;
    const { kind, peer } = props.node;
    if (kind !== 3 || !/^[0-9a-f]{64}$/i.test(owner || "") || !/^[0-9a-f]{64}$/i.test(peer)) return "";
    return `meshchat-next.room-auto-login:${JSON.stringify([owner, radioId || "default", peer])}`;
});
let lastAutoLoginAttempt = "";
const repeaterAutoLoginPaused = ref(false);
watch([() => props.node.peer, () => props.visit], () => {
    repeaterAutoLoginPaused.value = false;
    lastAutoLoginAttempt = "";
});
function savedAutoLogin(scope) {
    try {
        return localStorage.getItem(scope) === "1";
    } catch {
        return false;
    }
}
function setAutoLogin(enabled) {
    const scope = autoLoginScope.value;
    if (!scope) return;
    try {
        if (enabled) localStorage.setItem(scope, "1");
        else localStorage.removeItem(scope);
        autoLoginEnabled.value = enabled;
    } catch {
        problem.value = "Could not save the automatic room login preference.";
    }
}
watch(
    autoLoginScope,
    (scope) => {
        autoLoginEnabled.value = Boolean(scope && savedAutoLogin(scope));
    },
    { immediate: true }
);
function logout() {
    if (props.node.kind === 2) repeaterAutoLoginPaused.value = true;
    else setAutoLogin(false);
    return operate("node-logout");
}
async function operate(action, extra = {}) {
    if (busy.value || (needsRecovery.value && action !== "node-route") || !props.snapshot.connected) return;
    busy.value = true;
    emit("busy", true);
    problem.value = "";
    notice.value = "";
    const token = generation,
        owner = props.snapshot.owner,
        peer = props.node.peer;
    const automatic = action === "node-auto-login" || action === "repeater-auto-login";
    try {
        const { data } = await window.api.post(
            apiPath(`/meshcore/${action}`),
            { peer, expected_owner: owner, ...extra },
            { timeout: 150000, ...(props.snapshot.radio_id ? { params: { radio: props.snapshot.radio_id } } : {}) }
        );
        if (stopped || token !== generation) return;
        const result = data.result;
        if (action === "node-login" && result.state === "verified") {
            passwordRefresh.value++;
            if (result.password_saved === false)
                problem.value = "Login succeeded, but the password could not be saved securely.";
        }
        if (automatic && result.state === "password_storage_unavailable") {
            notice.value = "Secure password storage is unavailable. Log in under Access.";
            return result;
        }
        if (automatic && result.state === "no_saved_password") {
            notice.value =
                props.node.kind === 2
                    ? "Save a password under Access to log in automatically next time."
                    : "Save a member password under Access to enable automatic login.";
            return result;
        }
        if (result.state === "route_received") {
            notice.value =
                result.out_hops === 0 && result.in_hops === 0
                    ? "Direct connection · no repeaters. Route check completed; login status unchanged."
                    : `Route confirmed: ${result.out_hops} outbound / ${result.in_hops} inbound repeater hops. Login status unchanged.`;
        } else if (action === "node-status" && result.state === "received") {
            status.value = result;
            notice.value = "Status received from this node.";
        } else if (result.state === "verified")
            notice.value = result.is_admin ? "Login verified · administrator." : "Login verified.";
        else if (result.state === "denied") problem.value = "The server denied this login.";
        else if (action === "room-message" && result.state === "not_sent")
            problem.value = `Post was not sent. ${result.reason || "Check the connection before trying again."}`;
        else if (result.state === "rejected") problem.value = "The radio rejected the request.";
        else if (result.state === "uncertain" || result.state === "unknown") {
            problem.value =
                action === "node-route"
                    ? "No route response received. This does not confirm the repeater is offline; you can still try logging in."
                    : action === "room-message"
                      ? "The post could not be verified and may already have been sent. Inspect room history before sending anything further."
                      : action === "node-admin"
                        ? "No reply confirmed. The command may have run. Read the setting before repeating a change."
                        : "No matching server response was verified. Reconnect MeshCore before retrying this server request.";
            if (action === "room-message") uncertain.value = true;
        } else if (action === "room-message") {
            draft.value = "";
            replyTo.value = null;
            notice.value = "Post accepted by radio. Check its room receipt below.";
        } else if (action === "node-logout") notice.value = "Logout submitted; local login cleared.";
        emit("changed");
        return result;
    } catch (error) {
        if (!stopped && token === generation) {
            if (action === "node-admin" && error?.response?.status === 400) {
                problem.value = "The app rejected this request. Check your current login and setting values.";
                emit("changed");
                return;
            }
            problem.value =
                action === "node-admin"
                    ? "The command could not be verified. Check the setting before repeating a change."
                    : "The request could not be verified. Check the connection and reconnect before retrying; no automatic retry was sent.";
            const code = error?.response?.status;
            if (code) problem.value += ` (App response ${code}.)`;
            emit("changed");
            if (action === "room-message") uncertain.value = true;
        }
    } finally {
        password.value = "";
        showPassword.value = false;
        busy.value = false;
        emit("busy", false);
    }
}
async function recover() {
    if (busy.value || !needsRecovery.value) return;
    busy.value = true;
    emit("busy", true);
    try {
        const context = props.snapshot.radio_id ? { params: { radio: props.snapshot.radio_id } } : {};
        const { data: saved } = props.snapshot.radio_id
            ? await window.api.get(apiPath("/meshcore/status"), context)
            : await window.api.get(apiPath("/meshcore/status"));
        if (!saved.connection) throw new Error("No selected radio");
        if (props.snapshot.radio_id) await window.api.post(apiPath("/meshcore/disconnect"), {}, context);
        else await window.api.post(apiPath("/meshcore/disconnect"), {});
        await window.api.post(
            apiPath("/meshcore/connect"),
            { ...saved.connection, receive: saved.receiving, auto_reconnect: saved.auto_reconnect },
            { timeout: 150000, ...context }
        );
        uncertain.value = false;
        problem.value = "";
        notice.value = autoLoginEnabled.value ? "MeshCore reconnected." : "MeshCore reconnected. Log in again.";
        emit("changed");
    } catch {
        problem.value = "MeshCore could not reconnect. Check the radio in MeshCore settings.";
    } finally {
        busy.value = false;
        emit("busy", false);
    }
}
async function login() {
    if (verified.value || needsRecovery.value) return;
    const value = password.value;
    password.value = "";
    showPassword.value = false;
    await operate("node-login", { password: value, ...(rememberPassword.value ? { remember: true } : {}) });
}
async function repeaterRequest(action, value = "", confirmed = false) {
    if (!administrator.value) throw new Error("Log in as administrator first.");
    const result = await operate("node-admin", { action, value, confirmed });
    if (action === "terminal" && result?.state === "admin_unverified_response")
        return `Unverified reply (may be from an earlier command): ${result.text}`;
    if (result?.state !== "admin_response")
        throw new Error(
            "No verified response. Check the connection before continuing; changes may already have applied."
        );
    return result.text || "";
}
async function chooseAdminAction(action) {
    if (!administrator.value || busy.value || needsRecovery.value) return;
    adminAction.value = action;
    await nextTick();
    if (!adminNeedsValue.value && !adminDisruptive.value) await administer();
}
async function administer() {
    if (!administrator.value || busy.value || needsRecovery.value || !adminAction.value) return;
    if ((adminNeedsValue.value && !adminValue.value.trim()) || (adminDisruptive.value && !adminConfirmed.value)) return;
    if (adminSecret.value && (!adminPasswordValid.value || adminPasswordConfirm.value !== adminValue.value)) return;
    adminResult.value = "";
    adminPending.value = true;
    const token = generation,
        action = adminAction.value,
        value = adminValue.value,
        confirmed = adminConfirmed.value;
    if (adminSecret.value) clearAdminPassword();
    try {
        const result = await operate("node-admin", { action, value, confirmed });
        if (token !== generation || stopped) return;
        if (["admin_response", "submitted"].includes(result?.state))
            adminResult.value = result.text || "Server returned an empty response.";
        else if (result?.state === "admin_unverified_response")
            adminResult.value = `Unverified reply (may be from an earlier command): ${result.text}`;
        adminConfirmed.value = false;
    } finally {
        adminPending.value = false;
    }
}
async function send() {
    if (!verified.value || uncertain.value || !draft.value.trim() || bytes.value > 160) return;
    pendingPostId.value = crypto.randomUUID();
    await operate("room-message", { text: postText.value, request_id: pendingPostId.value });
}
watch(
    [
        () => props.snapshot.owner,
        () => props.snapshot.radio_id,
        () => props.snapshot.connected,
        () => props.snapshot.connection_id,
        () => props.node.peer,
    ],
    () => {
        ++generation;
        rememberPassword.value = false;
        vaultAvailable.value = null;
        password.value = "";
        showPassword.value = false;
        draft.value = "";
        replyTo.value = null;
        pendingPostId.value = null;
        status.value = null;
        notice.value = "";
        problem.value = "";
        uncertain.value = false;
        clearAdminPassword();
        adminAction.value = "";
        adminResult.value = "";
        adminConfirmed.value = false;
    }
);
watch(
    [
        autoLoginScope,
        autoLoginEnabled,
        repeaterAutoLoginPaused,
        () => props.node.kind,
        () => props.node.peer,
        () => props.visit,
        () => props.snapshot.owner,
        () => props.snapshot.radio_id,
        () => props.snapshot.connection_id,
        () => props.snapshot.connected,
        verified,
        needsRecovery,
        busy,
    ],
    () => {
        const repeater = props.node.kind === 2;
        const { owner, radio_id: radio, connection_id: connection } = props.snapshot;
        const scope = repeater
            ? owner && JSON.stringify([owner, radio, props.node.peer, props.visit])
            : autoLoginScope.value;
        if (!scope || !connection || !props.snapshot.connected || busy.value || needsRecovery.value || password.value)
            return;
        if (repeater ? repeaterAutoLoginPaused.value : !autoLoginEnabled.value || !savedAutoLogin(scope)) return;
        const attempt = JSON.stringify([scope, connection]);
        if (attempt === lastAutoLoginAttempt) return;
        if (verified.value) {
            if (repeater) lastAutoLoginAttempt = attempt;
            return;
        }
        lastAutoLoginAttempt = attempt;
        void operate(repeater ? "repeater-auto-login" : "node-auto-login", { expected_connection_id: connection });
    },
    { immediate: true, flush: "post" }
);
onBeforeUnmount(() => {
    clearAdminPassword();
    stopped = true;
    ++generation;
    password.value = "";
    showPassword.value = false;
    emit("busy", false);
});
</script>
