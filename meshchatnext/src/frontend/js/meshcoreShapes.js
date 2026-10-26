// SPDX-License-Identifier: MIT
// Adapts Open TAK's shape coordinate conventions to the existing OpenLayers map.
import { toLonLat, fromLonLat } from "ol/proj";
import { getDistance } from "ol/sphere";
import LineString from "ol/geom/LineString";
import Polygon, { circular } from "ol/geom/Polygon";
function vertex(point) {
    if (!Array.isArray(point) || point.length < 2 || !point.slice(0, 2).every(Number.isFinite))
        throw new Error("Drawing contains invalid coordinates.");
    const [lon, lat] = toLonLat(point);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180)
        throw new Error("Drawing is outside supported coordinates.");
    return [lat, lon];
}
export function drawingShape(feature, route = false) {
    const geometry = feature?.getGeometry?.();
    const type = geometry?.getType?.();
    let shape_kind, points, radius_m;
    if (type === "LineString") {
        shape_kind = route ? 5 : 0;
        points = geometry.getCoordinates().map(vertex);
    } else if (type === "Polygon") {
        const rings = geometry.getCoordinates();
        if (rings.length !== 1)
            throw new Error("Polygons with holes cannot fit this team format. Draw a single boundary instead.");
        points = rings[0].map(vertex);
        const first = points[0],
            last = points[points.length - 1];
        if (first && last && first[0] === last[0] && first[1] === last[1]) points.pop();
        shape_kind = 2;
    } else if (type === "Circle") {
        shape_kind = 4;
        const center = geometry.getCenter(),
            radius = geometry.getRadius();
        points = [vertex(center)];
        radius_m = Math.round(getDistance(toLonLat(center), toLonLat([center[0] + radius, center[1]])));
        if (!Number.isFinite(radius_m) || radius_m < 1)
            throw new Error("The circle radius must be at least one metre.");
    } else throw new Error("Choose a single line, polygon or circle from the drawing layer.");
    if (points.length > 120)
        throw new Error("This drawing has more than 120 vertices. Simplify or split it before sharing.");
    const result = { kind: "shape", shape_kind, points };
    if (radius_m != null) result.radius_m = radius_m;
    return result;
}
export function shapeGeometry(item) {
    if (!Array.isArray(item.points) || !item.points.length || item.points.length > 120) return null;
    const points = item.points;
    if (
        points.some(
            (p) =>
                !Array.isArray(p) ||
                p.length !== 2 ||
                !p.every(Number.isFinite) ||
                Math.abs(p[0]) > 90 ||
                Math.abs(p[1]) > 180
        )
    )
        return null;
    const coordinates = points.map(([lat, lon]) => fromLonLat([lon, lat]));
    if (item.shape_kind === 4) {
        if (points.length !== 1 || !Number.isFinite(item.radius_m) || item.radius_m <= 0 || item.radius_m > 10000000)
            return null;
        return circular([points[0][1], points[0][0]], item.radius_m, 64).transform("EPSG:4326", "EPSG:3857");
    }
    if ([2, 3].includes(item.shape_kind)) {
        if (coordinates.length < 3) return null;
        return new Polygon([[...coordinates, coordinates[0]]]);
    }
    return coordinates.length >= 2 ? new LineString(coordinates) : null;
}
