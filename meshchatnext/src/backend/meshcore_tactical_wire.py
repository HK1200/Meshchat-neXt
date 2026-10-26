# SPDX-License-Identifier: MIT
"""Open TAK team datagrams, adapted from jade-on-mesh/meshcore-open-tak.

Source: c12abb588ab960707b67b63c95bc09d7f9ab2e7e/lib/team/team_wire.dart.
Copyright (c) 2025 zjs81. MIT notice is shipped in THIRD_PARTY_NOTICES.txt.
A channel key protects the group, but a four-byte sender alias is NOT an
individually authenticated public identity. Never automatically link contacts.
"""

from __future__ import annotations

import math
import re
import struct

DATA_TYPE = 0x5654
MAX_PAYLOAD = 163
ROLES = (
    "Team member",
    "Team lead",
    "Medic",
    "Navigator",
    "Comms",
    "Driver / vehicle",
    "Security",
    "Observer",
    "Command / HQ",
    "Press",
)
COLORS = (
    "#00bcd4",
    "#ffffff",
    "#ffeb3b",
    "#ff9800",
    "#e040fb",
    "#f44336",
    "#8b1a1a",
    "#7e57c2",
    "#1a237e",
    "#2196f3",
    "#009688",
    "#4caf50",
    "#1b5e20",
    "#795548",
)
STATUSES = ("", "OK", "Busy", "Need help", "Returning", "Resting")
PIN_KINDS = (
    "Point",
    "Last known point",
    "Staging / command post",
    "Clue",
    "Hazard",
    "Landing zone",
    "Medical",
    "Subject found",
    "Water / resources",
    "Area searched",
)
SHAPE_KINDS = ("Line", "Freehand", "Polygon", "Rectangle", "Circle", "Route")
GEOFENCES = ("Off", "Entry", "Exit", "Entry and exit")
ROUTE_METHODS = ("Walking", "Driving", "Flying", "Swimming", "Watercraft")
AFFILIATIONS = ("Unknown", "Hostile", "Neutral", "Friendly")
URGENCIES = ("Other", "Observed", "Active", "Critical")
CASEVAC_COUNTS = (
    "urgent",
    "urgent_surgical",
    "priority",
    "routine",
    "convenience",
    "us_military",
    "us_civilian",
    "non_us_military",
    "non_us_civilian",
    "epw",
    "child",
)
CASEVAC_TEXT = {
    "frequency": 12,
    "callsign": 12,
    "marking_detail": 12,
    "place": 20,
    "remarks": 40,
}
CASEVAC_NUMBERS = {
    **dict.fromkeys(CASEVAC_COUNTS, 255),
    "equipment_flags": 31,
    "litter": 255,
    "ambulatory": 255,
    "security": 3,
    "marking": 4,
    "terrain_flags": 31,
    "nbc": 3,
}
ALERT_KINDS = ("SOS / 911", "In contact", "Ring the bell", "Geofence breached", "Alert")


def number(value, low, high):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError("Invalid tactical numeric value")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid tactical integer")
    return value


def coordinate(value, latitude=True):
    return number(value, -90 if latitude else -180, 90 if latitude else 180)


def degrees(value, latitude=True):
    scaled = coordinate(value, latitude) * 10000000
    # Dart rounds half away from zero, whereas Python round uses ties-to-even.
    return int(math.copysign(math.floor(abs(scaled) + 0.5), scaled))


def text(value, limit):
    if not isinstance(value, str) or "\x00" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid tactical text")
    raw = value.strip().encode("utf-8")
    if len(raw) > limit:
        raise ValueError("Tactical text exceeds its UTF-8 byte limit")
    return bytes([len(raw)]) + raw


