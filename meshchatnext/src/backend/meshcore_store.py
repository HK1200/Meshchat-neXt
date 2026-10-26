# SPDX-License-Identifier: MIT
"""Private MeshCore history, isolated by the companion's full public identity.

One messaging controller owns a database. No Reticulum tables or identity keys
are read or written. Call blocking methods through asyncio.to_thread.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from pathlib import Path


def public_key(value):
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("A full MeshCore public key is required")
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        raise ValueError("Invalid MeshCore public key") from None
    if len(raw) != 32:
        raise ValueError("Invalid MeshCore public key")
    return raw.hex()


def notification_key(owner, kind, target):
    return "meshcore-" + hashlib.sha256(f"{owner}:{kind}:{target}".encode()).hexdigest()


def channel_sender(text):
    """Unverified display-name prefix, never a public identity."""
    if not isinstance(text, str):
        return None
    sender, separator, _ = text.partition(": ")
    return (
        sender.strip() if separator and sender.strip() and len(sender) <= 128 else None
    )


def _json(value):
    def binary(item):
        if isinstance(item, bytes):
            return {"bytes_hex": item.hex()}
        raise TypeError("Unsupported received payload")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=binary)


class MeshCoreStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS contact_links (
                    owner TEXT NOT NULL, account TEXT NOT NULL, contact INTEGER NOT NULL,
                    peer TEXT NOT NULL, PRIMARY KEY(owner,account,contact), UNIQUE(owner,account,peer));
                CREATE TABLE IF NOT EXISTS read_markers (
                    owner TEXT NOT NULL, peer TEXT NOT NULL, seen REAL NOT NULL,
                    PRIMARY KEY(owner,peer));
                CREATE TABLE IF NOT EXISTS announces (
                    owner TEXT NOT NULL, peer TEXT NOT NULL, name TEXT NOT NULL,
                    kind INTEGER NOT NULL, advertised INTEGER NOT NULL,
                    heard REAL, path_len INTEGER, path_bytes INTEGER,
                    PRIMARY KEY(owner,peer));
                CREATE TABLE IF NOT EXISTS map_positions (owner TEXT NOT NULL,peer TEXT NOT NULL,latitude REAL NOT NULL,longitude REAL NOT NULL,updated REAL NOT NULL,PRIMARY KEY(owner,peer));
                CREATE TABLE IF NOT EXISTS region_preferences (owner TEXT PRIMARY KEY,channel_default TEXT);
                CREATE TABLE IF NOT EXISTS regions (owner TEXT NOT NULL,name TEXT NOT NULL,PRIMARY KEY(owner,name));
                CREATE TABLE IF NOT EXISTS hidden_channels (owner TEXT NOT NULL,channel_id TEXT NOT NULL,PRIMARY KEY(owner,channel_id));
                CREATE TABLE IF NOT EXISTS channel_scopes (owner TEXT NOT NULL,channel_id TEXT NOT NULL,scope TEXT,PRIMARY KEY(owner,channel_id));
                CREATE TABLE IF NOT EXISTS saved_nodes (
                    owner TEXT NOT NULL,peer TEXT NOT NULL,PRIMARY KEY(owner,peer));
                CREATE TABLE IF NOT EXISTS channel_preferences (
                    owner TEXT NOT NULL,channel_id TEXT NOT NULL,seen REAL NOT NULL DEFAULT 0,
                    muted INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(owner,channel_id));
                CREATE TABLE IF NOT EXISTS channel_banishments (
                    owner TEXT NOT NULL,channel_id TEXT NOT NULL,sender TEXT NOT NULL,created REAL NOT NULL,
                    PRIMARY KEY(owner,channel_id,sender));
                CREATE TABLE IF NOT EXISTS config_imports (
                    owner TEXT NOT NULL,id TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,
                    result TEXT NOT NULL,PRIMARY KEY(owner,id));
                CREATE TABLE IF NOT EXISTS profiles (
                    owner TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contacts (
                    owner TEXT NOT NULL, peer TEXT NOT NULL, name TEXT NOT NULL,
                    kind INTEGER NOT NULL, active INTEGER NOT NULL,
                    PRIMARY KEY(owner,peer));
                CREATE TABLE IF NOT EXISTS messages (
                    owner TEXT NOT NULL, id TEXT NOT NULL, peer TEXT,
                    direction TEXT NOT NULL, text TEXT NOT NULL,
                    timestamp INTEGER NOT NULL, state TEXT NOT NULL,
                    created REAL NOT NULL, ack TEXT, deadline REAL,
                    fingerprint TEXT, payload TEXT,
                    PRIMARY KEY(owner,id), UNIQUE(owner,fingerprint));
                CREATE INDEX IF NOT EXISTS conversation ON messages(owner,peer,created);
                CREATE TABLE IF NOT EXISTS receipts (
                    owner TEXT NOT NULL, code TEXT NOT NULL, received REAL NOT NULL,
                    PRIMARY KEY(owner,code,received));
                CREATE TABLE IF NOT EXISTS channels (
                    owner TEXT NOT NULL, slot INTEGER NOT NULL,
                    channel_id TEXT, name TEXT NOT NULL, kind TEXT NOT NULL,
                    PRIMARY KEY(owner,slot));
                CREATE TABLE IF NOT EXISTS channel_messages (
                    owner TEXT NOT NULL, id TEXT NOT NULL, channel_id TEXT,
                    slot INTEGER NOT NULL, direction TEXT NOT NULL,
                    text TEXT NOT NULL, timestamp INTEGER NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL,
                    fingerprint TEXT, payload TEXT,
                    PRIMARY KEY(owner,id), UNIQUE(owner,fingerprint));
                CREATE INDEX IF NOT EXISTS channel_conversation
                    ON channel_messages(owner,channel_id,created);
                CREATE TABLE IF NOT EXISTS message_paths (
                    owner TEXT NOT NULL,kind TEXT NOT NULL,message_id TEXT NOT NULL,
                    observation TEXT NOT NULL,created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS message_path_lookup ON message_paths(owner,kind,message_id);
                CREATE TABLE IF NOT EXISTS clocks (
                    owner TEXT NOT NULL, peer TEXT NOT NULL, stamp INTEGER NOT NULL,
                    PRIMARY KEY(owner,peer));
            """)

            region_columns = {
                row[1] for row in db.execute("PRAGMA table_info(region_preferences)")
            }
            if "auto_scan" not in region_columns:
                db.execute(
                    "ALTER TABLE region_preferences ADD COLUMN auto_scan INTEGER NOT NULL DEFAULT 0"
                )
            if "last_scan" not in region_columns:
                db.execute(
                    "ALTER TABLE region_preferences ADD COLUMN last_scan REAL NOT NULL DEFAULT 0"
                )

            for table in ("messages", "channel_messages"):
                message_columns = {
                    row[1] for row in db.execute(f"PRAGMA table_info({table})")
                }
                if "heard_repeats" not in message_columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN heard_repeats INTEGER")

            columns = {
                row[1] for row in db.execute("PRAGMA table_info(channel_preferences)")
            }
            if "mentions_only" not in columns:
                db.execute(
                    "ALTER TABLE channel_preferences ADD COLUMN mentions_only INTEGER NOT NULL DEFAULT 0"
                )

            if "sort_order" not in columns:
                db.execute(
                    "ALTER TABLE channel_preferences ADD COLUMN sort_order INTEGER"
                )

    def repeat_observation(self, owner, kind, message_id, count=0):
        if (
            kind not in ("direct", "channel")
            or type(count) is not int
            or not 0 <= count <= 10000
        ):
            raise ValueError("Invalid repeat observation")
        table = "messages" if kind == "direct" else "channel_messages"
        with self._lock, self._connect() as db:
            db.execute(
                f"UPDATE {table} SET heard_repeats=COALESCE(heard_repeats,0)+? WHERE owner=? AND id=? AND direction='out'",
                (count, owner, message_id),
            )

    def save_message_paths(self, owner, kind, message_id, observations):
        if kind not in ("direct", "channel") or not isinstance(observations, list):
            raise ValueError("Invalid path observation")
        table = "messages" if kind == "direct" else "channel_messages"
        with self._lock, self._connect() as db:
            if not db.execute(
                f"SELECT 1 FROM {table} WHERE owner=? AND id=?", (owner, message_id)
            ).fetchone():
                return
            for observation in observations[-32:]:
                db.execute(
                    "INSERT INTO message_paths VALUES(?,?,?,?,?)",
                    (owner, kind, message_id, _json(observation), time.time()),
                )
            db.execute(
                "DELETE FROM message_paths WHERE owner=? AND kind=? AND message_id=? AND rowid NOT IN (SELECT rowid FROM message_paths WHERE owner=? AND kind=? AND message_id=? ORDER BY rowid DESC LIMIT 32)",
                (owner, kind, message_id, owner, kind, message_id),
            )

    def message_details(self, owner, kind, target, message_id):
        from meshchatnext.src.backend.meshcore_message_paths import describe_paths

        owner, target = public_key(owner), public_key(target)
        if (
            kind not in ("direct", "channel")
            or not isinstance(message_id, str)
            or not 1 <= len(message_id) <= 128
        ):
            raise ValueError("Invalid message selection")
        table, column = (
            ("messages", "peer")
            if kind == "direct"
            else ("channel_messages", "channel_id")
        )
        with self._lock, self._connect() as db:
            row = db.execute(
                f"SELECT * FROM {table} WHERE owner=? AND {column}=? AND id=?",
                (owner, target, message_id),
            ).fetchone()
            if not row:
                raise ValueError("Message is unavailable in this destination")
            observations = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT observation FROM message_paths WHERE owner=? AND kind=? AND message_id=? ORDER BY rowid LIMIT 32",
                    (owner, kind, message_id),
                )
            ]
        return describe_paths(
            dict(row),
            observations,
            self.announces(owner),
            self.map_nodes(owner),
            owner=owner,
            kind=kind,
            target=target,
        )

    def update_profile_name(self, owner, name):
        with self._lock, self._connect() as db:
            db.execute("UPDATE profiles SET name=? WHERE owner=?", (name, owner))

    @contextlib.contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.create_function("channel_sender", 1, channel_sender, deterministic=True)
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def bind(self, owner, name):
        owner = public_key(owner)
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO profiles VALUES (?,?)", (owner, name))
            # A prior process may have died after writing to the radio. Never replay.
            db.execute(
                "UPDATE messages SET state='unknown' WHERE owner=? AND state='submitting'",
                (owner,),
            )
            db.execute(
                "UPDATE channel_messages SET state='unknown' WHERE owner=? AND state='submitting'",
                (owner,),
            )
        return owner

    def replace_contacts(self, owner, contacts):
        rows = [
            (
                owner,
                public_key(contact["public_key"]),
                str(contact.get("adv_name", "")),
                int(contact["type"]),
                1,
            )
            for contact in contacts.values()
        ]
        with self._lock, self._connect() as db:
            db.execute("UPDATE contacts SET active=0 WHERE owner=?", (owner,))
            db.executemany("INSERT OR REPLACE INTO contacts VALUES (?,?,?,?,?)", rows)

    def contacts(self, owner):
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT peer,name,kind,active FROM contacts WHERE owner=? ORDER BY name,peer",
                    (owner,),
                )
            ]

    def outgoing_clock(self, owner, peer):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT stamp FROM clocks WHERE owner=? AND peer=?", (owner, peer)
            ).fetchone()
            return row[0] if row else 0

    def reserve_command_clock(self, owner, peer, floor):
        peer = public_key(peer)
        if type(floor) is not int or not 0 <= floor < 0xFFFFFFFF:
            raise ValueError("Invalid command clock")
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT stamp FROM clocks WHERE owner=? AND peer=?", (owner, peer)
            ).fetchone()
            stamp = max(int(time.time()), floor, row[0] + 1 if row else 0)
            if stamp > min(0xFFFFFFFF, int(time.time()) + 60):
                raise ValueError("Command clock is too far ahead; wait before sending")
            db.execute(
                "INSERT OR REPLACE INTO clocks VALUES (?,?,?)", (owner, peer, stamp)
            )
            return stamp

    def prepare_send(
        self, owner, peer, text, request_id, *, room=False, timestamp_floor=0
    ):
        peer = public_key(peer)
        if not isinstance(text, str) or not text or "\x00" in text:
            raise ValueError("Message must contain text without NUL characters")
        if len(text.encode("utf-8")) > 160:
            raise ValueError("MeshCore direct messages support at most 160 UTF-8 bytes")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("A stable message request ID is required")
        if type(timestamp_floor) is not int or not 0 <= timestamp_floor < 0xFFFFFFFF:
            raise ValueError("Invalid message timestamp floor")
        now = time.time()
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT * FROM messages WHERE owner=? AND id=?", (owner, request_id)
            ).fetchone()
            if existing:
                if (
                    existing["peer"] != peer
                    or existing["text"] != text
                    or existing["direction"] != "out"
                ):
                    raise ValueError("Message request ID has already been used")
                return dict(existing), False
            candidates = db.execute(
                "SELECT peer,kind FROM contacts WHERE owner=? AND active=1 AND substr(peer,1,12)=?",
                (owner, peer[:12]),
            ).fetchall()
            if (
                len(candidates) != 1
                or candidates[0]["peer"] != peer
                or candidates[0]["kind"] != (3 if room else 1)
            ):
                raise ValueError("Choose an unambiguous active chat contact")
            row = db.execute(
                "SELECT stamp FROM clocks WHERE owner=? AND peer=?", (owner, peer)
            ).fetchone()
            stamp = max(int(now), timestamp_floor, row["stamp"] + 1 if row else 0)
            if stamp > 0xFFFFFFFF:
                raise ValueError("Message timestamp exhausted")
            if stamp > int(now) + 60 or not 0 <= stamp <= 0xFFFFFFFF:
                raise ValueError("Message clock is too far ahead; wait before sending")
            db.execute(
                "INSERT OR REPLACE INTO clocks VALUES (?,?,?)", (owner, peer, stamp)
            )
            db.execute(
                """INSERT INTO messages(owner,id,peer,direction,text,timestamp,state,created)
                          VALUES (?,?,?,'out',?,?,'submitting',?)""",
                (owner, request_id, peer, text, stamp, now),
            )
            return dict(
                db.execute(
                    "SELECT * FROM messages WHERE owner=? AND id=?", (owner, request_id)
                ).fetchone()
            ), True

    def result(self, owner, message_id, state, ack=None, timeout=None):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE messages SET state=?,ack=?,deadline=? WHERE owner=? AND id=?",
                (
                    state,
                    ack,
                    time.time() + timeout if timeout is not None else None,
                    owner,
                    message_id,
                ),
            )
            self._reconcile(db, owner)
            return dict(
                db.execute(
                    "SELECT * FROM messages WHERE owner=? AND id=?", (owner, message_id)
                ).fetchone()
            )

    @staticmethod
    def _reconcile(db, owner):
        # A 32-bit receipt code is not globally unique. Do not guess on collisions.
        rows = db.execute(
            "SELECT id,ack,created FROM messages WHERE owner=? AND ack IS NOT NULL AND state IN ('accepted','unconfirmed')",
            (owner,),
        ).fetchall()
        for row in rows:
            count = db.execute(
                "SELECT count(*) FROM messages WHERE owner=? AND ack=?",
                (owner, row["ack"]),
            ).fetchone()[0]
            receipt = db.execute(
                "SELECT 1 FROM receipts WHERE owner=? AND code=? AND received>=? LIMIT 1",
                (owner, row["ack"], row["created"]),
            ).fetchone()
            if count == 1 and receipt:
                db.execute(
                    "UPDATE messages SET state='delivered' WHERE owner=? AND id=?",
                    (owner, row["id"]),
                )

    def receipt(self, owner, code, received):
        if not isinstance(code, str) or len(code) != 8 or len(bytes.fromhex(code)) != 4:
            raise ValueError("Invalid receipt code")
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO receipts VALUES (?,?,?)",
                (owner, code.lower(), received),
            )
            self._reconcile(db, owner)

    def receive(self, owner, kind, payload):
        encoded = _json(payload)
        # Path/SNR can change on repeated reception; they are not message identity.
        identity = {
            key: payload.get(key)
            for key in (
                "pubkey_prefix",
                "channel_idx",
                "sender_timestamp",
                "txt_type",
                "text",
                "signature",
                "data_type",
                "data",
                "payload",
            )
        }
        fingerprint = hashlib.sha256((kind + _json(identity)).encode()).hexdigest()
        # Binary channel packets have no sender timestamp or unique wire ID.
        # Retain repeated datagrams rather than collapsing equal data forever.
        if kind == "channel_data" and "sender_timestamp" not in payload:
            fingerprint = uuid.uuid4().hex
        with self._lock, self._connect() as db:
            peer = None
            prefix = payload.get("pubkey_prefix")
            if kind == "direct" and isinstance(prefix, str) and len(prefix) == 12:
                candidates = db.execute(
                    "SELECT peer FROM contacts WHERE owner=? AND substr(peer,1,12)=?",
                    (owner, prefix.lower()),
                ).fetchall()
                if len(candidates) == 1:
                    peer = candidates[0]["peer"]
            if kind in ("channel", "channel_data"):
                slot = payload.get("channel_idx")
                if type(slot) is not int or not 0 <= slot <= 255:
                    raise ValueError("Invalid received channel slot")
                binding = db.execute(
                    "SELECT channel_id FROM channels WHERE owner=? AND slot=?",
                    (owner, slot),
                ).fetchone()
                fingerprint = hashlib.sha256(
                    (
                        fingerprint + str(binding["channel_id"] if binding else None)
                    ).encode()
                ).hexdigest()
                received = db.execute(
                    """INSERT OR IGNORE INTO channel_messages
                       (owner,id,channel_id,slot,direction,text,timestamp,state,created,fingerprint,payload)
                       VALUES (?,?,?,?, 'in',?,?,'received',?,?,?)""",
                    (
                        owner,
                        uuid.uuid4().hex,
                        binding["channel_id"] if binding else None,
                        slot,
                        str(payload.get("text", "")),
                        int(payload.get("sender_timestamp", 0)),
                        time.time(),
                        fingerprint,
                        encoded,
                    ),
                )
            direct_received = db.execute(
                """INSERT OR IGNORE INTO messages
                (owner,id,peer,direction,text,timestamp,state,created,fingerprint,payload)
                VALUES (?,?,?,'in',?,?,'received',?,?,?)""",
                (
                    owner,
                    uuid.uuid4().hex,
                    peer,
                    str(payload.get("text", "")),
                    int(payload.get("sender_timestamp", 0)),
                    time.time(),
                    fingerprint,
                    _json({"kind": kind, "event": json.loads(encoded)}),
                ),
            )

        fresh = direct_received.rowcount if kind == "direct" else received.rowcount
        if fresh and kind in ("direct", "channel"):
            return self.notification_event(owner, kind, fingerprint)
        return None

    def config_import_result(self, owner, request_id):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT result FROM config_imports WHERE owner=? AND id=?",
                (owner, request_id),
            ).fetchone()
            return json.loads(row["result"]) if row else {"state": "not_found"}

    def config_import_run(self, owner, request_id, digest, *, claim=False, result=None):
        """Durable at-most-once import receipt; contains no source files or secrets."""
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT * FROM config_imports WHERE owner=? AND id=?",
                (owner, request_id),
            ).fetchone()
            if row and row["digest"] != digest:
                raise ValueError("Import request ID already used for another review")
            if result is not None:
                if not row:
                    raise ValueError("Import receipt missing")
                db.execute(
                    "UPDATE config_imports SET state=?,result=? WHERE owner=? AND id=?",
                    (result["state"], _json(result), owner, request_id),
                )
                return result
            if row:
                return json.loads(row["result"])
            if claim:
                pending = {
                    "state": "uncertain",
                    "completed": [],
                    "message": "Import was started. Inspect the radio before attempting a new import.",
                }
                db.execute(
                    "INSERT INTO config_imports VALUES (?,?,?,?,?)",
                    (owner, request_id, digest, "running", _json(pending)),
                )
            return None

    def notification_event(self, owner, kind, fingerprint):
        with self._lock, self._connect() as db:
            table = "messages" if kind == "direct" else "channel_messages"
            row = db.execute(
                f"SELECT * FROM {table} WHERE owner=? AND fingerprint=?",
                (owner, fingerprint),
            ).fetchone()
            if not row or not row["text"].strip():
                return None
            target = row["peer"] if kind == "direct" else row["channel_id"]
            if kind == "channel" and target is None:
                return None
            name = (
                db.execute(
                    "SELECT name FROM contacts WHERE owner=? AND peer=?",
                    (owner, target),
                ).fetchone()
                if kind == "direct"
                else db.execute(
                    "SELECT name FROM channels WHERE owner=? AND channel_id=? LIMIT 1",
                    (owner, target),
                ).fetchone()
            )
            return {
                "type": "meshcore.message",
                "owner": owner,
                "kind": kind,
                "target": target,
                "id": row["id"],
                "name": name[0] if name else "Unknown sender",
                "text": row["text"],
                "created": row["created"],
                "notification_key": notification_key(owner, kind, target),
            }

    def notification_allowed(self, event):
        owner, target = event["owner"], event["target"]
        with self._lock, self._connect() as db:
            if event["kind"] == "direct":
                seen = db.execute(
                    "SELECT seen FROM read_markers WHERE owner=? AND peer=?",
                    (owner, target),
                ).fetchone()
                return not seen or seen[0] < event["created"]
            if db.execute(
                "SELECT 1 FROM hidden_channels WHERE owner=? AND channel_id=?",
                (owner, target),
            ).fetchone():
                return False
            prefs = db.execute(
                "SELECT seen,muted,mentions_only FROM channel_preferences WHERE owner=? AND channel_id=?",
                (owner, target),
            ).fetchone()
            if prefs and (prefs["muted"] or prefs["seen"] >= event["created"]):
                return False
            if prefs and prefs["mentions_only"]:
                profile = db.execute(
                    "SELECT name FROM profiles WHERE owner=?", (owner,)
                ).fetchone()
                name = (
                    unicodedata.normalize("NFC", profile[0]).casefold()
                    if profile
                    else ""
                )
                # MeshCore channel text includes a sender prefix; it is not a mention.
                body = event["text"].partition(": ")[2]
                mentions = re.findall(r"@\[([^\]\r\n]+)\]", body)
                if not name or not any(
                    unicodedata.normalize("NFC", item).casefold() == name
                    for item in mentions
                ):
                    return False
            sender = channel_sender(event["text"])
            return not db.execute(
                "SELECT 1 FROM channel_banishments WHERE owner=? AND channel_id=? AND sender=?",
                (owner, target, sender),
            ).fetchone()

    def history(self, owner, peer=None, limit=100):
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("History limit must be 1-1000")
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE messages SET state='unconfirmed' WHERE owner=? AND state='accepted' AND deadline<=?",
                (owner, time.time()),
            )
            if peer is None:
                rows = db.execute(
                    "SELECT * FROM messages WHERE owner=? ORDER BY created DESC,id LIMIT ?",
                    (owner, limit),
                )
            else:
                rows = db.execute(
                    "SELECT * FROM messages WHERE owner=? AND peer=? ORDER BY created DESC,id LIMIT ?",
                    (owner, public_key(peer), limit),
                )
            return [dict(row) for row in rows]

    def invalidate_channels(self, owner):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE channels SET channel_id=NULL,kind='unknown' WHERE owner=?",
                (owner,),
            )

    def invalidate_channel(self, owner, slot):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE channels SET channel_id=NULL,kind='unknown' WHERE owner=? AND slot=?",
                (owner, slot),
            )

    def replace_channels(self, owner, rows):
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM channels WHERE owner=?", (owner,))
            db.executemany(
                "INSERT INTO channels VALUES (?,?,?,?,?)",
                [
                    (owner, row["slot"], row["channel_id"], row["name"], row["kind"])
                    for row in rows
                ],
            )

    def prepare_channel_send(self, owner, channel, text, request_id):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("A stable message request ID is required")
        now = time.time()
        identity = channel["channel_id"]
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT * FROM channel_messages WHERE owner=? AND id=?",
                (owner, request_id),
            ).fetchone()
            if existing:
                if (
                    existing["channel_id"] != identity
                    or existing["text"] != text
                    or existing["direction"] != "out"
                ):
                    raise ValueError("Message request ID has already been used")
                return dict(existing), False
            row = db.execute(
                "SELECT stamp FROM clocks WHERE owner=? AND peer=?",
                (owner, "channel:" + identity),
            ).fetchone()
            stamp = max(int(now), row["stamp"] + 1 if row else 0)
            if stamp > int(now) + 60 or not 0 <= stamp <= 0xFFFFFFFF:
                raise ValueError("Message clock is too far ahead; wait before sending")
            db.execute(
                "INSERT OR REPLACE INTO clocks VALUES (?,?,?)",
                (owner, "channel:" + identity, stamp),
            )
            db.execute(
                """INSERT INTO channel_messages
                          (owner,id,channel_id,slot,direction,text,timestamp,state,created)
                          VALUES (?,?,?,?,'out',?,?,'submitting',?)""",
                (owner, request_id, identity, channel["slot"], text, stamp, now),
            )
            return dict(
                db.execute(
                    "SELECT * FROM channel_messages WHERE owner=? AND id=?",
                    (owner, request_id),
                ).fetchone()
            ), True

    def channel_result(self, owner, message_id, state):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE channel_messages SET state=? WHERE owner=? AND id=?",
                (state, owner, message_id),
            )
            return dict(
                db.execute(
                    "SELECT * FROM channel_messages WHERE owner=? AND id=?",
                    (owner, message_id),
                ).fetchone()
            )

    def message_view(self, owner, kind, target):
        target = public_key(target)
        channel = kind == "channel"
        table, column = (
            ("channel_messages", "channel_id") if channel else ("messages", "peer")
        )
        with self._lock, self._connect() as db:
            marker = db.execute(
                "SELECT seen FROM channel_preferences WHERE owner=? AND channel_id=?"
                if channel
                else "SELECT seen FROM read_markers WHERE owner=? AND peer=?",
                (owner, target),
            ).fetchone()
            seen = marker[0] if marker else 0
            filtering = (
                "AND NOT EXISTS(SELECT 1 FROM channel_banishments b WHERE b.owner=m.owner AND b.channel_id=m.channel_id AND b.sender=channel_sender(m.text))"
                if channel
                else "AND COALESCE(json_extract(payload,'$.event.txt_type'),0)!=1"
            )
            role = (
                db.execute(
                    "SELECT kind FROM contacts WHERE owner=? AND peer=?",
                    (owner, target),
                ).fetchone()
                if not channel
                else None
            )
            if role and role[0] == 3:
                filtering += (
                    " AND COALESCE(json_extract(payload,'$.event.txt_type'),0)=2"
                )
            row = db.execute(
                f"SELECT id,created FROM {table} m WHERE owner=? AND {column}=? AND direction='in' AND created>? {filtering} ORDER BY created,id LIMIT 1",
                (owner, target, seen),
            ).fetchone()
            return {
                "seen": seen,
                "first_unread": dict(row) if row else None,
                "target": target,
                "kind": kind,
            }

    def message_window(self, owner, kind, target, *, anchor=None, after=None):
        if kind not in ("channel", "direct") or (anchor and after):
            raise ValueError("Invalid history window")
        target = public_key(target)
        table, column = (
            ("channel_messages", "channel_id")
            if kind == "channel"
            else ("messages", "peer")
        )
        with self._lock, self._connect() as db:
            cursor = anchor or after
            row = (
                db.execute(
                    f"SELECT created,id FROM {table} WHERE owner=? AND {column}=? AND id=?",
                    (owner, target, cursor),
                ).fetchone()
                if cursor
                else None
            )
            if cursor and row is None:
                raise ValueError("Message is unavailable in this destination")
            filtering = (
                "AND NOT EXISTS(SELECT 1 FROM channel_banishments b WHERE b.owner=m.owner AND b.channel_id=m.channel_id AND b.sender=channel_sender(m.text))"
                if kind == "channel"
                else "AND COALESCE(json_extract(payload,'$.event.txt_type'),0)!=1"
            )
            role = (
                db.execute(
                    "SELECT kind FROM contacts WHERE owner=? AND peer=?",
                    (owner, target),
                ).fetchone()
                if kind == "direct"
                else None
            )
            if role and role[0] == 3:
                filtering += " AND (direction!='in' OR COALESCE(json_extract(payload,'$.event.txt_type'),0)=2)"
            condition, args = "", [owner, target]
            if row:
                condition = (
                    "AND (created>? OR (created=? AND id"
                    + (">" if after else ">=")
                    + "?))"
                )
                args += [row["created"], row["created"], row["id"]]
            direction = "ASC" if row else "DESC"
            projection = (
                "*,channel_sender(text) AS sender" if kind == "channel" else "*"
            )
            return [
                dict(item)
                for item in db.execute(
                    f"SELECT {projection} FROM {table} m WHERE owner=? AND {column}=? {filtering} {condition} ORDER BY created {direction},id {direction} LIMIT 1000",
                    args,
                )
            ]

    def notification_target(self, owner, key):
        if (
            not isinstance(key, str)
            or len(key) != 73
            or not key.startswith("meshcore-")
        ):
            raise ValueError("Invalid notification key")
        with self._lock, self._connect() as db:
            for row in db.execute(
                "SELECT peer,kind FROM contacts WHERE owner=? AND kind IN (1,3)",
                (owner,),
            ):
                if notification_key(owner, "direct", row["peer"]) == key:
                    return {
                        "owner": owner,
                        "kind": "room" if row["kind"] == 3 else "direct",
                        "target": row["peer"],
                    }
            for row in db.execute(
                "SELECT DISTINCT channel_id FROM channels WHERE owner=? AND channel_id IS NOT NULL",
                (owner,),
            ):
                if notification_key(owner, "channel", row[0]) == key:
                    return {"owner": owner, "kind": "channel", "target": row[0]}
        return None

    def channel_history(self, owner, identity, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("History limit must be 1-1000")
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT *,channel_sender(text) AS sender FROM channel_messages m
                       WHERE owner=? AND channel_id IS ? AND (direction!='in' OR NOT EXISTS(
                       SELECT 1 FROM channel_banishments b WHERE b.owner=m.owner AND b.channel_id=m.channel_id AND b.sender=channel_sender(m.text)))
                       ORDER BY created DESC,id LIMIT ?""",
                    (owner, identity, limit),
                )
            ]

    def save_announce(self, owner, contact, heard=None):
        """Keep one discovery per radio identity; never add it as a contact."""
        peer = public_key(contact["public_key"])
        advertised = max(0, int(contact.get("last_advert", 0)))
        path_len = contact.get("out_path_len")
        mode = contact.get("out_path_hash_mode")
        path_len = path_len if type(path_len) is int and -1 <= path_len <= 63 else None
        path_bytes = mode + 1 if type(mode) is int and 0 <= mode <= 2 else None
        with self._lock, self._connect() as db:
            previous = db.execute(
                "SELECT * FROM announces WHERE owner=? AND peer=?", (owner, peer)
            ).fetchone()
            if heard is None and previous and advertised < previous["advertised"]:
                return
            db.execute(
                """INSERT INTO announces VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(owner,peer) DO UPDATE SET
                   name=excluded.name,kind=excluded.kind,
                   advertised=MAX(announces.advertised,excluded.advertised),
                   heard=COALESCE(MAX(announces.heard,excluded.heard),announces.heard,excluded.heard),
                   path_len=excluded.path_len,path_bytes=excluded.path_bytes""",
                (
                    owner,
                    peer,
                    str(contact.get("adv_name", ""))[:128],
                    int(contact.get("type", 0)),
                    advertised,
                    heard,
                    path_len,
                    path_bytes,
                ),
            )
            lat, lon = contact.get("adv_lat"), contact.get("adv_lon")
            if (
                type(lat) in (int, float)
                and type(lon) in (int, float)
                and math.isfinite(lat)
                and math.isfinite(lon)
                and -90 <= lat <= 90
                and -180 <= lon <= 180
                and (lat != 0 or lon != 0)
            ):
                updated = advertised or (heard if type(heard) in (int, float) else 0)
                db.execute(
                    """INSERT INTO map_positions VALUES(?,?,?,?,?)
                    ON CONFLICT(owner,peer) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,updated=excluded.updated
                    WHERE excluded.updated>=map_positions.updated""",
                    (owner, peer, lat, lon, updated),
                )

    def map_nodes(self, owner):
        owner = public_key(owner)
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT p.peer,p.latitude,p.longitude,p.updated,a.heard,a.advertised,a.name,a.kind,
                EXISTS(SELECT 1 FROM contacts c WHERE c.owner=p.owner AND c.peer=p.peer AND c.active=1) AS saved
                FROM map_positions p JOIN announces a ON a.owner=p.owner AND a.peer=p.peer
                WHERE p.owner=? ORDER BY COALESCE(a.heard,
                CASE WHEN p.updated<=? THEN p.updated ELSE 0 END) DESC,p.peer LIMIT 1000""",
                    (owner, time.time() + 60),
                )
            ]

    def touch_announce(self, owner, peer, heard):
        peer = public_key(peer)
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO announces VALUES (?,?, '',0,0,?,NULL,NULL)
                   ON CONFLICT(owner,peer) DO UPDATE SET heard=MAX(COALESCE(announces.heard,0),excluded.heard)""",
                (owner, peer, heard),
            )

    def announces(self, owner):
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT peer,name,kind,advertised,heard,path_len,path_bytes,
                   EXISTS(SELECT 1 FROM contacts c WHERE c.owner=a.owner AND c.peer=a.peer AND c.active=1) AS saved
                   FROM announces a WHERE owner=?
                   ORDER BY COALESCE(heard,CASE WHEN advertised<=? THEN advertised ELSE 0 END) DESC,peer""",
                    (owner, time.time() + 60),
                )
            ]

    def channel_visibility(self, owner, channel, hidden):
        owner, channel = public_key(owner), public_key(channel)
        if type(hidden) is not bool:
            raise ValueError("Hidden must be a boolean")
        with self._lock, self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM channels WHERE owner=? AND channel_id=?",
                (owner, channel),
            ).fetchone():
                raise ValueError("Channel is not configured for this identity")
            if hidden:
                db.execute(
                    "INSERT OR IGNORE INTO hidden_channels VALUES (?,?)",
                    (owner, channel),
                )
            else:
                db.execute(
                    "DELETE FROM hidden_channels WHERE owner=? AND channel_id=?",
                    (owner, channel),
                )

    def channel_ui(self, owner):
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT c.slot,c.channel_id,c.name,c.kind,EXISTS(SELECT 1 FROM hidden_channels h WHERE h.owner=c.owner AND h.channel_id=c.channel_id) AS hidden,(SELECT scope FROM channel_scopes s WHERE s.owner=c.owner AND s.channel_id=c.channel_id) AS scope,COALESCE(p.muted,0) AS muted,COALESCE(p.mentions_only,0) AS mentions_only,
                   (SELECT count(*) FROM channel_messages m WHERE m.owner=c.owner AND m.channel_id=c.channel_id
                    AND m.direction='in' AND m.created>COALESCE(p.seen,0) AND NOT EXISTS(
                     SELECT 1 FROM channel_banishments b WHERE b.owner=m.owner AND b.channel_id=m.channel_id AND b.sender=channel_sender(m.text))) AS unread
                   FROM channels c LEFT JOIN channel_preferences p ON p.owner=c.owner AND p.channel_id=c.channel_id
                   WHERE c.owner=? AND c.channel_id IS NOT NULL AND c.kind IN ('public','private') ORDER BY p.sort_order IS NULL,p.sort_order,c.slot""",
                    (owner,),
                )
            ]

    def reorder_channels(self, owner, channels):
        if not isinstance(channels, list) or len(channels) > 256:
            raise ValueError("Invalid channel order")
        channels = [public_key(channel) for channel in channels]
        if len(channels) != len(set(channels)):
            raise ValueError("Duplicate channel order entry")
        with self._lock, self._connect() as db:
            configured = {
                row[0]
                for row in db.execute(
                    "SELECT channel_id FROM channels WHERE owner=? AND channel_id IS NOT NULL AND kind IN ('public','private')",
                    (owner,),
                )
            }
            if set(channels) != configured:
                raise ValueError("Channels changed; refresh before reordering")
            for position, channel in enumerate(channels):
                db.execute(
                    "INSERT INTO channel_preferences(owner,channel_id,sort_order) VALUES (?,?,?) ON CONFLICT(owner,channel_id) DO UPDATE SET sort_order=excluded.sort_order",
                    (owner, channel, position),
                )

    def channel_preference(
        self, owner, channel, *, through=None, muted=None, mentions_only=None
    ):
        channel = public_key(channel)
        if muted is not None and type(muted) is not bool:
            raise ValueError("Mute must be a boolean")
        if mentions_only is not None and type(mentions_only) is not bool:
            raise ValueError("Mentions only must be a boolean")
        with self._lock, self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM channels WHERE owner=? AND channel_id=?",
                (owner, channel),
            ).fetchone():
                raise ValueError("Unknown channel")
            db.execute(
                "INSERT OR IGNORE INTO channel_preferences(owner,channel_id) VALUES (?,?)",
                (owner, channel),
            )
            if through is not None:
                if (
                    type(through) not in (int, float)
                    or not 0 <= through <= time.time() + 1
                ):
                    raise ValueError("Invalid read marker")
                latest = db.execute(
                    "SELECT MAX(created) FROM channel_messages WHERE owner=? AND channel_id=?",
                    (owner, channel),
                ).fetchone()[0]
                db.execute(
                    "UPDATE channel_preferences SET seen=MAX(seen,?) WHERE owner=? AND channel_id=?",
                    (min(through, latest or 0), owner, channel),
                )
            if mentions_only is not None:
                db.execute(
                    "UPDATE channel_preferences SET mentions_only=? WHERE owner=? AND channel_id=?",
                    (int(mentions_only), owner, channel),
                )
            if muted is not None:
                db.execute(
                    "UPDATE channel_preferences SET muted=? WHERE owner=? AND channel_id=?",
                    (int(muted), owner, channel),
                )

    def region_automation(self, owner, enabled=None, scanned=None):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT auto_scan,last_scan FROM region_preferences WHERE owner=?",
                (owner,),
            ).fetchone()
            if enabled is not None or scanned is not None:
                db.execute(
                    "INSERT OR IGNORE INTO region_preferences(owner) VALUES (?)",
                    (owner,),
                )
                if enabled is not None:
                    if type(enabled) is not bool:
                        raise ValueError("Invalid region automation setting")
                    db.execute(
                        "UPDATE region_preferences SET auto_scan=? WHERE owner=?",
                        (int(enabled), owner),
                    )
                if scanned is not None:
                    db.execute(
                        "UPDATE region_preferences SET last_scan=? WHERE owner=?",
                        (scanned, owner),
                    )
                row = db.execute(
                    "SELECT auto_scan,last_scan FROM region_preferences WHERE owner=?",
                    (owner,),
                ).fetchone()
            return {
                "enabled": bool(row[0]) if row else False,
                "last_scan": row[1] if row else 0,
            }

    def region_default(self, owner):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT channel_default FROM region_preferences WHERE owner=?", (owner,)
            ).fetchone()
            return row[0] if row else None

    def set_region_default(self, owner, scope):
        if scope is not None:
            from meshchatnext.src.backend.meshcore_tools import region_name

            scope = region_name(scope)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO region_preferences(owner,channel_default) VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET channel_default=excluded.channel_default",
                (owner, scope),
            )
            if scope:
                db.execute("INSERT OR IGNORE INTO regions VALUES (?,?)", (owner, scope))

    def regions(self, owner):
        with self._lock, self._connect() as db:
            return [
                r["name"]
                for r in db.execute(
                    "SELECT name FROM regions WHERE owner=? ORDER BY name", (owner,)
                )
            ]

    def save_region(self, owner, name):
        from meshchatnext.src.backend.meshcore_tools import region_name

        name = region_name(name)
        with self._lock, self._connect() as db:
            if (
                db.execute(
                    "SELECT count(*) FROM regions WHERE owner=?", (owner,)
                ).fetchone()[0]
                >= 256
            ):
                raise ValueError("Saved region limit reached")
            db.execute("INSERT OR IGNORE INTO regions VALUES (?,?)", (owner, name))

    def channel_scope(self, owner, channel, scope=...):
        channel = public_key(channel)
        with self._lock, self._connect() as db:
            if scope is ...:
                row = db.execute(
                    "SELECT scope FROM channel_scopes WHERE owner=? AND channel_id=?",
                    (owner, channel),
                ).fetchone()
                if row and row["scope"] is not None:
                    return row["scope"]
                pref = db.execute(
                    "SELECT channel_default FROM region_preferences WHERE owner=?",
                    (owner,),
                ).fetchone()
                return pref[0] if pref else None
            if not db.execute(
                "SELECT 1 FROM channels WHERE owner=? AND channel_id=?",
                (owner, channel),
            ).fetchone():
                raise ValueError("Channel is not configured for this radio identity")
            if scope is not None and scope != "*":
                from meshchatnext.src.backend.meshcore_tools import region_name

                scope = region_name(scope)
                db.execute("INSERT OR IGNORE INTO regions VALUES (?,?)", (owner, scope))
            db.execute(
                "INSERT INTO channel_scopes VALUES (?,?,?) ON CONFLICT(owner,channel_id) DO UPDATE SET scope=excluded.scope",
                (owner, channel, scope),
            )
        return None

    def record_node_discovery(self, owner, peer, kind, heard):
        peer = public_key(peer)
        if type(kind) is not int or kind not in (2, 3, 4):
            raise ValueError("Invalid infrastructure node type")
        with self._lock, self._connect() as db:
            previous = db.execute(
                "SELECT kind FROM announces WHERE owner=? AND peer=?", (owner, peer)
            ).fetchone()
            if previous and previous["kind"] not in (0, kind):
                return False
            name = (
                f"{ {2: 'Repeater', 3: 'Room server', 4: 'Sensor'}[kind] } {peer[:12]}"
            )
            db.execute(
                """INSERT INTO announces VALUES (?,?,?,?,0,?,NULL,NULL)
                ON CONFLICT(owner,peer) DO UPDATE SET kind=excluded.kind,
                name=CASE WHEN announces.name='' THEN excluded.name ELSE announces.name END,
                heard=MAX(COALESCE(announces.heard,0),excluded.heard)""",
                (owner, peer, name, kind, heard),
            )
            return True

    def node_preference(self, owner, peer, saved):
        peer = public_key(peer)
        with self._lock, self._connect() as db:
            if saved:
                if not db.execute(
                    "SELECT 1 FROM announces WHERE owner=? AND peer=? AND kind IN (2,3,4)",
                    (owner, peer),
                ).fetchone():
                    raise ValueError("Select a repeater, room server or sensor")
                db.execute(
                    "INSERT OR IGNORE INTO saved_nodes VALUES (?,?)", (owner, peer)
                )
            else:
                db.execute(
                    "DELETE FROM saved_nodes WHERE owner=? AND peer=?", (owner, peer)
                )

    def nodes(self, owner):
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT a.peer,a.name,a.kind,a.advertised,a.heard,a.path_len,a.path_bytes,
                   (SELECT count(*) FROM messages m WHERE m.owner=a.owner AND m.peer=a.peer AND m.direction='in'
                   AND m.created>COALESCE((SELECT seen FROM read_markers r WHERE r.owner=a.owner AND r.peer=a.peer),0)) AS unread
                   FROM saved_nodes s JOIN announces a ON a.owner=s.owner AND a.peer=s.peer
                   WHERE s.owner=? ORDER BY a.name,a.peer""",
                    (owner,),
                )
            ]

    def banish_channel_sender(self, owner, channel, message):
        channel = public_key(channel)
        if not isinstance(message, str) or not 1 <= len(message) <= 128:
            raise ValueError("Invalid channel message")
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT text FROM channel_messages WHERE owner=? AND channel_id=? AND id=? AND direction='in'",
                (owner, channel, message),
            ).fetchone()
            sender = channel_sender(row["text"]) if row else None
            if not sender:
                raise ValueError("No displayed sender name is available")
            db.execute(
                "INSERT OR IGNORE INTO channel_banishments VALUES (?,?,?,?)",
                (owner, channel, sender, time.time()),
            )

    def unbanish_channel_sender(self, owner, channel, sender):
        channel = public_key(channel)
        if not isinstance(sender, str) or not 1 <= len(sender) <= 128:
            raise ValueError("Invalid sender name")
        with self._lock, self._connect() as db:
            db.execute(
                "DELETE FROM channel_banishments WHERE owner=? AND channel_id=? AND sender=?",
                (owner, channel, sender),
            )

    def channel_banishments(self, owner):
        with self._lock, self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT b.channel_id,b.sender,b.created,(SELECT name FROM channels c WHERE c.owner=b.owner AND c.channel_id=b.channel_id LIMIT 1) AS channel_name
                   FROM channel_banishments b WHERE b.owner=? ORDER BY b.created DESC""",
                    (owner,),
                )
            ]

    def ui_snapshot(self, owner, account):
        with self._lock, self._connect() as db:
            contacts = [
                dict(row)
                for row in db.execute(
                    "SELECT peer,name,kind,active FROM contacts WHERE owner=? AND kind=1 ORDER BY name,peer",
                    (owner,),
                )
            ]
            links = [
                dict(row)
                for row in db.execute(
                    "SELECT contact,peer FROM contact_links WHERE owner=? AND account=?",
                    (owner, account),
                )
            ]
            db.execute(
                "UPDATE messages SET state='unconfirmed' WHERE owner=? AND state='accepted' AND deadline<=?",
                (owner, time.time()),
            )
            peers = db.execute(
                "SELECT DISTINCT m.peer FROM messages m JOIN contacts c ON c.owner=m.owner AND c.peer=m.peer WHERE m.owner=? AND c.kind=1",
                (owner,),
            ).fetchall()
            conversations = []
            names = {row["peer"]: row["name"] for row in contacts}
            for peer_row in peers:
                peer = peer_row["peer"]
                last = db.execute(
                    "SELECT text,created,state,direction FROM messages WHERE owner=? AND peer=? ORDER BY created DESC,id DESC LIMIT 1",
                    (owner, peer),
                ).fetchone()
                unread = db.execute(
                    "SELECT count(*) FROM messages WHERE owner=? AND peer=? AND direction='in' AND created>COALESCE((SELECT seen FROM read_markers WHERE owner=? AND peer=?),0)",
                    (owner, peer, owner, peer),
                ).fetchone()[0]
                conversations.append(
                    {
                        "peer": peer,
                        "name": names.get(peer, ""),
                        "unread": unread,
                        **dict(last),
                    }
                )
            conversations.sort(key=lambda row: row["created"], reverse=True)
            return {
                "owner": owner,
                "contacts": contacts,
                "links": links,
                "conversations": conversations,
                "announces": self.announces(owner),
                "channels": self.channel_ui(owner),
                "nodes": self.nodes(owner),
                "channel_banishments": self.channel_banishments(owner),
                "profile_name": (
                    db.execute(
                        "SELECT name FROM profiles WHERE owner=?", (owner,)
                    ).fetchone()
                    or [""]
                )[0],
            }

    def link_contact(self, owner, account, contact, peer):
        if type(contact) is not int or contact < 1:
            raise ValueError("Invalid Reticulum contact")
        with self._lock, self._connect() as db:
            if peer is None:
                db.execute(
                    "DELETE FROM contact_links WHERE owner=? AND account=? AND contact=?",
                    (owner, account, contact),
                )
                return
            peer = public_key(peer)
            if (
                db.execute(
                    "SELECT 1 FROM contacts WHERE owner=? AND peer=? AND kind=1",
                    (owner, peer),
                ).fetchone()
                is None
            ):
                raise ValueError("Select a saved MeshCore chat contact")
            # Never steal an existing link to another contact through an upsert.
            existing = db.execute(
                "SELECT contact FROM contact_links WHERE owner=? AND account=? AND peer=?",
                (owner, account, peer),
            ).fetchone()
            if existing and existing["contact"] != contact:
                raise ValueError("Unlink the existing contact first")
            db.execute(
                "INSERT OR REPLACE INTO contact_links VALUES (?,?,?,?)",
                (owner, account, contact, peer),
            )

    def mark_read(self, owner, peer, through):
        peer = public_key(peer)
        if type(through) not in (int, float) or not 0 <= through <= time.time() + 1:
            raise ValueError("Invalid read marker")
        with self._lock, self._connect() as db:
            maximum = db.execute(
                "SELECT max(created) FROM messages WHERE owner=? AND peer=?",
                (owner, peer),
            ).fetchone()[0]
            if maximum is not None:
                db.execute(
                    "INSERT INTO read_markers VALUES (?,?,?) ON CONFLICT(owner,peer) DO UPDATE SET seen=max(seen,excluded.seen)",
                    (owner, peer, min(through, maximum)),
                )
