<template>
    <SettingsSectionBlock
        v-if="snapshot.available"
        data-settings-section="meshcore"
        eyebrow="MeshCore"
        title="MeshCore radio"
        description="Connection and radio settings for your MeshCore companion. RNode is managed separately."
        body-class="space-y-4"
    >
        <p class="text-sm text-sem-fg-muted" role="status">
            {{ snapshot.connected ? "Connected" : "Disconnected"
            }}<span v-if="snapshot.profile_name"> · {{ snapshot.profile_name }}</span>
        </p>
        <p v-if="connectionIssue" role="status" class="text-sm text-sem-fg-muted">{{ connectionIssue }}</p>
        <p v-if="error || problem" role="alert" class="text-sm text-sem-danger">{{ problem || error }}</p>
        <p v-if="notice" role="status" class="text-sm text-sem-accent">{{ notice }}</p>
        <form class="space-y-3" @submit.prevent="connect">
            <fieldset :disabled="controlsBusy" class="grid gap-3 sm:grid-cols-2">
                <label
                    >Connection<select v-model="kind" class="input-field" @change="changeTransport">
                        <option value="ble">Bluetooth</option>
                        <option value="usb">USB</option>
                    </select></label
                >
                <label v-if="kind === 'ble'"
                    >Paired Bluetooth radio
                    <select
                        v-model="bluetoothChoice"
                        class="input-field"
                        aria-label="Paired Bluetooth radio"
                        @change="chooseBluetooth"
                    >
                        <option disabled value="">Choose a paired radio</option>
                        <option
                            v-if="
                                target &&
                                !devices.some((device) => device.address === target) &&
                                bluetoothChoice !== 'manual'
                            "
                            :value="target"
                        >
                            Selected radio · {{ target }}
                        </option>
                        <option v-for="device in devices" :key="device.address" :value="device.address">
                            {{ device.name }} · {{ device.address }}
                        </option>
                        <option value="manual">Enter address manually…</option>
                    </select>
                </label>
                <label v-if="kind === 'usb'">
                    USB radio
                    <select v-model="target" class="input-field" aria-label="USB radio">
                        <option disabled value="">Choose an attached radio</option>
                        <option v-if="target && !usbDevices.some((device) => device.path === target)" :value="target">
                            Previously selected · {{ target }}
                        </option>
                        <option v-for="device in usbDevices" :key="device.path" :value="device.path">
                            {{ device.name }} · {{ device.path }}
                        </option>
                    </select>
                </label>
                <label v-if="kind === 'ble' && bluetoothChoice === 'manual'"
                    >{{ kind === "ble" ? "Bluetooth address" : "USB device path" }}
                    <input
                        v-model="target"
                        class="input-field"
                        autocomplete="off"
                        :placeholder="kind === 'ble' ? 'AA:BB:CC:DD:EE:FF' : '/dev/bus/usb/…'"
                        required
                    />
                </label>
            </fieldset>
            <div v-if="kind === 'ble'" class="space-y-2">
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="loadingDevices || controlsBusy"
                    @click="loadDevices"
                >
                    {{ loadingDevices ? "Loading radios…" : "Refresh paired radios" }}
                </button>
                <p v-if="deviceProblem" role="alert" class="text-xs text-sem-danger">{{ deviceProblem }}</p>
                <p class="text-xs text-sem-fg-muted">
                    Pair your radio in Android Bluetooth settings, then refresh. These are paired Bluetooth devices;
                    select your MeshCore companion, not your RNode.
                </p>
            </div>
            <div v-if="kind === 'usb'" class="space-y-2">
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="loadingUsb || controlsBusy"
                    @click="loadUsbDevices"
                >
                    {{ loadingUsb ? "Loading USB radios…" : "Refresh USB radios" }}
                </button>
                <p v-if="usbProblem" role="alert" class="text-xs text-sem-danger">{{ usbProblem }}</p>
                <p class="text-xs text-sem-fg-muted">
                    Connect through an OTG cable, then select your MeshCore companion. Select your RNode separately
                    under Interfaces. Android may ask for USB permission when you connect.
                </p>
            </div>
            <div class="flex flex-wrap gap-2">
                <button class="primary-chip" :disabled="controlsBusy || snapshot.connected || !target.trim()">
                    Connect MeshCore
                </button>
                <button
                    v-if="snapshot.connected || snapshot.selected"
                    type="button"
                    class="secondary-chip"
                    :disabled="controlsBusy"
                    @click="disconnect"
                >
                    Disconnect MeshCore
                </button>
            </div>
        </form>
        <RouterLink
            v-if="!props.setupMode"
            :to="{ name: 'meshcore-tools', params: { tool: 'regions' } }"
            class="block text-sm text-sem-accent py-2"
            >MeshCore regions &amp; channel scoping</RouterLink
        >
        <MeshCoreRadio2Settings
            v-if="!props.setupMode"
            id="meshcore-radio2"
            :snapshot="snapshot"
            :disabled="busy || backupBusy || identityBusy"
            @busy="radio2Busy = $event"
        />
        <MeshCoreIdentitySettings
            v-if="!props.setupMode"
            :snapshot="snapshot"
            :disabled="busy || backupBusy || radio2Busy"
            :refresh-key="identityRefresh"
            @saved="refresh"
            @busy="identityBusy = $event"
        />
        <details :open="!props.setupMode" class="border-t border-sem-border pt-4 space-y-3">
            <summary v-if="props.setupMode" class="cursor-pointer font-medium text-sm">
                Check or change the primary radio profile
            </summary>
            <div class="flex flex-wrap items-center justify-between gap-2">
                <h3 class="font-semibold">Primary radio · MeshCore network</h3>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="controlsBusy || !snapshot.connected"
                    @click="read"
                >
                    Read from radio
                </button>
            </div>
            <p class="text-sm text-sem-fg-muted">
                Use your local network’s primary profile for messages and announces. Radio2 has its own MediaMesh
                profile; it does not need to match this primary profile.
            </p>
            <p v-if="!baseline" class="text-sm text-sem-fg-muted">
                {{
                    snapshot.connected
                        ? "Read the current settings before making changes."
                        : "Connect a MeshCore radio to read its settings."
                }}
            </p>
            <form v-else class="space-y-4" @submit.prevent="apply">
                <div class="rounded-lg border border-sem-border p-3 space-y-2">
                    <p class="text-sm font-medium">Puget Mesh / USA–Canada preset</p>
                    <p class="text-xs text-sem-fg-muted">910.525 MHz · 62.5 kHz · SF7 · CR4/5</p>
                    <p class="text-xs text-sem-fg-muted">
                        Frequency, bandwidth, and SF must match the network you are joining. Coding rate adds error
                        correction: a higher value uses more airtime. Follow your community’s recommendation when
                        choosing it.
                    </p>
                    <button
                        type="button"
                        class="secondary-chip"
                        :disabled="controlsBusy || !snapshot.connected || needsRead"
                        @click="useRegionalPreset"
                    >
                        Use Puget Mesh preset
                    </button>
                    <a
                        class="ml-2 text-xs text-sem-info underline"
                        href="https://pugetmesh.org/meshcore/#radio-settings"
                        target="_blank"
                        rel="noopener noreferrer"
                        >Published settings</a
                    >
                </div>
                <fieldset
                    :disabled="controlsBusy || !snapshot.connected || needsRead"
                    class="grid gap-3 sm:grid-cols-2"
                >
                    <label
                        >Frequency (MHz)<input
                            v-model="draft.frequency_mhz"
                            class="input-field"
                            type="number"
                            min="150"
                            max="2500"
                            step="0.001"
                            required
                    /></label>
                    <label
                        >Bandwidth (kHz)<input
                            v-model="draft.bandwidth_khz"
                            class="input-field"
                            type="number"
                            min="7"
                            max="500"
                            step="0.001"
                            required
                    /></label>
                    <label
                        >Spreading factor (SF)<select v-model.number="draft.sf" class="input-field">
                            <option v-for="sf in 8" :key="sf" :value="sf + 4">SF {{ sf + 4 }}</option>
                        </select></label
                    >
                    <label
                        >Coding rate (CR)<select v-model.number="draft.cr" class="input-field">
                            <option v-for="cr in [5, 6, 7, 8]" :key="cr" :value="cr">4/{{ cr }}</option>
                        </select></label
                    >
                    <label
                        >TX power (dBm)<input
                            v-model="draft.tx_power_dbm"
                            class="input-field"
                            type="number"
                            min="-9"
                            :max="baseline.max_tx_power_dbm"
                            step="1"
                            required
                        /><span class="block text-xs text-sem-fg-muted"
                            >Radio maximum: {{ baseline.max_tx_power_dbm }} dBm</span
                        ></label
                    >
                    <label
                        >Default path hash size<select
                            v-model.number="draft.path_hash_bytes"
                            class="input-field"
                            :disabled="!baseline.path_hash_supported"
                        >
                            <option v-if="!baseline.path_hash_supported" :value="null">
                                Unsupported by this firmware
                            </option>
                            <option v-for="size in [1, 2, 3]" :key="size" :value="size">
                                {{ size }} {{ size === 1 ? "byte" : "bytes" }}
                            </option>
                        </select></label
                    >
                </fieldset>
                <p class="text-xs text-sem-fg-muted">
                    Use settings appropriate for your radio and local network. Changes are checked against the radio
                    after saving; firmware may reject unsupported values.
                </p>
                <div class="flex flex-wrap gap-2">
                    <button class="primary-chip" :disabled="controlsBusy || !snapshot.connected || needsRead || !dirty">
                        {{ controlsBusy ? "Working…" : "Apply and verify" }}</button
                    ><button type="button" class="secondary-chip" :disabled="controlsBusy || !dirty" @click="reset">
                        Discard changes
                    </button>
                </div>
            </form>
        </details>
        <MeshCoreBackups
            v-if="!props.setupMode"
            id="meshcore-backups"
            :snapshot="snapshot"
            :disabled="busy || identityBusy || radio2Busy"
            @changed="afterImport"
            @busy="backupBusy = $event"
        />
    </SettingsSectionBlock>
