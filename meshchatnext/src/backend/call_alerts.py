# SPDX-License-Identifier: 0BSD
"""Explicit recipient routes and bounded signed call hints; never carries audio."""

import contextlib
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from meshchatnext.src.backend.call_wake import (
    build_hint,
    destination_hash,
    hex_value,
    voice_hash,
)

MAX_BYTES = 1_048_576
_lock = threading.RLock()
_workers = threading.BoundedSemaphore(8)


@dataclass(frozen=True)
class Route:
    provider: str
    audience: str
    public_key: str

    @property
    def voice(self):
        return voice_hash(bytes.fromhex(self.public_key))


def parse_route(recipient, entry):
    if (
        not hex_value(recipient, 16)
        or type(entry) is not dict
        or entry.keys() != {"provider", "audience", "public_key"}
    ):
        return None
    try:
        provider, audience, key = (
            entry[k] for k in ("provider", "audience", "public_key")
        )
        if (
            type(provider) is not str
            or len(provider) > 2048
            or any(ord(c) < 32 or ord(c) == 127 for c in provider)
            or type(audience) is not str
            or re.fullmatch(r"[A-Za-z0-9 _.-]{1,128}", audience) is None
            or not hex_value(key, 64)
        ):
            return None
        parts = urlsplit(provider)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
            or (parts.port is not None and not 1 <= parts.port <= 65535)
            or destination_hash("lxmf.delivery", bytes.fromhex(key)) != recipient
        ):
            return None
        return Route(provider.rstrip("/"), audience, key)
    except (ValueError, TypeError, AttributeError):
        return None


def read_routes(profile):
    path = Path(profile) / "call-alert-routes.json"
    try:
        if path.is_symlink():
            raise ValueError("Call-alert settings cannot be a link")
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        return {}
    with os.fdopen(fd, "rb") as stream:
        import stat

        info = os.fstat(stream.fileno())
        if path.is_symlink() or not os.path.samestat(path.stat(), info):
            raise ValueError("Call-alert settings changed while opening")
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("Invalid call-alert settings file")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Call-alert settings exceed their storage limit")
    rows = json.loads(raw)
    if (
        type(rows) is not dict
        or len(rows) > 256
        or any(parse_route(key, entry) is None for key, entry in rows.items())
    ):
        raise ValueError("Invalid call-alert settings")
    return rows


def route_for(profile, recipient):
    try:
        return parse_route(recipient, read_routes(profile).get(recipient))
    except (OSError, ValueError, TypeError):
        return None


