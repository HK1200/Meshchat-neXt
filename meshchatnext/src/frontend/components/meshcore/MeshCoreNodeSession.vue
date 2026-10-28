<template>
    <div class="space-y-4 border-t border-sem-border pt-4">
        <p class="text-sm text-sem-fg-muted">
            {{ snapshot.connected ? "MeshCore radio connected" : "Disconnected · saved history" }} ·
            {{ administrator ? "Administrator login verified" : verified ? "Member login verified" : "Not logged in" }}
        </p>
        <p class="text-xs text-sem-fg-muted">
            {{
                node.kind === 3
                    ? "Room login remains active for this MeshCore connection, until logout or a confirmed disconnection."
                    : "Repeater login is remembered for five minutes in this app session."
            }}
            Passwords are only saved when you explicitly choose secure storage below.
        </p>
        <form class="flex flex-wrap items-end gap-2" @submit.prevent="login">
            <label v-if="!verified" class="text-sm w-full min-w-0"
                >Server password
                <input
                    v-model="password"
                    :type="showPassword ? 'text' : 'password'"
                    autocomplete="off"
                    class="bg-sem-surface-muted border border-sem-border text-sm rounded-2xl focus:ring-2 focus:ring-sem-focus block w-full p-2.5 text-sem-fg mt-1"
                    :disabled="busy || needsRecovery || !snapshot.connected"
                    aria-label="MeshCore server password"
                />
            </label>
            <button
                v-if="!verified"
                type="button"
                class="secondary-chip"
                :aria-pressed="showPassword"
                :disabled="busy || needsRecovery || !snapshot.connected"
                @click="showPassword = !showPassword"
            >
                {{ showPassword ? "Hide password" : "Show password" }}
            </button>
            <button v-if="!verified" class="primary-chip" :disabled="busy || needsRecovery || !snapshot.connected">
                {{ busy ? "Working…" : "Log in" }}
            </button>
            <button
                v-if="verified"
                type="button"
                class="secondary-chip"
                :disabled="busy || needsRecovery || !snapshot.connected || !verified"
                @click="operate('node-logout')"
            >
                Log out
            </button>
        </form>
        <MeshCoreNodePasswords
            :owner="snapshot.owner"
            :peer="node.peer"
            :disabled="busy || !snapshot.connected"
            :can-login="!verified && !needsRecovery"
            :refresh-key="passwordRefresh"
            @use-saved="operate('node-login', { use_saved_role: $event })"
            @available="vaultAvailable = $event"
        />
        <label v-if="!verified && vaultAvailable" class="flex items-center gap-2 text-sm"
            ><input v-model="rememberPassword" type="checkbox" :disabled="busy" />Save password securely after
            successful login</label
        >
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
        <button
            class="secondary-chip"
            :disabled="busy || needsRecovery || !snapshot.connected || !verified"
            @click="operate('node-status')"
        >
            Request status
        </button>
        <button
            class="secondary-chip"
            :disabled="busy || needsRecovery || !snapshot.connected"
            @click="operate('node-route')"
        >
            Check route
        </button>
        <dl v-if="status" class="grid grid-cols-2 gap-2 text-sm">
            <template v-for="(value, key) in status.values" :key="key"
                ><dt class="text-sem-fg-muted">{{ label(key) }}</dt>
                <dd>{{ value }}</dd></template
            >
        </dl>
        <section
            v-if="administrator"
            class="space-y-3 border-t border-sem-border pt-4"
            aria-label="MeshCore administrator controls"
        >
            <h3 class="font-semibold">Administrator · MeshCore</h3>
            <p class="text-xs text-sem-fg-muted">Manage this server using your verified administrator login.</p>
            <form class="space-y-3" @submit.prevent="administer">
                <label class="block text-sm"
                    >Server action
                    <select
                        v-model="adminAction"
                        class="block w-full bg-sem-surface-muted text-sem-fg border border-sem-border rounded-2xl p-2.5 mt-1"
                        :disabled="busy || needsRecovery"
                    >
                        <option v-for="item in adminOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option>
                    </select>
                </label>
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
                        This password is for member logins. The administrator password is separate. Maximum 15 UTF-8
                        bytes.
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
                    Uses the connected MeshCore radio’s clock. The server will refuse to move its clock backwards.
                </p>
                <p v-if="['set-latitude', 'set-longitude'].includes(adminAction)" class="text-xs text-sem-fg-muted">
                    Updates the server’s saved position. Its firmware and location-sharing settings control which
                    position appears in adverts.
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
                    Run server action
                </button>
            </form>
            <p v-if="adminResult" role="status" class="whitespace-pre-wrap break-words text-sm">{{ adminResult }}</p>
        </section>
        <template v-if="node.kind === 3">
            <h3 class="font-semibold">Room messages · MeshCore</h3>
            <p v-if="roomPositionError" role="alert" class="text-sm text-sem-danger">{{ roomPositionError }}</p>
            <p class="text-xs text-sem-fg-muted">
                Posts are shared with room members. Received posts identify their author by a short key prefix supplied
                by the server.
            </p>
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
                    <p class="text-xs text-sem-fg-muted">{{ row.direction === "out" ? "You" : author(row) }}</p>
                    <p v-if="row.id === roomFirstUnreadId" class="text-xs font-semibold text-sem-accent mb-2">
                        New messages
                    </p>
                    <p class="whitespace-pre-wrap break-words">{{ row.text }}</p>
                    <p class="text-xs text-sem-fg-muted">
                        {{ new Date(row.created * 1000).toLocaleString() }} ·
                        {{ row.direction === "in" ? "Received via room server" : states[row.state] || row.state }}
                    </p>
                </article>
            </div>
            <button v-if="roomHasNewer" class="secondary-chip" :disabled="roomLoading" @click="loadRoomNewer">
                Show newer messages
            </button>
            <form class="space-y-2" @submit.prevent="send">
                <label class="text-sm"
                    >Post to {{ node.name }} via MeshCore<textarea
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
        </template>
    </div>
