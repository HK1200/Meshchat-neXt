from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from meshchatnext.src.backend import appcontainer_paths as paths


class NativeCall:
    def __init__(self, callback):
        self.callback = callback
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


def access_error(code=5):
    error = OSError("Native operation denied")
    error.winerror = code
    return error


def install(monkeypatch, original):
    original._meshchat_container_canonical = False
    monkeypatch.setattr(paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(paths, "is_appcontainer_process", lambda: True)
    monkeypatch.setattr(paths.ntpath, "_getfinalpathname", original, raising=False)
    assert paths.install_private_path_compat()
    return paths.ntpath._getfinalpathname


def test_normal_process_path_behavior_unchanged(monkeypatch):
    monkeypatch.setattr(paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(paths, "is_appcontainer_process", lambda: False)
    original = Mock()
    monkeypatch.setattr(paths.ntpath, "_getfinalpathname", original, raising=False)
    assert not paths.install_private_path_compat()
    assert paths.ntpath._getfinalpathname is original


def test_non_windows_does_not_query_token(monkeypatch):
    monkeypatch.setattr(paths, "os", SimpleNamespace(name="posix"))
    token = Mock(side_effect=AssertionError("must not query Windows token"))
    monkeypatch.setattr(paths, "is_appcontainer_process", token)
    assert not paths.install_private_path_compat()
    token.assert_not_called()


def test_missing_native_resolver_fails_closed(monkeypatch):
    monkeypatch.setattr(paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(paths, "is_appcontainer_process", lambda: True)
    monkeypatch.setattr(paths.ntpath, "_getfinalpathname", None, raising=False)
    with pytest.raises(RuntimeError, match="unavailable"):
        paths.install_private_path_compat()


def test_native_success_and_idempotence(monkeypatch):
    original = Mock(return_value="canonical DOS path")
    resolver = install(monkeypatch, original)
    assert resolver("input") == "canonical DOS path"
    assert paths.install_private_path_compat()
    assert paths.ntpath._getfinalpathname is resolver
    original.assert_called_once_with("input")


@pytest.mark.parametrize("code", [2, 3, 32])
def test_other_native_errors_not_hidden(monkeypatch, code):
    error = access_error(code)
    resolver = install(monkeypatch, Mock(side_effect=error))
    fallback = Mock(side_effect=AssertionError("must not fall back"))
    monkeypatch.setattr(paths, "_final_nt_path", fallback)
    with pytest.raises(OSError) as caught:
        resolver("missing-or-locked")
    assert caught.value is error
    fallback.assert_not_called()


def test_access_denied_requires_handle_resolution(monkeypatch):
    resolver = install(monkeypatch, Mock(side_effect=access_error()))
    fallback = Mock(return_value=r"\\?\GLOBALROOT\Device\HarddiskVolume1\public")
    monkeypatch.setattr(paths, "_final_nt_path", fallback)
    assert resolver("public") == fallback.return_value
    fallback.assert_called_once_with("public")
    fallback.side_effect = access_error()
    with pytest.raises(OSError):
        resolver("outside-denied")


@pytest.mark.parametrize("as_bytes", [False, True])
@pytest.mark.parametrize(
    "mode",
    ["success", "resize", "open-denied", "query-denied", "unexpected", "too-long"],
)
def test_handle_canonicalization_and_cleanup(monkeypatch, mode, as_bytes):
    close = NativeCall(lambda handle: 1)
    create = NativeCall(lambda *args: None if mode == "open-denied" else 123)
    count = 0

    def query(handle, buffer, size, flags):
        nonlocal count
        count += 1
        assert flags == 2
        if mode == "query-denied":
            return 0
        if mode == "too-long":
            return 40000
        if mode == "resize" and count == 1:
            return 700
        buffer.value = (
            "unexpected"
            if mode == "unexpected"
            else r"\Device\HarddiskVolume1\resolved-link-target"
        )
        return len(buffer.value)

    kernel = SimpleNamespace(
        CreateFileW=create,
        GetFinalPathNameByHandleW=NativeCall(query),
        CloseHandle=close,
    )
    monkeypatch.setattr(paths.ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    monkeypatch.setattr(paths.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(
        paths.ctypes, "WinError", lambda code: access_error(code), raising=False
    )
    target = b"input-link" if as_bytes else "input-link"
    expected = r"\\?\GLOBALROOT\Device\HarddiskVolume1\resolved-link-target"
    if mode in ("success", "resize"):
        assert paths._final_nt_path(target) == (
            expected.encode() if as_bytes else expected
        )
    else:
        with pytest.raises(OSError):
            paths._final_nt_path(target)
    # Never request file content, directory listing or writes.
    assert create.calls == [("input-link", 0x80, 7, None, 3, 0x02000000, None)]
    assert close.calls == ([] if mode == "open-denied" else [(123,)])
