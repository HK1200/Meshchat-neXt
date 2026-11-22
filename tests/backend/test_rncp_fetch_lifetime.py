# SPDX-License-Identifier: 0BSD
from functools import wraps
from types import MethodType
from unittest.mock import MagicMock

import pytest

from meshchatnext.src.backend.rncp_handler import RNCPHandler
from tests.backend.rncp_lifetime_fixture import exercise


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.asyncio
async def test_fetch_deadline_only_limits_waiting_for_resource_start(
    tmp_path, monkeypatch, started, wrapped
):
    handler = RNCPHandler(MagicMock(), MagicMock(), str(tmp_path / "storage"))
    if wrapped:
        original = RNCPHandler.fetch_file

        @wraps(original)
        async def instrumented(*args, **kwargs):
            return await original(*args, **kwargs)

        handler.fetch_file = MethodType(instrumented, handler)
    if started:
        await exercise(handler, monkeypatch, tmp_path, started=True)
    else:
        with pytest.raises(TimeoutError, match="waiting for remote resource"):
            await exercise(handler, monkeypatch, tmp_path, started=False)
