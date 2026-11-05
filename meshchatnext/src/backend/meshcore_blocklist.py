# SPDX-License-Identifier: 0BSD
"""Shared phrase rules for incoming MeshCore text, without identity banishment."""

from meshchatnext.src.backend.meshcore_store import channel_sender
from meshchatnext.src.backend.message_blocklist import (
    first_matching_blocklist_entry,
    parse_message_blocklist_json,
)


def active_blocklist(app):
    """Read the active account on every message; do not cache settings or secrets."""
    context = getattr(app, "current_context", None)
    config = getattr(context, "config", None)
    if config is None or not config.message_blocklist_enabled.get():
        return None
    return parse_message_blocklist_json(config.message_blocklist_json.get())


def blocks_meshcore_message(rules, kind, payload, contacts):
    """Names and four-byte room hints never establish contact membership."""
    if rules is None or kind not in ("direct", "channel"):
        return False
    text = payload.get("text")
    if not isinstance(text, str):
        return False
    is_contact = False
    peer_fields = ""
    if kind == "channel":
        peer_fields = channel_sender(text) or ""
        if peer_fields:
            text = text.partition(": ")[2]
    elif payload.get("txt_type") == 1:
        return False  # Explicit administrator CLI replies are not chat.
    elif payload.get("txt_type") == 2:
        # The enclosing contact is the room server, not this post's author.
        signature = payload.get("signature")
        if isinstance(signature, str):
            peer_fields = signature
    else:
        prefix = payload.get("pubkey_prefix")
        if isinstance(prefix, str) and len(prefix) == 12:
            matches = {
                contact["peer"]: contact
                for contact in contacts
                if contact.get("active") and contact["peer"].startswith(prefix.lower())
            }
            if len(matches) == 1:
                peer, contact = next(iter(matches.items()))
                is_contact = True
                peer_fields = f"{peer}\n{contact.get('name', '')}"
            else:
                peer_fields = prefix
    return (
        first_matching_blocklist_entry(
            rules, peer_fields, is_contact=is_contact, message_haystack=text
        )
        is not None
    )
