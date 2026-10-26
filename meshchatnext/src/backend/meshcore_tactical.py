# SPDX-License-Identifier: MIT
"""Opt-in Open TAK team traffic on a selected private MeshCore channel.

No location acquisition, background beacons, TAK server, or Reticulum bridge is
started implicitly. All sends are explicit, owner scoped and idempotent.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from meshchatnext.src.backend.meshcore_beacons import BeaconConsent
from meshchatnext.src.backend.meshcore_cot import CotSession
from meshchatnext.src.backend.meshcore_geofences import (
    CrossingMonitor,
    boundary_version,
)
from meshchatnext.src.backend.meshcore_store import notification_key, public_key
from meshchatnext.src.backend.meshcore_tactical_wire import (
    AFFILIATIONS,
    ALERT_KINDS,
    CASEVAC_NUMBERS,
    CASEVAC_TEXT,
    COLORS,
    DATA_TYPE,
    GEOFENCES,
    PIN_KINDS,
    ROLES,
    ROUTE_METHODS,
    SHAPE_KINDS,
    STATUSES,
    URGENCIES,
    decode,
    encode,
    integer,
    text,
)


def _db(folder):
    @contextlib.contextmanager
    def connection():
        db = sqlite3.connect(Path(folder) / "tactical.sqlite")
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS preferences(owner TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records(owner TEXT NOT NULL,channel TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,heard REAL NOT NULL,PRIMARY KEY(owner,channel,key));
                CREATE TABLE IF NOT EXISTS trails(owner TEXT NOT NULL,channel TEXT NOT NULL,alias TEXT NOT NULL,latitude REAL,longitude REAL,heard REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS alert_events(owner TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,key));
                CREATE TABLE IF NOT EXISTS fence_events(owner TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,key));
                CREATE TABLE IF NOT EXISTS sends(owner TEXT NOT NULL,id TEXT NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,id));
                """)
                yield db
        finally:
            db.close()

    return connection()


def preferences(folder, owner):
    with _db(folder) as db:
        row = db.execute(
            "SELECT value FROM preferences WHERE owner=?", (owner,)
        ).fetchone()
    return (
        json.loads(row["value"])
        if row
        else {
            "enabled": False,
            "monitor_geofences": False,
            "notify_team_alerts": False,
            "channel_id": None,
            "callsign": "",
            "role": 0,
            "color": 0,
            "status": 0,
        }
    )


def snapshot(folder, owner):
    config = preferences(folder, owner)
    result = {
        **config,
        "alias": owner[:8],
        "records": [],
        "trails": [],
        "roles": ROLES,
        "colors": COLORS,
        "statuses": STATUSES,
        "pin_kinds": PIN_KINDS,
        "alert_kinds": ALERT_KINDS,
        "affiliations": AFFILIATIONS,
        "urgencies": URGENCIES,
        "shape_kinds": SHAPE_KINDS,
        "geofences": GEOFENCES,
        "route_methods": ROUTE_METHODS,
    }
    if not config["enabled"]:
        return result
    with _db(folder) as db:
        result["records"] = [
            {**json.loads(row["value"]), "heard": row["heard"]}
            for row in db.execute(
                "SELECT value,heard FROM records WHERE owner=? AND channel=? AND heard>? ORDER BY heard DESC LIMIT 500",
                (owner, config["channel_id"], time.time() - 7 * 86400),
            )
        ]
        result["trails"] = [
            dict(row)
            for row in db.execute(
                "SELECT alias,latitude,longitude,heard FROM trails WHERE owner=? AND channel=? AND heard>? ORDER BY heard DESC LIMIT 2000",
                (owner, config["channel_id"], time.time() - 86400),
            )
        ]
    return result


