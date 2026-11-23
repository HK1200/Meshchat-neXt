# SPDX-License-Identifier: 0BSD
"""Cancellation must not leak partial files or close an in-flight write."""

import asyncio
import os
import threading

import pytest

from meshchatnext.src.backend.http import uploads


@pytest.mark.asyncio
async def test_canceled_reader_removes_partial_file_and_closes_descriptor(tmp_path):
    entered = asyncio.Event()

    class Reader:
        async def read_chunk(self, _size):
            entered.set()
            await asyncio.Event().wait()

    target = tmp_path / "partial.bin"
    task = asyncio.create_task(uploads.write_field_to_path(Reader(), target, 100))
    await asyncio.wait_for(entered.wait(), 2)
    assert target.exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not target.exists()


@pytest.mark.asyncio
async def test_cancel_waits_for_current_write_before_closing_and_unlinking(
    tmp_path, monkeypatch
):
    target = tmp_path / "inflight.bin"
    entered, release = threading.Event(), threading.Event()
    captured = {"fd": None, "closed_while_writing": False}
    original_open, original_fdopen = os.open, os.fdopen

    def open_file(path, *args, **kwargs):
        descriptor = original_open(path, *args, **kwargs)
        if path == target:
            captured["fd"] = descriptor
        return descriptor

    class Handle:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, *args):
            captured["closed_while_writing"] = not release.is_set()
            return self.wrapped.__exit__(*args)

        def write(self, chunk):
            entered.set()
            assert release.wait(3), "Private write fixture did not release"
            if self.wrapped.closed:
                return len(chunk)
            return self.wrapped.write(chunk)

    def fdopen(descriptor, *args, **kwargs):
        handle = original_fdopen(descriptor, *args, **kwargs)
        return Handle(handle) if descriptor == captured["fd"] else handle

    monkeypatch.setattr(uploads.os, "open", open_file)
    monkeypatch.setattr(uploads.os, "fdopen", fdopen)

    class Reader:
        async def read_chunk(self, _size):
            return b"private bytes"

    task = asyncio.create_task(uploads.write_field_to_path(Reader(), target, 100))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.03)
        assert not done
        assert not captured["closed_while_writing"]
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not captured["closed_while_writing"]
    assert not target.exists()
    with pytest.raises(OSError):
        os.fstat(captured["fd"])
