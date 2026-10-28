<!-- SPDX-License-Identifier: MIT -->
<template>
    <section class="flex-1 min-h-0 flex flex-col bg-sem-canvas text-sem-fg" aria-label="MeshCore network visualiser">
        <div class="p-3 border-b border-sem-border space-y-2 shrink-0">
            <div class="flex flex-wrap items-center gap-2">
                <label
                    >Radio
                    <select
                        v-model="radio"
                        class="bg-sem-surface text-sem-fg border border-sem-border rounded-lg p-2"
                        @change="changeRadio"
                    >
                        <option v-for="item in radios" :key="item.id" :value="item.id">
                            {{ item.label }}{{ item.connected ? " · connected" : " · offline" }}
                        </option>
                    </select></label
                >
                <button class="secondary-chip" :disabled="busy" @click="refresh">Refresh</button>
                <button class="secondary-chip" @click="network?.fit({ animation: true })">Fit</button>
                <label class="flex items-center gap-1"><input v-model="auto" type="checkbox" /> Auto refresh</label>
                <input
                    v-model="search"
                    class="bg-sem-surface border border-sem-border rounded-lg p-2 min-w-0"
                    placeholder="Find a node"
                    aria-label="Find a MeshCore node"
                    @input="findNode"
                />
            </div>
            <p class="text-xs text-sem-fg-muted">
                Solid line: connected companion. Dashed arrows: latest stored outbound routes, not live coverage or
                delivery receipts. Short hop identifiers can match multiple nodes.
            </p>
            <p v-if="problem" role="alert" class="text-sm text-sem-danger">{{ problem }}</p>
            <p v-if="!snapshot?.owner && !busy" class="text-sm">
                Connect a MeshCore radio in Settings to load its identity and known nodes.
            </p>
            <p v-else class="text-xs text-sem-fg-muted">
                {{ snapshot?.connected ? "Companion connected" : "Companion offline · stored information" }} ·
                {{ graph.nodes.length }} displayed nodes<span v-if="graph.omitted || graph.limited">
                    · Display limited for responsiveness</span
                >
            </p>
        </div>
        <div class="relative flex-1 min-h-40 overflow-hidden">
            <div ref="canvas" class="absolute inset-0" aria-label="MeshCore network diagram"></div>
            <aside
                v-if="selected"
                class="absolute bottom-2 left-2 right-2 sm:right-auto sm:w-96 max-h-[70%] overflow-auto rounded-xl border border-sem-border bg-sem-surface p-3 shadow-lg"
                aria-label="MeshCore node information"
                data-app-back-scope
                @app-back.stop="selected = null"
                @keydown.esc.stop.prevent="selected = null"
            >
                <button
                    class="float-right secondary-chip"
                    aria-label="Close node information"
                    data-app-back
                    @click="selected = null"
                >
                    Close
                </button>
                <h2 class="font-semibold break-words">
                    {{ selected.name || selected.peer?.slice(0, 12) || "MeshCore node" }}
                </h2>
                <p>{{ selected.type }}</p>
                <p v-if="selected.peer" class="font-mono text-xs break-all mt-2">{{ selected.peer }}</p>
                <p v-if="selected.heard" class="text-sm mt-2">Last heard: {{ date(selected.heard) }}</p>
                <p v-else-if="selected.advertised" class="text-sm mt-2">Advertised: {{ date(selected.advertised) }}</p>
                <p v-if="selected.route" class="text-sm mt-2">
                    {{
                        selected.route.hops < 0
                            ? "Flood routing; no fixed outbound path"
                            : `${selected.route.hops} saved repeater hops`
                    }}
                </p>
                <p v-if="selected.route?.stored_at" class="text-xs text-sem-fg-muted">
                    Route first stored or changed here: {{ date(selected.route.stored_at) }}
                </p>
                <p v-if="selected.route?.hops > 0" class="text-xs text-sem-fg-muted mt-2">
                    Hop matches use short prefixes and remain unverified. Lines describe a stored route, not a live
                    connection.
                </p>
                <p v-if="selected.note" class="text-sm mt-2">{{ selected.note }}</p>
            </aside>
        </div>
    </section>
