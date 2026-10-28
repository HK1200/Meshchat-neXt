<template>
    <section
        v-if="query.mcMessage && active"
        class="shrink-0 min-w-0 w-full border-b border-sem-border bg-sem-surface px-3 py-2 text-xs"
        aria-label="MeshCore captured message route"
    >
        <div class="flex items-center gap-2 min-w-0">
            <button
                data-app-back
                type="button"
                aria-label="Back to message"
                class="underline shrink-0 p-1"
                @click="navigateAppBack(router)"
            >
                Back
            </button>
            <p class="font-semibold flex-1 min-w-0 truncate">
                MeshCore · {{ query.mcObservation === "-1" ? "client locations" : "message path" }}
            </p>
            <button v-if="count" class="underline shrink-0 p-1" type="button" @click="fit">Fit path</button>
            <button class="underline shrink-0 p-1" type="button" @click="close">Close path</button>
        </div>
        <p v-if="loading" role="status">Loading reported locations…</p>
        <p v-if="error" role="alert" class="break-words">{{ error }}</p>
        <details v-if="count" class="mt-1">
            <summary class="cursor-pointer">{{ count }} reported locations · About this path</summary>
            <p v-if="query.mcObservation === '-1'" class="mt-1 max-h-20 overflow-y-auto">
                Reported client positions only. The message’s full route was not inferred from these locations.
            </p>
            <p v-else class="mt-1 max-h-20 overflow-y-auto">
                Dashed lines join adjacent known hops only; gaps and ambiguous hashes are not joined. Positions may have
                changed since the message.
            </p>
        </details>
    </section>
</template>
<script setup>
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import { fromLonLat } from "ol/proj";
import { Style, Stroke, Fill, Circle as CircleStyle, Text } from "ol/style";
import { navigateAppBack } from "../../../js/androidBackNavigation";
import { apiPath } from "../../../js/constants";
import { useMeshCoreUi } from "../../../js/meshcoreUi";
const props = defineProps({ map: { type: Object, default: null }, active: Boolean });
const router = useRouter(),
    query = computed(() => router?.currentRoute?.value?.query || {});
const { snapshot } = useMeshCoreUi(
    () => null,
    () => Boolean(props.active && query.value.mcMessage)
);
const source = new VectorSource(),
    layer = new VectorLayer({ source, zIndex: 90 });
const count = ref(0),
    error = ref(""),
    loading = ref(false);
let generation = 0,
    attached = null;
function clear() {
    source.clear();
    count.value = 0;
}
function fit() {
    if (count.value && props.map)
        props.map.getView().fit(source.getExtent(), { padding: [90, 60, 90, 60], maxZoom: 13, duration: 200 });
}
watch(
    () => [
        props.map,
        props.active,
        query.value.mcMessage,
        query.value.mcOwner,
        query.value.mcTarget,
        query.value.mcKind,
        query.value.mcObservation,
    ],
    async () => {
        const current = ++generation;
        clear();
        error.value = "";
        loading.value = false;
        if (attached && attached !== props.map) {
            attached.removeLayer(layer);
            attached = null;
        }
        if (!props.map || !props.active || !query.value.mcMessage) return;
        if (!attached) {
            props.map.addLayer(layer);
            attached = props.map;
        }
        loading.value = true;
        try {
            const q = query.value;
            const { data } = await window.api.get(apiPath("/meshcore/message-details"), {
                params: { owner: q.mcOwner, kind: q.mcKind, target: q.mcTarget, id: q.mcMessage },
            });
            if (current !== generation) return;
            const index = Number(q.mcObservation || 0);
            if (!Number.isInteger(index) || index < -1) throw new Error("Invalid captured path");
            const route =
                index === -1 ? { points: data.result.endpoints, route: "endpoints" } : data.result.routes[index];
            if (!route?.points?.length) throw new Error("No unambiguous reported locations available");
            const points = route.points;
            for (let i = 0; i < points.length; i++) {
                const p = { order: i, ...points[i] },
                    coordinate = fromLonLat([p.longitude, p.latitude]);
                const marker = new Feature({
                    geometry: new Point(coordinate),
                    meshcoreRouteNode: p,
                    meshcoreMapContext: { radio_id: q.mcRadio, owner: q.mcOwner },
                });
                marker.setStyle(
                    new Style({
                        image: new CircleStyle({
                            radius: 7,
                            fill: new Fill({ color: "#78d6ba" }),
                            stroke: new Stroke({ color: "#153b36", width: 2 }),
                        }),
                        text: new Text({
                            text: `${p.order + 1} · ${p.name}`,
                            offsetY: -18,
                            font: "12px sans-serif",
                            fill: new Fill({ color: "#102e29" }),
                            backgroundFill: new Fill({ color: "#ffffffdd" }),
                            padding: [3, 4, 3, 4],
                        }),
                    })
                );
                source.addFeature(marker);
                const previous = points[i - 1];
                if (route.route === "flood" && previous && p.order === previous.order + 1) {
                    const segment = new Feature({
                        geometry: new LineString([fromLonLat([previous.longitude, previous.latitude]), coordinate]),
                    });
                    segment.setStyle(
                        new Style({ stroke: new Stroke({ color: "#208c72", width: 3, lineDash: [7, 7] }) })
                    );
                    source.addFeature(segment);
                }
            }
            count.value = points.length;
            fit();
        } catch (e) {
            if (current === generation) {
                clear();
                error.value = e.message || "Captured path unavailable";
            }
        } finally {
            if (current === generation) loading.value = false;
        }
    },
    { immediate: true }
);
watch(
    () => snapshot.value.owner,
    (owner) => {
        if (owner && owner !== query.value.mcOwner) {
            generation++;
            clear();
            loading.value = false;
            error.value = "MeshCore identity changed. Reopen the message path from its conversation.";
        }
    }
);
onBeforeUnmount(() => {
    generation++;
    if (attached) attached.removeLayer(layer);
    clear();
});
function close() {
    const next = { ...query.value };
    for (const key of ["mcMessage", "mcOwner", "mcTarget", "mcKind", "mcObservation"]) delete next[key];
    void router.replace({ query: next });
}
</script>
