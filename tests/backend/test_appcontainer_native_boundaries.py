import ctypes
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from meshchatnext.src.backend import appcontainer_security as security
from meshchatnext.src.backend import appcontainer_temp as private_temp


class Call:
    def __init__(self, callback):
        self.callback = callback
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


def native_error(code):
    return OSError(code, "native failure")


@pytest.mark.parametrize(
    "mode",
    ["success", "open-denied", "query-size-denied", "query-denied", "convert-denied"],
)
def test_token_reads_use_real_native_identity_and_release_handles(monkeypatch, mode):
    def open_token(process, rights, output):
        assert process == 100 and rights == 8
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(101)
        return mode != "open-denied"

    def query(token, kind, buffer, size, needed):
        assert token.value == 101 and kind == 31
        ctypes.cast(needed, ctypes.POINTER(ctypes.c_ulong))[0] = (
            0 if mode == "query-size-denied" else ctypes.sizeof(ctypes.c_void_p)
        )
        if buffer is None:
            return 0
        if mode == "query-denied":
            return 0
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(102)
        return 1

    sid_holder = ctypes.create_unicode_buffer("S-1-15-2-123")

    def convert(sid, output):
        assert sid.value == 102
        if mode == "convert-denied":
            return 0
        ctypes.cast(output, ctypes.POINTER(ctypes.c_wchar_p))[0] = ctypes.cast(
            sid_holder, ctypes.c_wchar_p
        )
        return 1

    kernel = SimpleNamespace(
        GetCurrentProcess=Call(lambda: 100),
        CloseHandle=Call(lambda h: 1),
        LocalFree=Call(lambda h: None),
    )
    advapi = SimpleNamespace(
        OpenProcessToken=Call(open_token),
        GetTokenInformation=Call(query),
        ConvertSidToStringSidW=Call(convert),
    )
    monkeypatch.setattr(security, "_kernel", lambda: kernel)
    monkeypatch.setattr(
        security.ctypes, "WinDLL", lambda *a, **kw: advapi, raising=False
    )
    monkeypatch.setattr(security.ctypes, "WinError", native_error, raising=False)
    monkeypatch.setattr(security.ctypes, "get_last_error", lambda: 5, raising=False)
    if mode == "success":
        assert security.token_sid(31) == "S-1-15-2-123"
        assert len(kernel.LocalFree.calls) == 1
    else:
        with pytest.raises(OSError):
            security.token_sid(31)
        assert not kernel.LocalFree.calls
    assert len(kernel.CloseHandle.calls) == (0 if mode == "open-denied" else 1)