</template>
<script setup>
import { ref, shallowRef, computed, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Network } from "vis-network";
import { DataSet } from "vis-data";
import "vis-network/styles/vis-network.css";
import { apiPath } from "../../js/constants";
import { meshcoreGraph } from "./internal/meshcoreTopology.js";
const route = useRoute(),
    router = useRouter(),
    canvas = ref(null),
    network = shallowRef(null),
    radios = ref([]),
    radio = ref(""),
    snapshot = ref(null),
    selected = ref(null),
    problem = ref(""),
    busy = ref(false),
    auto = ref(true),
    search = ref("");
let stopped = false,
    generation = 0,
    timer,
    controller;
const graph = computed(() =>
    meshcoreGraph(snapshot.value, radios.value.find((item) => item.id === radio.value)?.label)
);
const date = (value) => new Date(value * 1000).toLocaleString();
function render() {
    const model = graph.value;
    network.value?.setData({ nodes: new DataSet(model.nodes), edges: new DataSet(model.edges) });
}
async function refresh() {
    if (stopped || busy.value) return;
    const requestVersion = ++generation;
    busy.value = true;
    problem.value = "";
    controller = new AbortController();
    try {
        const status = (await window.api.get(apiPath("/meshcore/status"), { signal: controller.signal })).data;
        if (stopped || requestVersion !== generation) return;
        radios.value = status.radios || [];
        if (!radios.value.some((item) => item.id === radio.value))
            radio.value = radios.value.some((item) => item.id === route.query.meshcoreRadio)
                ? route.query.meshcoreRadio
                : status.radio_id || radios.value[0]?.id || "";
        if (!radio.value) {
            snapshot.value = null;
            render();
            return;
        }
        const owner = radios.value.find((item) => item.id === radio.value)?.owner;
        const response = await window.api.get(apiPath("/meshcore/topology"), {
            params: { radio: radio.value, ...(owner ? { owner } : {}) },
            signal: controller.signal,
        });
        if (stopped || requestVersion !== generation) return;
        snapshot.value = response.data.result;
        if (owner && snapshot.value?.owner !== owner) throw new Error("Radio identity changed; refresh to continue");
        if (selected.value?.peer)
            selected.value =
                graph.value.nodes.find((node) => node.details.peer === selected.value.peer)?.details || null;
        render();
    } catch (error) {
        if (!stopped && requestVersion === generation) {
            snapshot.value = null;
            selected.value = null;
            render();
            problem.value = error.response?.data?.message || error.message || "Could not read saved MeshCore routes";
        }
    } finally {
        if (requestVersion === generation) busy.value = false;
    }
}
function changeRadio() {
    generation++;
    controller?.abort();
    busy.value = false;
    snapshot.value = null;
    selected.value = null;
    render();
    router.replace({ query: { ...route.query, meshcoreRadio: radio.value } });
    refresh();
}
function findNode() {
    const term = search.value.trim().toLowerCase();
    if (!term) return;
    const node = graph.value.nodes.find(
        (node) => node.label.toLowerCase().includes(term) || node.details.peer?.includes(term)
    );
    if (node) {
        network.value?.selectNodes([node.id]);
        network.value?.focus(node.id, { scale: 1, animation: true });
        selected.value = node.details;
    }
}
onMounted(() => {
    network.value = new Network(
        canvas.value,
        { nodes: [], edges: [] },
        {
            nodes: { font: { size: 13, color: "#64748b" } },
            edges: { font: { size: 10, color: "#64748b" }, smooth: { type: "continuous" } },
            physics: { stabilization: { iterations: 120 } },
            interaction: { hover: true },
            layout: { improvedLayout: true },
        }
    );
    network.value.on("click", (event) => {
        selected.value = graph.value.nodes.find((node) => node.id === event.nodes[0])?.details || null;
    });
    refresh();
    timer = setInterval(() => {
        if (auto.value) refresh();
    }, 15000);
});
onBeforeUnmount(() => {
    stopped = true;
    generation++;
    controller?.abort();
    clearInterval(timer);
    network.value?.destroy();
    network.value = null;
});
</script>
