// SPDX-License-Identifier: 0BSD
import { toLonLat } from "ol/proj";

const NODE_KINDS = { 1: "Client", 2: "Repeater", 3: "Room server", 4: "Sensor" };
const text = (v, max = 512) =>
    typeof v === "string" ? v.trim().slice(0, max) : typeof v === "number" && Number.isFinite(v) ? String(v) : "";
const object = (v) => (v && typeof v === "object" ? v : {});
export const nodePressIsSuppressed = (map) => Date.now() < (map?.get?.("nodeDetailsPressUntil") || 0);

function isNodePoint(feature) {
    const geometry = feature?.getGeometry?.();
    return ["Point", "MultiPoint"].includes(geometry?.getType?.());
}

export function mapNodeDetails(feature, pressedCoordinate) {
    if (!isNodePoint(feature)) return null;
    const get = (key) => feature.get?.(key);
    const telemetry = object(get("telemetry")),
        peer = object(get("peer")),
        discovered = object(get("discovered"));
    const meshcore = object(get("meshcore")),
        team = object(get("meshcoreTeam")),
        route = object(get("meshcoreRouteNode"));
    const context = object(get("meshcoreMapContext")),
        props = object(feature.getProperties?.());
    const isTeam = Boolean(get("meshcoreTeam")),
        isMeshcore = Boolean(get("meshcore") || isTeam || get("meshcoreRouteNode"));
    const source = isTeam
        ? "MeshCore team"
        : isMeshcore
          ? "MeshCore"
          : get("telemetry")
            ? "Reticulum"
            : get("discovered")
              ? "Discovered interface"
              : "Map point";
    const data = isTeam
        ? team
        : get("meshcore")
          ? meshcore
          : get("meshcoreRouteNode")
            ? route
            : get("discovered")
              ? discovered
              : get("telemetry")
                ? telemetry
                : props;
    const title =
        text(
            data.name ||
                data.label ||
                data.callsign ||
                peer.display_name ||
                get("name") ||
                get("label") ||
                data.alias ||
                data.public_key ||
                telemetry.destination_hash,
            160
        ) || "Unnamed map point";
    const rows = [];
    const add = (label, value) => {
        const v = text(value);
        if (v) rows.push({ label, value: v });
    };
    add("Type", isTeam ? team.kind : isMeshcore ? NODE_KINDS[data.kind] || data.kind : discovered.type || data.type);
    add(
        "Public address",
        data.public_key || data.peer || data.destination_hash || data.address || peer.destination_hash
    );
    const loc = object(telemetry.telemetry?.location);
    let lat = data.latitude ?? loc.latitude,
        lon = data.longitude ?? loc.longitude;
    const geometry = feature.getGeometry();
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        const coordinate =
            geometry.getType() === "Point"
                ? geometry.getCoordinates?.() || geometry.getFlatCoordinates?.()?.slice(0, 2)
                : geometry.getClosestPoint?.(pressedCoordinate);
        if (Array.isArray(coordinate) && coordinate.every(Number.isFinite)) [lon, lat] = toLonLat(coordinate);
    }
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180)
        add("Position", `${lat.toFixed(6)}, ${lon.toFixed(6)}`);
    const altitude = data.altitude ?? loc.altitude;
    add("Altitude", Number.isFinite(altitude) ? `${altitude} m` : null);
    add("Accuracy", Number.isFinite(loc.accuracy) ? `${loc.accuracy} m` : null);
    add("Speed", Number.isFinite(loc.speed) ? `${loc.speed} m/s` : null);
    add("Heading", Number.isFinite(loc.heading) ? `${loc.heading}°` : null);
    const battery = telemetry.telemetry?.battery?.charge_percent ?? data.battery_percent;
    add("Battery", Number.isFinite(battery) ? `${battery}%` : null);
    add("Advertised hops", Number.isInteger(data.hops) && data.hops >= 0 ? data.hops : null);
    const stamp = data.heard || data.timestamp || data.updated;
    const date =
        typeof stamp === "number"
            ? new Date(stamp < 1e12 ? stamp * 1000 : stamp)
            : typeof stamp === "string"
              ? new Date(stamp)
              : null;
    if (date && Number.isFinite(date.getTime())) add(data.heard ? "Last heard" : "Reported", date.toLocaleString());
    add("Radio", context.radio_label || context.radio_id);
    if (context.team_enabled) add("View", "Teams");
    if (isTeam) {
        add("Callsign", team.callsign);
        add("Alias", team.alias);
        add("Role", context.roles?.[team.role]);
        add(
            "Status",
            team.withdrawn
                ? "Withdrawn"
                : team.active === false
                  ? "Inactive"
                  : team.kind === "alert"
                    ? "Active alert"
                    : null
        );
        add("Priority", context.urgencies?.[team.urgency]);
        add("Location", team.place);
        add("Activity", team.activity);
        add("Unit", team.unit);
        add("Equipment", team.equipment);
        add("Remarks", team.remarks);
    }
    add("Interface", discovered.interface);
    add("Via", discovered.via);
    add("Note", data.note || data.description || telemetry.note);
    if (get("meshcoreRouteNode")) {
        add("Captured path position", Number.isInteger(route.order) ? route.order + 1 : null);
        add("Path context", "Reported location; this does not prove that this node relayed the message.");
    }
    const link = object(telemetry.physical_link);
    add("RSSI", Number.isFinite(link.rssi) ? `${link.rssi} dBm` : null);
    add("SNR", Number.isFinite(link.snr) ? `${link.snr} dB` : null);
    return { title, source, rows, team: isTeam };
}

/** Read all overlapping dots, including children of an aggregate marker. */
export function pickMapNodeDetails(map, event) {
    const pixel = map.getEventPixel(event),
        coordinate = map.getCoordinateFromPixel?.(pixel);
    const features = new Set();
    map.forEachFeatureAtPixel(
        pixel,
        (feature) => {
            const children = feature.get?.("clusterItems");
            if (Array.isArray(children)) children.forEach((f) => features.add(f));
            else if (isNodePoint(feature)) features.add(feature);
            return undefined;
        },
        { hitTolerance: 15 }
    );
    return [...features].map((feature) => mapNodeDetails(feature, coordinate)).filter(Boolean);
}
