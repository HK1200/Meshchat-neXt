# SPDX-License-Identifier: MIT
"""Family v1 encrypted DIRECT location frames; never rooms or channels.

Consent belongs to a full companion identity and full saved user key. Sending is
one-shot only; no GPS acquisition, background sharing or automatic retry here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from typing import TypedDict

FRAME = re.compile(
    r"!NFLOC1:geo:(-?[0-9]+\.[0-9]{7}),(-?[0-9]+\.[0-9]{7}),"
    r"(-?[0-9]+\.[0-9]{2});u=([0-9]+\.[0-9]{2});t=([0-9]{1,10});"
    r"s=([0-9]+\.[0-9]{2});b=([0-9]+\.[0-9]{2})"
)
_UNSET_GENERATION = object()
WRITE_GUARD: ContextVar[Callable[[], None] | None] = ContextVar(
    "meshcore_private_location_write_guard", default=None
)


class LocationPermissionChanged(ValueError):
    pass


def check_write_permission():
    guard = WRITE_GUARD.get()
    if guard is not None:
        guard()


def valid_fix(raw, *, now=None):
    now = time.time() if now is None else now
    if not isinstance(raw, dict):
        raise ValueError("Invalid private location")
    limits = {
        "latitude": (-90, 90, None),
        "longitude": (-180, 180, None),
        "altitude": (-12000, 100000, 0),
        "accuracy": (0, 655.35, 0),
        "speed": (0, 1000, 0),
        "bearing": (0, 360, 0),
        "last_update": (now - 86400, now + 300, now),
    }
    result = {}
    for key, (low, high, default) in limits.items():
        value = raw.get(key, default)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not low <= value <= high
        ):
            raise ValueError("Invalid private location " + key)
        result[key] = value
    return result


def encode(fix, *, now=None):
    f = valid_fix(fix, now=now)
    for key in ("accuracy", "speed", "bearing"):
        if f[key] == 0:
            f[key] = 0.0  # Canonical unsigned fields must not encode negative zero.
    text = (
        f"!NFLOC1:geo:{f['latitude']:.7f},{f['longitude']:.7f},{f['altitude']:.2f}"
        f";u={f['accuracy']:.2f};t={int(f['last_update'])};s={f['speed']:.2f};b={f['bearing']:.2f}"
    )
    if len(text.encode("utf-8")) > 160:
        raise ValueError("Private location exceeds 160 bytes")
    return text


def decode(text, *, now=None):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 160:
        raise ValueError("Invalid private location frame")
    match = FRAME.fullmatch(text)
    if match is None:
        raise ValueError("Invalid private location frame")
    lat, lon, altitude, accuracy, stamp, speed, bearing = match.groups()
    return valid_fix(
        {
            "latitude": float(lat),
            "longitude": float(lon),
            "altitude": float(altitude),
            "accuracy": float(accuracy),
            "last_update": int(stamp),
            "speed": float(speed),
            "bearing": float(bearing),
        },
        now=now,
    )


def create_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS private_location_policy (
            owner TEXT NOT NULL,peer TEXT NOT NULL,receive INTEGER NOT NULL,
            share INTEGER NOT NULL,generation TEXT NOT NULL,last_sent REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(owner,peer));
        CREATE TABLE IF NOT EXISTS private_locations (
            owner TEXT NOT NULL,peer TEXT NOT NULL,stamp INTEGER NOT NULL,fix TEXT NOT NULL,
            PRIMARY KEY(owner,peer));
        CREATE TABLE IF NOT EXISTS private_location_replays (
            owner TEXT NOT NULL,peer TEXT NOT NULL,stamp INTEGER NOT NULL,PRIMARY KEY(owner,peer));
        CREATE TABLE IF NOT EXISTS private_location_sends (
            owner TEXT NOT NULL,id TEXT NOT NULL,peer TEXT NOT NULL,frame TEXT NOT NULL,
            state TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,id));
    """)


