"""Captured real reconnect queue state, using actual packed LXMF messages."""

import threading
from types import SimpleNamespace

import LXMF
import pytest
import RNS

from meshchatnext.src.backend.lxmf_reconnect import (
    install_reconnect_recovery,
    recover_pending_direct_messages,
)


def fixture(fields=None, content="Private synthetic reconnect test"):
    source = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    target = RNS.Destination(
        RNS.Identity(), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
    )
    message = LXMF.LXMessage(
        target, source, content, fields=fields, desired_method=LXMF.LXMessage.DIRECT
    )
    message.pack()
    message.state = LXMF.LXMessage.SENDING
    message.delivery_attempts = 2
    message.next_delivery_attempt = 1234567
    router = SimpleNamespace(
        outbound_processing_lock=threading.Lock(),
        pending_outbound=[message],
        direct_links={target.hash: SimpleNamespace(status=RNS.Link.ACTIVE)},
        backchannel_links={},
    )
    return router, message


def test_missing_delivery_link_recovers_without_repacking_rebudgeting_or_firing_callbacks():
    router, message = fixture()
    seen = []
    message.register_delivery_callback(lambda *_: seen.append("delivered"))
    message.register_failed_callback(lambda *_: seen.append("failed"))
    packet, hash_before = message.packed, message.hash
    assert message._LXMessage__delivery_destination is None
    assert recover_pending_direct_messages(router) == 1
    assert message.state == LXMF.LXMessage.OUTBOUND
    assert message.packed == packet and message.hash == hash_before
    assert (
        message.delivery_attempts == 2
        and message.next_delivery_attempt == 1234567
        and seen == []
    )
    assert recover_pending_direct_messages(router) == 0


@pytest.mark.parametrize(
    "state",
    [
        LXMF.LXMessage.OUTBOUND,
        LXMF.LXMessage.SENT,
        LXMF.LXMessage.DELIVERED,
        LXMF.LXMessage.CANCELLED,
        LXMF.LXMessage.FAILED,
        LXMF.LXMessage.REJECTED,
    ],
)
def test_completed_cancelled_and_other_states_are_never_revived(state):
    router, message = fixture()
    message.state = state
    assert recover_pending_direct_messages(router) == 0 and message.state == state


@pytest.mark.parametrize(
    "kind",
    [
        "healthy",
        "closed-assigned",
        "pending-route",
        "no-route",
        "propagated",
        "opportunistic",
        "unknown-layout",
    ],
)
def test_only_the_captured_missing_link_direct_state_can_recover(kind):
    router, message = fixture()
    if kind == "healthy":
        message.set_delivery_destination(SimpleNamespace(status=RNS.Link.ACTIVE))
    elif kind == "closed-assigned":
        message.set_delivery_destination(SimpleNamespace(status=RNS.Link.CLOSED))
    elif kind == "pending-route":
        router.direct_links[message.destination_hash].status = RNS.Link.PENDING
    elif kind == "no-route":
        router.direct_links.clear()
    elif kind == "propagated":
        message.method = LXMF.LXMessage.PROPAGATED
    elif kind == "opportunistic":
        message.method = LXMF.LXMessage.OPPORTUNISTIC
    elif kind == "unknown-layout":
        del message._LXMessage__delivery_destination
    assert (
        recover_pending_direct_messages(router) == 0
        and message.state == LXMF.LXMessage.SENDING
    )


@pytest.mark.parametrize(
    "fields,content",
    [
        ({LXMF.FIELD_TELEMETRY: b"synthetic"}, "text"),
        ({LXMF.FIELD_TELEMETRY_STREAM: []}, "text"),
        ({}, "!NFLOC1:geo:48.0000000,-122.0000000,0.00;u=10.00;t=1;s=0.00;b=0.00"),
    ],
)
def test_live_location_is_never_requeued_by_generic_recovery(fields, content):
    router, message = fixture(fields, content)
    assert (
        recover_pending_direct_messages(router) == 0
        and message.state == LXMF.LXMessage.SENDING
    )


def test_sdk_processing_lock_is_respected_and_a_fresh_backchannel_is_supported():
    router, message = fixture()
    router.backchannel_links = router.direct_links
    router.direct_links = {}
    with router.outbound_processing_lock:
        assert (
            recover_pending_direct_messages(router) == 0
            and message.state == LXMF.LXMessage.SENDING
        )
    assert recover_pending_direct_messages(router) == 1


def test_scheduler_wrap_is_once_only_and_preserves_link_callback_arguments():
    router, message = fixture()
    calls = []
    router.process_outbound = lambda *args, **kwargs: calls.append(
        (args, kwargs, message.state)
    )
    assert install_reconnect_recovery(router)
    assert not install_reconnect_recovery(router)
    router.process_outbound("native link callback", key="retained")
    assert calls == [
        (("native link callback",), {"key": "retained"}, LXMF.LXMessage.OUTBOUND)
    ]


@pytest.mark.parametrize("outcome", ["cancelled", "delivered", "assigned", "removed"])
def test_concurrent_terminal_or_handoff_change_is_rechecked_before_recovery(outcome):
    router, message = fixture()

    class ChangedRoute:
        @property
        def status(self):
            if outcome == "cancelled":
                message.state = LXMF.LXMessage.CANCELLED
            elif outcome == "delivered":
                message.state = LXMF.LXMessage.DELIVERED
            elif outcome == "assigned":
                message.set_delivery_destination(
                    SimpleNamespace(status=RNS.Link.ACTIVE)
                )
            else:
                router.pending_outbound.clear()
            return RNS.Link.ACTIVE

    router.direct_links[message.destination_hash] = ChangedRoute()
    assert recover_pending_direct_messages(router) == 0
    if outcome == "cancelled":
        assert message.state == LXMF.LXMessage.CANCELLED
    elif outcome == "delivered":
        assert message.state == LXMF.LXMessage.DELIVERED
    else:
        assert message.state == LXMF.LXMessage.SENDING
