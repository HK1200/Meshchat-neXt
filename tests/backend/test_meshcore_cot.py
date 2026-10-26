# SPDX-License-Identifier: 0BSD
import asyncio
import ssl
import subprocess

import pytest

from meshchatnext.src.backend.meshcore_cot import (
    CotSession,
    point_from_cot,
    point_to_cot,
)


def test_cot_point_roundtrip_and_rejected_inputs():
    point = {
        "latitude": 0,
        "longitude": 0,
        "label": '<Synthetic & "point">',
        "note": "test only",
    }
    assert point_from_cot(point_to_cot(point))["label"] == point["label"]
    for raw in (
        b"<!DOCTYPE event><event/>",
        b'<event><point lat="nan" lon="0"/></event>',
        b"x" * 65537,
    ):
        with pytest.raises(ValueError):
            point_from_cot(raw)
    with pytest.raises(ValueError):
        point_to_cot({"latitude": True, "longitude": 0})


@pytest.fixture
def tls_files(tmp_path):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
        ],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return cert.read_text(), context


@pytest.mark.asyncio
async def test_local_tls_xml_exchange_requires_explicit_connection(tmp_path, tls_files):
    cert, context = tls_files
    received = []

    async def handler(reader, writer):
        try:
            received.append(await reader.readuntil(b"</event>"))
            data = point_to_cot(
                {"latitude": 0, "longitude": 0, "label": "Synthetic server"}
            )
            writer.write(data[:40])
            await writer.drain()
            writer.write(data[40:])
            await writer.drain()
            await reader.read()
        finally:
            writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=context)
    session = CotSession(tmp_path)
    try:
        assert not (await session.status())["connected"]
        await session.connect("localhost", server.sockets[0].getsockname()[1], ca=cert)
        await session.send_point(
            {"latitude": 0, "longitude": 0, "label": "Synthetic client"}
        )
        for _ in range(100):
            if session.items:
                break
            await asyncio.sleep(0.01)
        assert session.items[0]["label"] == "Synthetic server"
        assert point_from_cot(received[0])["label"] == "Synthetic client"
        await session.close()
        assert not session.items
        assert not (await session.status())["connected"]
    finally:
        await session.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_tls_rejects_hostname_mismatch(tmp_path, tls_files):
    cert, context = tls_files

    async def handler(reader, writer):
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=context)
    session = CotSession(tmp_path)
    try:
        with pytest.raises(ConnectionError):
            await session.connect(
                "127.0.0.1", server.sockets[0].getsockname()[1], ca=cert
            )
        assert not (await session.status())["connected"]
    finally:
        await session.close()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_negotiated_protobuf_switch_and_shape_exchange(tmp_path, tls_files):
    import xml.etree.ElementTree as ET

    from meshchatnext.src.backend.meshcore_tak_protocol import (
        encode_event,
        pop_stream_frame,
        safe_xml,
        stream_frame,
    )

    cert, context = tls_files
    done = asyncio.Event()

    async def handler(reader, writer):
        try:
            offer = safe_xml(point_to_cot({"latitude": 0, "longitude": 0}))
            offer.set("uid", "protocol-test")
            offer.set("type", "t-x-takp-v")
            detail = offer.find("detail")
            detail.clear()
            ET.SubElement(
                ET.SubElement(detail, "TakControl"),
                "TakProtocolSupport",
                {"version": "1"},
            )
            writer.write(ET.tostring(offer))
            await writer.drain()
            request = safe_xml(await reader.readuntil(b"</event>"))
            assert request.get("type") == "t-x-takp-q"
            assert request.get("uid") == "protocol-test"
            offer.set("type", "t-x-takp-r")
            detail.clear()
            ET.SubElement(
                ET.SubElement(detail, "TakControl"), "TakResponse", {"status": "true"}
            )
            shape = {
                "kind": "shape",
                "shape_kind": 5,
                "points": [[0, 0], [0.001, 0.001]],
                "label": "Protocol route",
                "route_method": 1,
            }
            frame = stream_frame(encode_event(point_to_cot(shape)))
            # Response and binary frame deliberately share one stream read.
            writer.write(ET.tostring(offer) + frame)
            await writer.drain()
            data = b""
            while pop_stream_frame(data) is None:
                data += await reader.read(1024)
            assert pop_stream_frame(data) is not None
            done.set()
            await reader.read()
        finally:
            writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=context)
    session = CotSession(tmp_path)
    try:
        await session.connect("localhost", server.sockets[0].getsockname()[1], ca=cert)
        for _ in range(100):
            if session.items:
                break
            await asyncio.sleep(0.01)
        assert session.protocol == "protobuf-v1"
        assert len(session.items) == 1
        assert session.items[0]["shape_kind"] == 5
        assert session.items[0]["points"] == [[0, 0], [0.001, 0.001]]
        await session.send_point(
            {"latitude": 0, "longitude": 0, "label": "Protocol reply"}
        )
        await asyncio.wait_for(done.wait(), 2)
    finally:
        await session.close()
        server.close()
        await server.wait_closed()


def test_malformed_shape_coordinate_is_rejected():
    import xml.etree.ElementTree as ET

    from meshchatnext.src.backend.meshcore_cot_geometry import shape_from_event

    with pytest.raises(ValueError, match="coordinate"):
        shape_from_event(
            ET.fromstring('<event><detail><link point="12"/></detail></event>')
        )


def test_rectangle_requires_four_vertices():
    from meshchatnext.src.backend.meshcore_cot_geometry import shape_details

    with pytest.raises(ValueError, match="vertex count"):
        shape_details(
            {"kind": "shape", "shape_kind": 3, "points": [[0, 0], [0, 1], [1, 1]]}
        )
