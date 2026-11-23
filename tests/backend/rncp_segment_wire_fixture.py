# SPDX-License-Identifier: 0BSD
"""A private, standard-Reticulum multi-segment RNCP exchange in fresh processes."""

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import RNS

from meshchatnext.src.backend.rncp_handler import RNCPHandler


def network(folder, kind, port):
    folder.mkdir(parents=True)
    endpoint = (
        f"listen_ip = 127.0.0.1\nlisten_port = {port}\n"
        if kind == "TCPServerInterface"
        else f"target_host = 127.0.0.1\ntarget_port = {port}\n"
    )
    (folder / "config").write_text(
        "[reticulum]\nshare_instance = No\nenable_transport = No\n"
        "[interfaces]\n[[Private segmented file]]\n"
        f"type = {kind}\nenabled = Yes\n{endpoint}"
    )
    stack = RNS.Reticulum(configdir=str(folder), loglevel=1)
    for interface in tuple(RNS.Transport.interfaces):
        interface.ingress_control = False
    return stack


async def receive(folder, port, allowed):
    stack = network(folder / "rns", "TCPServerInterface", port)
    handler = RNCPHandler(stack, RNS.Identity(), str(folder / "files"))
    address = handler.setup_receive_destination(allowed_hashes=[allowed])
    (folder / "ready.json").write_text(json.dumps({"address": address}))
    announced = set()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        for interface in tuple(RNS.Transport.interfaces):
            if interface.online and interface.OUT and id(interface) not in announced:
                interface.ingress_control = False
                handler.receive_destination.announce(attached_interface=interface)
                announced.add(id(interface))
        await asyncio.sleep(0.05)


