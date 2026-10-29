# SPDX-License-Identifier: MIT
from unittest.mock import AsyncMock

import pytest

from meshchatnext.src.backend import sip_desktop_audio as audio_module
from meshchatnext.src.backend.sip_desktop_audio import DesktopSipAudio


@pytest.mark.asyncio
async def test_private_echo_pair_is_owned_and_never_changes_defaults(monkeypatch):
    monkeypatch.setattr(audio_module.sys, "platform", "linux")
    monkeypatch.delenv("PULSE_SOURCE", raising=False)
    monkeypatch.delenv("PULSE_SINK", raising=False)
    command = AsyncMock(side_effect=["mic", "speakers", "42", ""])
    audio = DesktopSipAudio(command=command)
    env = await audio.open()
    assert audio.available
    assert env["PULSE_SOURCE"].startswith("meshchat_next_")
    assert env["PULSE_SINK"].endswith("_speaker")
    assert command.await_args_list[2].args[:2] == ("load-module", "module-echo-cancel")
    await audio.close()
    command.assert_awaited_with("unload-module", "42")
    assert not audio.available
    assert not any("set-default" in str(call) for call in command.await_args_list)
    await audio.close()
    assert command.await_count == 4


@pytest.mark.asyncio
async def test_missing_audio_filter_falls_back_and_explicit_devices_are_honored(
    monkeypatch,
):
    monkeypatch.setattr(audio_module.sys, "platform", "linux")
    monkeypatch.delenv("PULSE_SOURCE", raising=False)
    monkeypatch.delenv("PULSE_SINK", raising=False)
    command = AsyncMock(side_effect=FileNotFoundError())
    audio = DesktopSipAudio(command=command)
    assert "PULSE_SOURCE" not in await audio.open()
    assert not audio.available
    monkeypatch.setenv("PULSE_SOURCE", "user_headset")
    command.reset_mock()
    assert (await audio.open())["PULSE_SOURCE"] == "user_headset"
    command.assert_not_awaited()
