<template>
    <section class="flex-1 min-w-0 h-full overflow-y-auto bg-sem-canvas text-sem-fg" aria-label="MeshCore tools">
        <ToolsPageHeader
            title="MeshCore tools"
            description="Diagnostics and channel regions for your MeshCore companion"
            icon="radio-tower"
            :back-to="{ name: 'tools' }"
        />
        <div class="max-w-4xl mx-auto p-4 md:p-6 space-y-5">
            <nav class="flex flex-wrap gap-2" aria-label="MeshCore diagnostics">
                <RouterLink
                    v-for="tab in tabs"
                    :key="tab.id"
                    class="secondary-chip"
                    :aria-current="tool === tab.id ? 'page' : undefined"
                    :to="{ name: 'meshcore-tools', params: { tool: tab.id } }"
                    >{{ tab.label }}</RouterLink
                >
            </nav>
            <p class="text-xs text-sem-fg-muted">MeshCore · {{ snapshot.connected ? "Connected" : "Disconnected" }}</p>
            <p v-if="error || problem" role="alert" class="text-sm text-sem-danger">{{ problem || error }}</p>
            <template v-if="tool === 'regions'">
                <h2 class="text-lg font-semibold">Regions &amp; channel scopes</h2>
                <button
                    type="button"
                    class="primary-chip"
                    :disabled="busy || !snapshot.connected || snapshot.region_scan?.state === 'running'"
                    @click="scanRegions"
                >
                    {{ snapshot.region_scan?.state === "running" ? "Scanning nearby regions…" : "Scan nearby regions" }}
                </button>
                <p v-if="snapshot.region_scan?.message" role="status" class="text-sm text-sem-fg-muted">
                    {{ snapshot.region_scan.message }}
                </p>
                <label class="flex items-center gap-2 text-sm"
                    ><input
                        type="checkbox"
                        :checked="snapshot.region_auto_scan"
                        :disabled="busy || !snapshot.connected"
                        @change="setAuto($event.target.checked)"
                    />Automatically discover nearby regions on MeshCore connection</label
                >
                <p class="text-xs text-sem-fg-muted">
                    Optional, off by default. Scans ask at most three nearby nodes; automatic scans run at most once per
                    ten minutes. Discovered regions never change a channel's chosen scope.
                </p>

                <p class="text-sm text-sem-fg-muted">
                    Regions guide where repeaters forward a channel message. They are separate from channel names and
                    encryption keys. These preferences affect channels only; direct messages keep their existing
                    routing.
                </p>
                <p class="text-xs text-sem-fg-muted">
                    Use the exact region name agreed by your mesh, up to 29 UTF-8 bytes. Region names are not limited to
                    three characters. The separate 1–3 byte path hash setting identifies repeater hops.
                </p>
                <form class="flex flex-wrap gap-2" @submit.prevent="addRegion">
                    <label class="flex-1 text-sm"
                        >Public region<input
                            v-model="regionName"
                            class="input-field w-full"
                            placeholder="Enter your region name"
                            aria-label="Public MeshCore region"
                    /></label>
                    <button class="primary-chip self-end" :disabled="busy || !snapshot.connected || !regionName.trim()">
                        Add region
                    </button>
                </form>
                <div class="flex flex-wrap items-end gap-2">
                    <label class="flex-1 text-sm"
                        >Default for channel messages<select
                            v-model="defaultScope"
                            class="input-field w-full"
                            aria-label="Default channel region"
                        >
                            <option value="">Radio default</option>
                            <option v-for="region in snapshot.regions || []" :key="region" :value="region">
                                {{ region }}
                            </option>
                        </select></label
                    >
                    <button class="primary-chip" :disabled="busy || !snapshot.connected" @click="applyDefault">
                        Save channel default
                    </button>
                </div>
                <button
                    type="button"
                    class="secondary-chip"
                    :disabled="busy || !snapshot.connected"
                    @click="readRadioDefault"
                >
                    Read radio’s existing scope
                </button>
                <p v-if="radioDefault" class="text-xs text-sem-fg-muted">
                    Radio's existing default: {{ radioDefault }}. The app's channel preference is stored separately.
                </p>
                <div class="space-y-2 border-t border-sem-border pt-4">
                    <h3 class="font-semibold">Discover regions on a nearby node</h3>
                    <select v-model="regionPeer" class="input-field w-full" aria-label="Region discovery node">
                        <option value="">Select a repeater, room server or sensor</option>
                        <option v-for="node in infrastructure" :key="node.peer" :value="node.peer">
                            {{ node.name || node.peer.slice(0, 12) }}
                        </option>
                    </select>
                    <button
                        class="secondary-chip"
                        :disabled="busy || !snapshot.connected || !regionPeer"
                        @click="discoverRegions"
                    >
                        Discover regions
                    </button>
                    <p class="text-xs text-sem-fg-muted">
                        Some firmware supports nearby region queries only. A timeout is not proof that the node has no
                        regions.
                    </p>
                </div>
            </template>
            <template v-else-if="tool === 'noise'">
                <h2 class="text-lg font-semibold">Radio noise floor</h2>
                <button class="primary-chip" :disabled="busy || !snapshot.connected" @click="readStats">
                    Read radio statistics
                </button>
                <dl v-if="stats" class="grid grid-cols-2 gap-3 text-sm">
                    <template v-for="field in statFields" :key="field.key"
                        ><dt class="text-sem-fg-muted">{{ field.label }}</dt>
                        <dd>
                            {{ stats[field.key] == null ? "Unavailable" : stats[field.key] + " " + field.unit }}
                        </dd></template
                    >
                </dl>
                <p class="text-xs text-sem-fg-muted">
                    These are measurements reported by the connected radio, not a spectrum scan. Reading them does not
                    transmit on LoRa.
                </p>
            </template>
            <template v-else-if="tool === 'rx'">
                <h2 class="text-lg font-semibold">MeshCore RX log</h2>
                <button class="primary-chip" :disabled="busy || !snapshot.connected" @click="readRx">
                    Refresh RX log
                </button>
                <p class="text-xs text-sem-fg-muted">
                    The latest 200 captured packets. This view is separate from Reticulum logs. Some firmware does not
                    provide RX log events.
                </p>
                <article
                    v-for="(packet, index) in packets"
                    :key="packet.received + ':' + index"
                    class="border-b border-sem-border py-2 text-xs space-y-1"
                >
                    <p>
                        {{ new Date(packet.received * 1000).toLocaleTimeString() }} ·
                        {{ packet.payload_length ?? "?" }} bytes · RSSI {{ packet.rssi ?? "?" }} dBm · SNR
                        {{ packet.snr ?? "?" }} dB · {{ packet.path_len ?? "?" }} hops
                    </p>
                    <details>
                        <summary class="cursor-pointer text-sem-fg-muted">Raw frame</summary>
                        <code class="break-all">{{ packet.raw }}</code>
                    </details>
                </article>
                <p v-if="!packets.length" class="text-sm text-sem-fg-muted">
                    No packets captured in this connection yet.
                </p>
            </template>
            <template v-else-if="tool === 'trace'">
                <h2 class="text-lg font-semibold">Trace a repeater path</h2>
                <p class="text-sm text-sem-fg-muted">
                    Enter the repeater hash sequence to probe. This sends one MeshCore trace request and listens for its
                    matching response.
                </p>
                <form class="space-y-2" @submit.prevent="trace">
                    <label class="block text-sm"
                        >Repeater path hashes<input
                            v-model="tracePath"
                            class="input-field w-full font-mono"
                            placeholder="ab,cd,ab"
                            aria-label="MeshCore trace path"
                    /></label>
                    <p class="text-xs text-sem-fg-muted">
                        Use equal-size hashes of 1, 2, 4 or 8 bytes, separated by commas. Trace hash sizes follow the
                        trace protocol and are separate from the radio's message path setting.
                    </p>
                    <button class="primary-chip" :disabled="busy || !snapshot.connected || !tracePath.trim()">
                        {{ busy ? "Waiting for trace…" : "Trace path" }}
                    </button>
                </form>
                <p v-if="traceResult" class="text-sm">
                    {{ traceResult.state === "verified" ? "Matching trace response received" : traceResult.message }}
                </p>
                <ol v-if="traceResult?.state === 'verified'" class="space-y-2 text-sm">
                    <li v-for="(hop, index) in traceResult.path || []" :key="index">
                        {{ index + 1 }}. {{ hop.hash || "This radio" }} · SNR {{ hop.snr ?? "?" }} dB
                    </li>
                </ol>
            </template>
            <p v-if="notice" role="status" class="text-sm text-sem-fg-muted">{{ notice }}</p>
        </div>
    </section>
