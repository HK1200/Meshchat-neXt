# SPDX-License-Identifier: 0BSD
"""Download the fixed, checksum-pinned regional map on explicit request."""

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing, suppress
from pathlib import Path

import aiohttp

from meshchatnext.src.backend.privacy_mode import ensure_outbound_http_allowed

NAME = "MeshchatNext-PNW-SouthernBC-detail.mbtiles"
URL = f"https://github.com/hk1200/Meshchat-neXt/releases/download/v0.1.0/{NAME}"
CATALOG = Path(__file__).parent / "data" / "map" / "REGIONAL_MAPS.json"


class RegionalMapDownload:
    def __init__(self, manager):
        self.manager = manager
        self.task = None
        self.state = {"status": "idle", "received": 0, "total": 0}

    def start(self):
        ensure_outbound_http_allowed(
            self.manager.config, feature="regional map download"
        )
        if self.task and not self.task.done():
            return
        self.state = {"status": "downloading", "received": 0, "total": 0}
        self.task = asyncio.create_task(self.run())

    def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            self.state["status"] = "cancelled"

    async def run(self):
        self.state.setdefault("received", 0)
        temporary = None
        try:
            ensure_outbound_http_allowed(
                self.manager.config, feature="regional map download"
            )
            spec = json.loads(CATALOG.read_text())["assets"][NAME]
            self.state["total"] = spec["bytes"]
            directory = Path(self.manager.get_mbtiles_dir())
            directory.mkdir(parents=True, exist_ok=True)
            for candidate in (
                directory / NAME,
                directory / f"regional-detail-{spec['sha256'][:12]}.mbtiles",
            ):
                if candidate.is_file() and candidate.stat().st_size == spec["bytes"]:
                    if (
                        await asyncio.to_thread(self._checksum, candidate)
                        == spec["sha256"]
                    ):
                        self._activate(candidate)
                        self.state.update(
                            status="completed",
                            filename=candidate.name,
                            received=spec["bytes"],
                        )
                        return
            if shutil.disk_usage(directory).free < spec["bytes"] + 16 * 1024 * 1024:
                raise ValueError("Not enough storage for the regional map")
            fd, temporary = tempfile.mkstemp(
                prefix=".regional-", suffix=".part", dir=directory
            )
            digest = hashlib.sha256()
            timeout = aiohttp.ClientTimeout(total=1800, sock_read=60)
            with os.fdopen(fd, "wb") as output:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(URL) as response:
                        response.raise_for_status()
                        async for chunk in response.content.iter_chunked(256 * 1024):
                            ensure_outbound_http_allowed(
                                self.manager.config, feature="regional map download"
                            )
                            self.state["received"] += len(chunk)
                            if self.state["received"] > spec["bytes"]:
                                raise ValueError(
                                    "Regional map exceeded its expected size"
                                )
                            output.write(chunk)
                            digest.update(chunk)
            if (
                self.state["received"] != spec["bytes"]
                or digest.hexdigest() != spec["sha256"]
            ):
                raise ValueError("Regional map verification failed; please retry")
            with closing(
                sqlite3.connect(Path(temporary).as_uri() + "?mode=ro", uri=True)
            ) as database:
                if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Regional map database is damaged")
                database.execute(
                    "SELECT zoom_level, tile_data FROM tiles LIMIT 1"
                ).fetchone()
            # Keep every existing map intact, including a custom file with this name.
            target = directory / NAME
            if target.exists():
                target = directory / f"regional-detail-{spec['sha256'][:12]}.mbtiles"
            if target.exists():
                raise ValueError(
                    "Regional detail is already installed; select it in Offline maps"
                )
            os.link(temporary, target)
            os.unlink(temporary)
            temporary = None
            self._activate(target)
            self.state.update(status="completed", filename=target.name)
        except asyncio.CancelledError:
            self.state["status"] = "cancelled"
        except Exception as error:
            self.state.update(status="failed", error=str(error))
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _checksum(path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(256 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _activate(self, path):
        self.manager.close()
        self.manager.config.map_offline_path.set(str(path))
        self.manager.config.map_offline_enabled.set(True)


def install_regional_map_lifecycle(web_app, owner):
    async def stop(_app):
        download = getattr(owner, "regional_map_download", None)
        if download and download.task and not download.task.done():
            download.cancel()
            with suppress(asyncio.CancelledError):
                await download.task

    web_app.on_shutdown.append(stop)
