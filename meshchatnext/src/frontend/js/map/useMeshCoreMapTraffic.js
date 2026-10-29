import { ref, watch, onBeforeUnmount } from "vue";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import Point from "ol/geom/Point";
import LineString from "ol/geom/LineString";
import { fromLonLat } from "ol/proj";
import { getVectorContext } from "ol/render";
import { Style, Stroke, Fill, Circle as CircleStyle } from "ol/style";
import { unByKey } from "ol/Observable";
import { apiPath } from "../constants";

const LIFETIME = 8000;

// Nulls retain their slot: never draw or move a packet across an unknown hop.
export function trafficGeometry(packet, progress) {
    if (packet.route !== "flood" || !Array.isArray(packet.points)) return { points: [], segments: [], head: null };
    const points = packet.points
        .slice(0, 64)
        .map((p) =>
            Array.isArray(p) &&
            p.length === 2 &&
            p.every(Number.isFinite) &&
            Math.abs(p[0]) <= 180 &&
            Math.abs(p[1]) <= 90
                ? fromLonLat(p)
                : null
        );
    // Keep antimeridian crossings local in the projected world.
    const world = 40075016.68557849;
    for (let i = 1; i < points.length; i++) {
        if (points[i] && points[i - 1]) {
            points[i][0] += Math.round((points[i - 1][0] - points[i][0]) / world) * world;
        }
    }
    const segments = [];
    for (let i = 1; i < points.length; i++) {
        if (points[i - 1] && points[i]) segments.push([points[i - 1], points[i]]);
    }
    const slot = Math.max(0, Math.min(0.999999, progress)) * Math.max(0, points.length - 1);
    const index = Math.floor(slot),
        fraction = slot - index;
    const a = points[index],
        b = points[index + 1];
    const head = a && b ? a.map((value, i) => value + (b[i] - value) * fraction) : null;
    const wake = head
        ? Array.from({ length: 21 }, (_, step) =>
              a.map((value, i) => value + (b[i] - value) * Math.max(0, fraction - 0.48 * (1 - step / 20)))
          )
        : [];
    return { points: points.filter(Boolean), segments, head, wake };
}

// A gap badge is an annotation between known points, never a claimed node position.
export function trafficGaps(packet) {
    if (packet.route !== "flood" || !Array.isArray(packet.points)) return [];
    const points = packet.points
        .slice(0, 64)
        .map((point) => trafficGeometry({ route: "flood", points: [point] }, 0).points[0] || null);
    const gaps = [];
    let previous = null,
        missing = 0;
    for (const point of points) {
        if (!point) {
            missing++;
            continue;
        }
        if (previous && missing) {
            const x = point[0] + Math.round((previous[0] - point[0]) / 40075016.68557849) * 40075016.68557849;
            gaps.push({
                key: `${previous}:${point}`,
                count: missing,
                position: [(previous[0] + x) / 2, (previous[1] + point[1]) / 2],
            });
        }
        previous = point;
        missing = 0;
    }
    return gaps;
}