def alias(value):
    if not isinstance(value, str) or len(value) != 8:
        raise ValueError("A four-byte team alias is required")
    try:
        raw = bytes.fromhex(value)
        if len(raw) != 4:
            raise ValueError("Invalid team alias")
        return raw
    except ValueError:
        raise ValueError("Invalid team alias") from None


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        if self.offset + size > len(self.data):
            raise ValueError("Truncated tactical datagram")
        start = self.offset
        self.offset += size
        return self.data[start : self.offset]

    def unpack(self, fmt):
        return struct.unpack(">" + fmt, self.take(struct.calcsize(">" + fmt)))

    def varint(self):
        value = 0
        for shift in range(0, 35, 7):
            byte = self.take(1)[0]
            if shift == 28 and byte > 15:
                raise ValueError("Tactical varint exceeds 32 bits")
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
        raise ValueError("Invalid tactical varint")

    def string(self, limit):
        size = self.take(1)[0]
        if size > limit:
            raise ValueError("Tactical text exceeds its wire limit")
        return self.take(size).decode("utf-8", errors="replace")

    @property
    def remaining(self):
        return len(self.data) - self.offset


def attachment(reader):
    if not reader.remaining:
        return None
    mode = reader.take(1)[0]
    if not mode:
        return None
    sid = reader.take(4).hex()
    packets, extra = reader.unpack("BH")
    if not 1 <= packets <= 64:
        raise ValueError("Invalid tactical attachment length")
    return {"mode": mode, "sid": sid, "packets": packets, "extra": extra}


def encode_attachment(value):
    """Open TAK pin/report reference. Media bytes are never embedded here."""
    if value is None:
        return b"\x00"
    if not isinstance(value, dict) or set(value) != {"mode", "sid", "packets", "extra"}:
        raise ValueError("Invalid tactical attachment")
    mode = integer(value["mode"], 1, 255)
    sid = value["sid"]
    if (
        not isinstance(sid, str)
        or not re.fullmatch(r"[0-9a-f]{8}", sid)
        or int(sid, 16) == 0
    ):
        raise ValueError("Invalid tactical attachment session")
    return (
        bytes([mode])
        + bytes.fromhex(sid)
        + struct.pack(
            ">BH", integer(value["packets"], 1, 64), integer(value["extra"], 0, 65535)
        )
    )


def varint(value):
    value = integer(value, 0, 0xFFFFFFFF)
    data = bytearray()
    while value >= 128:
        data.append((value & 127) | 128)
        value >>= 7
    data.append(value)
    return bytes(data)


def grid(value, latitude=True):
    scaled = coordinate(value, latitude) * 100000
    return int(math.copysign(math.floor(abs(scaled) + 0.5), scaled))


def shape_points(value, kind, deleted):
    if not isinstance(value, (tuple, list)) or len(value) > 120:
        raise ValueError("A tactical shape supports at most 120 vertices")
    points = []
    for point in value:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError("Invalid tactical shape vertex")
        points.append([coordinate(point[0]), coordinate(point[1], False)])
    minimum = 1 if kind == 4 else 3 if kind in (2, 3) else 2
    if not deleted and (len(points) < minimum or (kind == 4 and len(points) != 1)):
        raise ValueError("Not enough vertices for this tactical shape")
    return points


