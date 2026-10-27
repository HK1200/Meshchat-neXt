import sys

from meshchatnext.src.backend import host_audio_probe as probe


def test_native_abort_is_contained_in_child(monkeypatch):
    monkeypatch.setattr(
        probe,
        "_probe_command",
        lambda: [
            sys.executable,
            "-c",
            "import resource,os;resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.abort()",
        ],
    )
    assert probe.host_audio_unavailable() is True


def test_stalled_native_probe_is_bounded(monkeypatch):
    monkeypatch.setattr(
        probe,
        "_probe_command",
        lambda: [sys.executable, "-c", "import time;time.sleep(30)"],
    )
    assert probe.host_audio_unavailable(timeout=0.05) is True


def test_successful_probe_keeps_host_audio(monkeypatch):
    monkeypatch.setattr(
        probe,
        "_probe_command",
        lambda: [sys.executable, "-c", "raise SystemExit(0)"],
    )
    assert probe.host_audio_unavailable() is False


def test_frozen_probe_uses_existing_executable_and_module_dispatch(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/Meshchat neXt/backend/MeshchatNext")
    assert probe._probe_command() == [
        "/opt/Meshchat neXt/backend/MeshchatNext",
        "--meshchatnext-run-module",
        probe.MODULE,
    ]
