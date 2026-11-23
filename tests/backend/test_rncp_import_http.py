# SPDX-License-Identifier: 0BSD
"""Actual multipart import and guarded transfer/delete HTTP contracts."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import FormData, web
from aiohttp.test_utils import TestClient, TestServer

from meshchatnext.src.backend.http.routes.rn_tools import register_rn_tools_routes
from tests.backend.api_json_contract_schemas import assert_matches_schema
from tests.backend.http_api_response_schemas import RNCP_UPLOADS_SCHEMA


def application(folder, sender, *, backend=None):
    async def broadcast(_message):
        return None

    backend = backend or SimpleNamespace(
        rncp_handler=SimpleNamespace(storage_dir=str(folder), send_file=sender),
        _broadcast_websocket_message=broadcast,
    )
    routes = web.RouteTableDef()
    register_rn_tools_routes(routes, backend)
    app = web.Application()
    app.add_routes(routes)
    return app


@pytest.mark.asyncio
async def test_real_multipart_stream_survives_restart_and_delete_waits_for_transfer(
    tmp_path,
):
    payload = b"private selected file\x00" * 100000
    entered, release = asyncio.Event(), asyncio.Event()

    async def sender(**kwargs):
        assert Path(kwargs["file_path"]).read_bytes() == payload
        entered.set()
        await release.wait()
        return {"status": "completed", "transfer_id": "private-transfer"}

    async with TestClient(TestServer(application(tmp_path, sender))) as client:
        form = FormData()
        form.add_field(
            "file",
            payload,
            filename="chosen.bin",
            content_type="application/octet-stream",
        )
        response = await client.post("/api/v1/rncp/upload", data=form)
        assert response.status == 200, await response.text()
        record = await response.json()
        assert record["size"] == len(payload)
        assert Path(record["file_path"]).read_bytes() == payload
        listed = await client.get("/api/v1/rncp/uploads")
        body = await listed.json()
        assert_matches_schema(body, RNCP_UPLOADS_SCHEMA)
        assert body["files"] == [record]
    # A fresh app/store must reconstruct the imported file and fence deletion
    # before the send starts pathfinding, even without opening the imports list.
    async with TestClient(TestServer(application(tmp_path, sender))) as client:
        operation = asyncio.create_task(
            client.post(
                "/api/v1/rncp/send",
                json={"destination_hash": "12" * 16, "file_path": record["file_path"]},
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 3)
            response = await client.delete("/api/v1/rncp/uploads/" + record["id"])
            assert response.status == 409
            assert Path(record["file_path"]).read_bytes() == payload
        finally:
            release.set()
        response = await operation
        assert response.status == 200, await response.text()
        response = await client.delete("/api/v1/rncp/uploads/" + record["id"])
        assert response.status == 200
        response = await client.get("/api/v1/rncp/uploads")
        assert response.headers["Cache-Control"] == "no-store"
        body = await response.json()
        assert_matches_schema(body, RNCP_UPLOADS_SCHEMA)
        assert body["files"] == []


@pytest.mark.asyncio
async def test_invalid_imports_and_identifiers_cannot_select_server_files(tmp_path):
    async def sender(**_kwargs):
        raise AssertionError("Invalid upload must never start a transfer")

    outside = tmp_path / "keep-private"
    outside.write_bytes(b"preserve")
    async with TestClient(TestServer(application(tmp_path, sender))) as client:
        response = await client.post(
            "/api/v1/rncp/upload", json={"file_path": str(outside)}
        )
        assert response.status == 400
        form = FormData(quote_fields=False)
        form.add_field("file", b"new bytes", filename="../keep-private")
        response = await client.post("/api/v1/rncp/upload", data=form)
        assert response.status == 400
        response = await client.delete("/api/v1/rncp/uploads/not-a-valid-import")
        assert response.status == 400
    assert outside.read_bytes() == b"preserve"


@pytest.mark.asyncio
async def test_identity_switch_keeps_the_active_import_lease(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    async def sender(**_kwargs):
        entered.set()
        await release.wait()
        return {"status": "completed", "transfer_id": "private-transfer"}

    async def broadcast(_message):
        pass

    first = SimpleNamespace(storage_dir=str(tmp_path / "first"), send_file=sender)
    second = SimpleNamespace(storage_dir=str(tmp_path / "second"), send_file=sender)
    backend = SimpleNamespace(
        rncp_handler=first, _broadcast_websocket_message=broadcast
    )
    async with TestClient(
        TestServer(application(tmp_path, sender, backend=backend))
    ) as client:
        form = FormData()
        form.add_field("file", b"private selected bytes", filename="first.bin")
        response = await client.post("/api/v1/rncp/upload", data=form)
        assert response.status == 200
        record = await response.json()
        pending = asyncio.create_task(
            client.post(
                "/api/v1/rncp/send",
                json={"destination_hash": "12" * 16, "file_path": record["file_path"]},
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 3)
            backend.rncp_handler = second
            response = await client.get("/api/v1/rncp/uploads")
            assert (await response.json())["files"] == []
            backend.rncp_handler = first
            response = await client.delete("/api/v1/rncp/uploads/" + record["id"])
            assert response.status == 409
        finally:
            backend.rncp_handler = first
            release.set()
            await pending
        response = await client.delete("/api/v1/rncp/uploads/" + record["id"])
        assert response.status == 200


def test_http_selected_file_delivers_all_standard_resource_segments(tmp_path):
    import json
    import subprocess
    import sys

    helper = Path(__file__).with_name("rncp_segment_wire_fixture.py")
    folder = tmp_path / "http-import-wire"
    result = subprocess.run(
        [sys.executable, str(helper), str(folder), "--http-import"],
        capture_output=True,
        text=True,
        timeout=70,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    proof = json.loads((folder / "proof.json").read_text())
    assert proof["all_segments_received"]
    assert proof["http_import_and_send"]
    assert proof["imported_copy_removed"]
    assert proof["file_bytes"] == 2 * 1024 * 1024
    assert proof["final_progress"] == 1.0
