# SPDX-License-Identifier: 0BSD
"""File chooser imports must never become arbitrary server-file access."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from meshchatnext.src.backend import rncp_uploads as module
from meshchatnext.src.backend.http.uploads import PayloadTooLargeError


class Field:
    def __init__(self, name="chosen.bin", chunks=(b"private selected bytes",)):
        self.filename = name
        self.chunks = iter(chunks)

    async def read_chunk(self, _size):
        return next(self.chunks, b"")


@pytest.mark.asyncio
async def test_streamed_copy_is_private_distinct_and_not_remotely_shared(tmp_path):
    store = module.RNCPUploads(tmp_path)
    first = await store.import_field(Field())
    second = await store.import_field(Field())
    assert first["id"] != second["id"]
    for record in (first, second):
        path = Path(record["file_path"])
        assert path.read_bytes() == b"private selected bytes"
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    assert not (tmp_path / "rncp_shared").exists()
    assert len(store.list()) == 2
    store.delete(first["id"])
    assert store.list() == [second]
    assert Path(second["file_path"]).read_bytes() == b"private selected bytes"


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        ".part",
        "../identity",
        "/etc/passwd",
        "a\\b",
        "a:b",
        "a\x00b",
        "x" * 241,
        "hidden.",
    ],
)
@pytest.mark.asyncio
async def test_bad_names_do_not_create_files(tmp_path, name):
    store = module.RNCPUploads(tmp_path)
    with pytest.raises(ValueError):
        await store.import_field(Field(name))
    assert not store.root.exists()


@pytest.mark.asyncio
async def test_oversize_and_cancellation_remove_only_the_incomplete_copy(
    tmp_path, monkeypatch
):
    store = module.RNCPUploads(tmp_path)
    original = await store.import_field(Field())
    monkeypatch.setattr(module, "MAX_FILE_BYTES", 3)
    with pytest.raises(PayloadTooLargeError):
        await store.import_field(Field(chunks=(b"too large",)))
    assert store.list() == [original]
    entered = asyncio.Event()

    class Blocking(Field):
        async def read_chunk(self, _size):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(store.import_field(Blocking()))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.list() == [original]
    assert len(list(store.root.iterdir())) == 1


@pytest.mark.asyncio
async def test_leases_cover_pathfinding_relative_paths_and_aliases(tmp_path):
    store = module.RNCPUploads(tmp_path)
    record = await store.import_field(Field())
    relative = str(Path(record["file_path"]).relative_to(tmp_path))
    with store.lease(relative):
        with store.lease(record["file_path"]):
            with pytest.raises(module.ImportBusyError):
                store.delete(record["id"])
        with pytest.raises(module.ImportBusyError):
            store.delete(record["id"])
    store.delete(record["id"])
    assert store.list() == []


@pytest.mark.asyncio
async def test_storage_quota_preserves_the_existing_import(tmp_path, monkeypatch):
    store = module.RNCPUploads(tmp_path)
    monkeypatch.setattr(module, "MAX_TOTAL_BYTES", 4)
    first = await store.import_field(Field(chunks=(b"123",)))
    with pytest.raises(PayloadTooLargeError):
        await store.import_field(Field(chunks=(b"45",)))
    assert store.list() == [first]
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=module.FREE_RESERVE_BYTES),
    )
    with pytest.raises(OSError):
        await store.import_field(Field())
    assert store.list() == [first]


@pytest.mark.asyncio
async def test_interrupted_copy_can_be_removed_after_restart(tmp_path):
    store = module.RNCPUploads(tmp_path)
    folder = store.root / ("a" * 32)
    folder.mkdir(parents=True)
    (folder / ".part").write_bytes(b"incomplete")
    record = store.list()[0]
    assert record["incomplete"] and record["file_path"] is None
    store.delete(record["id"])
    assert store.list() == []


def test_symlinked_root_and_unmanaged_files_are_never_followed_or_removed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    private = outside / "keep"
    private.write_bytes(b"preserve")
    store = module.RNCPUploads(tmp_path)
    try:
        store.root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    with pytest.raises(PermissionError):
        store.list()
    assert private.read_bytes() == b"preserve"