async def send(folder, *, http_import=False):
    identity = RNS.Identity()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (folder / "receiver.log").open("w") as log:
        peer = subprocess.Popen(
            [
                sys.executable,
                __file__,
                str(folder / "receiver"),
                "--port",
                str(port),
                "--allowed",
                identity.hash.hex(),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        proxy = None
        proxy_tasks = set()
        try:
            ready = folder / "receiver/ready.json"
            deadline = time.monotonic() + 10
            while not ready.exists():
                assert peer.poll() is None, "Private receiver exited"
                assert time.monotonic() < deadline, "Private receiver did not start"
                await asyncio.sleep(0.05)
            address = bytes.fromhex(json.loads(ready.read_text())["address"])
            # A fast loopback can finish every segment inside the sender's
            # 100 ms poll. Pace intact TCP bytes so the old first-segment bug
            # cannot pass by winning that race.
            proxy_tasks = set()

            async def relay(reader, writer):
                task = asyncio.current_task()
                proxy_tasks.add(task)
                upstream = None
                flows = []
                try:
                    remote, upstream = await asyncio.open_connection("127.0.0.1", port)

                    async def flow(source, target):
                        while part := await source.read(16 * 1024):
                            await asyncio.sleep(0.005)
                            target.write(part)
                            await target.drain()

                    flows = [
                        asyncio.create_task(flow(reader, upstream)),
                        asyncio.create_task(flow(remote, writer)),
                    ]
                    await asyncio.wait(flows, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for flow_task in flows:
                        flow_task.cancel()
                    await asyncio.gather(*flows, return_exceptions=True)
                    for stream in (writer, upstream):
                        if stream is not None:
                            stream.close()
                            try:
                                await asyncio.wait_for(stream.wait_closed(), 1)
                            except (OSError, TimeoutError):
                                stream.transport.abort()
                    proxy_tasks.discard(task)

            proxy = await asyncio.start_server(relay, "127.0.0.1", 0)
            proxy_port = proxy.sockets[0].getsockname()[1]
            stack = network(folder / "rns", "TCPClientInterface", proxy_port)
            storage = folder / "files"
            storage.mkdir()
            handler = RNCPHandler(stack, identity, str(storage))
            payload = os.urandom(2 * 1024 * 1024)
            assert len(payload) > 2 * RNS.Resource.MAX_EFFICIENT_SIZE
            progress = []
            if http_import:
                from types import SimpleNamespace

                from aiohttp import FormData, web
                from aiohttp.test_utils import TestClient, TestServer

                from meshchatnext.src.backend.async_utils import AsyncUtils
                from meshchatnext.src.backend.http.routes.rn_tools import (
                    register_rn_tools_routes,
                )

                AsyncUtils.set_main_loop(asyncio.get_running_loop())
                final_progress = asyncio.Event()

                async def broadcast(event):
                    if event.get("type") == "rncp.transfer.progress":
                        progress.append(event["progress"])
                        if event["progress"] == 1.0:
                            final_progress.set()

                backend = SimpleNamespace(
                    rncp_handler=handler, _broadcast_websocket_message=broadcast
                )
                routes = web.RouteTableDef()
                register_rn_tools_routes(routes, backend)
                app = web.Application()
                app.add_routes(routes)
                async with TestClient(TestServer(app)) as client:
                    form = FormData()
                    form.add_field(
                        "file",
                        payload,
                        filename="segmented.bin",
                        content_type="application/octet-stream",
                    )
                    response = await client.post("/api/v1/rncp/upload", data=form)
                    assert response.status == 200, await response.text()
                    imported = await response.json()
                    assert Path(imported["file_path"]).read_bytes() == payload
                    assert "rncp_uploads" in Path(imported["file_path"]).parts
                    response = await asyncio.wait_for(
                        client.post(
                            "/api/v1/rncp/send",
                            json={
                                "destination_hash": address.hex(),
                                "file_path": imported["file_path"],
                                "timeout": 10,
                                "no_compress": True,
                            },
                        ),
                        40,
                    )
                    assert response.status == 200, await response.text()
                    result = await response.json()
                    response = await client.delete(
                        "/api/v1/rncp/uploads/" + imported["id"]
                    )
                    assert response.status == 200
                    response = await client.get("/api/v1/rncp/uploads")
                    assert (await response.json())["files"] == []
                    # The endpoint schedules progress broadcasts after the final
                    # standard Resource callback. Let that queued callback run.
                    await asyncio.wait_for(final_progress.wait(), 2)
            else:
                source = storage / "segmented.bin"
                source.write_bytes(payload)
                progress = []
                result = await asyncio.wait_for(
                    handler.send_file(
                        address,
                        str(source),
                        timeout=10,
                        no_compress=True,
                        on_progress=progress.append,
                    ),
                    40,
                )
            assert result["status"] == "completed"
            target = folder / "receiver/files/rncp_received/segmented.bin"
            deadline = time.monotonic() + 3
            while not target.exists():
                assert time.monotonic() < deadline, (
                    "Sender completed before receiver saved the full file"
                )
                await asyncio.sleep(0.05)
            assert target.read_bytes() == payload
            assert progress and progress[-1] == 1.0
            proof = {
                "ok": True,
                "private_loopback_only": True,
                "http_import_and_send": http_import,
                "imported_copy_removed": http_import,
                "standard_resource_segmentation": True,
                "file_bytes": len(payload),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
                "all_segments_received": True,
                "final_progress": progress[-1],
            }
            (folder / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
        finally:
            if proxy is not None:
                proxy.close()
            for task in tuple(proxy_tasks):
                task.cancel()
            await asyncio.gather(*tuple(proxy_tasks), return_exceptions=True)
            # Python 3.13+ waits for accepted clients as well as the listener.
            # Close their handlers before awaiting the server's shutdown.
            if proxy is not None:
                await proxy.wait_closed()
            peer.terminate()
            try:
                peer.wait(timeout=5)
            except subprocess.TimeoutExpired:
                peer.kill()
                peer.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--allowed")
    parser.add_argument("--http-import", action="store_true")
    args = parser.parse_args()
    if args.port:
        asyncio.run(receive(args.folder, args.port, args.allowed))
    else:
        args.folder.mkdir()
        asyncio.run(send(args.folder, http_import=args.http_import))
