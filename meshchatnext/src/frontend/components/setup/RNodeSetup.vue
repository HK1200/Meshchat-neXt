<!-- SPDX-License-Identifier: 0BSD -->
<template>
    <details class="border border-sem-border rounded-xl p-4">
        <summary class="cursor-pointer font-medium">Connect an RNode radio · optional</summary>
        <p class="text-sm text-sem-fg-muted py-3">
            Use RNode firmware for Reticulum. This connection is separate from your MeshCore client. Match the radio
            profile used by your local Reticulum group.
        </p>
        <form class="space-y-3" @submit.prevent="save">
            <fieldset :disabled="busy" class="space-y-3">
                <label class="block text-sm"
                    >Connection<select v-model="kind" class="input-field" @change="target = ''">
                        <option value="ble">Bluetooth LE</option>
                        <option value="bt">Bluetooth Classic</option>
                        <option value="usb">USB / serial</option>
                        <option value="tcp">RNode over IP</option>
                    </select></label
                >
                <button v-if="kind !== 'tcp'" type="button" class="secondary-chip" @click="devices">
                    Refresh {{ kind === "usb" ? "USB radios" : "paired radios" }}
                </button>
                <label v-if="rows.length" class="block text-sm"
                    >Radio<select v-model="target" class="input-field">
                        <option value="">Choose your RNode</option>
                        <option v-for="row in rows" :key="row.value" :value="row.value">{{ row.name }}</option>
                    </select></label
                >
                <label class="block text-sm"
                    >{{
                        kind === "tcp"
                            ? "RNode host:port"
                            : kind === "usb"
                              ? "USB device path"
                              : "Bluetooth address or paired name"
                    }}<input v-model="target" class="input-field" required autocomplete="off"
                /></label>
                <p class="text-xs text-sem-fg-muted">
                    For Bluetooth, pair in the system settings first. For USB on Android, connect an OTG cable and allow
                    USB access when asked.
                </p>
                <div class="grid grid-cols-2 gap-3">
                    <label class="text-sm"
                        >Frequency (MHz)<input
                            v-model.number="frequency"
                            class="input-field"
                            type="number"
                            step="0.001"
                            required
                    /></label>
                    <label class="text-sm"
                        >Bandwidth (kHz)<select v-model.number="bandwidth" class="input-field">
                            <option
                                v-for="bw in [7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500]"
                                :key="bw"
                                :value="bw"
                            >
                                {{ bw }}
                            </option>
                        </select></label
                    >
                    <label class="text-sm"
                        >Spreading factor<select v-model.number="sf" class="input-field">
                            <option v-for="value in [5, 6, 7, 8, 9, 10, 11, 12]" :key="value" :value="value">
                                SF{{ value }}
                            </option>
                        </select></label
                    >
                    <label class="text-sm"
                        >Coding rate<select v-model.number="cr" class="input-field">
                            <option v-for="value in [5, 6, 7, 8]" :key="value" :value="value">4/{{ value }}</option>
                        </select></label
                    >
                    <label class="text-sm"
                        >TX power (dBm)<input
                            v-model.number="power"
                            class="input-field"
                            type="number"
                            min="0"
                            max="37"
                            required
                    /></label>
                </div>
                <p class="text-xs text-sem-fg-muted">
                    Use a frequency and power appropriate for your region and hardware. Existing RNode interfaces are
                    kept.
                </p>
                <button type="submit" class="secondary-chip">
                    {{ busy ? "Connecting…" : "Add RNode connection" }}
                </button>
            </fieldset>
        </form>
        <p v-if="error" role="alert" class="text-sm text-sem-danger pt-2">{{ error }}</p>
        <p v-if="notice" role="status" class="text-sm text-sem-accent pt-2">{{ notice }}</p>
    </details>
</template>
<script setup>
import { ref } from "vue";
import { apiPath } from "../../js/constants";
const emit = defineEmits(["busy"]);
const kind = ref("ble"),
    target = ref(""),
    rows = ref([]),
    frequency = ref(914.875),
    bandwidth = ref(125),
    sf = ref(8),
    cr = ref(7),
    power = ref(17),
    busy = ref(false),
    error = ref(""),
    notice = ref("");
async function devices() {
    error.value = "";
    rows.value = [];
    try {
        const { data } = await window.api.get(
            apiPath(kind.value === "usb" ? "/comports" : "/meshcore/bluetooth-devices")
        );
        rows.value =
            kind.value === "usb"
                ? (data.comports || []).map((row) => ({ value: row.device, name: row.product || row.device }))
                : (data.result || []).map((row) => ({ value: row.address, name: `${row.name} · ${row.address}` }));
        if (!rows.value.length) notice.value = "No radios found. Connect or pair your RNode, then refresh.";
    } catch {
        error.value = "Could not list radios. Check the connection and Bluetooth permissions.";
    }
}
async function save() {
    if (busy.value) return;
    error.value = "";
    notice.value = "";
    if (!Number.isFinite(frequency.value) || frequency.value <= 0 || !target.value.trim()) {
        error.value = "Choose a radio and enter its frequency.";
        return;
    }
    busy.value = true;
    emit("busy", true);
    try {
        const current = (await window.api.get(apiPath("/reticulum/interfaces"))).data.interfaces || {};
        const port =
            kind.value === "usb"
                ? target.value.trim()
                : `${kind.value}://${target.value.trim().replace(/^(bt|ble|tcp):\/\//i, "")}`;
        if (Object.values(current).some((row) => row.type === "RNodeInterface" && row.port === port)) {
            notice.value = "This RNode connection is already configured. Manage it under Interfaces.";
            return;
        }
        let name = "RNode",
            index = 2;
        while (current[name]) name = `RNode ${index++}`;
        await window.api.post(apiPath("/reticulum/interfaces/add"), {
            name,
            type: "RNodeInterface",
            port,
            frequency: Math.round(frequency.value * 1e6),
            bandwidth: Math.round(bandwidth.value * 1000),
            spreadingfactor: sf.value,
            codingrate: cr.value,
            txpower: power.value,
            mode: "full",
        });
        await window.api.post(apiPath("/reticulum/reload"));
        notice.value = "RNode configuration saved. Its connection status is available under Interfaces.";
    } catch (e) {
        error.value =
            e.response?.data?.message ||
            "Could not configure this RNode. Check its firmware, connection and radio profile.";
    } finally {
        busy.value = false;
        emit("busy", false);
    }
}
</script>
<style scoped>
@reference "../../style.css";
.input-field {
    @apply block w-full rounded-lg border border-sem-border bg-sem-surface px-3 py-2 text-sem-fg;
}
</style>
