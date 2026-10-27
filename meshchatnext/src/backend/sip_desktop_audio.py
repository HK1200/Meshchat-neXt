# SPDX-License-Identifier: MIT
"""Private per-engine Pulse/PipeWire echo cancellation; never changes defaults."""

import asyncio
import contextlib
import os
import uuid


async def _pactl(*args):
    process = await asyncio.create_subprocess_exec(
        "pactl",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), 5)
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise
    if process.returncode or len(stdout) > 65536:
        raise RuntimeError("Audio routing unavailable")
    return stdout.decode().strip()


class DesktopSipAudio:
    def __init__(self, *, command=_pactl):
        self.command = command
        self.module = None
        self.available = False

    async def open(self):
        await self.close()
        env = dict(os.environ)
        # Honor explicitly selected devices instead of overriding another audio setup.
        if env.get("PULSE_SOURCE") or env.get("PULSE_SINK"):
            return env
        try:
            source = await self.command("get-default-source")
            sink = await self.command("get-default-sink")
            if any(
                not name or len(name) > 256 or any(c.isspace() for c in name)
                for name in (source, sink)
            ):
                raise ValueError("Invalid audio device")
            prefix = "meshchat_next_" + uuid.uuid4().hex
            module = await self.command(
                "load-module",
                "module-echo-cancel",
                "source_master=" + source,
                "sink_master=" + sink,
                "source_name=" + prefix + "_mic",
                "sink_name=" + prefix + "_speaker",
                "aec_method=webrtc",
            )
            if not module.isascii() or not module.isdigit():
                raise ValueError("Invalid audio module")
            self.module = module
            self.available = True
            env.update(PULSE_SOURCE=prefix + "_mic", PULSE_SINK=prefix + "_speaker")
        except (OSError, ValueError, RuntimeError, TimeoutError):
            # Calling remains usable with a headset or an existing system audio filter.
            await self.close()
        return env

    async def close(self):
        module, self.module = self.module, None
        self.available = False
        if module is not None:
            with contextlib.suppress(OSError, RuntimeError, TimeoutError):
                await self.command("unload-module", module)