</template>
<script setup>
import { useMeshCoreMessagePosition } from "../../js/meshcoreMessagePosition";
import { computed, ref, watch, onBeforeUnmount } from "vue";
import MeshCoreNodePasswords from "./MeshCoreNodePasswords.vue";
const vaultAvailable = ref(false),
    rememberPassword = ref(false),
    passwordRefresh = ref(0);
import { apiPath } from "../../js/constants";
const props = defineProps({
    node: { type: Object, required: true },
    snapshot: { type: Object, required: true },
    visit: { type: String, default: "" },
});
const emit = defineEmits(["changed", "busy"]);
const showPassword = ref(false);
const adminAction = ref("version"),
    adminValue = ref(""),
    adminConfirmed = ref(false),
    adminResult = ref(""),
    adminUncertain = ref(false);
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
const adminNeedsValue = computed(() => adminAction.value.startsWith("set-") || adminAction.value === "room-post");
const adminDisruptive = computed(() => ["set-radio", "reboot", "set-room-password"].includes(adminAction.value));
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
            "room-post": "Server announcement (140 UTF-8 bytes maximum)",
        })[adminAction.value] || "Value"
);
function clearAdminPassword() {
    adminValue.value = "";
    adminPasswordConfirm.value = "";
    showAdminPassword.value = false;
}
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
        adminUncertain.value ||
        uncertain.value ||
        (props.snapshot.node_operations?.[props.node.peer]?.operation !== "route" &&
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
const bytes = computed(() => new TextEncoder().encode(draft.value).length);
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
    const key = payload(row).signature;
    return /^[a-f0-9]{8}$/i.test(key || "") ? `Author ${key}` : "Unknown author";
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
async function operate(action, extra = {}) {
    if (busy.value || needsRecovery.value || !props.snapshot.connected) return;
    busy.value = true;
    emit("busy", true);
    problem.value = "";
    notice.value = "";
    const token = generation,
        owner = props.snapshot.owner,
        peer = props.node.peer;
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
        if (result.state === "route_received") {
            notice.value =
                result.out_hops === 0 && result.in_hops === 0
                    ? "Direct connection · no repeaters. Route check completed; login status unchanged."
                    : `Route confirmed: ${result.out_hops} outbound / ${result.in_hops} inbound repeater hops. Login status unchanged.`;
        } else if (action === "node-admin" && ["admin_response", "submitted"].includes(result.state)) {
            adminResult.value = result.text || "Server returned an empty response.";
        } else if (action === "node-status" && result.state === "received") {
            status.value = result;
            notice.value = "Status received from this node.";
        } else if (result.state === "verified")
            notice.value = result.is_admin ? "Login verified · administrator." : "Login verified.";
        else if (result.state === "denied") problem.value = "The server denied this login.";
        else if (result.state === "rejected") problem.value = "The radio rejected the request.";
        else if (result.state === "uncertain" || result.state === "unknown") {
            problem.value =
                action === "node-route"
                    ? "No route response received. This does not confirm the repeater is offline; you can still try logging in."
                    : action === "room-message"
                      ? "The post could not be verified and may already have been sent. Inspect room history before sending anything further."
                      : "No matching server response was verified. Reconnect MeshCore before retrying this server request.";
            if (action === "node-admin") adminUncertain.value = true;
            if (action === "room-message") uncertain.value = true;
        } else if (action === "room-message") {
            draft.value = "";
            notice.value = "Post accepted by radio. Check its room receipt below.";
        } else if (action === "node-logout") notice.value = "Logout submitted; local login cleared.";
        emit("changed");
    } catch (error) {
        if (!stopped && token === generation) {
            if (action === "node-admin" && error?.response?.status === 400) {
                problem.value = "The app rejected this request. Check your current login and setting values.";
                emit("changed");
                return;
            }
            problem.value =
                "The request could not be verified. Check the connection and reconnect before retrying; no automatic retry was sent.";
            const code = error?.response?.status;
            if (code) problem.value += ` (App response ${code}.)`;
            emit("changed");
            if (action === "node-admin") adminUncertain.value = true;
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
        adminUncertain.value = false;
        uncertain.value = false;
        problem.value = "";
        notice.value = "MeshCore reconnected. Log in again.";
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
async function administer() {
    if (!administrator.value || adminUncertain.value || (adminDisruptive.value && !adminConfirmed.value)) return;
    if (adminSecret.value && (!adminPasswordValid.value || adminPasswordConfirm.value !== adminValue.value)) return;
    adminResult.value = "";
    const action = adminAction.value,
        value = adminValue.value,
        confirmed = adminConfirmed.value;
    if (adminSecret.value) clearAdminPassword();
    await operate("node-admin", { action, value, confirmed });
    adminConfirmed.value = false;
}
async function send() {
    if (!verified.value || uncertain.value || !draft.value.trim() || bytes.value > 160) return;
    await operate("room-message", { text: draft.value, request_id: crypto.randomUUID() });
}
watch(
    [
        () => props.snapshot.owner,
        () => props.snapshot.connected,
        () => props.snapshot.connection_id,
        () => props.node.peer,
    ],
    () => {
        ++generation;
        rememberPassword.value = false;
        vaultAvailable.value = false;
        password.value = "";
        showPassword.value = false;
        draft.value = "";
        status.value = null;
        notice.value = "";
        problem.value = "";
        uncertain.value = false;
        clearAdminPassword();
        adminResult.value = "";
        adminConfirmed.value = false;
        adminUncertain.value = false;
    }
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
