# SPDX-License-Identifier: MIT
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend.sip_desktop_service import DesktopSipService
from meshchatnext.src.backend.sip_desktop_store import SipAccounts


class Vault:
    def __init__(self):
        self.data = {}

    def save(self, key, value):
        self.data[key] = value

    def load(self, key, **options):
        return self.data[key]

    def remove(self, key):
        self.data.pop(key, None)


def setup(tmp_path):
    store = SipAccounts(tmp_path / "sip.json", Vault())
    row = store.save(
        {"extension": "1234", "allowed_networks": ["wifi", "mobile"]}, "test-secret"
    )
    network = [
        {"interface": "wlan0", "kind": "wifi", "address": "10.0.0.2", "metric": 10}
    ]
    made = []

    def factory(executable, **fields):
        engine = type("Engine", (), {})()
        engine.running = False
        engine.interface = fields["interface"]
        engine.options = dict(fields)

        async def launch():
            engine.running = True

        async def close():
            engine.running = False

        async def command(op, **values):
            if op == "start":
                engine.on_event({"state": "registered"})
            return {"state": "ok"}

        engine.launch = AsyncMock(side_effect=launch)
        engine.close = AsyncMock(side_effect=close)
        engine.command = AsyncMock(side_effect=command)
        made.append(engine)
        return engine

    service = DesktopSipService(
        store, "unused", engine_factory=factory, networks=lambda: list(network)
    )
    return service, row, network, made


@pytest.mark.asyncio
async def test_explicit_connect_reconcile_no_duplicate_registration(tmp_path):
    service, row, _, made = setup(tmp_path)
    assert service.status()["enabled"] is False and made == []
    await service.command("connect", id=row["id"])
    for _ in range(4):
        await service.reconcile()
    assert len(made) == 1 and made[0].command.await_count == 1
    assert service.status()["registered"]
    assert "test-secret" not in str(service.status())
    await service.close()
    assert service.store.enabled  # app close preserves user's desired startup state
    assert not service.store.session_passwords


@pytest.mark.asyncio
async def test_allowed_network_failover_closes_old_engine_before_replacement(tmp_path):
    service, row, network, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    old = made[0]
    network[:] = [
        {"interface": "wwan0", "kind": "mobile", "address": "10.1.0.2", "metric": 5}
    ]
    await service.reconcile()
    old.close.assert_awaited_once()
    assert made[-1].interface == "wwan0" and len(made) == 2
    network[:] = [
        {"interface": "enp1s0", "kind": "ethernet", "address": "10.2.0.2", "metric": 1}
    ]
    await service.reconcile()
    assert service.engine is None and service.status()["state"] == "waiting_network"
    assert len(made) == 2
    await service.close()


@pytest.mark.asyncio
async def test_privacy_feature_gate_stops_connection_without_losing_preference(
    tmp_path,
):
    service, row, _, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    service.permitted = lambda: False
    await service.reconcile()
    assert (
        service.state == "blocked" and service.engine is None and service.store.enabled
    )
    assert not made[0].running
    await service.close()


@pytest.mark.asyncio
async def test_auth_denial_does_not_repeatedly_register_until_explicit_retry(tmp_path):
    service, row, _, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    old = made[0]
    old.on_event({"state": "registration_failed", "code": 403})
    for _ in range(3):
        await service.reconcile()
    assert len(made) == 1 and service.engine is None
    await service.command("connect", id=row["id"])
    assert len(made) == 2
    old.on_event({"state": "registration_failed", "code": 401})
    assert service.state == "registered"
    await service.command("disconnect")
    assert not service.store.enabled and service.engine is None
    await service.close()


@pytest.mark.asyncio
async def test_existing_ui_target_contract_and_password_metadata(tmp_path):
    service, row, _, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    assert service.status()["accounts"][0]["has_password"] is True
    await service.command("call", target="5678")
    made[0].command.assert_awaited_with(
        "dial", peer="sip:5678@premium.hamsoverip.com:5160"
    )
    await service.close()


@pytest.mark.asyncio
async def test_resume_reconnects_once_without_reenabling_disabled_or_denied_account(
    tmp_path,
):
    service, row, _, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    old = made[0]
    old.on_event({"state": "incoming", "peer": "sip:test@localhost"})
    assert service.call_id
    await service.command("resume")
    assert len(made) == 2 and not old.running
    assert service.call_state == "idle" and service.call_id == ""
    await service.command("resume")
    assert len(made) == 2
    made[-1].on_event({"state": "registration_failed", "code": 403})
    await service.command("resume")
    assert len(made) == 2
    await service.command("disconnect")
    await service.command("resume")
    assert not service.store.enabled and service.engine is None
    await service.close()


@pytest.mark.asyncio
async def test_windows_engine_receives_selected_adapter_and_local_address(
    tmp_path, monkeypatch
):
    from meshchatnext.src.backend import sip_desktop_service as module

    service, row, network, made = setup(tmp_path)
    network[0]["interface"] = "7"
    monkeypatch.setattr(module.sys, "platform", "win32")
    await service.command("connect", id=row["id"])
    try:
        assert made[0].options == {"interface": "7", "local_address": "10.0.0.2"}
        assert service.status()["platform"] == "windows"
        network[:] = [
            {"interface": "8", "kind": "ethernet", "address": "10.2.0.2", "metric": 1}
        ]
        await service.reconcile()
        assert not made[0].running
        assert service.status()["state"] == "waiting_network"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_registration_failure_rotates_allowed_network_and_keeps_success(
    tmp_path, monkeypatch
):
    from meshchatnext.src.backend import sip_desktop_service as module

    now = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    service, row, network, made = setup(tmp_path)
    network.append(
        {"interface": "wwan0", "kind": "mobile", "address": "10.1.0.2", "metric": 20}
    )
    await service.command("connect", id=row["id"])
    made[0].on_event({"state": "registration_failed", "code": 408})
    await service.reconcile()
    assert len(made) == 2 and made[-1].interface == "wwan0"
    assert not made[0].running
    now[0] += 120
    await service.reconcile()
    assert len(made) == 2  # available preferred Wi-Fi does not disturb healthy mobile
    await service.close()


@pytest.mark.asyncio
async def test_registration_timeout_and_all_failed_cooldown_retry(
    tmp_path, monkeypatch
):
    from meshchatnext.src.backend import sip_desktop_service as module

    now = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    service, row, _network, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    service.state = "registering"
    now[0] += 46
    await service.reconcile()
    assert service.engine is None and len(made) == 1
    now[0] += 59
    await service.reconcile()
    assert len(made) == 1
    now[0] += 1
    await service.reconcile()
    assert len(made) == 2 and service.state == "registered"
    await service.close()


@pytest.mark.asyncio
async def test_registration_failure_does_not_terminate_active_audio(tmp_path):
    service, row, _network, made = setup(tmp_path)
    await service.command("connect", id=row["id"])
    made[0].on_event({"state": "connected", "peer": "test"})
    made[0].on_event({"state": "registration_failed", "code": 408})
    await service.reconcile()
    assert made[0].running and service.call_state == "connected"
    made[0].on_event({"state": "ended"})
    await service.reconcile()
    assert service.engine is None
    await service.close()