def _contact(db, owner, peer):
    from meshchatnext.src.backend.meshcore_store import public_key

    owner, peer = public_key(owner), public_key(peer)
    row = db.execute(
        "SELECT name FROM contacts WHERE owner=? AND peer=? AND active=1 AND kind=1",
        (owner, peer),
    ).fetchone()
    if row is None:
        raise ValueError("Select a saved MeshCore user, not a repeater or room")
    matches = db.execute(
        "SELECT COUNT(*) FROM contacts WHERE owner=? AND substr(peer,1,12)=?",
        (owner, peer[:12]),
    ).fetchone()[0]
    if matches != 1:
        raise ValueError(
            "Ambiguous MeshCore contact key prefix; private sharing is unavailable"
        )
    return owner, peer


class LocationPolicy(TypedDict):
    receive: bool
    share: bool
    generation: str | None
    last_sent: float


def _policy(db, owner, peer) -> LocationPolicy:
    row = db.execute(
        "SELECT * FROM private_location_policy WHERE owner=? AND peer=?", (owner, peer)
    ).fetchone()
    if row is None:
        return {"receive": False, "share": False, "generation": None, "last_sent": 0.0}
    return {
        "receive": bool(row["receive"]),
        "share": bool(row["share"]),
        "generation": row["generation"],
        "last_sent": float(row["last_sent"]),
    }


