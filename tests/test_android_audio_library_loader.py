from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from meshchatnext.android_opus import _OpusLoader


def test_android_loader_finds_both_packaged_audio_libraries(tmp_path, monkeypatch):
    monkeypatch.setenv("MESHCHAT_NATIVE_LIB_DIR", str(tmp_path))
    for name in ["opus", "ogg", "opusfile"]:
        Path(tmp_path, f"lib{name}.so").write_bytes(b"test library")
    original = Mock(return_value="fallback")
    module = SimpleNamespace(Library=SimpleNamespace(load=original))
    library = object()
    load = Mock(return_value=library)
    monkeypatch.setattr("meshchatnext.android_opus.ctypes.CDLL", load)
    _OpusLoader(SimpleNamespace(exec_module=lambda module: None)).exec_module(module)
    for name in ["opus", "ogg", "opusfile"]:
        assert module.Library.load({"external": name}) is library
        assert load.call_args.args == (str(tmp_path / f"lib{name}.so"),)
    assert module.Library.load({"external": "vorbis"}) == "fallback"