@pytest.mark.parametrize(
    "sid,expected", [("S-1-15-2-123", True), ("S-1-5-21-123", False), (None, False)]
)
def test_attestation_does_not_accept_environment_markers(monkeypatch, sid, expected):
    monkeypatch.setenv("MESHCHAT_APPCONTAINER_CHILD", "1")
    monkeypatch.setattr(security, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(security, "token_sid", lambda _: sid)
    assert security.is_appcontainer_process() is expected


def test_attestation_native_failure_is_not_active(monkeypatch):
    monkeypatch.setattr(security, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        security, "token_sid", Mock(side_effect=OSError("token denied"))
    )
    assert not security.is_appcontainer_process()


@pytest.mark.parametrize("mode", ["success", "convert-denied", "create-denied"])
def test_private_mkdir_uses_only_explicit_user_container_system_admin_sids(
    monkeypatch, mode
):
    original = Mock()
    fake_os = SimpleNamespace(
        name="nt", mkdir=original, fsdecode=os.fsdecode, fspath=os.fspath
    )
    original._meshchat_container_private = False
    audit = Mock()
    monkeypatch.setattr(private_temp, "os", fake_os)
    monkeypatch.setattr(private_temp, "sys", SimpleNamespace(audit=audit))
    monkeypatch.setattr(
        private_temp,
        "token_sid",
        lambda kind: "S-1-15-2-123" if kind == 31 else "S-1-5-21-456",
    )
    descriptors = []

    def convert(text, revision, output, unused):
        descriptors.append(text)
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(42)
        return mode != "convert-denied"

    create = Call(lambda path, attributes: mode != "create-denied")
    free = Call(lambda handle: None)
    adv = SimpleNamespace(
        ConvertStringSecurityDescriptorToSecurityDescriptorW=Call(convert)
    )
    kernel = SimpleNamespace(CreateDirectoryW=create, LocalFree=free)
    monkeypatch.setattr(
        private_temp.ctypes,
        "WinDLL",
        lambda name, **kw: adv if name == "advapi32" else kernel,
        raising=False,
    )
    monkeypatch.setattr(private_temp.ctypes, "WinError", native_error, raising=False)
    monkeypatch.setattr(private_temp.ctypes, "get_last_error", lambda: 5, raising=False)
    assert private_temp.install_private_directory_compat()
    installed = fake_os.mkdir
    assert (
        private_temp.install_private_directory_compat() and fake_os.mkdir is installed
    )
    installed("ordinary", 0o755)
    installed("relative", 0o700, dir_fd=3)
    assert original.call_args_list[0].args == ("ordinary", 0o755)
    assert original.call_args_list[1].kwargs == {"dir_fd": 3}
    if mode == "success":
        installed("private", 0o700)
    else:
        with pytest.raises(OSError):
            installed("private", 0o700)
    assert descriptors == [
        "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;S-1-5-21-456)(A;OICI;FA;;;S-1-15-2-123)"
    ]
    assert len(free.calls) == (0 if mode == "convert-denied" else 1)
    before = len(create.calls)
    with pytest.raises(ValueError, match="null"):
        installed("bad\0path", 0o700)
    assert len(create.calls) == before
    audit.assert_any_call("os.mkdir", "private", 0o700, -1)


@pytest.mark.parametrize("sid", ["S-1-5-21-456", "", None])
def test_private_mkdir_leaves_non_container_tokens_unchanged(monkeypatch, sid):
    original = Mock()
    monkeypatch.setattr(private_temp, "os", SimpleNamespace(name="nt", mkdir=original))
    monkeypatch.setattr(private_temp, "token_sid", lambda kind: sid)
    if sid is None:
        # A malformed token must not be accepted as an AppContainer.
        monkeypatch.setattr(
            private_temp, "token_sid", Mock(side_effect=OSError("token unavailable"))
        )
    assert not private_temp.install_private_directory_compat()
    assert private_temp.os.mkdir is original


@pytest.mark.parametrize(
    "mode", ["success", "derive-denied", "wrong-count", "empty-sid"]
)
def test_named_capability_sid_copies_owned_buffer_and_frees_native_arrays(
    monkeypatch, mode
):
    from meshchatnext.src.backend import appcontainer_sandbox as sandbox

    sid_bytes = ctypes.create_string_buffer(b"valid-sid-bytes")
    groups = (ctypes.c_void_p * 1)(ctypes.addressof(sid_bytes))
    caps = (ctypes.c_void_p * 1)(ctypes.addressof(sid_bytes))
    pointer_array = ctypes.POINTER(ctypes.c_void_p)

    def derive(name, groups_out, group_count, caps_out, cap_count):
        assert name == "registryRead"
        ctypes.cast(groups_out, ctypes.POINTER(pointer_array))[0] = ctypes.cast(
            groups, pointer_array
        )
        ctypes.cast(caps_out, ctypes.POINTER(pointer_array))[0] = ctypes.cast(
            caps, pointer_array
        )
        ctypes.cast(group_count, ctypes.POINTER(ctypes.c_ulong))[0] = 1
        ctypes.cast(cap_count, ctypes.POINTER(ctypes.c_ulong))[0] = (
            0 if mode == "wrong-count" else 1
        )
        return mode != "derive-denied"

    api = SimpleNamespace(DeriveCapabilitySidsFromName=Call(derive))
    adv = SimpleNamespace(
        GetLengthSid=Call(
            lambda sid: 0 if mode == "empty-sid" else ctypes.sizeof(sid_bytes)
        )
    )
    monkeypatch.setattr(
        sandbox.ctypes,
        "WinDLL",
        lambda name, **kw: api if name == "kernelbase" else adv,
        raising=False,
    )
    monkeypatch.setattr(sandbox.ctypes, "WinError", native_error, raising=False)
    monkeypatch.setattr(sandbox.ctypes, "get_last_error", lambda: 5, raising=False)
    free = Mock()
    monkeypatch.setattr(sandbox, "_local_free", free)
    if mode == "success":
        owned = sandbox._named_capability_sid("registryRead")
        assert owned.value != ctypes.addressof(sid_bytes)
        assert ctypes.string_at(owned, ctypes.sizeof(sid_bytes)) == sid_bytes.raw
    else:
        with pytest.raises(OSError):
            sandbox._named_capability_sid("registryRead")
    # Each array and every populated SID are released on success and failure.
    assert free.call_count == (3 if mode == "wrong-count" else 4)


@pytest.mark.parametrize("mode", ["success", "open-denied", "set-denied"])
def test_ancestor_dacl_update_never_walks_children_and_closes_handle(monkeypatch, mode):
    from meshchatnext.src.backend import appcontainer_sandbox as sandbox

    create = Call(lambda *args: None if mode == "open-denied" else 42)
    close = Call(lambda handle: 1)
    setter = Call(lambda *args: 5 if mode == "set-denied" else 0)
    kernel = SimpleNamespace(CreateFileW=create, CloseHandle=close)
    adv = SimpleNamespace(SetSecurityInfo=setter)
    monkeypatch.setattr(
        sandbox.ctypes,
        "WinDLL",
        lambda name, **kw: kernel if name == "kernel32" else adv,
        raising=False,
    )
    monkeypatch.setattr(sandbox.ctypes, "WinError", native_error, raising=False)
    monkeypatch.setattr(sandbox.ctypes, "get_last_error", lambda: 5, raising=False)
    if mode == "open-denied":
        with pytest.raises(OSError):
            sandbox._set_directory_dacl_without_propagation("parent-only", 100)
        assert not setter.calls and not close.calls
    else:
        assert sandbox._set_directory_dacl_without_propagation("parent-only", 100) == (
            5 if mode == "set-denied" else 0
        )
        assert setter.calls == [
            (
                42,
                sandbox._SE_FILE_OBJECT,
                sandbox._DACL_SECURITY_INFORMATION,
                None,
                None,
                100,
                None,
            )
        ]
        assert close.calls == [(42,)]
    assert create.calls == [("parent-only", 0x02000000, 7, None, 3, 0x02000000, None)]
