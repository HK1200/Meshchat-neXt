<template>
    <div class="relative shrink-0" aria-label="MeshCore map tools">
        <button
            type="button"
            class="secondary-chip text-xs !px-2"
            aria-label="MeshCore map"
            :aria-expanded="open"
            :disabled="!map"
            @click="open = !open"
        >
            MeshCore<span class="hidden sm:inline"> map</span>
        </button>
        <Teleport :to="map?.getTargetElement?.()?.parentElement || 'body'">
            <section
                v-if="open"
                class="absolute right-3 top-3 z-40 w-80 max-w-[85vw] max-h-[65dvh] overflow-y-auto rounded-xl border border-sem-border bg-sem-surface p-3 shadow-xl space-y-3"
                aria-label="MeshCore map layer"
            >
                <div class="flex justify-between items-center gap-2">
                    <h3 class="font-semibold text-sm">MeshCore map</h3>
                    <button
                        type="button"
                        class="text-xs secondary-chip"
                        aria-label="Close MeshCore map tools"
                        @click="open = false"
                    >
                        Close
                    </button>
                </div>
                <label class="flex items-center gap-2 text-sm"
                    ><input v-model="visible" type="checkbox" /> Show MeshCore nodes and team</label
                >
                <p class="text-xs text-sem-fg-muted">
                    Positions reported in MeshCore announces. Reticulum markers stay separate. Viewing this layer does
                    not share your location.
                </p>
                <p v-if="owner" class="text-xs text-sem-fg-muted">
                    {{ connected ? "MeshCore connected" : "MeshCore offline · saved positions" }} ·
                    {{ nodes.length }} located nodes
                </p>
                <p v-else class="text-xs text-sem-fg-muted">Connect a MeshCore companion to select its map history.</p>
                <div class="flex gap-2">
                    <button type="button" class="secondary-chip text-xs" :disabled="busy" @click="refresh">
                        {{ busy ? "Reading…" : "Refresh positions" }}
                    </button>
                    <button
                        type="button"
                        class="secondary-chip text-xs"
                        :disabled="!locatedCount || !visible"
                        @click="fit"
                    >
                        Fit positions
                    </button>
                </div>
                <p v-if="problem" role="alert" class="text-xs text-sem-danger">{{ problem }}</p>
                <p v-if="!busy && owner && !nodes.length" class="text-xs text-sem-fg-muted">
                    No reported positions yet. Nodes without coordinates are omitted.
                </p>
                <div v-if="selected" class="rounded-lg border border-sem-border p-2 space-y-1 text-xs">
                    <p class="font-semibold">
                        {{ selected.name || "Unnamed MeshCore node" }} <span class="text-sem-info">· MeshCore</span>
                    </p>
                    <p>{{ kinds[selected.kind] || "Node" }} · reported position</p>
                    <p class="font-mono">{{ selected.latitude.toFixed(5) }}, {{ selected.longitude.toFixed(5) }}</p>
                    <p class="text-sem-fg-muted">{{ nodeAge(selected) }}</p>
                    <button
                        v-if="selected.kind === 1 && !selected.saved"
                        type="button"
                        class="secondary-chip text-xs"
                        :disabled="busy || !connected"
                        @click="addContact"
                    >
                        Add MeshCore contact
                    </button>
                    <button
                        v-if="selected.kind === 1 && selected.saved"
                        type="button"
                        class="secondary-chip text-xs"
                        @click="message"
                    >
                        Message via MeshCore
                    </button>
                    <button
                        v-if="[2, 3, 4].includes(selected.kind)"
                        type="button"
                        class="secondary-chip text-xs"
                        @click="manage"
                    >
                        View MeshCore node
                    </button>
                </div>
                <div
                    v-if="selectedTeam"
                    class="rounded-lg border border-sem-border p-2 space-y-1 text-xs"
                    aria-label="Selected MeshCore team item"
                >
                    <p class="font-semibold">
                        {{ selectedTeam.label || selectedTeam.callsign || selectedTeam.alias }} · MeshCore team
                    </p>
                    <p>{{ selectedTeam.kind }} · unverified team alias</p>
                    <p v-if="selectedTeam.note">{{ selectedTeam.note }}</p>
                    <p v-if="selectedTeam.place">{{ selectedTeam.place }}</p>
                    <p v-if="selectedTeam.kind === 'position' && Date.now() / 1000 - selectedTeam.heard >= 600">
                        Stale position · last heard {{ age(selectedTeam.heard) }}
                    </p>
                    <p v-if="!targetPoint">No location included.</p>
                    <p v-else>{{ targetPoint[1].toFixed(5) }}, {{ targetPoint[0].toFixed(5) }}</p>
                    <p v-if="targetMetrics">
                        From {{ rangePosition ? "phone location" : "map centre" }}: {{ targetMetrics
                        }}<span v-if="selectedTeam.kind === 'shape'"> · nearest boundary</span>
                    </p>
                    <p>Range reference: {{ rangePosition ? "phone location · one-time fix" : "map centre" }}.</p>
                </div>
                <div class="space-y-2 text-xs">
                    <p>
                        Use a one-time phone location for distance and bearing. This stays on this screen and is not
                        shared.
                    </p>
                    <button type="button" class="secondary-chip text-xs" :disabled="locating" @click="locateRange">
                        {{ locating ? "Getting location…" : "Use phone location for range" }}
                    </button>
                    <button v-if="rangePosition" type="button" class="secondary-chip text-xs" @click="clearRange">
                        Use map centre
                    </button>
                    <p v-if="rangePosition">
                        Location captured {{ age(rangePosition.captured) }} · accuracy ±{{ rangePosition.accuracy }} m
                    </p>
                    <p v-if="rangeProblem" role="alert" class="text-sem-danger">{{ rangeProblem }}</p>
                </div>
                <MeshCoreTeamPanel
                    :owner="owner"
                    :team="team"
                    :channels="channels"
                    :contacts="contacts"
                    :default-scope="defaultScope"
                    :connected="connected"
                    :supported="teamSupported"
                    :map="map"
                    :draw-source="drawSource"
                    @refresh="refresh"
                    @focus="focus"
                />
                <ul class="space-y-1" aria-label="Located MeshCore nodes">
                    <li v-for="node in nodes" :key="node.peer">
                        <button
                            type="button"
                            class="w-full text-left rounded-lg border border-sem-border p-2 text-xs hover:bg-sem-surface-muted"
                            @click="focus(node)"
                        >
                            <span class="font-semibold">{{ node.name || "Unnamed node" }}</span
                            ><span class="block text-sem-fg-muted"
                                >MeshCore · {{ kinds[node.kind] || "Node" }} · {{ nodeAge(node) }}</span
                            >
                        </button>
                    </li>
                </ul>
            </section>
        </Teleport>
    </div>
