<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <section class="space-y-4 py-4 text-sem-fg" :aria-label="mode === 'settings' ? 'SIP settings' : 'SIP telephone'">
        <div v-if="mode === 'phone'" class="rounded-xl border border-sem-border bg-sem-surface p-4 space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <p role="status" class="text-sm">
                    SIP · {{ statusLabel }}<span v-if="state.network"> · {{ state.network }}</span>
                </p>
                <div class="flex gap-2 items-center">
                    <button
                        v-if="!state.registered && state.available && state.selected"
                        type="button"
                        class="secondary-chip"
                        :disabled="busy || ['starting', 'registering'].includes(state.state)"
                        @click="run('connect', { id: state.selected })"
                    >
                        Reconnect
                    </button>
                    <RouterLink :to="{ name: 'sip-settings' }" class="text-sm text-sem-accent">SIP settings</RouterLink>
                </div>
            </div>
            <p v-if="!state.accounts.length" class="text-sm text-sem-fg-muted">
                Add your extension and password in SIP settings to get started.
            </p>
            <div v-if="state.call_state !== 'idle'" class="space-y-3">
                <p role="status" class="font-semibold">SIP · {{ state.call_state }} · {{ state.peer }}</p>
                <div class="flex flex-wrap gap-2">
                    <button
                        v-if="state.call_state === 'incoming'"
                        class="primary-chip"
                        type="button"
                        @click="run('answer')"
                    >
                        Answer SIP call</button
                    ><button class="secondary-chip text-sem-danger" type="button" @click="run('hangup')">
                        End SIP call</button
                    ><button
                        class="secondary-chip"
                        type="button"
                        :aria-pressed="state.muted"
                        @click="run('mute', { value: !state.muted })"
                    >
                        {{ state.muted ? "Unmute" : "Mute" }}</button
                    ><button
                        class="secondary-chip"
                        type="button"
                        :aria-pressed="state.speaker"
                        @click="run('speaker', { value: !state.speaker })"
                    >
                        Speaker {{ state.speaker ? "on" : "off" }}
                    </button>
                </div>
            </div>
            <form v-else class="flex flex-wrap gap-2" @submit.prevent="run('call', { target })">
                <label class="text-sm flex-1 min-w-0"
                    >SIP extension or address<input
                        v-model="target"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                        placeholder="Extension or sip:user@server" /></label
                ><button
                    class="primary-chip self-end"
                    type="submit"
                    :disabled="!state.registered || selected !== state.selected || !target.trim()"
                >
                    Call via SIP
                </button>
            </form>
            <div class="grid grid-cols-3 gap-2 max-w-xs mx-auto" aria-label="SIP keypad">
                <button
                    v-for="digit in '123456789*0#'"
                    :key="digit"
                    class="secondary-chip justify-center py-3 text-lg"
                    type="button"
                    @click="keypad(digit)"
                >
                    {{ digit }}
                </button>
            </div>
        </div>
        <div v-if="mode === 'settings'" class="rounded-xl border border-sem-border bg-sem-surface p-4 space-y-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
                <h2 class="font-semibold">SIP · HOIP</h2>
                <span class="text-sm" role="status">{{ statusLabel }}</span>
            </div>
            <p v-if="!state.available" class="text-sm text-sem-fg-muted">
                {{
                    state.error || "SIP calling is available in the Android app. Account passwords stay on that device."
                }}
            </p>
            <div v-else class="space-y-3">
                <button type="button" class="secondary-chip" @click="edit(null)">Add account</button>
                <label class="flex items-center gap-2 text-sm"
                    ><input
                        type="checkbox"
                        :checked="state.enabled"
                        :disabled="busy || (!selected && !state.enabled)"
                        @change="
                            run(
                                $event.target.checked ? 'connect' : 'disconnect',
                                $event.target.checked ? { id: selected, password: sessionPassword } : {}
                            )
                        "
                    />Enable SIP · reconnect automatically</label
                >
                <p class="text-xs text-sem-fg-muted">
                    Enabled SIP reconnects on launch and after connection loss. Session-only passwords must be entered
                    again after a restart.
                </p>

                <label class="block text-sm"
                    >Selected account<select
                        v-model="selected"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                    >
                        <option value="">Choose an account</option>
                        <option v-for="account in state.accounts" :key="account.id" :value="account.id">
                            {{ account.label || account.extension }} · {{ account.extension }}@{{ account.host }}:{{
                                account.port
                            }}
                        </option>
                    </select></label
                >
                <div class="flex flex-wrap gap-2">
                    <button
                        type="button"
                        class="primary-chip"
                        :disabled="!selected || busy"
                        @click="run('connect', { id: selected, password: sessionPassword })"
                    >
                        Connect SIP</button
                    ><button
                        type="button"
                        class="secondary-chip"
                        :disabled="state.state === 'disconnected'"
                        @click="run('disconnect')"
                    >
                        Disconnect SIP</button
                    ><button type="button" class="secondary-chip" :disabled="!selected" @click="edit(selectedAccount)">
                        Edit account
                    </button>
                </div>
                <label v-if="selectedAccount && !selectedAccount.has_password" class="block text-sm"
                    >Session password<input
                        v-model="sessionPassword"
                        type="password"
                        autocomplete="current-password"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                /></label>
                <p v-if="state.network" class="text-xs text-sem-fg-muted">SIP network · {{ state.network }}</p>
            </div>
            <p class="text-xs text-sem-fg-muted">
                HOIP preset · premium.hamsoverip.com:5160 · UDP. Server and port are editable for each account.
            </p>
        </div>
        <form
            v-if="form"
            class="rounded-xl border border-sem-border bg-sem-surface p-4 space-y-3"
            @submit.prevent="save"
        >
            <h3 class="font-semibold">{{ form.id ? "Edit SIP account" : "Add SIP account" }}</h3>
            <div class="grid gap-3 sm:grid-cols-2">
                <label class="text-sm"
                    >Account label<input
                        v-model="form.label"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                        maxlength="80"
                /></label>
                <label class="text-sm"
                    >Extension / username<input
                        v-model="form.extension"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                        required
                        autocomplete="username"
                        maxlength="64"
                /></label>
                <label class="text-sm"
                    >Server<input
                        v-model="form.host"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                        required
                /></label>
                <label class="text-sm"
                    >Port<input
                        v-model.number="form.port"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent block w-full"
                        type="number"
                        min="1"
                        max="65535"
                        required
                /></label>
            </div>
            <label class="block text-sm"
                >Password {{ form.id ? "(leave blank to keep existing)" : "" }}
                <div class="flex gap-2">
                    <input
                        v-model="password"
                        :type="showPassword ? 'text' : 'password'"
                        class="rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg focus:outline-none focus:ring-1 focus:ring-sem-accent min-w-0 flex-1"
                        autocomplete="new-password"
                        :required="!form.id"
                        maxlength="256"
                    /><button
                        type="button"
                        class="secondary-chip"
                        :aria-pressed="showPassword"
                        @click="showPassword = !showPassword"
                    >
                        {{ showPassword ? "Hide" : "Show" }}
                    </button>
                </div></label
            >
            <label class="flex gap-2 items-center text-sm"
                ><input v-model="form.save_password" type="checkbox" />Save password securely on this device</label
            >
            <p class="text-xs text-sem-fg-muted">
                Saved passwords use Android Keystore encryption and are excluded from backups. With saving off, re-enter
                the password after the SIP service stops.
            </p>
            <fieldset class="space-y-2">
                <legend class="text-sm mb-2">Allowed networks</legend>
                <label class="flex items-center gap-2 text-sm"
                    ><input v-model="form.allowed_networks" type="checkbox" value="wifi" />Wi-Fi</label
                >
                <label class="flex items-center gap-2 text-sm"
                    ><input v-model="form.allowed_networks" type="checkbox" value="mobile" />Mobile data</label
                >
                <label v-if="state.i2p_available" class="flex items-center gap-2 text-sm"
                    ><input v-model="form.allowed_networks" type="checkbox" value="i2p" />I2P</label
                >
            </fieldset>
            <p class="text-xs text-sem-fg-muted">
                SIP uses an available allowed network, preferring Wi-Fi. It reconnects over mobile data when Wi-Fi drops
                if both are allowed. Switching networks may end an active call.
            </p>
            <div class="flex flex-wrap gap-2">
                <button type="submit" class="primary-chip">Save account</button
                ><button type="button" class="secondary-chip" @click="cancel">Cancel</button
                ><button v-if="form.id" type="button" class="secondary-chip text-sem-danger" @click="remove">
                    Remove account
                </button>
            </div>
        </form>
        <p
            v-if="error || state.error"
            role="alert"
            class="rounded-lg border border-sem-danger p-3 text-sem-danger text-sm"
        >
            {{ error || state.error }}
        </p>
        <details v-if="state.quality?.sent || state.quality?.received" class="text-xs text-sem-fg-muted">
            <summary class="cursor-pointer">SIP call diagnostics</summary>
            <p>
                Packets sent {{ state.quality.sent }} · received {{ state.quality.received }} · lost
                {{ state.quality.lost_rx }} received / {{ state.quality.lost_tx }} sent · jitter
                {{ state.quality.jitter_ms }} ms · round trip {{ state.quality.rtt_ms }} ms
            </p>
        </details>
    </section>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { HOIP_DEFAULTS, sipState as state, refreshSip, sipCommand } from "../../js/sip";