def decode(data):
    if not isinstance(data, bytes) or not 5 <= len(data) <= MAX_PAYLOAD:
        raise ValueError("Invalid tactical datagram length")
    r = Reader(data)
    kind = r.take(1)[0]
    result = {"alias": r.take(4).hex(), "identity_verified": False}
    if kind == 0x50:
        flags, lat, lon, alt, speed, heading, accuracy, battery, role_color, status = (
            r.unpack("BiihBBBBBB")
        )
        role = role_color >> 4
        result.update(
            kind="position",
            latitude=coordinate(lat / 1e7),
            longitude=coordinate(lon / 1e7, False),
            altitude=alt if flags & 1 else None,
            speed=speed / 2 if flags & 2 else None,
            heading=heading * 360 / 256 if flags & 2 else None,
            accuracy=accuracy,
            battery=None if battery == 255 else min(battery, 100),
            role=role,
            color=role_color & 15,
            status=status if status < len(STATUSES) else 0,
            callsign=r.string(20),
            from_radio=bool(flags & 4),
            sos=bool(flags & 8),
            relayed=bool(flags & 16),
        )
        if role == 15:
            result["role"] = integer(r.take(1)[0], 0, 24) if flags & 32 else 0
        if flags & 64:
            name_hash, count = r.unpack("HB")
            if count > 4:
                raise ValueError("Invalid heard-message list")
            result.update(name_hash=name_hash, heard=list(r.unpack("H" * count)))
        if result["color"] >= len(COLORS):
            result["color"] = 0
    elif kind == 0x4D:
        item_id, operation, pin_kind, lat, lon, timestamp = r.unpack("IBBiiI")
        if operation not in (0, 1) or pin_kind >= len(PIN_KINDS):
            raise ValueError("Invalid tactical pin operation")
        result.update(
            kind="pin",
            id=item_id,
            deleted=operation == 1,
            pin_kind=pin_kind,
            latitude=coordinate(lat / 1e7),
            longitude=coordinate(lon / 1e7, False),
            timestamp=timestamp,
            label=r.string(32),
            note=r.string(60),
            attachment=attachment(r),
        )
    elif kind == 0x53:
        item_id, state, lat, lon, accuracy = r.unpack("H B i i B")
        alert_kind = state >> 4
        if alert_kind >= len(ALERT_KINDS):
            raise ValueError("Invalid tactical alert")
        result.update(
            kind="alert",
            id=item_id,
            active=bool(state & 1),
            alert_kind=alert_kind,
            latitude=coordinate(lat / 1e7) if state & 2 else None,
            longitude=coordinate(lon / 1e7, False) if state & 2 else None,
            accuracy=accuracy,
            callsign=r.string(20),
            note=r.string(80),
        )
    elif kind == 0x43:
        item_id, op, lat, lon, stamp = r.unpack("IBiiI")
        if op not in (0, 1):
            raise ValueError("Invalid CASEVAC operation")
        result.update(
            kind="casevac",
            id=item_id,
            deleted=bool(op),
            latitude=coordinate(lat / 1e7),
            longitude=coordinate(lon / 1e7, False),
            timestamp=stamp,
            frequency=r.string(12),
            callsign=r.string(12),
        )
        for name in CASEVAC_COUNTS[:5]:
            result[name] = r.take(1)[0]
        for name in ("equipment_flags", "litter", "ambulatory", "security", "marking"):
            result[name] = integer(r.take(1)[0], 0, CASEVAC_NUMBERS[name])
        result["marking_detail"] = r.string(12)
        for name in CASEVAC_COUNTS[5:]:
            result[name] = r.take(1)[0]
        for name in ("terrain_flags", "nbc"):
            result[name] = integer(r.take(1)[0], 0, CASEVAC_NUMBERS[name])
        result.update(place=r.string(20), remarks=r.string(40))
    elif kind == 0x44:
        item_id, operation, shape_kind, color, timestamp = r.unpack("IBBBI")
        integer(operation, 0, 1)
        integer(shape_kind, 0, len(SHAPE_KINDS) - 1)
        integer(color, 0, len(COLORS) - 1)
        label = r.string(24)
        geofence = integer(r.take(1)[0], 0, 3)
        param, count = r.varint(), r.take(1)[0]
        if count > 120:
            raise ValueError("Too many tactical vertices")
        points, lat, lon = [], 0, 0
        for index in range(count):
            if index == 0:
                lat, lon = r.unpack("ii")
            else:
                a, b = r.varint(), r.varint()
                lat += (a >> 1) ^ -(a & 1)
                lon += (b >> 1) ^ -(b & 1)
            points.append([coordinate(lat / 1e5), coordinate(lon / 1e5, False)])
        result.update(
            kind="shape",
            id=item_id,
            deleted=operation == 1,
            shape_kind=shape_kind,
            color=color,
            timestamp=timestamp,
            label=label,
            geofence=geofence if shape_kind in (2, 3, 4) else 0,
            radius_m=integer(param, 1, 10000000)
            if shape_kind == 4 and operation == 0
            else 0,
            route_method=integer(param, 0, 4) if shape_kind != 4 else 0,
            points=shape_points(points, shape_kind, operation == 1),
        )
    elif kind == 0x52:
        item_id, ku, affiliation, lat, lon, timestamp, vehicles, people = r.unpack(
            "IBBiiIBB"
        )
        report_kind = integer(ku >> 4, 0, 1)
        result.update(
            kind="report",
            id=item_id,
            report_kind=report_kind,
            urgency=integer(ku & 15, 0, 3),
            affiliation=integer(affiliation, 0, 3),
            latitude=coordinate(lat / 1e7),
            longitude=coordinate(lon / 1e7, False),
            timestamp=timestamp,
            vehicles=vehicles,
            people=people,
            place=r.string(24),
            size=r.string(12),
            activity=r.string(100 if report_kind else 32),
            unit=r.string(24),
            equipment=r.string(28),
            attachment=attachment(r),
        )
        result["withdrawn"] = bool(r.take(1)[0] & 1) if r.remaining else False
    else:
        raise ValueError("Unsupported tactical datagram")
    # Allow future bounded trailing extensions, as Open TAK does.
    return result


