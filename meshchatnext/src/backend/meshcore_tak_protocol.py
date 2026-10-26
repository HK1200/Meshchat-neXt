# SPDX-License-Identifier: 0BSD
"""Bounded TAK v1 protobuf codec; independently implemented from public wire fields.

Reference: deptofdefense/AndroidTacticalAssaultKit-CIV/takproto.
No generated upstream implementation or schema is bundled.
"""

from __future__ import annotations

import datetime
import math
import struct
import xml.etree.ElementTree as ET

LIMIT = 65536


def varint(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("Invalid protobuf integer")
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def read_varint(data, offset=0):
    value = 0
    for index in range(10):
        if offset + index >= len(data):
            raise EOFError("Incomplete protobuf integer")
        byte = data[offset + index]
        if index == 9 and byte > 1:
            raise ValueError("Oversized protobuf integer")
        value |= (byte & 127) << (index * 7)
        if not byte & 128:
            return value, offset + index + 1
    raise ValueError("Oversized protobuf integer")


def _field_varint(data, offset):
    try:
        return read_varint(data, offset)
    except EOFError as error:
        raise ValueError("Truncated protobuf integer") from error


def fields(data):
    if len(data) > LIMIT:
        raise ValueError("Oversized protobuf message")
    offset, count = 0, 0
    while offset < len(data):
        tag, offset = _field_varint(data, offset)
        number, kind = tag >> 3, tag & 7
        count += 1
        if not number or number > 0x1FFFFFFF or count > 4096:
            raise ValueError("Invalid protobuf field")
        if kind == 0:
            value, offset = _field_varint(data, offset)
        elif kind in (1, 2, 5):
            if kind == 2:
                length, offset = _field_varint(data, offset)
            else:
                length = 8 if kind == 1 else 4
            if length > LIMIT or offset + length > len(data):
                raise ValueError("Truncated protobuf field")
            value = data[offset : offset + length]
            offset += length
        else:
            raise ValueError("Unsupported protobuf wire type")
        yield number, kind, value


def message_field(number, data):
    return varint(number << 3 | 2) + varint(len(data)) + data


def safe_xml(data):
    if len(data) > LIMIT:
        raise ValueError("Oversized XML")
    text = data.decode("utf-8", errors="strict")
    if "<!" in text:
        raise ValueError("DTD and entities are unsupported")
    root = ET.fromstring(text)  # noqa: S314 -- UTF-8, bounded, declarations rejected.
    pending = [(root, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth > 64 or count > 4096:
            raise ValueError("XML structure exceeds limits")
        pending.extend((child, depth + 1) for child in node)
    return root


def encode_event(xml_data):
    event = safe_xml(xml_data)
    if event.tag != "event":
        raise ValueError("Expected a CoT event")
    result = bytearray()
    for number, key in (
        (1, "type"),
        (2, "access"),
        (3, "qos"),
        (4, "opex"),
        (5, "uid"),
        (9, "how"),
    ):
        value = event.get(key)
        if value:
            result += message_field(number, value.encode("utf-8"))
    for number, key in ((6, "time"), (7, "start"), (8, "stale")):
        raw = event.get(key)
        if not raw:
            raise ValueError("CoT event requires timestamps")
        date = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("Timestamp requires timezone")
        result += varint(number << 3) + varint(int(date.timestamp() * 1000))
    point = event.find("point")
    if point is None:
        raise ValueError("CoT event requires point")
    for number, key in ((10, "lat"), (11, "lon"), (12, "hae"), (13, "ce"), (14, "le")):
        if key in ("lat", "lon") and point.get(key) is None:
            raise ValueError("CoT coordinate is missing")
        value = float(point.get(key, "9999999"))
        if not math.isfinite(value):
            raise ValueError("Non-finite CoT point")
        result += varint(number << 3 | 1) + struct.pack("<d", value)
    detail = event.find("detail")
    if detail is not None:
        # Keeping complete detail elements as XML is explicitly allowed by TAK v1.
        raw = b"".join(ET.tostring(child, encoding="utf-8") for child in detail)
        result += message_field(15, message_field(1, raw))
    payload = message_field(2, bytes(result))
    if len(payload) > LIMIT:
        raise ValueError("Oversized TAK event")
    return payload


_DETAIL_FIELDS = {
    2: ("contact", {1: ("endpoint", 2), 2: ("callsign", 2)}),
    3: ("__group", {1: ("name", 2), 2: ("role", 2)}),
    4: ("precisionlocation", {1: ("geopointsrc", 2), 2: ("altsrc", 2)}),
    5: ("status", {1: ("battery", 0)}),
    6: (
        "takv",
        {1: ("device", 2), 2: ("platform", 2), 3: ("os", 2), 4: ("version", 2)},
    ),
    7: ("track", {1: ("speed", 1), 2: ("course", 1)}),
}


def decode_event(payload):
    events = [
        value for number, kind, value in fields(payload) if number == 2 and kind == 2
    ]
    if not events:
        return None  # Control-only messages do not invent a map point.
    if len(events) != 1:
        raise ValueError("Repeated TAK event")
    event, point, detail = (
        ET.Element("event", {"version": "2.0"}),
        ET.Element("point", {"lat": "0", "lon": "0", "hae": "0", "ce": "0", "le": "0"}),
        ET.Element("detail"),
    )
    typed = []
    for number, kind, value in fields(events[0]):
        if number in (1, 2, 3, 4, 5, 9) and kind == 2:
            event.set(
                {1: "type", 2: "access", 3: "qos", 4: "opex", 5: "uid", 9: "how"}[
                    number
                ],
                value.decode("utf-8"),
            )
        elif number in (6, 7, 8) and kind == 0:
            stamp = (
                datetime.datetime.fromtimestamp(value / 1000, datetime.UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )
            event.set({6: "time", 7: "start", 8: "stale"}[number], stamp)
        elif 10 <= number <= 14 and kind == 1:
            value = struct.unpack("<d", value)[0]
            if not math.isfinite(value):
                raise ValueError("Non-finite protobuf point")
            point.set(
                {10: "lat", 11: "lon", 12: "hae", 13: "ce", 14: "le"}[number],
                str(value),
            )
        elif number == 15 and kind == 2:
            for sub, wire, raw in fields(value):
                if sub == 1 and wire == 2:
                    fragment = safe_xml(b"<detail>" + raw + b"</detail>")
                    detail.extend(fragment)
                elif sub in _DETAIL_FIELDS and wire == 2:
                    name, mapping = _DETAIL_FIELDS[sub]
                    node = ET.Element(name)
                    for tag, scalar, content in fields(raw):
                        if tag not in mapping or scalar != mapping[tag][1]:
                            continue
                        attr = mapping[tag][0]
                        if scalar == 2:
                            content = content.decode("utf-8")
                        elif scalar == 1:
                            content = struct.unpack("<d", content)[0]
                            if not math.isfinite(content):
                                raise ValueError("Invalid detail scalar")
                        node.set(attr, str(content))
                    typed.append(node)
    if (
        "lat" not in point.attrib
        or "lon" not in point.attrib
        or not event.get("uid")
        or not event.get("type")
    ):
        raise ValueError("Incomplete TAK event")
    for node in typed:
        if detail.find(node.tag) is None:
            detail.append(node)
    event.extend((point, detail))
    return ET.tostring(event, encoding="utf-8")


def stream_frame(payload):
    if not payload or len(payload) > LIMIT:
        raise ValueError("Invalid TAK frame size")
    return b"\xbf" + varint(len(payload)) + payload


def pop_stream_frame(buffer):
    if not buffer:
        return None
    if buffer[0] != 0xBF:
        raise ValueError("Invalid TAK stream header")
    try:
        length, offset = read_varint(buffer, 1)
    except EOFError:
        return None
    if not 0 < length <= LIMIT:
        raise ValueError("Invalid TAK stream length")
    if len(buffer) < offset + length:
        return None
    return buffer[offset : offset + length], buffer[offset + length :]
