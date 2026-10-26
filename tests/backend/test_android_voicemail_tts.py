# SPDX-License-Identifier: 0BSD
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from meshchatnext import android_tts
from meshchatnext.src.backend.voicemail_manager import VoicemailManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    vm = VoicemailManager.__new__(VoicemailManager)
    vm.config = MagicMock()
    vm.config.voicemail_tts_voice.get.return_value = "en"
    vm.config.voicemail_tts_speed.get.return_value = 175
    vm.config.voicemail_tts_pitch.get.return_value = 50
    vm.greetings_dir = str(tmp_path)
    vm.has_espeak = False
    vm._tts_status_cache = None
    vm._tts_status_checked_at = 0
    vm._greeting_generation_lock = threading.Lock()
    monkeypatch.setattr(android_tts, "_is_chaquopy_android", lambda: True)
    return vm


def test_android_provider_enables_generation_without_espeak(manager, monkeypatch):
    probe = MagicMock(return_value=True)
    monkeypatch.setattr(android_tts, "available", probe)
    assert manager.get_tts_status() == {
        "has_tts": True,
        "tts_provider": "android",
        "tts_supports_word_gap": False,
    }
    manager.get_tts_status()
    probe.assert_called_once()


def test_missing_android_voice_keeps_recording_available(manager, monkeypatch):
    monkeypatch.setattr(android_tts, "available", lambda: False)
    assert manager.get_tts_status()["has_tts"] is False
    assert manager.get_tts_status()["tts_provider"] == "android"


def test_android_greeting_is_converted_and_temporary_audio_removed(
    manager, monkeypatch
):
    def speak(text, filename, **options):
        assert text == "Hello"
        assert options == {"voice": "en", "speed": 175, "pitch": 50}
        Path(filename).write_bytes(b"generated WAV")

    monkeypatch.setattr(android_tts, "synthesize", speak)

    def convert(filename):
        assert Path(filename).read_bytes() == b"generated WAV"
        return "greeting.opus"

    manager.convert_to_greeting = convert
    assert manager.generate_greeting("Hello") == "greeting.opus"
    assert not Path(manager.greetings_dir, "greeting.wav").exists()


def test_android_failure_preserves_existing_greeting(manager, monkeypatch):
    greeting = Path(manager.greetings_dir, "greeting.opus")
    greeting.write_bytes(b"existing greeting")

    def fail(text, filename, **options):
        Path(filename).write_bytes(b"partial audio")
        raise RuntimeError("Speech engine failed")

    monkeypatch.setattr(android_tts, "synthesize", fail)
    with pytest.raises(RuntimeError, match="Speech engine failed"):
        manager.generate_greeting("Hello")
    assert greeting.read_bytes() == b"existing greeting"
    assert not Path(manager.greetings_dir, "greeting.wav").exists()


def test_desktop_keeps_espeak_provider(manager, monkeypatch):
    monkeypatch.setattr(android_tts, "_is_chaquopy_android", lambda: False)
    manager.has_espeak = True
    assert manager.get_tts_status() == {
        "has_tts": True,
        "tts_provider": "espeak",
        "tts_supports_word_gap": True,
    }


def test_failed_encoding_preserves_previous_greeting(manager, monkeypatch):
    from meshchatnext.src.backend import voicemail_manager

    greeting = Path(manager.greetings_dir, "greeting.opus")
    greeting.write_bytes(b"previous greeting")

    def fail(source, destination):
        Path(destination).write_bytes(b"partial opus")
        raise RuntimeError("Encoder failed")

    monkeypatch.setattr(voicemail_manager.audio_codec, "encode_audio_to_ogg_opus", fail)
    with pytest.raises(RuntimeError, match="Encoder failed"):
        manager.convert_to_greeting("input.wav")
    assert greeting.read_bytes() == b"previous greeting"
    assert sorted(p.name for p in Path(manager.greetings_dir).iterdir()) == [
        "greeting.opus"
    ]
