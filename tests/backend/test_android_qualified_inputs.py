"""Qualified native archives are checked completely before changing a build tree."""

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "qualified",
    Path(__file__).parents[2] / "scripts/android/restore-qualified-inputs.py",
)
qualified = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualified)


def archive(tmp_path, entries):
    path = tmp_path / "inputs.tar.xz"
    with tarfile.open(path, "w:xz") as output:
        for name, body in entries:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            output.addfile(member, io.BytesIO(body))
    return path, {
        "size": path.stat().st_size,
        "sha256": qualified.sha(path),
        "files": {n: hashlib.sha256(b).hexdigest() for n, b in entries},
    }


def test_restore_exact_inputs_is_idempotent(tmp_path):
    p, meta = archive(tmp_path, [("android/vendor/library.whl", b"verified bytes")])
    dest = tmp_path / "tree"
    qualified.install_archive(p, dest, meta)
    first = (dest / "android/vendor/library.whl").stat().st_mtime_ns
    qualified.install_archive(p, dest, meta)
    assert (dest / "android/vendor/library.whl").read_bytes() == b"verified bytes"
    assert (dest / "android/vendor/library.whl").stat().st_mtime_ns == first


@pytest.mark.parametrize("bad", ["digest", "inventory", "duplicate", "path", "symlink"])
def test_untrusted_archive_never_writes_inputs(tmp_path, bad):
    entries = [("android/vendor/library.whl", b"bytes")]
    if bad == "duplicate":
        entries *= 2
    if bad == "path":
        entries = [("android/vendor/../../outside", b"bytes")]
    p, meta = archive(tmp_path, entries)
    if bad == "digest":
        meta["sha256"] = "0" * 64
    if bad == "inventory":
        meta["files"]["android/vendor/missing.whl"] = "0" * 64
    dest = tmp_path / "tree"
    if bad == "symlink":
        with tarfile.open(p, "w:xz") as output:
            item = tarfile.TarInfo("android/vendor/library.whl")
            item.type = tarfile.SYMTYPE
            item.linkname = "../../outside"
            output.addfile(item)
        meta["size"] = p.stat().st_size
        meta["sha256"] = qualified.sha(p)
    with pytest.raises(ValueError):
        qualified.install_archive(p, dest, meta)
    assert not dest.exists()


def test_different_existing_input_preserved_and_no_partial_restore(tmp_path):
    p, meta = archive(
        tmp_path, [("android/vendor/a.whl", b"new"), ("android/vendor/z.whl", b"other")]
    )
    dest = tmp_path / "tree"
    target = dest / "android/vendor/z.whl"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(ValueError, match="Existing input differs"):
        qualified.install_archive(p, dest, meta)
    assert target.read_bytes() == b"existing"
    assert not (dest / "android/vendor/a.whl").exists()


def test_existing_directory_symlink_cannot_redirect_installs(tmp_path):
    p, meta = archive(tmp_path, [("android/vendor/a.whl", b"new")])
    dest = tmp_path / "tree"
    (dest / "elsewhere").mkdir(parents=True)
    (dest / "android").symlink_to(dest / "elsewhere", target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe existing destination"):
        qualified.install_archive(p, dest, meta)
    assert not list((dest / "elsewhere").iterdir())