defineProps({ mode: { type: String, default: "phone" } });
const emit = defineEmits(["busy"]);
const route = useRoute(),
    selected = ref(""),
    target = ref(String(route.query.sip_target || "")),
    form = ref(null),
    password = ref(""),
    sessionPassword = ref(""),
    showPassword = ref(false),
    error = ref(""),
    busy = ref(false);
watch(busy, (value) => emit("busy", value));
const selectedAccount = computed(() => state.accounts.find((a) => a.id === selected.value));
const statusLabel = computed(
    () =>
        ({
            unavailable: state.error ? "SIP unavailable" : "Android app required",
            starting: "Starting SIP service",
            disconnected: "Disconnected",
            registering: "Registering",
            registered: "Registered",
            waiting_for_network: "Waiting for an allowed network",
            registration_failed: "Registration failed",
        })[state.state] || state.state.replaceAll("_", " ")
);
let timer;
onMounted(() => {
    refreshSip();
    selected.value = state.selected || state.accounts[0]?.id || "";
    timer = setInterval(() => {
        refreshSip();
        if (!selected.value) selected.value = state.selected || state.accounts[0]?.id || "";
    }, 1000);
});
onBeforeUnmount(() => {
    clearInterval(timer);
    password.value = "";
    sessionPassword.value = "";
});
function edit(a) {
    error.value = "";
    password.value = "";
    showPassword.value = false;
    form.value = a
        ? {
              ...a,
              allowed_networks: a.allowed_networks
                  ? [...a.allowed_networks]
                  : a.network === "wifi_mobile"
                    ? ["wifi", "mobile"]
                    : [a.network || "wifi"],
          }
        : { ...HOIP_DEFAULTS, allowed_networks: [...HOIP_DEFAULTS.allowed_networks], label: "HOIP", extension: "" };
}
function cancel() {
    form.value = null;
    password.value = "";
    showPassword.value = false;
}
async function run(op, fields = {}) {
    busy.value = true;
    error.value = "";
    try {
        await sipCommand(op, fields);
        if (op === "connect") sessionPassword.value = "";
    } catch (e) {
        error.value = e.message;
    } finally {
        busy.value = false;
    }
}
async function save() {
    if (busy.value) return;
    busy.value = true;
    try {
        await sipCommand("save", { account: form.value, password: password.value });
        cancel();
    } catch (e) {
        error.value = e.message;
    } finally {
        busy.value = false;
    }
}
async function remove() {
    if (busy.value) return;
    busy.value = true;
    try {
        await sipCommand("remove", { id: form.value.id });
        selected.value = "";
        cancel();
    } catch (e) {
        error.value = e.message;
    } finally {
        busy.value = false;
    }
}
function keypad(digit) {
    if (state.call_state !== "idle") run("dtmf", { digit });
    else target.value += digit;
}
</script>