export function useMeshCoreMapTraffic(options, gapDetails = ref([])) {
    const status = ref("");
    let stop = () => {};
    const unwatch = watch(
        options,
        ({ map, enabled, owner, radioId, connected }) => {
            stop();
            status.value = "";
            gapDetails.value = [];
            if (!map || !enabled || !owner || !connected) return;
            const source = new VectorSource({ wrapX: false });
            const layer = new VectorLayer({ source, zIndex: 116 });
            const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
            const seen = new Set();
            let packets = [],
                stopped = false,
                fetching = false,
                baseline = true,
                frame = null;
            let lastFrame = 0,
                epoch = 0;
            const request = new AbortController();
            function syncGaps() {
                const gaps = new Map(packets.flatMap(trafficGaps).map((gap) => [gap.key, gap]));
                // One control summary, never geographically placed unknown-node overlays.
                gapDetails.value = [...gaps.values()].map(({ key, count }) => ({ key, count }));
            }
            const clear = () => {
                packets = [];
                syncGaps();
                if (frame !== null) cancelAnimationFrame(frame);
                frame = null;
                map.render?.();
            };
            function tick(time) {
                frame = null;
                if (stopped || document.hidden) return;
                if (time - lastFrame >= 32) {
                    const count = packets.length;
                    packets = packets.filter((p) => Date.now() - p.started < LIFETIME);
                    if (packets.length !== count) syncGaps();
                    lastFrame = time;
                    map.render?.();
                }
                if (packets.length) frame = requestAnimationFrame(tick);
            }
            const key = layer.on("postrender", (event) => {
                if (!event.context || document.hidden || stopped) return;
                const context = getVectorContext(event);
                for (const packet of packets) {
                    const age = (Date.now() - packet.started) / LIFETIME;
                    if (age >= 1) continue;
                    const fade = Math.min(1, (1 - age) * 2);
                    const geometry = trafficGeometry(packet, (age * 2) % 1);
                    const phase = (age * 4) % 1;
                    context.setStyle(
                        new Style({
                            image: new CircleStyle({
                                radius: motion?.matches ? 7 : 7 + phase * 17,
                                stroke: new Stroke({
                                    color: `rgba(34,211,238,${fade * (motion?.matches ? 1 : 1 - phase)})`,
                                    width: 2,
                                }),
                            }),
                        })
                    );
                    for (const point of geometry.points) context.drawGeometry(new Point(point));
                    // The comet's wake stays within the current known segment.
                    if (geometry.head && !motion?.matches) {
                        for (let step = 1; step < geometry.wake.length; step++) {
                            const strength = step / (geometry.wake.length - 1);
                            const alpha = fade * strength * strength;
                            const segment = new LineString([geometry.wake[step - 1], geometry.wake[step]]);
                            for (const [color, width] of [
                                [`rgba(8,145,178,${alpha * 0.32})`, 4 + strength * 15],
                                [`rgba(34,211,238,${alpha})`, 0.5 + strength * 7],
                                [`rgba(224,252,255,${alpha * strength})`, 0.5 + strength * 2],
                            ]) {
                                context.setStyle(new Style({ stroke: new Stroke({ color, width, lineCap: "round" }) }));
                                context.drawGeometry(segment);
                            }
                        }
                        for (const [radius, color] of [
                            [18, `rgba(34,211,238,${fade * 0.12})`],
                            [10, `rgba(34,211,238,${fade * 0.35})`],
                            [5, `rgba(255,255,255,${fade})`],
                        ]) {
                            context.setStyle(
                                new Style({
                                    image: new CircleStyle({
                                        radius,
                                        fill: new Fill({ color }),
                                        stroke: radius === 5 ? new Stroke({ color: "#0891b2", width: 1.5 }) : undefined,
                                    }),
                                })
                            );
                            context.drawGeometry(new Point(geometry.head));
                        }
                    }
                }
            });
            map.addLayer(layer);
            async function poll() {
                if (stopped || fetching || document.hidden) return;
                fetching = true;
                const token = epoch;
                try {
                    const { data } = await window.api.get(apiPath("/meshcore/map-traffic"), {
                        signal: request.signal,
                        params: { radio: radioId || undefined, owner },
                    });
                    if (stopped || token !== epoch || document.hidden) return;
                    const result = data.result || {};
                    if (result.owner !== owner || (radioId && result.radio_id !== radioId) || !result.connected) {
                        clear();
                        baseline = true;
                        status.value = "Traffic paused · refresh positions or reconnect MeshCore.";
                        return;
                    }
                    const fresh = [];
                    for (const packet of result.packets || []) {
                        if (seen.has(packet.id)) continue;
                        seen.add(packet.id);
                        if (!baseline && packet.route === "flood" && Date.now() / 1000 - packet.received <= 15) {
                            fresh.push({ ...packet, started: Date.now() });
                        }
                    }
                    // Do not replay history when enabling, resuming, or changing maps/radios.
                    baseline = false;
                    if (seen.size > 512) for (const id of [...seen].slice(0, seen.size - 256)) seen.delete(id);
                    packets = [...packets.filter((p) => Date.now() - p.started < LIFETIME), ...fresh].slice(-16);
                    syncGaps();
                    status.value = packets.length
                        ? "Partial routes · sender/destination unavailable; gaps mark unknown, ambiguous or unlocated hops."
                        : "Listening for new flood packets · direct routes are not shown as observed travel.";
                    if (packets.length && frame === null) frame = requestAnimationFrame(tick);
                } catch {
                    if (!stopped && token === epoch) {
                        clear();
                        baseline = true;
                        status.value = "Packet traffic unavailable · retrying.";
                    }
                } finally {
                    fetching = false;
                }
            }
            const visibility = () => {
                epoch++;
                clear();
                baseline = true;
                if (!document.hidden) void poll();
            };
            document.addEventListener("visibilitychange", visibility);
            const timer = setInterval(poll, 2000);
            void poll();
            stop = () => {
                stopped = true;
                request.abort();
                clearInterval(timer);
                document.removeEventListener("visibilitychange", visibility);
                clear();
                unByKey(key);
                map.removeLayer(layer);
            };
        },
        { immediate: true }
    );
    onBeforeUnmount(() => {
        unwatch();
        stop();
    });
    return status;
}