class PrivateLocationStore:
    """Mixin for the companion-scoped store; blocking calls run off the UI loop."""

    def private_location_policy(self, owner, peer):
        with self._lock, self._connect() as db:
            owner, peer = _contact(db, owner, peer)
            p = _policy(db, owner, peer)
            return {
                "receive": bool(p["receive"]),
                "share": bool(p["share"]),
                "generation": p["generation"],
            }

    def configure_private_location(
        self, owner, peer, receive, share, *, generation=_UNSET_GENERATION
    ):
        if type(receive) is not bool or type(share) is not bool:
            raise ValueError("Private location consent must be boolean")
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owner, peer = _contact(db, owner, peer)
            if (
                generation is not _UNSET_GENERATION
                and generation != _policy(db, owner, peer)["generation"]
            ):
                raise LocationPermissionChanged(
                    "Private location permissions changed; read them again before saving"
                )
            db.execute(
                """INSERT INTO private_location_policy VALUES(?,?,?,?,?,0)
                ON CONFLICT(owner,peer) DO UPDATE SET receive=excluded.receive,
                share=excluded.share,generation=excluded.generation""",
                (owner, peer, receive, share, uuid.uuid4().hex),
            )
            if not receive:
                db.execute(
                    "DELETE FROM private_locations WHERE owner=? AND peer=?",
                    (owner, peer),
                )
        return self.private_location_policy(owner, peer)

    def receive_private_location(self, owner, kind, payload):
        text = payload.get("text")
        if (
            kind != "direct"
            or not isinstance(text, str)
            or not text.startswith("!NFLOC")
        ):
            return False
        # Consume malformed and unsupported reserved frames without history/alerts.
        prefix = payload.get("pubkey_prefix")
        if (
            payload.get("txt_type", 0) != 0
            or not isinstance(prefix, str)
            or not re.fullmatch(r"[0-9a-fA-F]{12}", prefix)
        ):
            return True
        with self._lock, self._connect() as db:
            matches = db.execute(
                "SELECT peer,kind,active FROM contacts WHERE owner=? AND substr(peer,1,12)=?",
                (owner, prefix.lower()),
            ).fetchall()
            if len(matches) == 1 and matches[0]["kind"] != 1:
                return False  # Room/repeater text is not this direct-user protocol.
            if len(matches) != 1 or not matches[0]["active"]:
                return True
            peer = matches[0]["peer"]
            if not _policy(db, owner, peer)["receive"]:
                return True
            try:
                fix = decode(text)
            except ValueError:
                return True
            previous = db.execute(
                "SELECT stamp FROM private_location_replays WHERE owner=? AND peer=?",
                (owner, peer),
            ).fetchone()
            if previous and previous["stamp"] >= fix["last_update"]:
                return True
            db.execute(
                "INSERT INTO private_location_replays VALUES(?,?,?) ON CONFLICT(owner,peer) DO UPDATE SET stamp=excluded.stamp",
                (owner, peer, int(fix["last_update"])),
            )
            db.execute(
                """INSERT INTO private_locations VALUES(?,?,?,?)
                ON CONFLICT(owner,peer) DO UPDATE SET stamp=excluded.stamp,fix=excluded.fix
                WHERE excluded.stamp>private_locations.stamp""",
                (owner, peer, int(fix["last_update"]), json.dumps(fix)),
            )
        return True

    def private_locations(self, owner):
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT l.peer,l.fix,c.name FROM private_locations l
                JOIN private_location_policy p ON p.owner=l.owner AND p.peer=l.peer AND p.receive=1
                JOIN contacts c ON c.owner=l.owner AND c.peer=l.peer AND c.active=1 AND c.kind=1
                WHERE l.owner=? AND l.stamp>=? AND l.stamp<=? ORDER BY l.stamp DESC LIMIT 1000""",
                (owner, time.time() - 86400, time.time() + 300),
            ).fetchall()
            return [
                dict(
                    json.loads(row["fix"]),
                    peer=row["peer"],
                    name=row["name"],
                    kind=1,
                    saved=True,
                    private_location=True,
                    updated=json.loads(row["fix"])["last_update"],
                )
                for row in rows
            ]

    def reserve_private_location(self, owner, peer, fix, request_id, generation):
        if not isinstance(request_id, str):
            raise ValueError("A unique private location request ID is required")
        try:
            uuid.UUID(request_id)
        except (ValueError, AttributeError):
            raise ValueError("Invalid private location request ID") from None
        now = time.time()
        fix = valid_fix(fix, now=now)
        frame = encode(fix, now=now)
        digest = hashlib.sha256(frame.encode("utf-8")).hexdigest()
        with self._lock, self._connect() as db:
            owner, peer = _contact(db, owner, peer)
            old = db.execute(
                "SELECT * FROM private_location_sends WHERE owner=? AND id=?",
                (owner, request_id),
            ).fetchone()
            if old:
                if old["peer"] != peer or old["frame"] != digest:
                    raise ValueError("Request ID belongs to another private location")
                return dict(old), False
            p = _policy(db, owner, peer)
            if not p["share"] or not generation or p["generation"] != generation:
                raise LocationPermissionChanged(
                    "Private location permission changed; review it again"
                )
            if fix["last_update"] < now - 120:
                raise ValueError("Acquire a fresh location before sharing")
            previous_send = (
                db.execute(
                    "SELECT MAX(created) FROM private_location_sends WHERE owner=? AND peer=?",
                    (owner, peer),
                ).fetchone()[0]
                or 0
            )
            if now - max(p["last_sent"], previous_send) < 60:
                raise ValueError(
                    "Wait one minute before sharing another private location"
                )
            clock = db.execute(
                "SELECT stamp FROM clocks WHERE owner=? AND peer=?", (owner, peer)
            ).fetchone()
            stamp = max(int(now), clock["stamp"] + 1 if clock else 0)
            if stamp > min(0xFFFFFFFF, int(now) + 60):
                raise ValueError(
                    "Private message clock is too far ahead; wait before sending"
                )
            db.execute(
                "INSERT OR REPLACE INTO clocks VALUES(?,?,?)", (owner, peer, stamp)
            )
            db.execute(
                "UPDATE private_location_policy SET last_sent=? WHERE owner=? AND peer=?",
                (now, owner, peer),
            )
            db.execute(
                "INSERT INTO private_location_sends VALUES(?,?,?,?,'submitting',?)",
                (owner, request_id, peer, digest, now),
            )
            return {
                "id": request_id,
                "peer": peer,
                "frame": frame,
                "state": "submitting",
                "created": now,
                "timestamp": stamp,
            }, True

    def check_private_location_send(self, owner, peer, generation):
        with self._lock, self._connect() as db:
            try:
                _contact(db, owner, peer)
            except ValueError:
                raise LocationPermissionChanged(
                    "Private location contact was removed"
                ) from None
            p = _policy(db, owner, peer)
            if not p["share"] or not generation or p["generation"] != generation:
                raise LocationPermissionChanged(
                    "Private location permission was revoked"
                )

    def private_location_result(self, owner, request_id, state):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE private_location_sends SET state=? WHERE owner=? AND id=?",
                (state, owner, request_id),
            )
        return {"request_id": request_id, "state": state}
