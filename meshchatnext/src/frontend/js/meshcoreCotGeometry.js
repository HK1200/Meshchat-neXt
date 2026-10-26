// SPDX-License-Identifier: 0BSD
// Independent implementation of ATAK editable-polyline/ellipse detail conventions.
const METHODS = ["Walking", "Driving", "Flying", "Swimming", "Watercraft"];
export function validCotVertex(lat, lon) {
    if ((typeof lat === "string" && !lat.trim()) || (typeof lon === "string" && !lon.trim()))
        throw new Error("Empty drawing coordinate.");
    lat = Number(lat);
    lon = Number(lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180)
        throw new Error("Invalid drawing coordinate.");
    return [lat, lon];
}
export function cotShape(event) {
    const detail = event.querySelector("detail");
    if (!detail) return null;
    const ellipse = detail.querySelector("shape > ellipse");
    const hint = detail.querySelector("meshcore");
    const points = [...detail.children]
        .filter((n) => n.tagName === "link" && n.hasAttribute("point"))
        .map((n) => {
            const fields = n.getAttribute("point").split(",");
            if (fields.length < 2) throw new Error("Invalid drawing vertex.");
            return validCotVertex(fields[0], fields[1]);
        });
    const polyline = detail.querySelector("shape > polyline");
    if (!points.length && polyline)
        for (const node of polyline.querySelectorAll("vertex"))
            points.push(validCotVertex(node.getAttribute("lat"), node.getAttribute("lon")));
    if (ellipse) {
        const major = Number(ellipse.getAttribute("major")),
            minor = Number(ellipse.getAttribute("minor"));
        if (
            !Number.isFinite(major) ||
            !Number.isFinite(minor) ||
            major <= 0 ||
            minor <= 0 ||
            major > 20000000 ||
            minor > 20000000
        )
            throw new Error("Invalid ellipse dimensions.");
        if (Math.abs(major - minor) > 0.001)
            throw new Error("This ellipse is not a circle; it cannot be represented exactly in MeshCore.");
        const point = event.querySelector("point");
        const result = {
            kind: "shape",
            shape_kind: 4,
            points: [validCotVertex(point?.getAttribute("lat"), point?.getAttribute("lon"))],
            radius_m: major / 2,
            color: 0,
            geofence: 0,
        };
        if (hint) {
            const fence = Number(hint.getAttribute("geofence")),
                color = Number(hint.getAttribute("color"));
            if (Number.isInteger(fence) && fence >= 0 && fence <= 3) result.geofence = fence;
            if (Number.isInteger(color) && color >= 0 && color <= 15) result.color = color;
        }
        return result;
    }
    if (!points.length) return null;
    if (points.length > 121) throw new Error("Drawing has more than 120 vertices.");
    const closed = points.length > 2 && points[0][0] === points.at(-1)[0] && points[0][1] === points.at(-1)[1];
    if (closed) points.pop();
    const route = event.getAttribute("type") === "b-m-r";
    const shape_kind = route ? 5 : closed || polyline?.getAttribute("closed") === "true" ? 2 : 0;
    if (points.length < (shape_kind === 2 ? 3 : 2) || points.length > 120)
        throw new Error("Invalid drawing vertex count.");
    const result = { kind: "shape", shape_kind, points, color: 0, geofence: 0 };
    if (route)
        result.route_method = Math.max(0, METHODS.indexOf(detail.querySelector("link_attr")?.getAttribute("method")));
    // This optional extension retains MeshCore-only presentation, never identity or trust.
    if (hint) {
        const requested = Number(hint.getAttribute("shapeKind"));
        if (([0, 1].includes(requested) && shape_kind === 0) || ([2, 3].includes(requested) && shape_kind === 2))
            result.shape_kind = requested;
        const fence = Number(hint.getAttribute("geofence")),
            color = Number(hint.getAttribute("color"));
        if (Number.isInteger(fence) && fence >= 0 && fence <= 3 && [2, 3, 4].includes(result.shape_kind))
            result.geofence = fence;
        if (Number.isInteger(color) && color >= 0 && color <= 15) result.color = color;
    }
    return result;
}
export function cotShapeDetail(item, escape) {
    if (!Array.isArray(item.points) || !item.points.length || item.points.length > 120)
        throw new Error("Drawing requires 1–120 vertices.");
    const points = item.points.map((p) => {
        if (!Array.isArray(p) || p.length !== 2) throw new Error("Invalid drawing vertex.");
        return validCotVertex(...p);
    });
    const kind = item.shape_kind;
    if (kind === 3 && points.length !== 4) throw new Error("A rectangle requires four vertices.");
    if (
        !Number.isInteger(item.color ?? 0) ||
        (item.color ?? 0) < 0 ||
        (item.color ?? 0) > 15 ||
        !Number.isInteger(item.geofence ?? 0) ||
        (item.geofence ?? 0) < 0 ||
        (item.geofence ?? 0) > 3
    )
        throw new Error("Invalid drawing style.");
    if (
        !Number.isInteger(kind) ||
        kind < 0 ||
        kind > 5 ||
        points.length < (kind === 4 ? 1 : [2, 3].includes(kind) ? 3 : 2)
    )
        throw new Error("Invalid drawing type or vertex count.");
    let detail,
        type = kind === 5 ? "b-m-r" : "u-d-f";
    if (kind === 4) {
        if (points.length !== 1 || !Number.isFinite(item.radius_m) || item.radius_m < 1 || item.radius_m > 10000000)
            throw new Error("Invalid circle radius.");
        type = "u-d-c-e";
        detail = `<shape><ellipse major="${item.radius_m * 2}" minor="${item.radius_m * 2}" angle="0"/></shape>`;
    } else {
        const vertices = [2, 3].includes(kind) ? [...points, points[0]] : points;
        detail = vertices
            .map(
                ([lat, lon], i) =>
                    `<link point="${lat},${lon}"${kind === 5 ? ` uid="${crypto.randomUUID()}" type="b-m-p-c" relation="c" callsign="${i + 1}"` : ""}/>`
            )
            .join("");
        if (kind === 5)
            detail += `<link_attr color="-16728876" stroke="3" type="Ground" method="${escape(METHODS[item.route_method || 0] || METHODS[0])}" direction="Infil" routetype="Primary" order="Ascending" prefix="CP"/>`;
    }
    detail += `<meshcore shapeKind="${kind}" geofence="${[2, 3, 4].includes(kind) ? item.geofence || 0 : 0}" color="${item.color || 0}"/>`;
    return { type, detail, latitude: points[0][0], longitude: points[0][1] };
}
export function meshcoreCotRecord(item) {
    const fields =
        item.kind === "shape"
            ? ["kind", "shape_kind", "points", "radius_m", "route_method", "color", "geofence", "label"]
            : ["kind", "latitude", "longitude", "pin_kind", "label", "note"];
    return Object.fromEntries(fields.filter((k) => item[k] !== undefined).map((k) => [k, item[k]]));
}
