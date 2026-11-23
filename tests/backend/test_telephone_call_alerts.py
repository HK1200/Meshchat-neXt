# SPDX-License-Identifier: 0BSD
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from meshchatnext.src.backend.telephone_manager import TelephoneManager


@pytest.fixture
def manager():
    value = TelephoneManager(identity=MagicMock())
    value.telephone = MagicMock(busy=False, active_call=None, call_status=3)
    value.call_alerts = MagicMock()
    value._status_poll_interval_s = 0.001
    return value


async def test_hint_starts_before_path_lookup_and_is_cancelled_on_failed_call(manager):
    events = []
    manager.call_alerts.started.side_effect = lambda call: events.append(("wake", call))

    def recall(*_args, **_kwargs):
        assert events and events[0][0] == "wake"
        return MagicMock()

    async def no_path(*_a, **_kw):
        return False

    with (
        patch(
            "meshchatnext.src.backend.telephone_manager.RNS.Identity.recall",
            side_effect=recall,
        ),
        patch(
            "meshchatnext.src.backend.telephone_manager.RNS.Transport.has_path",
            return_value=False,
        ),
        patch.object(manager, "_await_path", side_effect=no_path),
        patch(
            "meshchatnext.src.backend.telephone_manager.asyncio.sleep",
            new=__import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(),
        ),
    ):
        with pytest.raises(RuntimeError, match="Path not found"):
            await manager.initiate(bytes.fromhex("ab" * 16))
    outgoing = events[0][1]
    assert len(outgoing.id) == 32 and outgoing.peer == "ab" * 16
    manager.call_alerts.ended.assert_called_once_with(outgoing)
    assert manager._outgoing_alert is None


async def test_provider_failure_never_prevents_ordinary_call(manager):
    manager.call_alerts.started.side_effect = OSError("Provider unavailable")
    manager.telephone.call.side_effect = lambda *_: setattr(
        manager.telephone, "call_status", 0
    )
    with (
        patch(
            "meshchatnext.src.backend.telephone_manager.RNS.Identity.recall",
            return_value=MagicMock(),
        ),
        patch(
            "meshchatnext.src.backend.telephone_manager.RNS.Transport.has_path",
            return_value=True,
        ),
    ):
        await asyncio.wait_for(manager.initiate(bytes.fromhex("ab" * 16)), 3)
    manager.telephone.call.assert_called_once()
    manager.call_alerts.ended.assert_called_once()


def test_local_remote_end_and_teardown_cancel_only_once(manager):
    outgoing = object()
    manager._outgoing_alert = outgoing
    manager.request_hangup()
    manager.on_telephone_call_ended(None)
    manager.teardown()
    manager.call_alerts.ended.assert_called_once_with(outgoing)
    manager.call_alerts.close.assert_called_once()
