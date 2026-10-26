# SPDX-License-Identifier: 0BSD
"""Explicit TLS XML CoT session, memory-only previews; no radio forwarding."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import math
import os
import ssl
import tempfile
import uuid
import xml.etree.ElementTree as ET

from meshchatnext.src.backend.meshcore_cot_geometry import (
    shape_details,
    shape_from_event,
)
from meshchatnext.src.backend.meshcore_tak_http import TakWebClient, enroll
from meshchatnext.src.backend.meshcore_tak_protocol import (
    decode_event,
    encode_event,
    pop_stream_frame,
    safe_xml,
    stream_frame,
)

MAX_EVENT = 65536


def point_from_cot(data):
    text = data.decode("utf-8", errors="strict")
    if len(data) > MAX_EVENT or "<!" in text:
        raise ValueError("Unsupported CoT XML")
    # UTF-8 only, no DTD/entity declarations, bounded to 64 KiB before parsing.
    event = ET.fromstring(text)  # noqa: S314
    if event.tag != "event":
        raise ValueError("Not a CoT event")
    point = event.find("point")
    if point is None:
        raise ValueError("No point")
    lat, lon = float(point.attrib["lat"]), float(point.attrib["lon"])
    if (
        not math.isfinite(lat)
        or not math.isfinite(lon)
        or not (-90 <= lat <= 90 and -180 <= lon <= 180)
    ):
        raise ValueError("Invalid coordinates")
    contact, remarks = event.find("detail/contact"), event.find("detail/remarks")
    return {
        "kind": "pin",
        "latitude": lat,
        "longitude": lon,
        "pin_kind": 0,
        "label": (
            (contact.get("callsign") if contact is not None else None) or "TAK point"
        )[:128],
        "note": ((remarks.text if remarks is not None else None) or "")[:256],
        "source_uid": event.get("uid", "")[:128],
        "stale": event.get("stale", "")[:64],
        **shape_from_event(event),
    }


def point_to_cot(record):
    shape = shape_details(record)
    lat, lon = (
        (shape["latitude"], shape["longitude"])
        if shape
        else (record.get("latitude"), record.get("longitude"))
    )
    if (
        type(lat) not in (float, int)
        or type(lon) not in (float, int)
        or not math.isfinite(lat)
        or not math.isfinite(lon)
        or not (-90 <= lat <= 90 and -180 <= lon <= 180)
    ):
        raise ValueError("Invalid coordinates")
    label, note = record.get("label", ""), record.get("note", "")
    if (
        not isinstance(label, str)
        or not isinstance(note, str)
        or len(label) > 128
        or len(note) > 256
    ):
        raise ValueError("Invalid point text")
    now = datetime.datetime.now(datetime.UTC)

    def stamp(value):
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")

    event = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": str(uuid.uuid4()),
            "type": shape["type"] if shape else "a-u-G",
            "time": stamp(now),
            "start": stamp(now),
            "stale": stamp(now + datetime.timedelta(minutes=5)),
            "how": "h-e",
        },
    )
    ET.SubElement(
        event,
        "point",
        {
            "lat": str(lat),
            "lon": str(lon),
            "hae": "9999999",
            "ce": "9999999",
            "le": "9999999",
        },
    )
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", {"callsign": label or "MeshCore point"})
    ET.SubElement(detail, "remarks").text = note
    if shape:
        detail.extend(shape["details"])
    return ET.tostring(event, encoding="utf-8") + b"\n"


class CotSession:
    def __init__(self, folder):
        self.folder = folder
        self.writer = None
        self.reader_task = None
        self.items = []
        self.state = "disconnected"
        self.host = ""
        self.dropped = 0
        self.protocol = "xml"
        self.negotiating = None
        self.negotiation_task = None
        self.write_lock = asyncio.Lock()
        self.auto_protocol = True
        self.web = None
        self.enrollment = None

    async def status(self):
        return {
            "connected": self.writer is not None and not self.writer.is_closing(),
            "state": self.state,
            "host": self.host,
            "items": list(self.items),
            "dropped": self.dropped,
            "protocol": self.protocol,
            "negotiating": self.negotiating is not None,
        }

    async def close(self):
        self.web = None
        self.enrollment = None
        timer, self.negotiation_task = self.negotiation_task, None
        if timer and timer is not asyncio.current_task():
            timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await timer
        self.negotiating = None
        self.protocol = "xml"
        task, self.reader_task = self.reader_task, None
        if task and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        writer, self.writer = self.writer, None
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(writer.wait_closed(), 2)
        self.items = []
        self.state = "disconnected"
        return {"connected": False}

    async def connect(
        self,
        host,
        port,
        ca="",
        certificate="",
        private_key="",
        auto_protocol=True,
        https_port=8443,
        username="",
        password="",
    ):
        if (
            not isinstance(host, str)
            or not host
            or len(host) > 253
            or any(c in host for c in "/\\@\r\n\t ")
        ):
            raise ValueError("Enter a server hostname")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid server port")
        if any(
            not isinstance(v, str) or len(v) > 32768
            for v in (ca, certificate, private_key)
        ) or bool(certificate) != bool(private_key):
            raise ValueError("Invalid TLS certificate configuration")
        if type(auto_protocol) is not bool:
            raise ValueError("Invalid protocol option")
        chosen = (
            self.enrollment
            if self.enrollment and self.enrollment["host"] == host and not certificate
            else None
        )
        if chosen:
            certificate, private_key = chosen["certificate"], chosen["private_key"]
            ca = ca or chosen["ca"]
        await self.close()
        self.auto_protocol = auto_protocol
        context = ssl.create_default_context(cadata=ca or None)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if certificate:
            paths = []
            try:
                for content in (certificate, private_key):
                    fd, path = tempfile.mkstemp(prefix="tak-tls-", dir=self.folder)
                    paths.append(path)
                    with os.fdopen(fd, "w") as f:
                        f.write(content)
                context.load_cert_chain(paths[0], paths[1])
            finally:
                for path in paths:
                    with contextlib.suppress(OSError):
                        os.unlink(path)
        web = TakWebClient(host, https_port, context, username, password)
        self.state = "connecting"
        try:
            reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, port, ssl=context, server_hostname=host, limit=MAX_EVENT
                ),
                15,
            )
        except Exception:
            self.state = "TLS connection failed · check address and certificates"
            raise ConnectionError("TAK TLS connection failed") from None
        if username:
            auth = ET.Element("auth")
            ET.SubElement(
                auth,
                "cot",
                {
                    "username": username,
                    "password": password,
                    "uid": "meshchat-next-" + str(uuid.uuid4()),
                },
            )
            try:
                self.writer.write(
                    b'<?xml version="1.0" encoding="UTF-8"?>\n'
                    + ET.tostring(auth, encoding="utf-8")
                )
                await asyncio.wait_for(self.writer.drain(), 5)
            except Exception:
                await self.close()
                raise ConnectionError(
                    "TAK authentication could not be submitted"
                ) from None
        self.host = host
        self.web = web
        self.state = "connected · XML"
        self.dropped = 0
        self.reader_task = asyncio.create_task(self._receive(reader))
        return {"connected": True}

    async def enroll(self, host, port, username, password, ca=""):
        self.enrollment = await enroll(host, port, username, password, ca)
        return {"enrolled": True, "expires": self.enrollment["expires"], "host": host}

    async def package_search(self, keywords=""):
        if self.web is None:
            raise ConnectionError("Connect a TAK server first")
        return await self.web.search(keywords)

    async def package_download(self, digest):
        if self.web is None:
            raise ConnectionError("Connect a TAK server first")
        return await self.web.download(digest)

    async def package_upload(self, zip_base64, name, private=True):
        if self.web is None:
            raise ConnectionError("Connect a TAK server first")
        return await self.web.upload(zip_base64, name, private)

    async def _write_event(self, data):
        async with self.write_lock:
            if self.writer is None or self.writer.is_closing():
                raise ConnectionError("TAK server is disconnected")
            wire = (
                stream_frame(encode_event(data))
                if self.protocol == "protobuf-v1"
                else b'<?xml version="1.0" encoding="UTF-8"?>\n' + data.strip()
            )
            self.writer.write(wire)
            await asyncio.wait_for(self.writer.drain(), 5)

    async def send_point(self, record):
        if self.negotiating:
            raise ConnectionError("Wait for TAK protocol negotiation")
        data = point_to_cot(record)
        try:
            await self._write_event(data)
        except Exception:
            await self.close()
            raise ConnectionError("TAK send unconfirmed; no automatic retry") from None
        return {"state": "submitted"}

    async def _negotiation_deadline(self):
        await asyncio.sleep(60)
        if self.negotiating:
            await self.close()
            self.state = "Protocol negotiation timed out · reconnect explicitly"

    async def _control(self, event):
        kind, uid = event.get("type"), event.get("uid")
        if kind == "t-x-takp-v":
            offered = event.findall("detail/TakControl/TakProtocolSupport")
            if (
                self.auto_protocol
                and not self.negotiating
                and self.protocol == "xml"
                and uid
                and len(uid) <= 128
                and any(node.get("version") == "1" for node in offered)
            ):
                request = safe_xml(point_to_cot({"latitude": 0, "longitude": 0}))
                request.set("type", "t-x-takp-q")
                request.set("uid", uid)
                detail = request.find("detail")
                if detail is None:
                    raise ValueError("Missing protocol request detail")
                detail.clear()
                ET.SubElement(
                    ET.SubElement(detail, "TakControl"), "TakRequest", {"version": "1"}
                )
                self.negotiating = uid
                await self._write_event(ET.tostring(request, encoding="utf-8"))
                self.state = "Negotiating TAK v1"
                self.negotiation_task = asyncio.create_task(
                    self._negotiation_deadline()
                )
            return True
        if kind == "t-x-takp-r":
            response = event.find("detail/TakControl/TakResponse")
            if self.negotiating and uid == self.negotiating and response is not None:
                accepted = response.get("status")
                if accepted not in ("true", "false"):
                    raise ValueError("Invalid protocol response")
                self.protocol = "protobuf-v1" if accepted == "true" else "xml"
                self.negotiating = None
                if self.negotiation_task:
                    self.negotiation_task.cancel()
                    self.negotiation_task = None
                self.state = "connected · " + self.protocol
            return True
        return kind.startswith("t-x-") if kind else False

    async def _receive(self, reader):
        buffer = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while buffer:
                    if self.protocol == "protobuf-v1":
                        frame = pop_stream_frame(buffer)
                        if frame is None:
                            break
                        payload, buffer = frame
                        raw = decode_event(payload)
                        if raw is None:
                            continue
                    else:
                        if b"</event>" not in buffer:
                            break
                        end = buffer.index(b"</event>") + 8
                        raw, buffer = buffer[:end], buffer[end:]
                        start = raw.find(b"<event")
                        if start < 0 or len(raw) > MAX_EVENT:
                            self.dropped += 1
                            continue
                        raw = raw[start:]
                    try:
                        event = safe_xml(raw)
                        if await self._control(event):
                            continue
                        item = point_from_cot(raw)
                    except (ValueError, KeyError, OverflowError, ET.ParseError):
                        self.dropped += 1
                        continue
                    if item["source_uid"]:
                        self.items = [
                            row
                            for row in self.items
                            if row["source_uid"] != item["source_uid"]
                        ]
                    self.items.insert(0, item)
                    del self.items[100:]
                if len(buffer) > MAX_EVENT + 16:
                    raise ValueError("Oversized CoT stream")
                await asyncio.sleep(0)
        except (OSError, ValueError, OverflowError):
            self.state = "Connection ended · invalid or unavailable TAK stream"
        finally:
            writer, self.writer = self.writer, None
            if writer:
                writer.close()
            if self.state.startswith("connected") or self.negotiating:
                self.state = "Server disconnected"
            self.web = None
            if self.negotiation_task:
                self.negotiation_task.cancel()
                self.negotiation_task = None
            self.negotiating = None