</template>
<script setup>
/* eslint-disable security/detect-possible-timing-attacks -- Public identity and lifetime comparisons contain no secrets. */
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import MeshCoreTeamPanel from "./MeshCoreTeamPanel.vue";
import { fromLonLat, toLonLat } from "ol/proj";
import { getDistance } from "ol/sphere";
import { sphericalInitialBearingDeg } from "../../../js/mapGeodesy";
import { Style, Fill, Stroke, Circle as CircleStyle, Text } from "ol/style";
import { unByKey } from "ol/Observable";
import { shapeGeometry } from "../../../js/meshcoreShapes";
import { getAndroidPosition, isAndroidLocationSupported } from "../../../js/androidLocation";
import { apiPath } from "../../../js/constants";
import { formatMeshcoreAge } from "../../../js/meshcoreTime";
const props = defineProps({
    map: { type: Object, default: null },
    active: { type: Boolean, default: true },
    drawSource: { type: Object, default: null },
});
const router = useRouter();
const clock = ref(Date.now());
const open = ref(false),
    visible = ref(false),
    nodes = ref([]),
    selected = ref(null),
    selectedTeam = ref(null),
    mapCenter = ref(null),
    owner = ref(null),
    radioId = ref(null),
    connected = ref(false),
    busy = ref(false),
    problem = ref("");
