# SPDX-License-Identifier: 0BSD

"""Exercise the worker build gate without spawning or importing native audio."""

import importlib
import multiprocessing
import sys
from pathlib import Path
from types import ModuleType

import pytest

from meshchatnext.src.backend import frozen_freeze_probe as probe


@pytest.mark.parametrize("mode", ["success", "bad-result", "timeout"])
def test_worker_probe_requires_spawn_result_and_deadline(monkeypatch, capsys, mode):
    target = importlib.import_module("LXMF.LXStamper").validate_pn_stamp
    calls = []
    monkeypatch.setitem(sys.modules, "LXST", ModuleType("LXST"))
    monkeypatch.setitem(sys.modules, "aiohttp", ModuleType("aiohttp"))
    monkeypatch.setattr(probe.sys, "platform", "synthetic-worker-test")
    monkeypatch.setattr(
        probe, "_lxst_filterlib_path", lambda: Path("/synthetic/filterlib.so")
    )

    class Result:
        def get(self, timeout):
            calls.append(("deadline", timeout))
            if mode == "timeout":
                raise TimeoutError("synthetic worker timeout")
            return (None, None, None, None) if mode == "success" else ("unexpected",)

    class Pool:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, _value, _traceback):
            calls.append(("closed", exc_type))
            return False

        def apply_async(self, function, args):
            calls.append(("task", function, args))
            return Result()

    class Context:
        def Pool(self, size):
            calls.append(("pool", size))
            return Pool()

    def context(method):
        calls.append(("context", method))
        return Context()

    monkeypatch.setattr(multiprocessing, "get_context", context)
    if mode == "success":
        probe.main()
        assert "frozen-freeze-probe ok" in capsys.readouterr().out
    else:
        expected = TimeoutError if mode == "timeout" else SystemExit
        with pytest.raises(expected):
            probe.main()
        assert "frozen-freeze-probe ok" not in capsys.readouterr().out
    assert calls == [
        ("context", "spawn"),
        ("pool", 1),
        ("task", target, (b"short", 1)),
        ("deadline", 15),
        ("closed", TimeoutError if mode == "timeout" else None),
    ]