class MeshCoreTactical:
    def __init__(self, messages, channels, folder):
        self.messages, self.channels, self.session = (
            messages,
            channels,
            messages.session,
        )
        self.owner, self.folder = public_key(messages.owner), Path(folder)
        self.config = preferences(self.folder, self.owner)
        self.last_send = {}
        self.beacons = BeaconConsent(self)
        self.cot = CotSession(self.folder)
        self.monitor = CrossingMonitor()
        self._monitor_lock = threading.RLock()
        self.on_notification = None

    async def cot_connect(
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
        return await self.cot.connect(
            host,
            port,
            ca,
            certificate,
            private_key,
            auto_protocol,
            https_port,
            username,
            password,
        )

    async def cot_enroll(self, host, port, username, password, ca=""):
        return await self.cot.enroll(host, port, username, password, ca)

    async def cot_package_search(self, keywords=""):
        return await self.cot.package_search(keywords)

    async def cot_package_download(self, digest):
        return await self.cot.package_download(digest)

    async def cot_package_upload(self, zip_base64, name, private=True):
        return await self.cot.package_upload(zip_base64, name, private)

    async def cot_disconnect(self):
        return await self.cot.close()

    async def cot_status(self):
        return await self.cot.status()

    async def cot_send(self, record):
        return await self.cot.send_point(record)

    async def beacon_start(self, interval, expected_channel_id, expected_scope):
        return self.beacons.start(interval, expected_channel_id, expected_scope)

    async def beacon_stop(self, token=None):
        if token is not None and (
            not isinstance(token, str)
            or not self.beacons.token
            or not secrets.compare_digest(token, self.beacons.token)
        ):
            raise ValueError("Beacon consent already changed")
        return self.beacons.stop()

    async def beacon_position(self, token, latitude, longitude, accuracy, timestamp):
        return await self.beacons.position(
            token, latitude, longitude, accuracy, timestamp
        )

    def attachment_channel(self, expected_channel_id):
        if (
            not self.config.get("enabled")
            or self.config.get("channel_id") != expected_channel_id
        ):
            raise ValueError("Team channel changed; refresh before using attachments")

    async def prepare_attachment(self, pcm_base64, request_id, expected_channel_id):
        self.attachment_channel(expected_channel_id)
        voice = self.messages.voice
        result = await voice.prepare(self.owner, pcm_base64, request_id)
        self.attachment_channel(expected_channel_id)
        return {
            **result,
            "attachment": {
                "mode": 1,
                "sid": result["sid"],
                "packets": result["total"],
                "extra": result["seconds"],
            },
        }

    async def fetch_attachment(self, peer, kind, item_id, alias, expected_channel_id):
        self.attachment_channel(expected_channel_id)
        peer = public_key(peer)
        if kind not in ("pin", "report") or peer[:8] != alias:
            raise ValueError("Select the attachment author's full MeshCore public key")
        key = kind + ":" + alias + ":" + str(item_id)
        with _db(self.folder) as db:
            row = db.execute(
                "SELECT value FROM records WHERE owner=? AND channel=? AND key=?",
                (self.owner, expected_channel_id, key),
            ).fetchone()
        if row is None:
            raise ValueError("Tactical item no longer available")
        record = json.loads(row["value"])
        meta = record.get("attachment")
        if not meta or record.get("deleted") or record.get("withdrawn"):
            raise ValueError("Tactical attachment no longer available")
        return await self.messages.voice.fetch_reference(
            peer,
            {
                "sid": meta["sid"],
                "mode": meta["mode"],
                "total": meta["packets"],
                "seconds": meta["extra"],
            },
        )

    async def configure(
        self,
        enabled,
        channel_id=None,
        callsign="",
        role=0,
        color=0,
        status=0,
        monitor_geofences=False,
        notify_team_alerts=False,
    ):
        if any(
            type(value) is not bool
            for value in (enabled, monitor_geofences, notify_team_alerts)
        ):
            raise ValueError("Invalid team mode")
        self.beacons.stop()
        text(callsign, 20)
        integer(role, 0, 24)
        integer(color, 0, len(COLORS) - 1)
        integer(status, 0, len(STATUSES) - 1)
        async with self.session._lock:
            self.messages._check()
            await self.messages._drain_pending()
            if enabled:
                channel_id = public_key(channel_id)
                rows = await asyncio.to_thread(
                    self.messages.store.channel_ui, self.owner
                )
                row = next((r for r in rows if r["channel_id"] == channel_id), None)
                if not row:
                    raise ValueError("Choose a saved private team channel")
                live, _ = await self.channels._read(row["slot"])
                if live["channel_id"] != channel_id or live["kind"] != "private":
                    raise ValueError("Team mode requires a verified private channel")
            config = {
                "enabled": enabled,
                "monitor_geofences": monitor_geofences,
                "notify_team_alerts": notify_team_alerts,
                "channel_id": channel_id,
                "callsign": callsign.strip(),
                "role": role,
                "color": color,
                "status": status,
            }

            def save():
                with _db(self.folder) as db:
                    db.execute("DELETE FROM fence_events WHERE owner=?", (self.owner,))
                    db.execute("DELETE FROM alert_events WHERE owner=?", (self.owner,))
                    db.execute(
                        "INSERT OR REPLACE INTO preferences VALUES(?,?)",
                        (self.owner, json.dumps(config)),
                    )

            await asyncio.to_thread(save)
            with self._monitor_lock:
                self.config = config
                self.monitor.reset()
        return config

    def _record(self, record, channel, heard, incoming=False):
        with self._monitor_lock:
            return self._record_locked(record, channel, heard, incoming)

    def _record_locked(self, record, channel, heard, incoming):
        record = {**record, "identity_verified": False}
        key = (
            record["kind"]
            + ":"
            + record["alias"]
            + ":"
            + str(record.get("id", "position"))
        )
        with _db(self.folder) as db:
            old = db.execute(
                "SELECT value,heard FROM records WHERE owner=? AND channel=? AND key=?",
                (self.owner, channel, key),
            ).fetchone()
            if old and json.loads(old["value"]).get("timestamp", 0) > record.get(
                "timestamp", 0
            ):
                return []
            if (
                record["kind"] == "alert"
                and old
                and record.get("active")
                and not json.loads(old["value"]).get("active")
                and heard - old["heard"] < 86400
            ):
                return []  # A delayed active copy must not revive a cleared alert ID.
            if record["kind"] == "shape" and (
                not old or json.loads(old["value"]) != record
            ):
                self.monitor.states = {
                    k: v
                    for k, v in self.monitor.states.items()
                    if k[:2] != (record["alias"], record["id"])
                }
            db.execute(
                "INSERT OR REPLACE INTO records VALUES(?,?,?,?,?)",
                (self.owner, channel, key, json.dumps(record), heard),
            )
            if record["kind"] == "position":
                db.execute(
                    "INSERT INTO trails VALUES(?,?,?,?,?,?)",
                    (
                        self.owner,
                        channel,
                        record["alias"],
                        record["latitude"],
                        record["longitude"],
                        heard,
                    ),
                )
            db.execute(
                "DELETE FROM records WHERE owner=? AND rowid NOT IN (SELECT rowid FROM records WHERE owner=? ORDER BY heard DESC LIMIT 1000)",
                (self.owner, self.owner),
            )
            db.execute(
                "DELETE FROM trails WHERE owner=? AND rowid NOT IN (SELECT rowid FROM trails WHERE owner=? ORDER BY heard DESC LIMIT 2000)",
                (self.owner, self.owner),
            )
            db.execute(
                "DELETE FROM sends WHERE owner=? AND created<?",
                (self.owner, heard - 7 * 86400),
            )

            events = []
            if (
                incoming
                and record["kind"] == "alert"
                and record.get("active")
                and self.config.get("enabled")
                and self.config.get("channel_id") == channel
                and self.config.get("notify_team_alerts")
                and (not old or json.loads(old["value"]) != record)
            ):
                item_id = "alert:" + record["alias"] + ":" + str(record["id"])
                key = notification_key(self.owner, "tactical", channel + ":" + item_id)
                event = {
                    "type": "meshcore.message",
                    "kind": "tactical",
                    "owner": self.owner,
                    "target": channel,
                    "item": item_id,
                    "id": str(uuid.uuid4()),
                    "record_version": boundary_version(record),
                    "name": "Team alert · " + ALERT_KINDS[record["alert_kind"]],
                    "text": f"{record.get('callsign') or record['alias']}: {record.get('note') or 'Active team alert'} · unverified team alias",
                    "created": heard,
                    "notification_key": key,
                }
                db.execute(
                    "INSERT OR REPLACE INTO alert_events VALUES(?,?,?,?)",
                    (self.owner, key, json.dumps(event), heard),
                )
                events.append(event)
            db.execute(
                "DELETE FROM alert_events WHERE owner=? AND (created<? OR rowid NOT IN (SELECT rowid FROM alert_events WHERE owner=? ORDER BY created DESC LIMIT 200))",
                (self.owner, heard - 86400, self.owner),
            )
            if (
                incoming
                and record["kind"] == "position"
                and self.config.get("monitor_geofences")
                and self.config.get("enabled")
                and self.config.get("channel_id") == channel
            ):
                shapes = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT value FROM records WHERE owner=? AND channel=? AND heard>?",
                        (self.owner, channel, heard - 7 * 86400),
                    )
                    if json.loads(r[0]).get("kind") == "shape"
                ]
                for shape, crossing in self.monitor.update(record, shapes, heard):
                    shape_id = shape["alias"] + ":" + str(shape["id"])
                    key = notification_key(
                        self.owner, "tactical", channel + ":" + shape_id
                    )
                    event = {
                        "type": "meshcore.message",
                        "kind": "tactical",
                        "owner": self.owner,
                        "target": channel,
                        "shape": shape_id,
                        "boundary_version": boundary_version(shape),
                        "id": str(uuid.uuid4()),
                        "name": "Geofence",
                        "text": f"{record.get('callsign') or record['alias']} {crossing} {shape.get('label') or 'boundary'} · unverified team position",
                        "created": heard,
                        "notification_key": key,
                    }
                    db.execute(
                        "INSERT OR REPLACE INTO fence_events VALUES(?,?,?,?)",
                        (self.owner, key, json.dumps(event), heard),
                    )
                    events.append(event)
            db.execute(
                "DELETE FROM fence_events WHERE owner=? AND (created<? OR rowid NOT IN (SELECT rowid FROM fence_events WHERE owner=? ORDER BY created DESC LIMIT 200))",
                (self.owner, heard - 86400, self.owner),
            )
            return events

    async def receive(self, payload):
        if payload.get("data_type") != DATA_TYPE:
            return False
        # Team data is never rendered as a blank ordinary channel message.
        if not self.config["enabled"]:
            return True
        rows = await asyncio.to_thread(self.messages.store.channel_ui, self.owner)
        binding = next(
            (r for r in rows if r["slot"] == payload.get("channel_idx")), None
        )
        if (
            not binding
            or binding["channel_id"] != self.config["channel_id"]
            or binding["kind"] != "private"
        ):
            return True
        raw = payload.get("payload")
        if not isinstance(raw, str) or len(raw) > 326:
            return True
        try:
            record = decode(bytes.fromhex(raw))
        except (ValueError, KeyError, TypeError):
            return True  # Malformed or not-yet-supported team types must not stop chat reception.
        if record["alias"] == self.owner[:8]:
            return True
        events = await asyncio.to_thread(
            self._record, record, binding["channel_id"], time.time(), True
        )
        if self.on_notification:
            for event in events:
                self.on_notification(event)
        return True

    async def preview_shape(self, record):
        allowed = {
            "kind",
            "id",
            "timestamp",
            "shape_kind",
            "points",
            "color",
            "label",
            "geofence",
            "radius_m",
            "route_method",
            "deleted",
        }
        if (
            not isinstance(record, dict)
            or record.get("kind") != "shape"
            or set(record) - allowed
        ):
            raise ValueError("Invalid tactical shape fields")
        self.messages._check()
        item = {**record, "alias": self.owner[:8]}
        item.setdefault("id", 0)
        item.setdefault("timestamp", int(time.time()))
        data = encode(item)
        return {
            "bytes": len(data),
            "limit": 163,
            "vertices": len(item["points"]),
            "grid_m": 1,
        }

    async def send(
        self, record, request_id, expected_channel_id=None, expected_scope=...
    ):
        if (
            expected_scope is not ...
            and expected_scope is not None
            and not isinstance(expected_scope, str)
        ):
            raise ValueError("Invalid expected channel scope")
        if (
            expected_channel_id is not None
            and public_key(expected_channel_id) != self.config["channel_id"]
        ):
            raise ValueError("Team channel changed; refresh before sharing")
        if not self.config["enabled"]:
            raise ValueError("Enable a private team channel before sharing")
        if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
            raise ValueError("Invalid tactical request ID")
        if not isinstance(record, dict) or record.get("kind") not in (
            "position",
            "pin",
            "alert",
            "report",
            "shape",
            "casevac",
        ):
            raise ValueError("Unsupported tactical item")
        allowed = {
            "casevac": {
                "kind",
                "id",
                "timestamp",
                "latitude",
                "longitude",
                "deleted",
                *CASEVAC_TEXT,
                *CASEVAC_NUMBERS,
            },
            "shape": {
                "kind",
                "id",
                "timestamp",
                "shape_kind",
                "points",
                "color",
                "label",
                "geofence",
                "radius_m",
                "route_method",
                "deleted",
            },
            "report": {
                "kind",
                "latitude",
                "longitude",
                "id",
                "timestamp",
                "report_kind",
                "urgency",
                "affiliation",
                "vehicles",
                "people",
                "place",
                "size",
                "activity",
                "unit",
                "equipment",
                "withdrawn",
                "attachment",
            },
            "position": {
                "kind",
                "latitude",
                "longitude",
                "altitude",
                "speed",
                "heading",
                "accuracy",
                "battery",
            },
            "pin": {
                "kind",
                "latitude",
                "longitude",
                "id",
                "deleted",
                "pin_kind",
                "attachment",
                "label",
                "note",
            },
            "alert": {
                "kind",
                "latitude",
                "longitude",
                "accuracy",
                "id",
                "active",
                "alert_kind",
                "note",
            },
        }[record["kind"]]
        if set(record) - allowed:
            raise ValueError("Invalid tactical fields")
        digest = hashlib.sha256(
            json.dumps(
                {
                    "channel": self.config["channel_id"],
                    "record": record,
                    "scope": expected_scope
                    if expected_scope is not ...
                    else "unspecified",
                },
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()

        def previous():
            with _db(self.folder) as db:
                row = db.execute(
                    "SELECT digest,result FROM sends WHERE owner=? AND id=?",
                    (self.owner, request_id),
                ).fetchone()
                if row and row["digest"] != digest:
                    raise ValueError("Tactical request ID reused for another item")
                return json.loads(row["result"]) if row else None

        saved = await asyncio.to_thread(previous)
        if saved is not None:
            return saved
        now = time.monotonic()
        interval = 30 if record["kind"] == "position" else 2
        if now - self.last_send.get(record["kind"], -1e9) < interval:
            raise ValueError("Wait before sharing another team update")
        item = {**record, "alias": self.owner[:8]}
        if item["kind"] == "position":
            item.update(
                {k: self.config[k] for k in ("callsign", "role", "color", "status")}
            )
        elif item["kind"] in ("pin", "report", "shape", "casevac"):
            item.setdefault("id", secrets.randbits(32))
            item.setdefault("timestamp", int(time.time()))
        else:
            item.setdefault("id", secrets.randbits(16))
            item["callsign"] = self.config["callsign"]
        data = encode(item)
        result = {
            "state": "unknown",
            "kind": item["kind"],
            "id": item.get("id"),
            "request_id": request_id,
        }

        def save():
            with _db(self.folder) as db:
                db.execute(
                    "INSERT OR REPLACE INTO sends VALUES(?,?,?,?,?)",
                    (self.owner, request_id, digest, json.dumps(result), time.time()),
                )

        async with self.session._lock:
            self.messages._check()
            rows = await asyncio.to_thread(self.messages.store.channel_ui, self.owner)
            row = next(
                (r for r in rows if r["channel_id"] == self.config["channel_id"]), None
            )
            if not row:
                raise ValueError("Team channel changed; review team settings")
            live, _ = await self.channels._read(row["slot"])
            if (
                live["channel_id"] != self.config["channel_id"]
                or live["kind"] != "private"
            ):
                raise ValueError("Team channel changed; review team settings")
            from meshchatnext.src.backend.meshcore_tools import channel_scope

            scope = await asyncio.to_thread(
                self.messages.store.channel_scope, self.owner, self.config["channel_id"]
            )
            if expected_scope is not ... and scope != expected_scope:
                raise ValueError("Channel scope changed; refresh before sharing")
            if item.get("attachment"):
                voice = self.messages.voice
                clip = voice.clip(self.owner, item["attachment"]["sid"], "out")
                meta = item["attachment"]
                if (meta["mode"], meta["packets"], meta["extra"]) != (
                    clip["mode"],
                    clip["total"],
                    clip["seconds"],
                ):
                    raise ValueError("Attachment changed; prepare it again")
                await voice.gate()
                with voice.db() as db:
                    db.execute(
                        "UPDATE clips SET announced=2 WHERE owner=? AND peer=? AND sid=? AND direction='out'",
                        (self.owner, self.owner, meta["sid"]),
                    )
            await asyncio.to_thread(
                save
            )  # Claim before RF: uncertain requests are never silently replayed.
            self.last_send[item["kind"]] = now
            async with channel_scope(self.session, scope):
                event = await self.session._client.commands.send_channel_data(
                    row["slot"], DATA_TYPE, data
                )
                result["state"] = (
                    "submitted"
                    if event is not None and event.type == self.messages._types.OK
                    else "rejected"
                    if event is not None
                    and event.is_error()
                    and isinstance(event.payload.get("error_code"), int)
                    else "unknown"
                )
            await asyncio.to_thread(save)
            if result["state"] == "submitted":
                await asyncio.to_thread(
                    self._record, decode(data), self.config["channel_id"], time.time()
                )
        return result


def fence_notification(folder, owner, key):
    config = preferences(folder, owner)
    if not config.get("enabled") or not config.get("monitor_geofences"):
        return None
    with _db(folder) as db:
        row = db.execute(
            "SELECT value FROM fence_events WHERE owner=? AND key=? AND created>?",
            (owner, key, time.time() - 86400),
        ).fetchone()
        if not row:
            return None
        event = json.loads(row[0])
        if event["target"] != config["channel_id"]:
            return None
        alias, shape_id = event["shape"].split(":")
        shape = db.execute(
            "SELECT value FROM records WHERE owner=? AND channel=? AND key=?",
            (owner, event["target"], f"shape:{alias}:{shape_id}"),
        ).fetchone()
        if not shape:
            return None
        shape = json.loads(shape[0])
        if (
            shape.get("deleted")
            or not shape.get("geofence")
            or event.get("boundary_version") != boundary_version(shape)
        ):
            return None
        return event


def team_notification(folder, owner, key):
    fence = fence_notification(folder, owner, key)
    if fence:
        return fence
    config = preferences(folder, owner)
    if not config.get("enabled") or not config.get("notify_team_alerts"):
        return None
    with _db(folder) as db:
        row = db.execute(
            "SELECT value FROM alert_events WHERE owner=? AND key=? AND created>?",
            (owner, key, time.time() - 86400),
        ).fetchone()
        if not row:
            return None
        event = json.loads(row[0])
        if event["target"] != config["channel_id"]:
            return None
        record = db.execute(
            "SELECT value FROM records WHERE owner=? AND channel=? AND key=?",
            (owner, event["target"], event["item"]),
        ).fetchone()
        if not record:
            return None
        record = json.loads(record[0])
        if (
            not record.get("active")
            or boundary_version(record) != event["record_version"]
        ):
            return None
        return event
