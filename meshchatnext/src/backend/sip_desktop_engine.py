# SPDX-License-Identifier: MIT
"""Private, bounded native SIP process control. No automatic registration."""

import asyncio
import contextlib
import json
import sys
import uuid
from pathlib import Path

from meshchatnext.src.backend.sip_desktop_audio import DesktopSipAudio


class DesktopSipEngine:
    def __init__(
        self,
        executable,
        *,
        test_audio=False,
        timeout=5,
        on_event=None,
        interface=None,
        local_address=None,
    ):
        self.executable = Path(executable)
        self.test_audio = test_audio
        self.interface = interface
        self.local_address = local_address
        self.timeout = timeout
        self.on_event = on_event
        self._process = None
        self._reader = None
        self._pending = {}
        self._lifecycle = asyncio.Lock()
        self._write = asyncio.Lock()
        self._ready = None
        self._audio = DesktopSipAudio()

    @property
    def running(self):
        return self._process is not None and self._process.returncode is None

    async def launch(self):
        async with self._lifecycle:
            if self.running:
                return
            if self._process is not None:
                await self._close()
            self._ready = asyncio.get_running_loop().create_future()
            try:
                args = [str(self.executable.resolve())]
                if self.test_audio:
                    args.append("--test-audio")
                if self.interface:
                    args.extend(["--interface", self.interface])
                    if sys.platform == "win32":
                        if not self.local_address:
                            raise ValueError("Select a Windows SIP interface address")
                        args.extend(["--local-address", self.local_address])
                self._process = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    # Native diagnostics must never become a password log.
                    stderr=asyncio.subprocess.DEVNULL,
                    env=None if self.test_audio else await self._audio.open(),
                    limit=4096,
                )
                self._reader = asyncio.create_task(self._read(self._process))
                await asyncio.wait_for(asyncio.shield(self._ready), self.timeout)
            except BaseException:
                await self._close()
                raise

    async def command(self, op, **fields):
        if op not in {
            "start",
            "dial",
            "answer",
            "hangup",
            "mute",
            "hold",
            "ping",
            "stats",
            "digit",
        }:
            raise ValueError("Unsupported SIP engine action")
        if "op" in fields or "id" in fields:
            raise ValueError("Reserved SIP engine field")
        if not self.running:
            raise ValueError("SIP engine is not running")
        request_id = uuid.uuid4().hex
        try:
            data = (
                json.dumps({**fields, "op": op, "id": request_id}, allow_nan=False)
                + "\n"
            ).encode()
        except (TypeError, ValueError):
            raise ValueError("Invalid SIP engine request") from None
        if len(data) > 4096:
            raise ValueError("SIP engine request is too large")
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with self._write:
                if not self.running:
                    raise ValueError("SIP engine is not running")
                self._process.stdin.write(data)
                await asyncio.wait_for(self._process.stdin.drain(), self.timeout)
            result = await asyncio.wait_for(asyncio.shield(future), self.timeout)
            if result["state"] == "command_failed":
                raise ValueError(
                    f"SIP engine rejected action (code {result.get('code', 0)})"
                )
            return result
        except (TimeoutError, BrokenPipeError, ConnectionError):
            await self.close()
            raise ValueError(
                "SIP engine stopped responding; reconnect before retrying"
            ) from None
        finally:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # retrieve errors during concurrent shutdown

    async def _read(self, process):
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                event = json.loads(line)
                if not isinstance(event, dict) or not isinstance(
                    event.get("state"), str
                ):
                    raise ValueError("Invalid SIP engine response")
                if process is not self._process:
                    break
                if event["state"] == "ready" and not self._ready.done():
                    self._ready.set_result(True)
                pending = self._pending.get(event.get("id"))
                if pending and not pending.done():
                    pending.set_result(event)
                if self.on_event:
                    with contextlib.suppress(Exception):
                        self.on_event(event)
        except (ValueError, OSError):
            pass
        finally:
            if process is self._process:
                if self._ready and not self._ready.done():
                    self._ready.set_exception(ValueError("SIP engine could not start"))
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(ValueError("SIP engine disconnected"))

    async def close(self):
        async with self._lifecycle:
            await self._close()

    async def _close(self):
        process, reader = self._process, self._reader
        self._process = self._reader = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ValueError("SIP engine disconnected"))
        if process:
            if process.returncode is None:
                with contextlib.suppress(Exception):
                    process.stdin.write(b'{"op":"stop","id":"shutdown"}\n')
                    await asyncio.wait_for(process.stdin.drain(), 0.5)
                    process.stdin.close()
                try:
                    await asyncio.wait_for(process.wait(), 3)
                except TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
            if reader:
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reader
        await self._audio.close()
        if self._ready and not self._ready.done():
            self._ready.cancel()