def save_route(profile, recipient, entry):
    if not hex_value(recipient, 16):
        raise ValueError("Choose a saved Reticulum contact")
    route = parse_route(recipient, entry) if entry is not None else None
    if entry is not None and route is None:
        raise ValueError(
            "Use an HTTPS provider, audience and this contact's bound public key"
        )
    with _lock:
        rows = read_routes(profile)
        if route is None:
            if recipient not in rows:
                return None
            del rows[recipient]
        else:
            rows[recipient] = {
                "provider": route.provider,
                "audience": route.audience,
                "public_key": route.public_key,
            }
        if len(rows) > 256:
            raise ValueError("At most 256 explicit call-alert routes are supported")
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > MAX_BYTES:
            raise ValueError("Call-alert settings exceed their storage limit")
        pending = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=profile, prefix=".call-alerts-", delete=False
            ) as stream:
                pending = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, Path(profile) / "call-alert-routes.json")
        finally:
            if pending is not None:
                with contextlib.suppress(OSError):
                    os.unlink(pending)
    return route


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(route, operation, payload):
    if (
        not isinstance(route, Route)
        or operation not in ("call-alert", "call-cancel")
        or not isinstance(payload, bytes)
        or len(payload) > 2048
    ):
        return 400
    try:
        recipient = destination_hash("lxmf.delivery", bytes.fromhex(route.public_key))
        if (
            parse_route(
                recipient,
                {
                    "provider": route.provider,
                    "audience": route.audience,
                    "public_key": route.public_key,
                },
            )
            != route
        ):
            return 400
    except (ValueError, TypeError):
        return 400
    try:
        request = Request(  # noqa: S310 -- validated HTTPS only; redirects disabled.route.provider + "/v1/" + operation, data=payload,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with build_opener(NoRedirect()).open(request, timeout=4) as response:
            return response.status
    except HTTPError as error:
        with error:
            return error.code
    except (OSError, URLError, ValueError):
        return 503


class PendingHint:
    """At most one wake and cancellation, ordered even if the first HTTP stalls."""

    def __init__(
        self, identity, route, call_id, permitted, *, sender=post, wall_clock=time.time
    ):
        self.identity, self.route, self.call_id = identity, route, call_id
        self.permitted, self.sender, self.wall_clock = permitted, sender, wall_clock
        self.ended = threading.Event()
        self.thread = None

    def start(self):
        if not _workers.acquire(blocking=False):
            return False
        try:
            self.thread = threading.Thread(
                target=self.run, daemon=True, name="Reticulum call hint"
            )
            self.thread.start()
            return True
        except BaseException:
            _workers.release()
            raise

    def cancel(self):
        self.ended.set()

    def run(self):
        try:
            if self.ended.is_set() or not self.permitted():
                return
            packet = build_hint(
                self.identity,
                self.route.voice,
                self.route.audience,
                call_id=self.call_id,
                issued=int(self.wall_clock()),
            )
            # No enrollment code, device token, contact name or audio is sent.
            try:
                self.sender(
                    self.route,
                    "call-alert",
                    json.dumps(packet, separators=(",", ":")).encode(),
                )
            except Exception:
                # A lost HTTP response cannot prove the provider rejected the
                # wake. Preserve the later ordered cancellation in this case.
                pass
            deadline = time.monotonic() + 30
            while (
                not self.ended.is_set()
                and self.permitted()
                and time.monotonic() < deadline
            ):
                if self.wall_clock() >= packet["issued"] + 30:
                    return
                self.ended.wait(min(1, max(0, deadline - time.monotonic())))
            if self.ended.is_set() or not self.permitted():
                cancelled = build_hint(
                    self.identity,
                    self.route.voice,
                    self.route.audience,
                    call_id=self.call_id,
                    issued=int(self.wall_clock()),
                    cancel=True,
                )
                self.sender(
                    self.route,
                    "call-cancel",
                    json.dumps(cancelled, separators=(",", ":")).encode(),
                )
        except Exception:
            pass  # Best effort; provider failures never fail or log a normal call.
        finally:
            _workers.release()


class CallAlerts:
    def __init__(
        self, profile, identity, contacts, blocked, *, sender=post, wall_clock=time.time
    ):
        self.profile, self.identity, self.contacts, self.blocked = (
            profile,
            identity,
            contacts,
            blocked,
        )
        self.sender, self.wall_clock = sender, wall_clock
        self.pending = {}
        self.approved = MappingProxyType({})
        self.refresh_contacts()

    def refresh_contacts(self):
        # The app loop owns SQLite. Worker threads read only this immutable
        # approval snapshot, just as the radio callbacks read the block set.
        self.approved = MappingProxyType(
            {key: row.get("id") for key, row in self.contacts().items()}
        )
        for handle in tuple(self.pending.values()):
            if not handle.permitted():
                handle.cancel()

    def started(self, call):
        if (
            call.incoming
            or not hex_value(call.id, 16)
            or not hex_value(call.peer, 16)
            or call.id in self.pending
        ):
            return
        self.refresh_contacts()
        for recipient, contact_id in self.approved.items():
            route = route_for(self.profile, recipient)
            if route is None:
                continue
            identity_hash = (
                hashlib.sha256(bytes.fromhex(route.public_key)).digest()[:16].hex()
            )
            aliases = {recipient, route.voice, identity_hash}
            if (
                call.peer not in aliases
                and getattr(call, "requested_peer", "") not in aliases
            ):
                continue

            def permitted(
                recipient=recipient, route=route, aliases=aliases, contact_id=contact_id
            ):
                approved = self.approved
                try:
                    return (
                        recipient in approved
                        and approved[recipient] == contact_id
                        and route_for(self.profile, recipient) == route
                        and not any(self.blocked(key) for key in aliases)
                    )
                except Exception:
                    return False

            handle = PendingHint(
                self.identity,
                route,
                call.id,
                permitted,
                sender=self.sender,
                wall_clock=self.wall_clock,
            )
            if handle.start():
                self.pending[call.id] = handle
            return

    def ended(self, call):
        handle = self.pending.pop(call.id, None)
        if handle is not None:
            handle.cancel()

    def close(self):
        pending, self.pending = tuple(self.pending.values()), {}
        for handle in pending:
            handle.cancel()