</template>
<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue";
import MeshCoreRadio2Settings from "./MeshCoreRadio2Settings.vue";
import MeshCoreBackups from "./MeshCoreBackups.vue";
import MeshCoreIdentitySettings from "./MeshCoreIdentitySettings.vue";
import SettingsSectionBlock from "../settings/SettingsSectionBlock.vue";
import { useMeshCoreUi } from "../../js/meshcoreUi";
import { apiPath } from "../../js/constants";
import { isBluetoothAddress } from "../../js/meshcoreSetupBackup";
const props = defineProps({ setupMode: Boolean, suggestedConnection: { type: Object, default: null } });
const emit = defineEmits(["busy"]);
const lifetime = new AbortController();
const { snapshot, error, action, refresh } = useMeshCoreUi();
const kind = ref("ble"),
    target = ref(""),
    busy = ref(false),
    problem = ref(""),
    notice = ref("");
const connectionIssue = computed(() => {
    if (snapshot.value.connected || !snapshot.value.connection_issue) return "";
    const labels = {
        usb_detached: "The USB radio or hub was disconnected. Reattach it, then refresh USB radios if needed.",
        device_missing: "The selected USB device is no longer attached. Refresh USB radios and select it again.",
        usb_permission_required: "USB access is needed. Select the radio and tap Connect MeshCore to allow access.",
        device_busy_or_unavailable: "The USB device is busy or unavailable. Check that it is your MeshCore radio.",
        serial_port_missing: "The selected USB device has no supported serial port.",
        usb_read_failed: "The USB serial connection stopped receiving data. Check the cable and reconnect.",
        usb_write_failed: "The USB serial connection could not send data. Check the cable and reconnect.",
    };
    return (
        labels[snapshot.value.connection_issue] ||
        "The MeshCore connection was interrupted. Check the radio and reconnect."
    );
});
const identityRefresh = ref(0);
const backupBusy = ref(false),
    identityBusy = ref(false);
