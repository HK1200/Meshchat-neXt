# SPDX-License-Identifier: 0BSD
"""Drive the real fetch method past 120 virtual seconds with bounded callbacks."""

from inspect import unwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


async def exercise(handler, monkeypatch, folder, *, started):
    namespace = unwrap(handler.fetch_file).__globals__
    complete = namespace["RNS"].Resource.COMPLETE
    seconds = [0]
    payload = b"healthy slow resource bytes"
    source = folder / "resource.tmp"
    source.write_bytes(payload)
    resource = SimpleNamespace(
        hash=b"a" * 32,
        status=0,
        metadata={"name": b"fixture.bin"},
        data=SimpleNamespace(name=str(source)),
        progress_callback=lambda callback: None,
    )
    links = []

    class Link:
        ACTIVE = 1
        ACCEPT_ALL = 2
        ACCEPT_APP = 3

        def __init__(self, destination):
            self.status = self.ACTIVE
            self.teardown = Mock()
            links.append(self)

        def identify(self, identity):
            pass

        def set_resource_strategy(self, strategy):
            pass

        def set_resource_callback(self, callback):
            pass

        def set_resource_started_callback(self, callback):
            self.started = callback

        def set_resource_concluded_callback(self, callback):
            self.concluded = callback

        def request(self, path, *, data, response_callback, failed_callback):
            response_callback(SimpleNamespace(response=True))
            if started:
                self.started(resource)

    async def sleep(delay):
        seconds[0] += 121
        if started and seconds[0] >= 242:
            resource.status = complete
            links[0].concluded(resource)

    fake = SimpleNamespace(
        Transport=SimpleNamespace(has_path=lambda destination: True),
        Identity=SimpleNamespace(recall=lambda destination: object()),
        Destination=type(
            "Destination",
            (),
            {"OUT": 1, "SINGLE": 1, "__init__": lambda self, *args: None},
        ),
        Link=Link,
        Resource=SimpleNamespace(COMPLETE=complete),
    )
    monkeypatch.setitem(namespace, "RNS", fake)
    monkeypatch.setitem(
        namespace,
        "asyncio",
        SimpleNamespace(
            sleep=sleep,
            get_running_loop=lambda: SimpleNamespace(time=lambda: seconds[0]),
        ),
    )
    monkeypatch.setitem(namespace, "link_establishment_window", lambda *args: 5)
    monkeypatch.setattr(handler, "_path_wait_seconds", lambda *args: 30)
    destination = Path(handler.storage_dir) / "rncp_received"
    destination.mkdir(parents=True, exist_ok=True)
    try:
        result = await handler.fetch_file(
            bytes.fromhex("ab" * 16), "fixture.bin", save_path=str(destination)
        )
        assert started and seconds[0] == 242
        assert (
            result["status"] == "completed"
            and Path(result["file_path"]).read_bytes() == payload
        )
        return result
    finally:
        assert len(links) == 1
        links[0].teardown.assert_called_once()
