# SPDX-License-Identifier: 0BSD
"""Independent ATAK drawing/route/ellipse wire-format conversion."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

METHODS = ("Walking", "Driving", "Flying", "Swimming", "Watercraft")


def vertex(lat, lon):
    if (
        lat is None
        or lon is None
        or isinstance(lat, bool)
        or isinstance(lon, bool)
        or str(lat).strip() == ""
        or str(lon).strip() == ""
    ):
        raise ValueError("Invalid drawing coordinate")
    lat, lon = float(lat), float(lon)
    if (
        not math.isfinite(lat)
        or not math.isfinite(lon)
        or abs(lat) > 90
        or abs(lon) > 180
    ):
        raise ValueError("Invalid drawing coordinate")
    return [lat, lon]


def shape_from_event(event):
    detail = event.find("detail")
    if detail is None:
        return {}
    ellipse = detail.find("shape/ellipse")
    points = []
    for link in detail.findall("link"):
        if link.get("point"):
            values = link.get("point").split(",")
            if len(values) < 2:
                raise ValueError("Invalid drawing coordinate")
            points.append(vertex(*values[:2]))
    polyline = detail.find("shape/polyline")
    if not points and polyline is not None:
        points = [
            vertex(p.get("lat"), p.get("lon")) for p in polyline.findall("vertex")
        ]
    if ellipse is not None:
        major, minor = (
            float(ellipse.get("major", "nan")),
            float(ellipse.get("minor", "nan")),
        )
        if (
            not all(math.isfinite(v) and 0 < v <= 20000000 for v in (major, minor))
            or abs(major - minor) > 0.001
        ):
            raise ValueError("Ellipse cannot be represented as a MeshCore circle")
        point = event.find("point")
        result = {
            "kind": "shape",
            "shape_kind": 4,
            "points": [vertex(point.get("lat"), point.get("lon"))],
            "radius_m": major / 2,
            "color": 0,
            "geofence": 0,
        }
    elif points:
        if len(points) > 121:
            raise ValueError("Too many vertices")
        closed = len(points) > 2 and points[0] == points[-1]
        if closed:
            points.pop()
        route = event.get("type") == "b-m-r"
        kind = (
            5
            if route
            else 2
            if closed or (polyline is not None and polyline.get("closed") == "true")
            else 0
        )
        if len(points) < (3 if kind == 2 else 2) or len(points) > 120:
            raise ValueError("Invalid vertex count")
        result = {
            "kind": "shape",
            "shape_kind": kind,
            "points": points,
            "color": 0,
            "geofence": 0,
        }
        if route:
            attributes = detail.find("link_attr")
            method = attributes.get("method") if attributes is not None else None
            result["route_method"] = METHODS.index(method) if method in METHODS else 0
    else:
        if event.get("type", "").startswith("u-d-") or event.get("type") == "b-m-r":
            raise ValueError("Unsupported drawing")
        return {}
    hint = detail.find("meshcore")
    if hint is not None:
        kind = int(hint.get("shapeKind", result["shape_kind"]))
        if (kind in (0, 1) and result["shape_kind"] == 0) or (
            kind in (2, 3) and result["shape_kind"] == 2
        ):
            result["shape_kind"] = kind
        color, fence = int(hint.get("color", "0")), int(hint.get("geofence", "0"))
        if 0 <= color <= 15:
            result["color"] = color
        if 0 <= fence <= 3 and result["shape_kind"] in (2, 3, 4):
            result["geofence"] = fence
    return result


def shape_details(record):
    if record.get("kind") != "shape":
        return None
    points = record.get("points")
    kind = record.get("shape_kind")
    if (
        not isinstance(points, list)
        or not 1 <= len(points) <= 120
        or type(kind) is not int
        or not 0 <= kind <= 5
    ):
        raise ValueError("Invalid drawing")
    points = [
        vertex(*p) for p in points if isinstance(p, (list, tuple)) and len(p) == 2
    ]
    if len(points) != len(record["points"]) or len(points) < (
        1 if kind == 4 else 4 if kind == 3 else 3 if kind == 2 else 2
    ):
        raise ValueError("Invalid drawing vertex count")
    details = []
    cot_type = "b-m-r" if kind == 5 else "u-d-f"
    if kind == 4:
        radius = record.get("radius_m")
        if (
            type(radius) not in (int, float)
            or not math.isfinite(radius)
            or not 1 <= radius <= 10000000
            or len(points) != 1
        ):
            raise ValueError("Invalid circle radius")
        shape = ET.Element("shape")
        ET.SubElement(
            shape,
            "ellipse",
            {"major": str(radius * 2), "minor": str(radius * 2), "angle": "0"},
        )
        details.append(shape)
        cot_type = "u-d-c-e"
    else:
        vertices = [*points, points[0]] if kind in (2, 3) else points
        for index, (lat, lon) in enumerate(vertices):
            attributes = {"point": f"{lat},{lon}"}
            if kind == 5:
                attributes.update(type="b-m-p-c", relation="c", callsign=str(index + 1))
            details.append(ET.Element("link", attributes))
        if kind == 5:
            method = record.get("route_method", 0)
            if type(method) is not int or not 0 <= method < len(METHODS):
                raise ValueError("Invalid route method")
            details.append(
                ET.Element(
                    "link_attr",
                    {
                        "method": METHODS[method],
                        "type": "Ground",
                        "color": "-16728876",
                        "stroke": "3",
                        "direction": "Infil",
                        "routetype": "Primary",
                        "order": "Ascending",
                        "prefix": "CP",
                    },
                )
            )
    color, fence = record.get("color", 0), record.get("geofence", 0)
    if (
        type(color) is not int
        or not 0 <= color <= 15
        or type(fence) is not int
        or not 0 <= fence <= 3
    ):
        raise ValueError("Invalid drawing style")
    details.append(
        ET.Element(
            "meshcore",
            {"shapeKind": str(kind), "color": str(color), "geofence": str(fence)},
        )
    )
    return {
        "type": cot_type,
        "latitude": points[0][0],
        "longitude": points[0][1],
        "details": details,
    }