const radio2Busy = ref(false);
watch([() => props.suggestedConnection, () => snapshot.value.connected, () => busy.value], ([hint]) => {
    if (!hint || snapshot.value.connected || busy.value || !isBluetoothAddress(hint.target)) return;
    kind.value = "ble";
    target.value = hint.target;
    bluetoothChoice.value = hint.target;
});
const controlsBusy = computed(() => busy.value || backupBusy.value || identityBusy.value || radio2Busy.value);
watch(controlsBusy, (value) => emit("busy", value));
const devices = ref([]),
    bluetoothChoice = ref(""),
    loadingDevices = ref(false),
    deviceProblem = ref("");
const usbDevices = ref([]),
    loadingUsb = ref(false),
    usbProblem = ref("");
async function loadUsbDevices() {
    if (loadingUsb.value) return;
    loadingUsb.value = true;
    usbProblem.value = "";
    try {
        const { data } = await window.api.get(apiPath("/meshcore/usb-devices"), { signal: lifetime.signal });
        if (!stopped) {
            usbDevices.value = Array.isArray(data.result) ? data.result : [];
            if (!usbDevices.value.length)
                usbProblem.value =
                    "No USB serial radios found. Attach your MeshCore radio through an OTG cable and refresh.";
        }
    } catch {
        if (!stopped) usbProblem.value = "Could not list USB radios. Check the OTG connection and refresh.";
    } finally {
        loadingUsb.value = false;
    }
}
function changeTransport() {
    target.value = "";
    bluetoothChoice.value = "";
    if (kind.value === "usb") loadUsbDevices();
}
function chooseBluetooth() {
    target.value = bluetoothChoice.value === "manual" ? "" : bluetoothChoice.value;
}
async function loadDevices() {
    if (snapshot.value.bluetooth_discovery_supported === false) {
        deviceProblem.value = "Paired-radio selection requires an Android backend.";
        return;
    }
    if (loadingDevices.value) return;
    loadingDevices.value = true;
    deviceProblem.value = "";
    try {
        const { data } = await window.api.get(apiPath("/meshcore/bluetooth-devices"), { signal: lifetime.signal });
        if (!stopped) {
            devices.value = Array.isArray(data.result) ? data.result : [];
            if (!devices.value.length)
                deviceProblem.value =
                    "No paired BLE radios found. Pair a radio in Android settings or enter its address manually.";
        }
    } catch {
        if (!stopped)
            deviceProblem.value =
                "Could not list paired radios. Check Bluetooth permission, or enter the address manually.";
    } finally {
        loadingDevices.value = false;
    }
}
const baseline = ref(null),
    draft = ref({}),
    needsRead = ref(false);
