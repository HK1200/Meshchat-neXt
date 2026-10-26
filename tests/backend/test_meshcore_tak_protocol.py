# SPDX-License-Identifier: 0BSD
import struct

import pytest

from meshchatnext.src.backend.meshcore_cot import point_to_cot
from meshchatnext.src.backend.meshcore_tak_protocol import (
    decode_event,
    encode_event,
    fields,
    message_field,
    pop_stream_frame,
    read_varint,
    safe_xml,
    stream_frame,
    varint,
)


def test_protobuf_roundtrip_and_fragmented_stream():
    payload = encode_event(
        point_to_cot({"latitude": 0, "longitude": 1, "label": "Synthetic"})
    )
    event = safe_xml(decode_event(payload))
    assert event.find("detail/contact").get("callsign") == "Synthetic"
    assert float(event.find("point").get("lon")) == 1
    frame = stream_frame(payload)
    for length in range(len(frame)):
        assert pop_stream_frame(frame[:length]) is None
    assert pop_stream_frame(frame + frame) == (payload, frame)


def test_independent_typed_contact_vector():
    # Hand-constructed protobuf fields, not produced by the encoder under test.
    contact = message_field(2, b"Typed sender")
    detail = message_field(2, contact)
    event = message_field(1, b"a-u-G") + message_field(5, b"test-uid")
    event += varint(10 << 3 | 1) + struct.pack("<d", 0)
    event += varint(11 << 3 | 1) + struct.pack("<d", 0)
    event += message_field(15, detail)
    xml = safe_xml(decode_event(message_field(2, event)))
    assert xml.find("detail/contact").get("callsign") == "Typed sender"


def test_bounds_and_invalid_wire():
    for bad in (b"\xbf\x00", b"\xbf" + varint(65537), b"x"):
        with pytest.raises(ValueError):
            pop_stream_frame(bad)
    with pytest.raises(ValueError):
        list(fields(b"\x0f"))
    with pytest.raises(ValueError):
        read_varint(b"\xff" * 10)
    with pytest.raises(ValueError):
        safe_xml(b"<!DOCTYPE event><event/>")
    assert decode_event(message_field(1, varint(8) + varint(1))) is None


def test_proto3_omitted_zero_coordinates_are_valid_and_truncated_varints_fail():
    event = message_field(1, b"a-u-G") + message_field(5, b"zero-point")
    xml = safe_xml(decode_event(message_field(2, event)))
    assert float(xml.find("point").get("lat")) == 0
    assert float(xml.find("point").get("lon")) == 0
    with pytest.raises(ValueError):
        list(fields(b"\x80"))
