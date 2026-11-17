import json
from types import SimpleNamespace

import LXMF
import pytest
import RNS

from meshchatnext.src.backend import mailbox_push

RECIPIENT = bytes.fromhex("a1" * 16)
RELAY = bytes.fromhex("b2" * 16)
ROUTE = {
    "provider": "https://alerts.example.invalid",
    "audience": "test mail",
    "relay": RELAY.hex(),
}


@pytest.mark.parametrize(
    "case", ["accepted", "direct", "failed", "wrong relay", "no link", "no route"]
)
def test_only_an_accepted_message_at_the_configured_relay_is_signed(
    tmp_path, monkeypatch, case
):
    route_file = tmp_path / "mailbox-push-routes.json"
    if case != "no route":
        route_file.write_text(json.dumps({RECIPIENT.hex(): ROUTE}))
    identity = RNS.Identity()
    message = SimpleNamespace(
        method=LXMF.LXMessage.DIRECT if case == "direct" else LXMF.LXMessage.PROPAGATED,
        state=LXMF.LXMessage.FAILED if case == "failed" else LXMF.LXMessage.SENT,
        transient_id=bytes.fromhex("c3" * 32),
        get_destination=lambda: SimpleNamespace(hash=RECIPIENT),
        get_source=lambda: SimpleNamespace(identity=identity),
    )
    if case != "no link":
        message._LXMessage__delivery_destination = SimpleNamespace(
            destination=SimpleNamespace(
                hash=bytes(16) if case == "wrong relay" else RELAY
            ),
        )

    sent = []

    def post(route, payload):
        sent.append((route, json.loads(payload)))
        return 204

    class ImmediateThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            assert daemon

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(mailbox_push.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(mailbox_push, "_post", post)
    mailbox_push.queue_accepted_hint(tmp_path, message)
    if case != "accepted":
        assert sent == []
        return
    ((route, hint),) = sent
    assert route.relay == RELAY.hex()
    signature = bytes.fromhex(hint.pop("signature"))
    assert set(hint) == {"recipient", "message", "sender", "issued"}
    signed = json.dumps(
        {"audience": ROUTE["audience"], **hint}, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    assert identity.validate(signature, b"neXt Family push v1\x00" + signed)


@pytest.mark.parametrize("change", [None, {**ROUTE, "audience": "changed"}])
def test_removed_or_edited_route_cancels_retry(tmp_path, monkeypatch, change):
    route_file = tmp_path / "mailbox-push-routes.json"
    route_file.write_text(json.dumps({RECIPIENT.hex(): ROUTE}))
    route = mailbox_push.route_for(tmp_path, RECIPIENT.hex())
    requests = []

    def post(destination, payload):
        requests.append((destination, payload))
        route_file.write_text(json.dumps({RECIPIENT.hex(): change} if change else {}))
        return 503

    monkeypatch.setattr(mailbox_push, "_post", post)
    monkeypatch.setattr(mailbox_push.time, "sleep", lambda _: None)
    assert mailbox_push._workers.acquire(blocking=False)
    mailbox_push._send(tmp_path, RECIPIENT.hex(), route, b"test")
    assert requests == [(route, b"test")]
