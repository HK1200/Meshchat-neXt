# SPDX-License-Identifier: MIT
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from meshchatnext.src.backend.sip_windows_network import candidates


def adapter(index=7, kind=71, address="192.0.2.10"):
    return {"index": index, "type": kind, "address": address}


def route(index=7, metric=10, **fields):
    return {
        "index": index,
        "metric": metric,
        "destination": 0,
        "mask": 0,
        "type": 4,
        **fields,
    }


def test_networks_classify_native_types_and_sort_default_routes():
    rows = candidates(
        [adapter(), adapter(8, 6), adapter(9, 243)],
        [route(8, 30), route(7, 10), route(9, 20), route(7, 50)],
    )
    assert [r["kind"] for r in rows] == ["wifi", "mobile", "ethernet"]
    assert rows[0]["interface"] == "7"
    assert rows[0]["address"] == "192.0.2.10"


@pytest.mark.parametrize(
    "row",
    [
        adapter(kind=131),
        adapter(address="0.0.0.0"),
        adapter(address="127.0.0.1"),
        adapter(address="169.254.1.2"),
        adapter(address="bad"),
        adapter(address="224.0.0.1"),
    ],
)
def test_unknown_tunnels_and_invalid_addresses_are_not_allowed(row):
    assert candidates([row], [route()]) == []


@pytest.mark.parametrize(
    "row",
    [
        route(destination=1),
        route(mask=1),
        route(type=2),
        route(metric=0xFFFFFFFF),
        route(index=99),
    ],
)
def test_nondefault_or_invalid_routes_cannot_activate_sip(row):
    assert candidates([adapter()], [row]) == []


def test_sip_windows_credentials_are_profile_account_scoped_and_redact_errors(
    tmp_path, monkeypatch
):
    from meshchatnext.src.backend import meshcore_windows_credentials as windows
    from meshchatnext.src.backend import sip_desktop_store as store

    api = Mock()
    api.read.return_value = b"example"
    monkeypatch.setattr(store.sys, "platform", "win32")
    monkeypatch.setattr(windows, "_CredentialManager", lambda: api)
    first = store.SipPasswords(tmp_path / "one")
    second = store.SipPasswords(tmp_path / "two")
    account = str(uuid.uuid4())
    first.save(account, "example")
    target = api.write.call_args.args[0]
    assert "org.meshchatnext.sip/v1/" in target
    assert target != second._windows_slot(account)
    assert first.load(account, interactive=False) == "example"
    api.read.assert_called_with(target, max_size=256)
    first.remove(account)
    api.delete.assert_called_with(target)
    api.read.side_effect = OSError("private diagnostic")
    with pytest.raises(ValueError) as error:
        first.load(account)
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_windows_audio_never_invokes_pactl(monkeypatch):
    from meshchatnext.src.backend import sip_desktop_audio as audio

    command = Mock(side_effect=AssertionError("Linux audio command invoked"))
    monkeypatch.setattr(audio.sys, "platform", "win32")
    router = audio.DesktopSipAudio(command=command)
    env = await router.open()
    assert isinstance(env, dict)
    assert (
        not router.available
    )  # No claimed echo cancellation without hardware verification.
    await router.close()
    command.assert_not_called()


def test_windows_build_sources_match_existing_pins_and_detect_tamper(tmp_path):
    root = Path(__file__).resolve().parents[2]

    def module(path):
        spec = importlib.util.spec_from_file_location("recipe", path)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result

    windows = module(root / "scripts/build-windows-sip.py")
    linux = module(root / "scripts/build-linux-sip.py")
    assert windows.SOURCES == linux.SOURCES
    for name in windows.SOURCES:
        (tmp_path / name).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        windows.verify_sources(tmp_path)