const team = ref(null),
    channels = ref([]),
    contacts = ref([]),
    teamSupported = ref(false),
    defaultScope = ref(null);
const rangePosition = ref(null),
    locating = ref(false),
    rangeProblem = ref("");
let rangeRequest = 0;
function clearRange() {
    rangeRequest++;
    rangePosition.value = null;
    locating.value = false;
    rangeProblem.value = "";
}
async function locateRange() {
    const request = ++rangeRequest;
    locating.value = true;
    rangeProblem.value = "";
    try {
        const point = isAndroidLocationSupported()
            ? await getAndroidPosition()
            : await new Promise((resolve, reject) => {
                  if (!navigator.geolocation) return reject(new Error("Location is unavailable."));
                  navigator.geolocation.getCurrentPosition((p) => resolve(p.coords), reject, {
                      enableHighAccuracy: true,
                      timeout: 20000,
                      maximumAge: 0,
                  });
              });
        if (request !== rangeRequest || stopped) return;
        if (
            !Number.isFinite(point.latitude) ||
            Math.abs(point.latitude) > 90 ||
            !Number.isFinite(point.longitude) ||
            Math.abs(point.longitude) > 180
        ) {
            throw new Error("No valid location was returned.");
        }
        // Reject stale native fallback fixes rather than presenting them as current range.
        if (point.time && Date.now() - point.time > 120000) throw new Error("Location is too old. Try again outdoors.");
        rangePosition.value = {
            latitude: point.latitude,
            longitude: point.longitude,
            accuracy: Math.max(0, Math.round(point.accuracy || 0)),
            captured: Date.now() / 1000,
        };
    } catch {
        if (request === rangeRequest && !stopped)
            rangeProblem.value = "Could not get a current location. Check location permission and try again.";
    } finally {
        if (request === rangeRequest) locating.value = false;
    }
}
const rangeReference = computed(() =>
    rangePosition.value ? fromLonLat([rangePosition.value.longitude, rangePosition.value.latitude]) : mapCenter.value
);
const targetPoint = computed(() => {
    const item = selectedTeam.value;
    if (!item) return null;
    if (item.kind === "shape") {
        const geometry = shapeGeometry(item);
        if (!geometry || !rangeReference.value) return null;
        return toLonLat(geometry.getClosestPoint(rangeReference.value));
    }
    return Number.isFinite(item.longitude) && Number.isFinite(item.latitude) ? [item.longitude, item.latitude] : null;
});
const targetMetrics = computed(() => {
    if (!targetPoint.value || !rangeReference.value) return "";
    const [lon, lat] = toLonLat(rangeReference.value),
        [toLon, toLat] = targetPoint.value;
    const distance = getDistance([lon, lat], [toLon, toLat]);
    if (distance < 1) return "at target";
    const bearing = sphericalInitialBearingDeg(lon, lat, toLon, toLat);
    return `${distance < 1000 ? Math.round(distance) + " m" : (distance / 1000).toFixed(1) + " km"} · ${Math.round(bearing)}° true`;
});
const locatedCount = computed(
    () =>
        nodes.value.length +
        (team.value?.enabled
            ? (team.value.records || []).filter(
                  (r) =>
                      !r.deleted &&
                      !r.withdrawn &&
                      (r.kind !== "alert" || r.active) &&
                      ((r.kind === "shape" && r.points?.length) ||
                          (Number.isFinite(r.latitude) && Number.isFinite(r.longitude)))
              ).length
            : 0)
);
const kinds = { 1: "User", 2: "Repeater", 3: "Room server", 4: "Sensor" };
let layer,
    source,
    clickKey,
    moveKey,
    currentMap,
    generation = 0,
    stopped = false;
