"""Best-effort signed alerts for explicitly configured LXMF mailbox recipients."""

import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import LXMF


@dataclass(frozen=True)
class Route:
    provider: str
    audience: str
    relay: str


_workers = threading.BoundedSemaphore(8)


def route_for(profile, recipient):
    try:
        with (profile / "mailbox-push-routes.json").open(encoding="utf-8") as settings:
            entry = json.load(settings).get(recipient)
        if not isinstance(entry, dict):
            return None
        provider, audience, relay = (
            entry[key] for key in ("provider", "audience", "relay")
        )
        parts = urlsplit(provider)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
            or not isinstance(audience, str)
            or not 0 < len(audience) <= 128
            or not re.fullmatch(r"[a-f0-9]{32}", relay)
        ):
            return None
        return Route(provider.rstrip("/"), audience, relay)
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(route, payload):
    if urlsplit(route.provider).scheme != "https":
        return 400
    try:
        request = Request(  # noqa: S310 -- HTTPS is required and redirects are disabled.
            route.provider + "/v1/mailbox-alert",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with build_opener(NoRedirect()).open(request, timeout=4) as response:
            return response.status
    except HTTPError as error:
        with error:
            return error.code
    except (OSError, URLError, ValueError):
        return 503


def _send(profile, recipient, route, payload):
    try:
        for delay in (0, 1, 3):
            if delay:
                time.sleep(delay)
            if route_for(profile, recipient) != route:
                return
            status = _post(route, payload)
            if status not in (404, 429, 500, 502, 503, 504):
                return
    finally:
        _workers.release()


def queue_accepted_hint(profile, message, expected_route=None):
    """Call only from LXMF's delivery callback, which also handles direct delivery."""
    if (
        message.method != LXMF.LXMessage.PROPAGATED
        or message.state != LXMF.LXMessage.SENT
        or not isinstance(message.transient_id, bytes)
        or len(message.transient_id) != 32
    ):
        return
    try:
        recipient = message.get_destination().hash.hex()
        route = route_for(profile, recipient)
        if route is None or (expected_route is not None and expected_route != route):
            return
        # LXMF exposes a setter but no accessor for the actual propagation link.
        # Bind the disclosure to the link that returned proof, not the router's current preference.
        link = getattr(message, "_LXMessage__delivery_destination", None)
        if link is None or link.destination.hash.hex() != route.relay:
            return
        identity = message.get_source().identity
        hint = {
            "recipient": recipient,
            "message": message.transient_id.hex(),
            "sender": identity.get_public_key().hex(),
            "issued": int(time.time()),
        }
        encoded = json.dumps(
            {"audience": route.audience, **hint}, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        hint["signature"] = identity.sign(b"neXt Family push v1\x00" + encoded).hex()
        payload = json.dumps(hint, separators=(",", ":")).encode("ascii")
    except (AttributeError, OSError, ValueError, TypeError):
        return
    if _workers.acquire(blocking=False):
        try:
            threading.Thread(
                target=_send, args=(profile, recipient, route, payload), daemon=True
            ).start()
        except RuntimeError:
            _workers.release()
