# SPDX-License-Identifier: MIT
"""Linux SIP lifecycle, account commands and allowed-network failover."""

import asyncio
import contextlib
import sys
import time
import uuid

from meshchatnext.src.backend.sip_desktop_engine import DesktopSipEngine
from meshchatnext.src.backend.sip_desktop_network import (
    available_networks,
    select_network,
)


class DesktopSipService:
    def __init__(
        self,
        accounts,
        executable,
        *,
        engine_factory=DesktopSipEngine,
        networks=available_networks,
        permitted=lambda: True,
    ):
        self.store = accounts
        self.executable = executable
        self.engine_factory = engine_factory
        self.networks = networks
        self.permitted = permitted
        self.engine = None
        self.binding = None
        self.state = "disconnected"
        self.call_state = "idle"
        self.peer = ""
        self.call_id = ""
        self.error = ""
        self.stats = {}
        self.muted = False
        self.held = False
        self._lock = asyncio.Lock()
        self._task = None
        self._closed = False
        self._retry_at = 0
        self._retry_delay = 5
        self._denied = False
        self._last_resume = float("-inf")
        self._network_retry_at = {}
        self._attempt_started = 0.0

    def _permitted(self):
        return self.store.feature_enabled and self.permitted()

    def status(self):
        return {
            "available": True,
            "platform": "windows" if sys.platform == "win32" else "linux",
            "feature_enabled": self.store.feature_enabled,
            "enabled": self.store.enabled,
            "state": self.state,
            "registered": self.state == "registered",
            "accounts": [
                {
                    **r,
                    "has_password": r["save_password"]
                    or r["id"] in self.store.session_passwords,
                }
                for r in self.store.accounts
            ],
            "selected": self.store.selected,
            "call_state": self.call_state,
            "peer": self.peer,
            "call_id": self.call_id,
            "error": self.error,
            "network": self.binding["kind"] if self.binding else "",
            "muted": self.muted,
            "held": self.held,
            "stats": dict(self.stats),
            "i2p_available": False,
            "ethernet_available": True,
            "native_telecom_available": False,
        }

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._watch())

    async def _watch(self):
        while not self._closed:
            try:
                await self.reconcile()
            except Exception:
                self.error = "SIP connection could not be restored; check account and connection settings"
                self._retry_at = time.monotonic() + 30
            await asyncio.sleep(2)

    async def _stop(self):
        engine, self.engine = self.engine, None
        self.binding = None
        self.call_state = "idle"
        self.peer = ""
        self.call_id = ""
        if engine:
            await engine.close()

    @staticmethod
    def _network_key(network):
        return (network["interface"], network["address"], network["kind"])

    def _network_failed(self):
        if self.binding:
            self._network_retry_at[self._network_key(self.binding)] = (
                time.monotonic() + 60
            )

    def _event(self, engine, event):
        if engine is not self.engine:
            return
        state = event["state"]
        if state in ("registering", "registered"):
            self.state = state
            if state == "registered":
                self.error = ""
                self._retry_delay = 5
        elif state == "registration_failed":
            self.state = "registration_failed"
            code = event.get("code", 0)
            self.error = f"SIP registration was not accepted (code {code})"
            self._network_failed()
            self._denied = False
            self._retry_at = 0
        elif state in ("incoming", "calling", "ringing", "connected", "ended"):
            if state in ("incoming", "calling") and self.call_state == "idle":
                self.call_id = uuid.uuid4().hex
            if state == "ended":
                self.call_id = ""
            self.call_state = "idle" if state == "ended" else state
            self.peer = "" if state == "ended" else event.get("peer", "")
        elif state == "stats":
            self.stats = {
                k: event[k]
                for k in ("sent", "received", "lost_rx", "jitter_ms", "rtt_ms")
                if k in event
            }
        elif state == "audio_error":
            self.error = "SIP audio device is unavailable; check system microphone and speaker settings"

    async def reconcile(self):
        async with self._lock:
            await self._reconcile()

    async def _reconcile(self):
        if not self.store.enabled or not self.store.selected or not self._permitted():
            await self._stop()
            self.state = "disconnected" if not self.store.enabled else "blocked"
            return
        row = self.store.find(self.store.selected)
        candidates = await asyncio.to_thread(self.networks)
        # Validate the account policy before considering any connection.
        select_network(row["allowed_networks"], candidates)
        candidates = [n for n in candidates if n["kind"] in row["allowed_networks"]]
        now = time.monotonic()
        current_allowed = self.binding and any(
            self._network_key(n) == self._network_key(self.binding) for n in candidates
        )
        if self.engine and current_allowed and self.engine.running:
            if self.call_state != "idle" or self.state == "registered":
                return
            if self.state in ("starting", "registering"):
                if now - self._attempt_started < 45:
                    return
                self._network_failed()
        elif self.engine and not self.engine.running:
            self._network_failed()
        selected = select_network(
            row["allowed_networks"],
            [
                n
                for n in candidates
                if self._network_retry_at.get(self._network_key(n), 0) <= now
            ],
        )
        if not selected:
            await self._stop()
            self.state = "waiting_network"
            self.error = "Waiting for an allowed SIP connection"
            return
        if (
            self.engine
            and self.binding == selected
            and self.engine.running
            and self.state in ("starting", "registering", "registered")
        ):
            return
        if self.engine:
            await self._stop()
        if self._denied or time.monotonic() < self._retry_at:
            return
        try:
            # Background restores never display a keyring unlock prompt.
            password = await asyncio.to_thread(
                self.store.password, row["id"], interactive=False
            )
        except ValueError:
            self.state = "password_required"
            self.error = (
                "Unlock your keyring or enter the account password to reconnect SIP"
            )
            self._retry_at = time.monotonic() + 30
            return
        options = {"interface": selected["interface"]}
        if sys.platform == "win32":
            options["local_address"] = selected["address"]
        engine = self.engine_factory(self.executable, **options)
        engine.on_event = lambda event: self._event(engine, event)
        self.engine = engine
        self.binding = selected
        self.state = "starting"
        self._attempt_started = time.monotonic()
        try:
            await engine.launch()
            await engine.command(
                "start",
                user=row["extension"],
                host=row["host"],
                port=row["port"],
                password=password,
            )
        except Exception:
            self._network_failed()
            await self._stop()
            self.state = "connection_failed"
            self.error = "SIP could not connect on the selected interface"
            self._retry_at = 0

    async def command(self, op, **fields):
        async with self._lock:
            if op == "save":
                row = await asyncio.to_thread(
                    self.store.save, fields.get("account"), fields.get("password")
                )
                if self.engine and row["id"] == self.store.selected:
                    await self._stop()
                self._denied = False
                self._retry_at = 0
                self._network_retry_at.clear()
            elif op == "remove":
                account_id = fields.get("id")
                if account_id == self.store.selected:
                    await self._stop()
                await asyncio.to_thread(self.store.remove, account_id)
            elif op == "connect":
                row = self.store.find(fields.get("id") or self.store.selected)
                password = fields.get("password")
                if password:
                    if (
                        not isinstance(password, str)
                        or "\0" in password
                        or len(password.encode()) > 256
                    ):
                        raise ValueError("Invalid SIP password")
                    self.store.session_passwords[row["id"]] = password
                else:
                    password = await asyncio.to_thread(self.store.password, row["id"])
                    self.store.session_passwords[row["id"]] = password
                if self.engine and row["id"] != self.store.selected:
                    await self._stop()
                self.store.selected = row["id"]
                self.store.enabled = True
                await asyncio.to_thread(self.store.persist)
                self._denied = False
                self._retry_at = 0
                self._network_retry_at.clear()
            elif op == "resume":
                now = time.monotonic()
                if (
                    self.store.enabled
                    and not self._denied
                    and now - self._last_resume >= 5
                ):
                    self._last_resume = now
                    await self._stop()
                    self._retry_at = 0
            elif op == "disconnect":
                self.store.enabled = False
                await asyncio.to_thread(self.store.persist)
                await self._stop()
                self.state = "disconnected"
            elif op in ("call", "answer", "hangup", "mute", "hold", "dtmf", "stats"):
                if not self._permitted() or not self.engine or not self.engine.running:
                    raise ValueError("Connect SIP before using call controls")
                native = {"call": "dial", "dtmf": "digit"}.get(op, op)
                payload = {}
                if op == "call":
                    address = fields.get("target", fields.get("address", ""))
                    if (
                        not isinstance(address, str)
                        or len(address) > 320
                        or any(c in address for c in '\r\n<>" ')
                    ):
                        raise ValueError("Invalid SIP address")
                    if not address.startswith("sip:"):
                        import re

                        if not re.fullmatch(r"[0-9*#+]{1,64}", address):
                            raise ValueError("Enter a SIP extension or address")
                        row = self.store.find(self.store.selected)
                        address = f"sip:{address}@{row['host']}:{row['port']}"
                    payload = {"peer": address}
                elif op in ("mute", "hold"):
                    value = fields.get("value")
                    if type(value) is not bool:
                        raise ValueError("Invalid SIP call option")
                    payload = {"value": value}
                elif op == "dtmf":
                    payload = {"digit": fields.get("digit")}
                await self.engine.command(native, **payload)
                if op == "mute":
                    self.muted = payload["value"]
                if op == "hold":
                    self.held = payload["value"]
            elif op != "status":
                raise ValueError("Unsupported SIP action")
            await self._reconcile()
            return self.status()

    async def close(self):
        self._closed = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        async with self._lock:
            await self._stop()
        self.store.session_passwords.clear()
