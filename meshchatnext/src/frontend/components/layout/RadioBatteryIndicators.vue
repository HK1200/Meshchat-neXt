<template>
    <div
        v-if="rows.length"
        class="px-3 py-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-sem-fg-muted"
        :class="collapsed ? 'justify-center px-1' : ''"
        aria-label="Connected Bluetooth radio batteries"
    >
        <div
            v-for="row in rows.filter((row) => (row.id === 'meshcore' ? appFeatures.meshcore : appFeatures.reticulum))"
            :key="row.id"
            class="inline-flex items-center gap-1 min-w-0"
            :title="row.title"
            :aria-label="row.title"
        >
            <span>{{ collapsed ? row.short : row.label }}</span>
            <svg viewBox="0 0 25 12" class="w-6 h-3 shrink-0" aria-hidden="true">
                <rect x="0.5" y="0.5" width="21" height="11" rx="2" fill="none" stroke="currentColor" />
                <path d="M23 4v4" stroke="currentColor" stroke-width="2" />
                <template v-if="row.level !== null">
                    <rect
                        v-for="segment in 4"
                        :key="segment"
                        :x="2.5 + (segment - 1) * 4.4"
                        y="2.5"
                        width="3.1"
                        height="7"
                        rx="0.5"
                        :fill="segment <= row.level ? 'currentColor' : 'none'"
                        :class="
                            row.level === 0
                                ? 'text-sem-danger'
                                : row.level === 1
                                  ? 'text-sem-warning'
                                  : 'text-sem-accent'
                        "
                    />
                </template>
                <text v-else x="10.5" y="9" text-anchor="middle" font-size="9" fill="currentColor">?</text>
            </svg>
        </div>
    </div>
</template>
<script setup>
import { appFeatures } from "../../js/appFeatures";
import { ref, onMounted, onBeforeUnmount } from "vue";
import { apiPath } from "../../js/constants";
import { radioBatteryLevel } from "../../js/radioBattery";
defineProps({ collapsed: Boolean });
const rows = ref([]);
let timer,
    stopped = false,
    reading = false;
const abort = new AbortController();
function percent(value) {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? Math.round(value) : null;
}
async function refresh() {
    if (reading || stopped || document.hidden || typeof window.api?.get !== "function") return;
    reading = true;
    const options = { signal: abort.signal, timeout: 12000 };
    const next = [];
    try {
        const results = await Promise.allSettled([
            window.api.get(apiPath("/reticulum/interfaces"), options),
            window.api.get(apiPath("/interface-stats"), options),
            window.api.get(apiPath("/meshcore/status"), options),
        ]);
        if (stopped) return;
        const config = results[0].status === "fulfilled" ? results[0].value.data.interfaces || {} : {};
        const stats = results[1].status === "fulfilled" ? results[1].value.data.interface_stats?.interfaces || [] : [];
        for (const row of stats) {
            const name = row.interface_name || row.short_name;
            const setting = config[name];
            if (
                !row.status ||
                !setting ||
                !String(setting.type).startsWith("RNode") ||
                !(
                    row.bluetooth_connected === true ||
                    /^(ble|bluetooth):\/\//i.test(setting.port || "") ||
                    setting.force_ble === true ||
                    ["yes", "true"].includes(String(setting.force_ble).toLowerCase()) ||
                    setting.ble_addr ||
                    setting.ble_name
                )
            )
                continue;
            const charge = row.battery_state ? percent(row.battery_percent) : null;
            next.push({
                id: `rns:${name}`,
                label: "RNode",
                short: "R",
                percent: charge,
                level: radioBatteryLevel({ percent: charge }),
                estimated: false,
                title: `RNode · ${name} · ${charge === null ? "battery unavailable" : charge + "% · " + row.battery_state}`,
            });
        }
        const status = results[2].status === "fulfilled" ? results[2].value.data : null;
        if (status?.connected && status.connection?.kind === "ble") {
            let battery = {};
            try {
                battery = (await window.api.get(apiPath("/meshcore/battery"), options)).data.result || {};
            } catch {
                /* Unknown battery is shown without a stale percentage. */
            }
            const charge = percent(battery.percent);
            next.push({
                id: "meshcore",
                voltage: battery.voltage_mv ? battery.voltage_mv / 1000 : null,
                label: "MeshCore",
                short: "M",
                percent: charge,
                level: radioBatteryLevel(battery),
                estimated: battery.estimated === true,
                title: `MeshCore · ${battery.voltage_mv ? (battery.voltage_mv / 1000).toFixed(2) + " V · approximate level from voltage" : "battery unavailable"}`,
            });
        }
        if (!stopped) rows.value = next;
    } catch {
        if (!stopped) rows.value = [];
    } finally {
        reading = false;
    }
}
function visible() {
    if (!document.hidden) refresh();
    else rows.value = [];
}
onMounted(() => {
    refresh();
    timer = setInterval(refresh, 30000);
    document.addEventListener("visibilitychange", visible);
});
onBeforeUnmount(() => {
    stopped = true;
    clearInterval(timer);
    abort.abort();
    document.removeEventListener("visibilitychange", visible);
});
</script>