</template>
<script setup>
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import ToolsPageHeader from "../tools/ToolsPageHeader.vue";
import { useMeshCoreUi } from "../../js/meshcoreUi";
defineProps({ tool: { type: String, default: "regions" } });
const busy = ref(false),
    problem = ref(""),
    notice = ref(""),
    regionName = ref(""),
    regionPeer = ref(""),
    defaultScope = ref(""),
    radioDefault = ref(""),
    stats = ref(null),
    packets = ref([]),
    tracePath = ref(""),
    traceResult = ref(null);
const { snapshot, error, action } = useMeshCoreUi(
    () => null,
    () => !busy.value
);
const tabs = [
    { id: "trace", label: "Trace path" },
    { id: "rx", label: "RX log" },
    { id: "regions", label: "Regions" },
    { id: "noise", label: "Noise floor" },
];
const statFields = [
    { key: "noise_floor", label: "Noise floor", unit: "dBm" },
    { key: "last_rssi", label: "Last RSSI", unit: "dBm" },
    { key: "last_snr", label: "Last SNR", unit: "dB" },
    { key: "tx_air_secs", label: "TX airtime", unit: "s" },
    { key: "rx_air_secs", label: "RX airtime", unit: "s" },
];
const infrastructure = computed(() => (snapshot.value.announces || []).filter((n) => [2, 3, 4].includes(n.kind)));
watch(
    () => snapshot.value.channel_default_scope,
    (value) => {
        defaultScope.value = value || "";
    }
);
watch(
    () => snapshot.value.owner,
    () => {
        stats.value = null;
        packets.value = [];
        traceResult.value = null;
        problem.value = "";
        notice.value = "";
        radioDefault.value = "";
        regionPeer.value = "";
    }
);
async function perform(name, body, accept) {
    if (busy.value || !snapshot.value.connected) return;
    const owner = snapshot.value.owner;
    busy.value = true;
    problem.value = "";
    notice.value = "";
    try {
        const result = await action(name, body);
        if (snapshot.value.owner === owner) accept(result);
    } catch (e) {
        problem.value =
            e.response?.data?.message || "MeshCore did not confirm this request. Check the connection and try again.";
    } finally {
        busy.value = false;
    }
}
const route = useRoute();
let scanFromLink = false;
watch(
    () => [snapshot.value.connected, snapshot.value.owner],
    () => {
        if (!scanFromLink && snapshot.value.connected && route?.query.scan === "1") {
            scanFromLink = true;
            scanRegions();
        }
    }
);
function scanRegions() {
    return perform("regions-scan", {}, () => {
        notice.value = "Region scan started; results will appear here.";
    });
}
function setAuto(enabled) {
    return perform("regions-auto", { enabled }, () => {
        notice.value = enabled ? "Automatic region discovery enabled." : "Automatic region discovery disabled.";
    });
}
function readStats() {
    return perform("tool-radio-stats", {}, (r) => {
        stats.value = r;
    });
}
function readRx() {
    return perform("tool-rx-log", {}, (r) => {
        packets.value = r.packets || [];
    });
}
function addRegion() {
    return perform("regions-add", { name: regionName.value }, (r) => {
        regionName.value = "";
        notice.value = `Added ${r.name}`;
    });
}
function readRadioDefault() {
    return perform("regions-read", {}, (r) => {
        radioDefault.value = r.radio_default_scope || "Unscoped";
    });
}
function applyDefault() {
    return perform("regions-default", { scope: defaultScope.value || null }, () => {
        notice.value = "Channel default saved. Direct-message routing is unchanged.";
    });
}
function discoverRegions() {
    return perform("regions-discover", { peer: regionPeer.value }, (r) => {
        notice.value =
            r.state === "verified" ? `Regions returned: ${r.regions.join(", ") || "none advertised"}` : r.message;
    });
}
function trace() {
    return perform("tool-trace", { path: tracePath.value }, (r) => {
        traceResult.value = r;
    });
}
</script>