const initialReadPending = ref(false);
const fields = ["frequency_mhz", "bandwidth_khz", "sf", "cr", "tx_power_dbm", "path_hash_bytes"];
let generation = 0,
    stopped = false;
const dirty = computed(
    () => baseline.value && fields.some((key) => Number(draft.value[key]) !== Number(baseline.value[key]))
);
function useRegionalPreset() {
    Object.assign(draft.value, { frequency_mhz: 910.525, bandwidth_khz: 62.5, sf: 7, cr: 5 });
    notice.value =
        "Puget Mesh preset selected. Review and apply to update the primary radio. TX power, path hash size, and Radio2 are unchanged.";
}
function reset() {
    draft.value = { ...baseline.value };
}
function accept(values) {
    baseline.value = { ...values };
    reset();
    needsRead.value = false;
}
async function read() {
    if (controlsBusy.value || !snapshot.value.connected) return;
    initialReadPending.value = false;
    const owner = snapshot.value.owner,
        token = ++generation;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        const { data } = await window.api.get(apiPath("/meshcore/settings"), { signal: lifetime.signal });
        if (!stopped && token === generation && owner === snapshot.value.owner && snapshot.value.connected) {
            accept(data.result);
            notice.value = "Current settings read from radio.";
        }
    } catch {
        if (!stopped && token === generation)
            problem.value = "Could not read radio settings. Check the connection and read again.";
    } finally {
        busy.value = false;
    }
}
async function apply() {
    if (controlsBusy.value || !dirty.value || needsRead.value || !snapshot.value.connected) return;
    const changes = {},
        owner = snapshot.value.owner,
        token = ++generation;
    for (const key of fields) {
        if (key === "path_hash_bytes" && !baseline.value.path_hash_supported) continue;
        const value = Number(draft.value[key]);
        if (String(draft.value[key]).trim() === "" || !Number.isFinite(value)) {
            problem.value = "Enter a number for every radio setting.";
            return;
        }
        if (value !== Number(baseline.value[key])) changes[key] = value;
    }
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        const { data } = await window.api.post(apiPath("/meshcore/settings"), { ...changes, expected_owner: owner });
        if (!stopped && token === generation && owner === snapshot.value.owner) {
            accept(data.result);
            notice.value = "Settings saved and verified against the radio.";
        }
    } catch {
        if (!stopped && token === generation) {
            needsRead.value = true;
            problem.value =
                "The update could not be fully verified. Some settings may have changed. Read from radio before trying again.";
        }
    } finally {
        busy.value = false;
    }
}
async function afterImport(result) {
    const sections = result?.completed || [];
    if (result?.state === "uncertain" || sections.includes("radio")) {
        baseline.value = null;
        draft.value = {};
        initialReadPending.value = true;
    }
    if (result?.state === "uncertain" || sections.includes("name")) ++identityRefresh.value;
    await refresh();
    if (initialReadPending.value && !controlsBusy.value) read();
}
async function connect() {
    if (controlsBusy.value) return;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        if (kind.value === "usb") {
            const { data } = await window.api.post(apiPath("/meshcore/usb-permission"), { path: target.value.trim() });
            if (stopped) return;
            if (!data.result?.granted) {
                notice.value = "Allow USB access in the Android prompt, then tap Connect MeshCore again.";
                return;
            }
        }
        await action("connect", { kind: kind.value, target: target.value.trim(), receive: true, auto_reconnect: true });
    } catch {
        problem.value = "Could not connect. Check the selected MeshCore radio, pairing and USB permission.";
    } finally {
        busy.value = false;
    }
}
async function disconnect() {
    if (controlsBusy.value) return;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        await action("disconnect", {});
    } catch {
        problem.value = "Could not confirm disconnection. Refresh the connection status.";
    } finally {
        busy.value = false;
    }
}
watch([() => snapshot.value.owner, () => snapshot.value.connected], () => {
    ++generation;
    baseline.value = null;
    draft.value = {};
    notice.value = "";
    needsRead.value = false;
    initialReadPending.value = Boolean(snapshot.value.connected);
    if (initialReadPending.value && !controlsBusy.value) read();
});
watch(controlsBusy, (value) => {
    if (!value && initialReadPending.value && snapshot.value.connected && !stopped) read();
});
watch(
    () => snapshot.value.connection,
    (value) => {
        if (value && ["ble", "usb"].includes(value.kind) && typeof value.target === "string" && !target.value) {
            kind.value = value.kind;
            target.value = value.target;
            if (value.kind === "ble") bluetoothChoice.value = value.target;
        }
    }
);
watch(
    () => [snapshot.value.available, snapshot.value.bluetooth_discovery_supported],
    ([available]) => {
        if (available) loadDevices();
    },
    { immediate: true }
);
onBeforeUnmount(() => {
    lifetime.abort();
    stopped = true;
    ++generation;
});
</script>
<style scoped>
@reference "../../style.css";
.settings-section {
    @apply w-full border-b border-sem-border py-6 sm:py-8 flex flex-col;
}
:deep(.settings-section__header) {
    @apply flex items-center justify-between gap-3 pb-4 border-b border-sem-border;
}
:deep(.settings-section__header h2) {
    @apply text-lg font-semibold text-sem-fg;
}
:deep(.settings-section__header p) {
    @apply text-sm text-sem-fg-muted;
}
:deep(.settings-section__eyebrow) {
    @apply text-xs uppercase tracking-wide text-sem-fg-muted;
}
:deep(.settings-section__body) {
    @apply pt-4 text-sem-fg;
}
.input-field {
    @apply bg-sem-surface-muted border border-sem-border text-sm rounded-2xl focus:ring-2 focus:ring-sem-focus focus:border-sem-focus-border block w-full p-2.5 text-sem-fg transition;
}
button {
    @apply disabled:opacity-50 disabled:cursor-not-allowed;
}
label {
    @apply text-sm;
}
</style>
