# SPDX-License-Identifier: MIT
"""Bounded MeshCore diagnostics and public region selection, independent of RNS."""

from __future__ import annotations

import asyncio
import contextlib
import math
import re
import secrets
import time
from contextlib import asynccontextmanager

from meshchatnext.src.backend.meshcore_store import public_key


def region_name(value):
    if not isinstance(value, str):
        raise ValueError("Enter a public MeshCore region name")
    value = value.strip()
    if not value.startswith("#"):
        value = "#" + value
    if not re.fullmatch(r"#[A-Za-z0-9][A-Za-z0-9_.\-/]{0,28}", value):
        raise ValueError(
            "Use a public region name of 1-29 ASCII letters, digits, dots, slashes, underscores or hyphens"
        )
    return value


@asynccontextmanager
async def channel_scope(session, scope):
    """Caller owns session lock. Scope override is sticky in companion firmware."""
    commands = session._client.commands
    setter = getattr(commands, "set_flood_scope", None)
    if scope is None:
        # Clear stale overrides left by earlier clients when this firmware supports it.
        version = (getattr(session, "_device_info", None) or {}).get("fw ver", 0)
        if setter is not None and version >= 12:
            try:
                session._payload(await setter(None))
            except BaseException:
                await session._close()
                raise
        yield
        return
    if setter is None:
        raise ValueError("This firmware does not support channel scopes")
    chosen = "*" if scope == "*" else region_name(scope)
    try:
        session._payload(await setter(chosen))
        yield
    finally:
        # A timeout cannot prove the override was not applied. Always reset it,
        # and close if reset is unconfirmed so a later DM cannot inherit it.
        try:
            session._payload(await setter(None))
        except BaseException:
            await session._close()
            raise ConnectionError(
                "Scope reset was not confirmed; reconnect MeshCore before sending again"
            ) from None


