# SPDX-License-Identifier: 0BSD
"""A segment proof is not the conclusion of a segmented Resource transfer."""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from meshchatnext.src.backend import rncp_handler as module


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["complete", "failed", "cancel", "immediate"])
async def test_first_segment_proof_does_not_finish_or_bypass_cancel(
    tmp_path, monkeypatch, terminal
):
    complete, failed = module.RNS.Resource.COMPLETE, module.RNS.Resource.FAILED
    active = module.RNS.Link.ACTIVE
    outgoing, single = module.RNS.Destination.OUT, module.RNS.Destination.SINGLE
    calls = []
    link = SimpleNamespace(status=active, identify=MagicMock(), teardown=MagicMock())

    class Link:
        ACTIVE = active

        def __new__(cls, *_):
            return link

    class Resource:
        COMPLETE, FAILED = complete, failed

        def __init__(self, handle, _link, **options):
            self.hash = bytes.fromhex("12" * 32)
            self.status = complete  # Only the first segment has its proof.
            self.total_size = 123
            self.get_progress = lambda: 1.0 if terminal == "immediate" else 1 / 3
            calls.append((self, handle, options))
            if terminal == "immediate":
                options["callback"](self)

    monkeypatch.setattr(module.RNS, "Link", Link)
    monkeypatch.setattr(module.RNS, "Resource", Resource)
    monkeypatch.setattr(module.RNS.Transport, "has_path", lambda *_: True)
    monkeypatch.setattr(module.RNS.Identity, "recall", lambda *_: object())

    class Destination:
        OUT, SINGLE = outgoing, single

        def __new__(cls, *_):
            return object()

    monkeypatch.setattr(module.RNS, "Destination", Destination)
    monkeypatch.setattr(module, "link_establishment_window", lambda *_: 1)
    monkeypatch.setattr(module.traffic_stats, "get_meter", lambda: MagicMock())
    handler = module.RNCPHandler(MagicMock(), object(), str(tmp_path))
    monkeypatch.setattr(handler, "_path_wait_seconds", lambda *_: 1)
    source = tmp_path / "selected.bin"
    source.write_bytes(b"Private segmented-transfer fixture")
    started = asyncio.Event()
    task = asyncio.create_task(
        handler.send_file(
            bytes.fromhex("34" * 16),
            str(source),
            on_transfer_started=lambda _: started.set(),
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 2)
        if terminal == "immediate":
            result = await asyncio.wait_for(task, 2)
            assert result["status"] == "completed"
            link.teardown.assert_called_once()
            assert handler.active_transfers["12" * 32]["status"] == "completed"
            return
        await asyncio.sleep(0.01)
        assert not task.done(), "First segment proof closed the complete file transfer"
        link.teardown.assert_not_called()
        assert handler.active_transfers["12" * 32]["status"] == "sending"
        if terminal == "cancel":
            handler.cancel_transfer("12" * 32)
            with pytest.raises(InterruptedError, match="cancelled"):
                await asyncio.wait_for(task, 2)
        else:
            final = SimpleNamespace(
                status=complete if terminal == "complete" else failed,
                total_size=123,
                get_progress=lambda: 1.0,
            )
            calls[0][2]["callback"](final)
            if terminal == "complete":
                result = await asyncio.wait_for(task, 2)
                assert result["status"] == "completed"
            else:
                with pytest.raises(Exception, match="Transfer failed"):
                    await asyncio.wait_for(task, 2)
        link.teardown.assert_called_once()
        assert (
            handler.active_transfers["12" * 32]["status"]
            == {"complete": "completed", "failed": "failed", "cancel": "cancelled"}[
                terminal
            ]
        )
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task
        for _, handle, _ in calls:
            handle.close()


def test_real_standard_resource_delivers_every_segment(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    helper = Path(__file__).with_name("rncp_segment_wire_fixture.py")
    folder = tmp_path / "private-wire"
    result = subprocess.run(
        [sys.executable, str(helper), str(folder)],
        capture_output=True,
        text=True,
        timeout=70,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    proof = json.loads((folder / "proof.json").read_text())
    assert proof["all_segments_received"]
    assert proof["file_bytes"] == 2 * 1024 * 1024
    assert proof["final_progress"] == 1.0