function age(updated) {
    void clock.value;
    return formatMeshcoreAge(updated);
}
function nodeTime(node) {
    return node.heard || node.updated;
}
function nodeAge(node) {
    return `${node.heard ? "Last heard" : "Position advertised"} · ${age(nodeTime(node))}`;
}
function draw() {
    if (!source) return;
    source.clear();
    for (const node of nodes.value) {
        const feature = new Feature({
            geometry: new Point(fromLonLat([node.longitude, node.latitude])),
            meshcore: node,
        });
        const stamp = nodeTime(node),
            now = Date.now() / 1000;
        const stale = !Number.isFinite(stamp) || stamp <= 0 || stamp > now + 60 || now - stamp > 1800;
        feature.setStyle(
            new Style({
                image: new CircleStyle({
                    radius: 7,
                    fill: new Fill({ color: stale ? "#64748b" : "#14b8a6" }),
                    stroke: new Stroke({ color: "#ffffff", width: 2 }),
                }),
                text: new Text({
                    text: `${node.name || kinds[node.kind] || "Node"} · MeshCore`,
                    offsetY: -17,
                    font: "12px sans-serif",
                    fill: new Fill({ color: "#0f766e" }),
                    stroke: new Stroke({ color: "#ffffff", width: 3 }),
                }),
            })
        );
        source.addFeature(feature);
    }
    if (team.value?.enabled) {
        for (const item of team.value.records || []) {
            if (item.kind === "shape" && !item.deleted) {
                const geometry = shapeGeometry(item);
                if (!geometry) continue;
                const color = team.value.colors?.[item.color] || "#00bcd4";
                const feature = new Feature({ geometry, meshcoreTeam: item });
                feature.setStyle(
                    new Style({
                        stroke: new Stroke({
                            color,
                            width: item.shape_kind === 5 ? 4 : 2,
                            lineDash: item.geofence ? [7, 4] : undefined,
                        }),
                        fill: [2, 3, 4].includes(item.shape_kind) ? new Fill({ color: color + "22" }) : undefined,
                        text: new Text({
                            text: `${item.label || team.value.shape_kinds?.[item.shape_kind] || "Drawing"} · MeshCore`,
                            font: "12px sans-serif",
                            fill: new Fill({ color: "#0f172a" }),
                            stroke: new Stroke({ color: "#ffffff", width: 3 }),
                        }),
                    })
                );
                source.addFeature(feature);
                continue;
            }
            if (
                item.deleted ||
                item.withdrawn ||
                (item.kind === "alert" && !item.active) ||
                !Number.isFinite(item.latitude) ||
                !Number.isFinite(item.longitude)
            )
                continue;
            const feature = new Feature({
                geometry: new Point(fromLonLat([item.longitude, item.latitude])),
                meshcoreTeam: item,
            });
            feature.setStyle(
                new Style({
                    image: new CircleStyle({
                        radius: item.kind === "position" ? 8 : 6,
                        fill: new Fill({
                            color: ["alert", "casevac"].includes(item.kind)
                                ? "#ef4444"
                                : item.kind === "pin"
                                  ? "#f59e0b"
                                  : team.value.colors?.[item.color] || "#00bcd4",
                        }),
                        stroke: new Stroke({ color: "#0f172a", width: 2 }),
                    }),
                    text: new Text({
                        text: `${item.label || item.callsign || item.alias} · MeshCore team${item.kind === "position" && Date.now() / 1000 - item.heard >= 600 ? " · stale" : ""}`,
                        offsetY: -20,
                        font: "12px sans-serif",
                        fill: new Fill({ color: "#0f172a" }),
                        stroke: new Stroke({ color: "#ffffff", width: 3 }),
                    }),
                })
            );
            source.addFeature(feature);
        }
        const trails = new Map();
        for (const item of team.value.trails || []) {
            if (!Number.isFinite(item.longitude) || !Number.isFinite(item.latitude)) continue;
            if (!trails.has(item.alias)) trails.set(item.alias, []);
            trails.get(item.alias).push(fromLonLat([item.longitude, item.latitude]));
        }
        for (const points of trails.values()) {
            if (points.length < 2) continue;
            const trail = new Feature(new LineString(points));
            trail.setStyle(new Style({ stroke: new Stroke({ color: "#0891b280", width: 2, lineDash: [5, 5] }) }));
            source.addFeature(trail);
        }
    }
    layer?.setVisible(visible.value);
}
function detach() {
    if (clickKey) unByKey(clickKey);
    if (moveKey) unByKey(moveKey);
    moveKey = null;
    clickKey = null;
    if (layer && currentMap?.removeLayer) currentMap.removeLayer(layer);
    layer = null;
    source = null;
    currentMap = null;
}
watch(
    () => props.map,
    (map) => {
        detach();
        if (!map?.addLayer) return;
        currentMap = map;
        mapCenter.value = map.getView?.().getCenter?.() || null;
        moveKey = map.on?.("moveend", () => {
            mapCenter.value = map.getView?.().getCenter?.() || null;
        });
        source = new VectorSource();
        layer = new VectorLayer({ source, zIndex: 115, visible: visible.value });
        map.addLayer(layer);
        clickKey = map.on?.("singleclick", (event) => {
            const feature = map.forEachFeatureAtPixel?.(
                event.pixel,
                (f) => (f.get("meshcoreTeam") || f.get("meshcore") ? f : undefined),
                {
                    layerFilter: (l) => l === layer,
                    hitTolerance: 8,
                }
            );
            if (feature?.get("meshcoreTeam")) {
                open.value = true;
                focus(feature.get("meshcoreTeam"));
            }
            if (feature?.get("meshcore")) {
                selected.value = feature.get("meshcore");
                open.value = true;
            }
        });
        draw();
    },
    { immediate: true }
);
async function refresh() {
    if (busy.value || stopped || !props.active) return;
    const token = generation;
    busy.value = true;
    problem.value = "";
    try {
        const { data } = await window.api.get(apiPath("/meshcore/map"), {
            params: { radio: router?.currentRoute?.value?.query?.meshcoreRadio },
        });
        if (stopped || token !== generation) return;
        const result = data.result || {};
        if (owner.value !== result.owner || team.value?.channel_id !== result.tactical?.channel_id) {
            selected.value = null;
            selectedTeam.value = null;
        }
        if (selectedTeam.value) {
            selectedTeam.value =
                result.tactical?.records?.find(
                    (r) =>
                        r.kind === selectedTeam.value.kind &&
                        r.alias === selectedTeam.value.alias &&
                        r.id === selectedTeam.value.id &&
                        !r.deleted &&
                        (r.kind !== "alert" || r.active)
                ) || null;
        }
        owner.value = result.owner;
        radioId.value = result.radio_id || null;
        connected.value = Boolean(result.connected);
        team.value = result.tactical || null;
        channels.value = result.channels || [];
        contacts.value = result.contacts || [];
        defaultScope.value = result.channel_default_scope ?? null;
        teamSupported.value = Boolean(result.team_supported);
        nodes.value = (result.nodes || []).filter(
            (n) =>
                typeof n.peer === "string" &&
                Number.isFinite(n.latitude) &&
                Number.isFinite(n.longitude) &&
                Math.abs(n.latitude) <= 90 &&
                Math.abs(n.longitude) <= 180
        );
        if (selected.value) selected.value = nodes.value.find((node) => node.peer === selected.value.peer) || null;
        draw();
        focusNotification();
    } catch {
        if (token === generation && !stopped)
            problem.value = "Could not read saved MeshCore positions. Try refreshing.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
let focusedNotification = "";
function focusNotification() {
    const query = router?.currentRoute?.value?.query || {};
    const signature = JSON.stringify(query);
    if (
        !props.active ||
        !props.map ||
        signature === focusedNotification ||
        query.meshcoreOwner !== owner.value ||
        query.meshcoreTeam !== team.value?.channel_id
    )
        return;
    const item = team.value?.records?.find(
        (r) =>
            ["shape", "alert"].includes(r.kind) &&
            !r.deleted &&
            (r.kind !== "alert" || r.active) &&
            (`${r.alias}:${r.id}` === query.meshcoreFence || `${r.kind}:${r.alias}:${r.id}` === query.meshcoreItem)
    );
    if (!item) return;
    focusedNotification = signature;
    open.value = true;
    visible.value = true;
    focus(item);
}
watch(
    () => [router?.currentRoute?.value?.query, props.active, props.map],
    () => {
        if (
            (router?.currentRoute?.value?.query?.meshcoreFence || router?.currentRoute?.value?.query?.meshcoreItem) &&
            props.active
        )
            void refresh();
    },
    { immediate: true }
);
watch(open, (value) => {
    if (value) void refresh();
});
watch(visible, (value) => {
    layer?.setVisible(value);
    if (value) void refresh();
});
function focus(node) {
    selectedTeam.value = typeof node.kind === "string" ? node : null;
    if (selectedTeam.value) selected.value = null;
    mapCenter.value = props.map?.getView?.().getCenter?.() || null;
    if (node.kind === "shape") {
        const geometry = shapeGeometry(node);
        if (geometry)
            props.map?.getView?.().fit(geometry.getExtent(), { padding: [50, 50, 50, 50], maxZoom: 15, duration: 350 });
        selected.value = null;
        return;
    }
    if (!Number.isFinite(node.latitude) || !Number.isFinite(node.longitude)) return;
    selected.value = ["position", "pin", "alert", "report", "casevac"].includes(node.kind) ? null : node;
    props.map?.getView?.().animate({ center: fromLonLat([node.longitude, node.latitude]), zoom: 13, duration: 350 });
}
function fit() {
    if (source?.getFeatures().length)
        props.map?.getView?.().fit(source.getExtent(), { padding: [50, 50, 50, 50], maxZoom: 12, duration: 350 });
}
async function addContact() {
    const target = selected.value,
        identity = owner.value,
        token = generation;
    if (busy.value || !connected.value || !target || target.kind !== 1) return;
    busy.value = true;
    problem.value = "";
    try {
        await window.api.post(apiPath("/meshcore/contact-add"), {
            peer: target.peer,
            name: target.name || "MeshCore contact",
            expected_owner: identity,
        });
        if (token === generation && owner.value === identity && selected.value?.peer === target.peer)
            selected.value = { ...target, saved: 1 };
    } catch (error) {
        if (token === generation)
            problem.value = error?.response?.data?.error || "Could not save this MeshCore contact.";
    } finally {
        if (token === generation) busy.value = false;
    }
}
function message() {
    router?.push({
        name: "messages",
        query: { meshcore: selected.value.peer, ...(radioId.value ? { meshcoreRadio: radioId.value } : {}) },
    });
}
function manage() {
    router?.push({
        name: "meshcore-nodes",
        params: { peer: selected.value.peer },
        ...(radioId.value ? { query: { meshcoreRadio: radioId.value } } : {}),
    });
}
watch(owner, clearRange);
const timer = setInterval(() => {
    clock.value = Date.now();
    if (rangePosition.value && Date.now() / 1000 - rangePosition.value.captured > 120) clearRange();
    if ((visible.value || open.value) && props.active && !document.hidden) void refresh();
}, 30000);
onBeforeUnmount(() => {
    clearRange();
    stopped = true;
    generation++;
    clearInterval(timer);
    detach();
});
</script>
