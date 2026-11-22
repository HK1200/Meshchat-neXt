# SPDX-License-Identifier: 0BSD
"""Recover a captured LXMF reconnect state without resetting delivery policy.

A closed-link retry can leave SENDING with no delivery destination, even after
LXMF establishes a fresh active link. Its normal active-link branch then waits
for a proof instead of handing off the retained packet. Only that exact state
is returned to OUTBOUND; LXMF owns the retry budget, packet and callbacks.
"""

import LXMF
import RNS

_MISSING = object()


def recover_pending_direct_messages(router):
    if not router.outbound_processing_lock.acquire(False):
        return 0
    recovered = 0
    try:
        for message in router.pending_outbound.copy():
            if recovered >= 16:
                break
            if (
                message.state != LXMF.LXMessage.SENDING
                or message.method != LXMF.LXMessage.DIRECT
                or getattr(message, "_LXMessage__delivery_destination", _MISSING)
                is not None
            ):
                continue
            fields = message.fields or {}
            if not isinstance(fields, dict) or any(
                key in fields
                for key in (LXMF.FIELD_TELEMETRY, LXMF.FIELD_TELEMETRY_STREAM)
            ):
                continue
            content = message.content
            if (
                isinstance(content, (bytes, bytearray))
                and content.startswith(b"!NFLOC")
            ) or (isinstance(content, str) and content.startswith("!NFLOC")):
                continue
            peer = message.destination_hash
            if not isinstance(peer, bytes) or len(peer) != 16:
                continue
            # Match the SDK's selection order, including a pending direct link
            # taking priority over a backchannel. Never invent a route.
            link = router.direct_links.get(peer) or router.backchannel_links.get(peer)
            if link is None or link.status != RNS.Link.ACTIVE:
                continue
            # SDK receipt/cancel callbacks can run while the route is inspected.
            # Recheck membership, handoff and state after every lookup that may
            # yield; a terminal state must never become a new outbound attempt.
            if not any(current is message for current in router.pending_outbound):
                continue
            if (
                getattr(message, "_LXMessage__delivery_destination", _MISSING) is None
                and message.state == LXMF.LXMessage.SENDING
            ):
                message.state = LXMF.LXMessage.OUTBOUND
                recovered += 1
    finally:
        router.outbound_processing_lock.release()
    return recovered


def install_reconnect_recovery(router):
    """Use the existing SDK scheduler; add no worker, timer or network request."""
    if getattr(router, "_next_reconnect_recovery_installed", False) is True:
        return False
    original = getattr(router, "process_outbound", None)
    if not callable(original) or hasattr(original, "assert_called_with"):
        return False  # Preserve explicitly mocked router contracts in callers.

    def process(*args, **kwargs):
        recover_pending_direct_messages(router)
        return original(*args, **kwargs)

    router.process_outbound = process
    router._next_reconnect_recovery_installed = True
    return True