class MeshCoreTools:
    TIMEOUT = 12

    def __init__(self, messages, nodes=None):
        self.messages = messages
        self.session = messages.session
        self._last_announce = None
        self._last_trace = None
        self._last_regions = {}
        self.nodes = nodes
        self._region_task = None
        self.region_scan: dict[str, object] = {"state": "idle"}

    async def close(self):
        if self._region_task is not None:
            self._region_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._region_task
            self._region_task = None

    async def set_region_auto(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Invalid region automation setting")
        self.messages._check()
        await asyncio.to_thread(
            self.messages.store.region_automation, self.messages.owner, enabled=enabled
        )
        if enabled:
            await self.start_region_scan(automatic=True)
        else:
            await self.close()
        return {"enabled": enabled}

    async def start_region_scan(self, automatic=False):
        self.messages._check()
        if self._region_task is not None and not self._region_task.done():
            return dict(self.region_scan)
        saved = await asyncio.to_thread(
            self.messages.store.region_automation, self.messages.owner
        )
        wait = (600 if automatic else 180) - (time.time() - saved["last_scan"])
        if wait > 0:
            if automatic:
                return {"state": "cooldown", "retry_after": int(wait) + 1}
            raise ValueError(f"Wait {int(wait) + 1} seconds before another region scan")
        if self.nodes is None:
            raise ValueError("Node discovery is unavailable")
        await asyncio.to_thread(
            self.messages.store.region_automation,
            self.messages.owner,
            scanned=time.time(),
        )
        self.region_scan = {
            "state": "running",
            "queried": 0,
            "found": 0,
            "message": "Discovering nearby infrastructure",
        }
        self._region_task = asyncio.create_task(self._scan_regions())
        return dict(self.region_scan)

    async def _scan_regions(self):
        try:
            try:
                discovered = await self.nodes.discover()
                peers = [n["peer"] for n in discovered["nodes"]]
            except ValueError:
                rows = await asyncio.to_thread(
                    self.messages.store.announces, self.messages.owner
                )
                peers = [
                    n["peer"]
                    for n in rows
                    if n["kind"] in (2, 3, 4)
                    and n.get("path_len") == 0
                    and time.time() - (n.get("heard") or 0) < 600
                ]
            unique = list(dict.fromkeys(peers))[:3]
            found = set()
            replies = 0
            queried = 0
            for peer in unique:
                self.messages._check()
                self.region_scan["message"] = "Asking nearby nodes for their regions"
                result = await self.discover_regions(peer)
                queried += 1
                self.region_scan["queried"] = queried
                if result["state"] == "verified":
                    replies += 1
                    found.update(result["regions"])
                self.region_scan["found"] = len(found)
                if peer != unique[-1]:
                    await asyncio.sleep(2)
            self.region_scan.update(
                state="complete",
                message=f"{replies} nodes returned region information; {len(found)} public regions found. Unsupported or silent nodes may have more regions.",
            )
        except asyncio.CancelledError:
            self.region_scan.update(state="cancelled", message="Region scan stopped")
            raise
        except Exception:
            self.region_scan.update(
                state="error",
                message="Region scan was not confirmed. Check the MeshCore connection.",
            )

    async def announce(self, flood):
        if type(flood) is not bool:
            raise ValueError("Choose a local or flood announce")
        if (
            self._last_announce is not None
            and time.monotonic() - self._last_announce < 30
        ):
            raise ValueError("Wait 30 seconds between MeshCore announces")
        async with self.session._lock:
            self.messages._check()
            self._last_announce = time.monotonic()
            self.session._payload(
                await self.session._client.commands.send_advert(flood=flood)
            )
        return {
            "state": "submitted",
            "kind": "flood" if flood else "local",
            "submitted_at": time.time(),
        }

    async def radio_stats(self):
        async with self.session._lock:
            self.messages._check()
            raw = self.session._payload(
                await self.session._client.commands.get_stats_radio()
            )
            result = {}
            for key in (
                "noise_floor",
                "last_rssi",
                "last_snr",
                "tx_air_secs",
                "rx_air_secs",
            ):
                value = raw.get(key)
                if type(value) in (int, float) and math.isfinite(value):
                    result[key] = value
            noise = result.get("noise_floor")
            if noise is not None and not -180 <= noise <= 0:
                result["noise_floor"] = None
            return result

    async def rx_log(self):
        self.messages._check()
        return {"packets": list(getattr(self.messages, "rx_log", []))[-200:][::-1]}

    async def read_regions(self):
        async with self.session._lock:
            self.messages._check()
            payload = self.session._payload(
                await self.session._client.commands.get_default_flood_scope()
            )
        return {
            "radio_default_scope": payload.get("scope_name", ""),
            "default_scope": await asyncio.to_thread(
                self.messages.store.region_default, self.messages.owner
            ),
            "regions": await asyncio.to_thread(
                self.messages.store.regions, self.messages.owner
            ),
        }

    async def add_region(self, name):
        self.messages._check()
        name = region_name(name)
        await asyncio.to_thread(
            self.messages.store.save_region, self.messages.owner, name
        )
        return {"name": name}

    async def set_default_region(self, scope):
        self.messages._check()
        value = None if scope is None else region_name(scope)
        await asyncio.to_thread(
            self.messages.store.set_region_default, self.messages.owner, value
        )
        return {"default_scope": value}

    async def trace(self, path):
        if not isinstance(path, str):
            raise ValueError("Enter comma-separated repeater path hashes")
        hops = [part.strip().lower() for part in path.split(",")]
        if (
            not 1 <= len(hops) <= 16
            or len(hops[0]) not in (2, 4, 8, 16)
            or any(
                len(h) != len(hops[0]) or not re.fullmatch(r"[0-9a-f]+", h)
                for h in hops
            )
        ):
            raise ValueError(
                "Use 1-16 equal-size hex path hashes (1, 2, 4 or 8 bytes each)"
            )
        if self._last_trace is not None and time.monotonic() - self._last_trace < 30:
            raise ValueError("Wait 30 seconds between traces")
        tag = secrets.randbits(32) or 1
        auth = secrets.randbits(32) or 1
        future = asyncio.get_running_loop().create_future()

        def receive(event):
            p = event.payload
            if (
                isinstance(p, dict)
                and p.get("tag") == tag
                and p.get("auth") == auth
                and not future.done()
            ):
                future.set_result(dict(p))

        kind = getattr(self.messages._types, "TRACE_DATA", None)
        if kind is None:
            raise ValueError("This companion does not support trace replies")
        subscription = self.session._client.subscribe(kind, receive)
        try:
            async with self.session._lock:
                self.messages._check()
                self._last_trace = time.monotonic()
                self.session._payload(
                    await self.session._client.commands.send_trace(
                        path=",".join(hops), tag=tag, auth_code=auth
                    )
                )
            try:
                result = await asyncio.wait_for(future, self.TIMEOUT)
            except TimeoutError:
                return {
                    "state": "unconfirmed",
                    "message": "No matching trace response before timeout",
                }
            self.messages._check()
            return {
                "state": "verified",
                "path": result.get("path", [])[:17],
                "path_len": result.get("path_len"),
            }
        finally:
            subscription.unsubscribe()

    async def discover_regions(self, peer):
        peer = public_key(peer)
        if time.monotonic() - self._last_regions.get(peer, -1e12) < 30:
            raise ValueError("Wait 30 seconds between region requests to the same node")
        known = await asyncio.to_thread(
            self.messages.store.announces, self.messages.owner
        )
        if not any(row["peer"] == peer and row["kind"] in (2, 3, 4) for row in known):
            raise ValueError("Select a discovered infrastructure node")
        future = asyncio.get_running_loop().create_future()
        buffered = []
        expected = None

        def receive(event):
            if not isinstance(event.payload, dict):
                return
            if len(buffered) < 64:
                buffered.append(dict(event.payload))
            if expected and event.payload.get("tag") == expected and not future.done():
                future.set_result(event.payload)

        kind = getattr(self.messages._types, "BINARY_RESPONSE", None)
        if kind is None:
            raise ValueError("This companion does not support region discovery")
        subscription = self.session._client.subscribe(kind, receive)
        try:
            async with self.session._lock:
                self.messages._check()
                self._last_regions[peer] = time.monotonic()
                if len(self._last_regions) > 256:
                    self._last_regions.pop(next(iter(self._last_regions)))
                client = self.session._client
                contact = getattr(client, "contacts", {}).get(peer)
                was_flood = (
                    isinstance(contact, dict) and contact.get("out_path_len") == -1
                )
                try:
                    event = await client.commands.req_regions_async(
                        peer, timeout=self.TIMEOUT
                    )
                finally:
                    # meshcore_py temporarily pins a flood contact to zero-hop.
                    # Restore even when the request raises or is cancelled.
                    if was_flood and contact.get("out_path_len") != -1:
                        try:
                            self.session._payload(
                                await asyncio.shield(
                                    client.commands.reset_path(contact)
                                )
                            )
                        except BaseException:
                            await self.session._close()
                            raise ConnectionError(
                                "Region probe route restoration was not confirmed; reconnect MeshCore"
                            ) from None
                payload = self.session._payload(event)
                ack = payload.get("expected_ack")
                if not isinstance(ack, bytes) or len(ack) != 4:
                    raise ConnectionError("Region request was not confirmed")
                expected = ack.hex()
                for p in buffered:
                    if p.get("tag") == expected and not future.done():
                        future.set_result(p)
            try:
                response = await asyncio.wait_for(future, self.TIMEOUT)
            except TimeoutError:
                return {
                    "state": "unconfirmed",
                    "regions": [],
                    "message": "No matching region response. Older nodes may not support region discovery.",
                }
            self.messages._check()
            data = bytes.fromhex(response.get("data", ""))
            if len(data) > 2048:
                raise ValueError("Region response exceeds limit")
            # Anonymous response data repeats its request tag before the names.
            if data[:4] != ack:
                raise ValueError("Region response tag did not match")
            text = data[4:].decode("utf-8", "strict").strip("\0")
            names = []
            for token in re.findall(r"#[A-Za-z0-9][A-Za-z0-9_.\-/]{0,28}", text):
                name = region_name(token)
                if name not in names and len(names) < 64:
                    names.append(name)
                    await asyncio.to_thread(
                        self.messages.store.save_region, self.messages.owner, name
                    )
            return {"state": "verified", "regions": names}
        finally:
            subscription.unsubscribe()
