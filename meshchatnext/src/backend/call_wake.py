# SPDX-License-Identifier: 0BSD
"""Domain-separated, signed Reticulum call-wake intents; no network side effects."""

import hashlib
import json
import re
import time
import uuid

FIELDS = frozenset(("recipient", "call", "sender", "issued", "signature"))
LIFETIME = 30
FUTURE_SKEW = 10


def hex_value(value, size):
    return (
        type(value) is str
        and re.fullmatch(r"[a-f0-9]{" + str(size * 2) + "}", value) is not None
    )


def destination_hash(name, public_key):
    if not isinstance(public_key, bytes) or len(public_key) != 64:
        raise ValueError("Expected a Reticulum public key")
    return (
        hashlib.sha256(
            hashlib.sha256(name.encode("ascii")).digest()[:10]
            + hashlib.sha256(public_key).digest()[:16]
        )
        .digest()[:16]
        .hex()
    )


def voice_hash(public_key):
    return destination_hash("lxst.telephony", public_key)


def signed_bytes(hint, audience, *, cancel=False):
    if (
        not isinstance(audience, str)
        or not re.fullmatch(r"[A-Za-z0-9 _.-]{1,128}", audience)
        or type(hint) is not dict
        or not {"recipient", "call", "sender", "issued"} <= hint.keys()
        or not hex_value(hint["recipient"], 16)
        or not hex_value(hint["call"], 16)
        or not hex_value(hint["sender"], 64)
        or type(hint["issued"]) is not int
        or not 0 <= hint["issued"] <= 2**53 - 1
    ):
        raise ValueError("Invalid signed call intent")
    domain = (
        b"neXt Reticulum call cancel v1\0"
        if cancel
        else b"neXt Reticulum call wake v1\0"
    )
    fields = {key: hint[key] for key in ("recipient", "call", "sender", "issued")}
    return domain + json.dumps(
        dict(audience=audience, **fields), sort_keys=True, separators=(",", ":")
    ).encode("ascii")


def valid_shape(hint):
    return (
        type(hint) is dict
        and hint.keys() == FIELDS
        and hex_value(hint.get("recipient"), 16)
        and hex_value(hint.get("call"), 16)
        and hex_value(hint.get("sender"), 64)
        and hex_value(hint.get("signature"), 64)
        and type(hint.get("issued")) is int
        and 0 <= hint["issued"] <= 2**53 - 1
    )


def fresh(hint, now):
    return valid_shape(hint) and now - LIFETIME <= hint["issued"] <= now + FUTURE_SKEW


def build_hint(
    identity, recipient, audience, *, call_id=None, issued=None, cancel=False
):
    hint = {
        "recipient": recipient,
        "call": call_id or uuid.uuid4().hex,
        "sender": identity.get_public_key().hex(),
        "issued": int(time.time()) if issued is None else issued,
    }
    hint["signature"] = identity.sign(signed_bytes(hint, audience, cancel=cancel)).hex()
    return hint