def encode(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid tactical record")
    for field in ("deleted", "active", "from_radio", "sos", "relayed", "withdrawn"):
        if field in value and type(value[field]) is not bool:
            raise ValueError("Invalid tactical flag")
    if (value.get("latitude") is None) != (value.get("longitude") is None):
        raise ValueError("Both tactical coordinates are required")
    key = alias(value.get("alias"))
    kind = value.get("kind")
    required = {
        "position": {"latitude", "longitude"},
        "pin": {"latitude", "longitude", "id", "timestamp"},
        "report": {"latitude", "longitude", "id", "timestamp"},
        "alert": {"id"},
        "shape": {"id", "timestamp", "points", "shape_kind"},
        "casevac": {"id", "timestamp", "latitude", "longitude"},
    }
    if kind not in required or not required[kind] <= value.keys():
        raise ValueError("Missing or unsupported tactical fields")
    if kind == "position":
        role = integer(value.get("role", 0), 0, 24)
        color = integer(value.get("color", 0), 0, len(COLORS) - 1)
        status = integer(value.get("status", 0), 0, len(STATUSES) - 1)
        alt = value.get("altitude")
        speed, heading = value.get("speed"), value.get("heading")
        moving = speed is not None and heading is not None
        flags = (
            (1 if alt is not None else 0)
            | (2 if moving else 0)
            | (4 if value.get("from_radio") else 0)
            | (8 if value.get("sos") else 0)
            | (16 if value.get("relayed") else 0)
            | (32 if role >= 15 else 0)
        )
        battery = value.get("battery")
        data = (
            b"P"
            + key
            + struct.pack(
                ">BiihBBBBBB",
                flags,
                degrees(value["latitude"]),
                degrees(value["longitude"], False),
                integer(alt, -32768, 32767) if alt is not None else 0,
                min(255, math.floor(number(speed, 0, 127.5) * 2 + 0.5))
                if moving
                else 0,
                math.floor((number(heading, 0, 360) % 360) * 256 / 360 + 0.5) & 255
                if moving
                else 0,
                integer(value.get("accuracy", 0), 0, 255),
                integer(battery, 0, 100) if battery is not None else 255,
                (min(role, 15) << 4) | color,
                status,
            )
            + text(value.get("callsign", ""), 20)
        )
        if role >= 15:
            data += bytes([role])
    elif kind == "pin":
        data = (
            b"M"
            + key
            + struct.pack(
                ">IBBiiI",
                integer(value["id"], 0, 0xFFFFFFFF),
                1 if value.get("deleted") else 0,
                integer(value.get("pin_kind", 0), 0, len(PIN_KINDS) - 1),
                degrees(value["latitude"]),
                degrees(value["longitude"], False),
                integer(value["timestamp"], 0, 0xFFFFFFFF),
            )
            + text(value.get("label", ""), 32)
            + text(value.get("note", ""), 60)
            + encode_attachment(value.get("attachment"))
        )
    elif kind == "alert":
        has_position = (
            value.get("latitude") is not None and value.get("longitude") is not None
        )
        state = (
            (1 if value.get("active", True) else 0)
            | (2 if has_position else 0)
            | (integer(value.get("alert_kind", 0), 0, len(ALERT_KINDS) - 1) << 4)
        )
        data = (
            b"S"
            + key
            + struct.pack(
                ">HBiiB",
                integer(value["id"], 0, 65535),
                state,
                degrees(value["latitude"]) if has_position else 0,
                degrees(value["longitude"], False) if has_position else 0,
                integer(value.get("accuracy", 0), 0, 255),
            )
            + text(value.get("callsign", ""), 20)
            + text(value.get("note", ""), 80)
        )
    elif kind == "shape":
        shape_kind = integer(value["shape_kind"], 0, len(SHAPE_KINDS) - 1)
        deleted = value.get("deleted", False)
        points = shape_points(value["points"], shape_kind, deleted)
        geofence = integer(value.get("geofence", 0), 0, 3)
        if geofence and shape_kind not in (2, 3, 4):
            raise ValueError("A geofence requires a closed shape")
        param = (
            integer(value.get("radius_m", 0), 0 if deleted else 1, 10000000)
            if shape_kind == 4
            else integer(value.get("route_method", 0), 0, 4)
        )
        data = (
            b"D"
            + key
            + struct.pack(
                ">IBBBI",
                integer(value["id"], 0, 0xFFFFFFFF),
                int(deleted),
                shape_kind,
                integer(value.get("color", 2), 0, len(COLORS) - 1),
                integer(value["timestamp"], 0, 0xFFFFFFFF),
            )
            + text(value.get("label", ""), 24)
            + bytes([geofence])
            + varint(param)
            + bytes([len(points)])
        )
        previous = None
        for lat, lon in points:
            point = (grid(lat), grid(lon, False))
            if previous is None:
                data += struct.pack(">ii", *point)
            else:
                for current, old in zip(point, previous, strict=True):
                    delta = current - old
                    data += varint((delta << 1) ^ (delta >> 31))
            previous = point
    elif kind == "casevac":
        data = (
            b"C"
            + key
            + struct.pack(
                ">IBiiI",
                integer(value["id"], 0, 0xFFFFFFFF),
                int(value.get("deleted", False)),
                degrees(value["latitude"]),
                degrees(value["longitude"], False),
                integer(value["timestamp"], 0, 0xFFFFFFFF),
            )
        )
        data += text(value.get("frequency", ""), 12) + text(
            value.get("callsign", ""), 12
        )
        for name in (
            *CASEVAC_COUNTS[:5],
            "equipment_flags",
            "litter",
            "ambulatory",
            "security",
            "marking",
        ):
            data += bytes(
                [
                    integer(
                        value.get(name, 3 if name == "marking" else 0),
                        0,
                        CASEVAC_NUMBERS[name],
                    )
                ]
            )
        data += text(value.get("marking_detail", ""), 12)
        for name in (*CASEVAC_COUNTS[5:], "terrain_flags", "nbc"):
            data += bytes([integer(value.get(name, 0), 0, CASEVAC_NUMBERS[name])])
        data += text(value.get("place", ""), 20) + text(value.get("remarks", ""), 40)
    elif kind == "report":
        report_kind = integer(value.get("report_kind", 0), 0, 1)
        data = (
            b"R"
            + key
            + struct.pack(
                ">IBBiiIBB",
                integer(value["id"], 0, 0xFFFFFFFF),
                (report_kind << 4) | integer(value.get("urgency", 1), 0, 3),
                integer(value.get("affiliation", 0), 0, 3),
                degrees(value["latitude"]),
                degrees(value["longitude"], False),
                integer(value["timestamp"], 0, 0xFFFFFFFF),
                integer(value.get("vehicles", 0), 0, 255),
                integer(value.get("people", 0), 0, 255),
            )
            + text(value.get("place", ""), 24)
            + text(value.get("size", ""), 12)
            + text(value.get("activity", ""), 100 if report_kind else 32)
            + text(value.get("unit", ""), 24)
            + text(value.get("equipment", ""), 28)
            + encode_attachment(value.get("attachment"))
        )
        if value.get("withdrawn"):
            data += b"\x01"
    else:
        raise ValueError("Unsupported tactical record")
    if len(data) > MAX_PAYLOAD:
        raise ValueError("Tactical payload exceeds radio capacity")
    return data
