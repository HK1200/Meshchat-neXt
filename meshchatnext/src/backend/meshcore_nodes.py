# SPDX-License-Identifier: MIT
"""Explicit server operations; passwords and verified logins are memory-only."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from meshchatnext.src.backend.meshcore_store import public_key


class MeshCoreNodes:
    DISCOVERY_WINDOW = 12
    DISCOVERY_COOLDOWN = 30
    TIMEOUT = 30
    LOGIN_LIFETIME = 300
    CLI_POLL_INTERVAL = 1.0

    def __init__(self, messages, passwords=None):
        self.passwords = passwords
        self.messages = messages
        self.session = messages.session
        self.logins = {}
        self.uncertain = set()
        self.operations = {}
        self._last_discovery = None

    async def discover(self):
        """One nearby infrastructure probe; never save nodes or log in automatically."""
        self.messages._check()
        client = self.session._client
        kind = getattr(self.messages._types, "DISCOVER_RESPONSE", None)
        command = getattr(client.commands, "send_node_discover_req", None)
        if kind is None or command is None:
            raise ValueError("This companion does not support active node discovery")
        now = time.monotonic()
        if (
            self._last_discovery is not None
            and now - self._last_discovery < self.DISCOVERY_COOLDOWN
        ):
            raise ValueError("Wait 30 seconds between nearby discovery requests")
        tag = secrets.randbits(32) or 1
        expected = tag.to_bytes(4, "little").hex()
        found = {}
        owner = self.messages.owner
        raw_kind = getattr(self.messages._types, "CONTROL_DATA", None)
        raw_command = getattr(client.commands, "send_control_data", None)
        extended = raw_kind is not None and callable(raw_command)

        def receive_raw(event):
            from meshchatnext.src.backend.meshcore_peer_radio2 import (
                decode_discovery_radio2,
            )

            body = event.payload
            if not isinstance(body, dict) or body.get("path_len") != 0:
                return
            packet = body.get("payload")
            # Full-key responses only. Prefixes must never select a cached peer.
            if not isinstance(packet, bytes) or len(packet) not in (38, 40, 50):
                return
            if packet[0] != 0x92 or packet[2:6].hex() != expected:
                return
            peer = packet[6:38].hex()
            if peer == owner or (len(found) >= 512 and peer not in found):
                return
            found[peer] = {
                "peer": peer,
                "kind": 2,
                "radio2": decode_discovery_radio2(packet[38:]),
            }

        def receive(event):
            payload = event.payload
            if not isinstance(payload, dict) or payload.get("tag") != expected:
                return
            node_type = payload.get("node_type")
            if type(node_type) is not int or node_type not in (2, 3, 4):
                return
            try:
                peer = public_key(payload.get("pubkey"))
            except ValueError:
                return
            if peer == self.messages.owner or (len(found) >= 512 and peer not in found):
                return
            found.setdefault(peer, {"peer": peer, "kind": node_type})

        subscription = client.subscribe(kind, receive)
        raw_subscription = None
        try:
            if extended:
                raw_subscription = client.subscribe(raw_kind, receive_raw)
            async with self.session._lock:
                self.messages._check()
                self._last_discovery = time.monotonic()
                if extended:
                    self.session._payload(
                        await cast(Callable[[int, bytes], Awaitable[Any]], raw_command)(
                            0x82, bytes([0x1C]) + tag.to_bytes(4, "little")
                        )
                    )
                else:
                    self.session._payload(
                        await command(filter=0x1C, prefix_only=False, tag=tag)
                    )
            await asyncio.sleep(self.DISCOVERY_WINDOW)
            self.messages._check()
            if self.session._client is not client or self.messages.owner != owner:
                raise ConnectionError("MeshCore connection changed during discovery")
            heard = time.time()
            results = []
            for row in found.values():
                recorded = await asyncio.to_thread(
                    self.messages.store.record_node_discovery,
                    self.messages.owner,
                    row["peer"],
                    row["kind"],
                    heard,
                )
                if recorded:
                    if "radio2" in row:
                        await asyncio.to_thread(
                            self.messages.store.record_peer_radio2,
                            owner,
                            row["peer"],
                            row["radio2"],
                            heard,
                        )
                    results.append(row)
            return {
                "nodes": results,
                "nearby": True,
                "window_seconds": self.DISCOVERY_WINDOW,
                "cooldown_seconds": self.DISCOVERY_COOLDOWN,
            }
        finally:
            subscription.unsubscribe()
            if raw_subscription is not None:
                raw_subscription.unsubscribe()

    def snapshot(self):
        now = time.monotonic()
        return {
            peer: {
                "state": "verified",
                "is_admin": value[1],
                "expires_in": None if value[0] is None else max(0, int(value[0] - now)),
            }
            for peer, value in self.logins.items()
            if value[0] is None or value[0] > now
        }

    async def _contact(self, peer):
        peer = public_key(peer)
        self.messages._check()
        rows = await self.messages.sync_contacts()
        matches = [
            row
            for row in rows
            if row.get("active") and row["peer"].startswith(peer[:12])
        ]
        if not matches:
            # An explicit server operation may import a newly advertised node.
            # Do not infer links or overwrite an existing contact of another type.
            announced = await asyncio.to_thread(
                self.messages.store.announces, self.messages.owner
            )
            candidate = next(
                (
                    row
                    for row in announced
                    if row["peer"] == peer and row["kind"] in (2, 3)
                ),
                None,
            )
            if candidate is not None:
                name = candidate["name"]
                if not name or "\0" in name or len(name.encode()) > 31:
                    raise ValueError("Invalid advertised server name")
                await self.messages.import_contact(
                    {
                        "public_key": peer,
                        "type": candidate["kind"],
                        "flags": 0,
                        "out_path": "",
                        "out_path_len": -1,
                        "out_path_hash_mode": -1,
                        "adv_name": name,
                        "last_advert": candidate["advertised"],
                        "adv_lat": 0,
                        "adv_lon": 0,
                    }
                )
                rows = await self.messages.sync_contacts()
                matches = [
                    row
                    for row in rows
                    if row.get("active") and row["peer"].startswith(peer[:12])
                ]
        if (
            len(matches) != 1
            or matches[0]["peer"] != peer
            or matches[0]["kind"] not in (2, 3)
        ):
            raise ValueError("Choose an unambiguous active repeater or room server")
        return matches[0]

    async def _exchange(self, peer, operation, password=None):
        diagnostic = {
            "operation": operation,
            "stage": "sending",
            "matching_responses": 0,
            "other_responses": 0,
        }
        self.operations[peer] = diagnostic
        try:
            contact = await self._contact(peer)
        except Exception as error:
            diagnostic.update(
                stage="contact_check_failed", error_type=type(error).__name__
            )
            raise
        if peer in self.uncertain and operation != "route":
            diagnostic["stage"] = "retry_blocked"
            raise ValueError(
                "Prior server response is uncertain; reconnect MeshCore before retrying"
            )
        client = self.session._client
        types = self.messages._types
        future = asyncio.get_running_loop().create_future()
        kinds = (
            [types.LOGIN_SUCCESS, types.LOGIN_FAILED]
            if operation == "login"
            else [types.PATH_RESPONSE]
            if operation == "route"
            else [types.STATUS_RESPONSE]
        )

        def receive(event):
            prefix = (
                event.payload.get("pubkey_prefix")
                or event.payload.get("pubkey_pre")
                or event.attributes.get("pubkey_prefix")
            )
            if prefix == peer[:12] and not future.done():
                diagnostic["matching_responses"] += 1
                future.set_result(event)
            else:
                diagnostic["other_responses"] += 1

        subscriptions = [client.subscribe(kind, receive) for kind in kinds]
        try:
            if contact["kind"] == 3 and operation in ("login", "status"):
                previous = await asyncio.to_thread(
                    self.messages.store.outgoing_clock, self.messages.owner, peer
                )
                if previous:
                    async with self.session._lock:
                        clock = self.session._payload(
                            await client.commands.get_time()
                        ).get("time")
                    if type(clock) is not int:
                        raise ConnectionError("Invalid companion clock")
                    delay = previous + 1 - clock
                    if delay > 120:
                        raise ValueError("Companion clock is behind the room history")
                    if delay > 0:
                        await asyncio.sleep(delay + 0.1)
            async with self.session._lock:
                self.messages._check()
                if operation == "login":
                    result = await client.commands._send_login_raw(peer, password)
                elif operation == "route":
                    result = await client.commands.send(
                        b"\x34\x00" + bytes.fromhex(peer), [types.MSG_SENT, types.ERROR]
                    )
                else:
                    # Legacy status request has a peer prefix in its push response.
                    result = await client.commands.send(
                        b"\x1b" + bytes.fromhex(peer), [types.MSG_SENT, types.ERROR]
                    )
            if result is None or result.type != types.MSG_SENT:
                if (
                    result is not None
                    and result.type == types.ERROR
                    and type(result.payload.get("error_code")) is int
                ):
                    diagnostic.update(
                        stage="radio_rejected", error_code=result.payload["error_code"]
                    )
                    return {"state": "rejected", "reason": "radio_rejected"}
                if operation != "route":
                    self.uncertain.add(peer)
                diagnostic["stage"] = "radio_unconfirmed"
                return {"state": "uncertain", "reason": "radio_unconfirmed"}
            suggested = result.payload.get("suggested_timeout")
            # The companion estimates the mesh round trip in milliseconds.
            timeout = self.TIMEOUT
            if (
                type(suggested) in (int, float)
                and math.isfinite(suggested)
                and suggested > 0
            ):
                timeout = min(120, max(timeout, suggested / 1000 * 1.5))
            diagnostic.update(stage="waiting_for_server", timeout_seconds=timeout)
            try:
                response = await asyncio.wait_for(future, timeout)
            except TimeoutError:
                if operation != "route":
                    self.uncertain.add(peer)
                diagnostic["stage"] = "server_timeout"
                return {"state": "uncertain", "reason": "server_timeout"}
            if operation == "login":
                if response.type == types.LOGIN_FAILED:
                    diagnostic["stage"] = "server_denied"
                    return {"state": "denied"}
                diagnostic["stage"] = "login_verified"
                admin = response.payload.get("is_admin") is True
                self.logins[peer] = (
                    None
                    if contact["kind"] == 3
                    else time.monotonic() + self.LOGIN_LIFETIME,
                    admin,
                )
                return {"state": "verified", "is_admin": admin}
            if operation == "route":
                diagnostic["stage"] = "route_received"
                return {
                    "state": "route_received",
                    "out_hops": response.payload.get("out_path_len"),
                    "in_hops": response.payload.get("in_path_len"),
                }
            diagnostic["stage"] = "status_received"
            # Display numeric status data only; never forward raw binary packets.
            values = {
                key: value
                for key, value in response.payload.items()
                if type(value) in (int, float) and math.isfinite(value)
            }
            if contact["kind"] == 3 and type(values.get("rx_airtime")) is int:
                # Room status uses the last four bytes for two 16-bit post counters.
                packed = values.pop("rx_airtime")
                values["room_posts"] = packed & 0xFFFF
                values["room_pushes"] = packed >> 16
            return {"state": "received", "values": values, "received": time.time()}
        except BaseException as error:
            diagnostic["stage"] = "local_error"
            diagnostic["error_type"] = type(error).__name__
            if operation != "route":
                self.uncertain.add(peer)
            raise
        finally:
            for subscription in subscriptions:
                subscription.unsubscribe()

    async def password_status(self, peer):
        from meshchatnext.src.backend.meshcore_credentials import NodePasswords

        return await asyncio.to_thread(
            (self.passwords or NodePasswords()).status,
            self.messages.owner,
            public_key(peer),
        )

    async def password_save(self, peer, role, password):
        if self.passwords is None:
            raise ValueError("Secure password storage is unavailable")
        await asyncio.to_thread(
            self.passwords.save, self.messages.owner, public_key(peer), role, password
        )
        return await self.password_status(peer)

    async def password_forget(self, peer, role):
        if self.passwords is None:
            raise ValueError("Secure password storage is unavailable")
        await asyncio.to_thread(
            self.passwords.forget, self.messages.owner, public_key(peer), role
        )
        return await self.password_status(peer)

    async def login(self, peer, password=None, remember=False, use_saved_role=None):
        peer = public_key(peer)
        if type(remember) is not bool:
            raise ValueError("Remember password must be a boolean")
        if use_saved_role is not None:
            if password is not None or remember or self.passwords is None:
                raise ValueError(
                    "Choose either a supplied password or a saved password"
                )
            password = await asyncio.to_thread(
                self.passwords.load, self.messages.owner, peer, use_saved_role
            )
        if (
            not isinstance(password, str)
            or "\0" in password
            or len(password.encode()) > 64
        ):
            raise ValueError("Password must contain at most 64 UTF-8 bytes without NUL")
        self.logins.pop(peer, None)
        result = await self._exchange(peer, "login", password)
        if remember and result.get("state") == "verified":
            try:
                await self.password_save(
                    peer, "admin" if result.get("is_admin") else "member", password
                )
                result["password_saved"] = True
            except Exception:
                result["password_saved"] = False
        return result

    async def route(self, peer):
        return await self._exchange(public_key(peer), "route")

    async def status(self, peer):
        peer = public_key(peer)
        if peer not in self.snapshot():
            raise ValueError("Log in before requesting server status")
        return await self._exchange(peer, "status")

    async def logout(self, peer):
        peer = public_key(peer)
        await self._contact(peer)
        self.logins.pop(peer, None)
        async with self.session._lock:
            self.messages._check()
            result = await self.session._client.commands.send_logout(peer)
        return {
            "state": "submitted"
            if result is not None and result.type == self.messages._types.OK
            else "uncertain"
        }

    async def admin(self, peer, action, value="", confirmed=False):
        peer = public_key(peer)
        if not self.snapshot().get(peer, {}).get("is_admin"):
            raise ValueError("A verified administrator login is required")
        if peer in self.uncertain:
            raise ValueError("Reconnect before another uncertain server request")
        contact = await self._contact(peer)
        reads = {
            "version": "ver",
            "board": "board",
            "name": "get name",
            "radio": "get radio",
            "tx": "get tx",
            "hash": "get path.hash.mode",
            "clock": "clock",
            "latitude": "get lat",
            "longitude": "get lon",
            "local-interval": "get advert.interval",
            "flood-interval": "get flood.advert.interval",
        }
        if not isinstance(value, str) or any(c in value for c in "\0\r\n"):
            raise ValueError("Invalid administrator value")
        if not isinstance(action, str):
            raise ValueError("Invalid administrator action")
        command = reads.get(action)
        secret_action = action == "set-room-password"
        if (
            action in ("room-access", "set-read-only", "set-room-password")
            and contact["kind"] != 3
        ):
            raise ValueError("Choose a room server for room access settings")
        if action == "room-access":
            command = "get allow.read.only"
            if value:
                raise ValueError("Read actions do not accept values")
        elif action == "set-read-only":
            if value not in ("on", "off"):
                raise ValueError("Choose on or off for read-only guest access")
            command = "set allow.read.only " + value
        elif secret_action:
            if not value or value != value.strip() or len(value.encode()) > 15:
                raise ValueError(
                    "Room password must contain 1-15 UTF-8 bytes without leading or trailing whitespace"
                )
            if confirmed is not True:
                raise ValueError("Confirm the room password change")
            command = "set guest.password " + value
        elif action == "sync-clock":
            command = "clock sync"
        elif action in ("set-latitude", "set-longitude"):
            try:
                coordinate = float(value)
            except ValueError:
                raise ValueError("Enter a decimal coordinate") from None
            limit = 90 if action == "set-latitude" else 180
            if not math.isfinite(coordinate) or not -limit <= coordinate <= limit:
                raise ValueError("Coordinate is outside the valid range")
            command = (
                f"set {'lat' if action == 'set-latitude' else 'lon'} {coordinate:.6f}"
            )
        elif action in ("set-local-interval", "set-flood-interval"):
            try:
                interval = int(value)
            except ValueError:
                raise ValueError("Enter a whole-number advert interval") from None
            if action == "set-local-interval":
                if interval != 0 and (not 60 <= interval <= 240 or interval % 2):
                    raise ValueError(
                        "Local interval must be 0 (off) or 60-240 minutes in two-minute steps"
                    )
                command = f"set advert.interval {interval}"
            else:
                if interval != 0 and not 3 <= interval <= 168:
                    raise ValueError("Flood interval must be 0 (off) or 3-168 hours")
                command = f"set flood.advert.interval {interval}"
        elif action == "set-name":
            if not value.strip() or len(value.encode()) > 31:
                raise ValueError("Name must contain 1-31 UTF-8 bytes")
            command = "set name " + value
        elif action in ("set-tx", "set-hash"):
            try:
                number = int(value)
            except ValueError:
                raise ValueError("Enter a whole number") from None
            if action == "set-tx" and 1 <= number <= 22:
                command = f"set tx {number}"
            elif action == "set-hash" and 1 <= number <= 3:
                command = f"set path.hash.mode {number - 1}"
        elif action == "set-radio":
            from meshchatnext.src.backend.meshcore_settings import validate_changes

            try:
                freq, bw, sf, cr = value.split(",")
                settings = validate_changes(
                    {
                        "frequency_mhz": float(freq),
                        "bandwidth_khz": float(bw),
                        "sf": int(sf),
                        "cr": int(cr),
                    },
                    22,
                )
            except (ValueError, TypeError):
                raise ValueError(
                    "Use frequency MHz,bandwidth kHz,SF,CR (5-8)"
                ) from None
            command = "set radio " + ",".join(
                str(settings[k]) for k in ("frequency_mhz", "bandwidth_khz", "sf", "cr")
            )
        elif action == "advert":
            command = "advert"
        elif action == "reboot":
            command = "reboot"
        elif action == "room-post" and contact["kind"] == 3:
            if not value.strip() or len(value.encode()) > 140:
                raise ValueError("Server announcement must contain 1-140 UTF-8 bytes")
            command = "room.post " + value
        if command is None:
            raise ValueError("Unsupported administrator action or value")
        if action in ("set-radio", "reboot") and confirmed is not True:
            raise ValueError("Confirm this action may disconnect the server")
        if action in reads and value:
            raise ValueError("Read actions do not accept values")
        client, types = self.session._client, self.messages._types
        future = asyncio.get_running_loop().create_future()

        armed = False
        polling = False
        may_have_sent = False

        def receive(event):
            if not armed:
                return
            payload = event.payload
            if (
                payload.get("pubkey_prefix") == peer[:12]
                and payload.get("txt_type") == 1
                and not future.done()
            ):
                diagnostic["response_via_queue_poll"] = polling
                text = str(payload.get("text", ""))[:512]
                if secret_action:
                    text = (
                        "Room password changed."
                        if text.strip() == "OK"
                        else "Server did not confirm the room password change."
                    )
                future.set_result(text)

        diagnostic = {
            "operation": "admin",
            "admin_action": action,
            "stage": "sending",
            "matching_responses": 0,
        }
        self.operations[peer] = diagnostic
        subscription = client.subscribe(types.CONTACT_MSG_RECV, receive)
        try:
            # The companion overwrites CLI timestamps with its own clock. Wait
            # beyond our last reserved post/command stamp before handing it CLI.
            previous = await asyncio.to_thread(
                self.messages.store.outgoing_clock, self.messages.owner, peer
            )
            if previous:
                async with self.session._lock:
                    clock = self.session._payload(await client.commands.get_time()).get(
                        "time"
                    )
                if type(clock) is not int:
                    raise ConnectionError("Invalid companion clock")
                delay = previous + 1 - clock
                if delay > 120:
                    raise ValueError("Companion clock is behind the server history")
                if delay > 0:
                    diagnostic["stage"] = "waiting_for_clock"
                    await asyncio.sleep(delay + 0.1)
            async with self.session._lock:
                self.messages._check()
                clock = self.session._payload(await client.commands.get_time()).get(
                    "time"
                )
                if type(clock) is not int:
                    raise ConnectionError("Invalid companion clock")
                await self.messages._drain_pending()
                timestamp = await asyncio.to_thread(
                    self.messages.store.reserve_command_clock,
                    self.messages.owner,
                    peer,
                    clock + 1,
                )
                armed = True
                may_have_sent = True
                if secret_action:
                    # send_cmd logs command text at debug level. Use the same wire
                    # frame directly so credentials never enter that log path.
                    frame = (
                        b"\x02\x01\x00"
                        + timestamp.to_bytes(4, "little")
                        + bytes.fromhex(peer[:12])
                        + command.encode()
                    )
                    sent = await client.commands.send(
                        frame, [types.MSG_SENT, types.ERROR]
                    )
                else:
                    sent = await client.commands.send_cmd(
                        peer, command, timestamp=timestamp, dst_type=contact["kind"]
                    )
            if sent is not None and sent.type == types.ERROR:
                diagnostic["stage"] = "radio_rejected"
                code = sent.payload.get("error_code")
                if type(code) is int:
                    diagnostic["error_code"] = code
                return {"state": "rejected", "reason": "radio_rejected"}
            if sent is None or sent.type != types.MSG_SENT:
                diagnostic["stage"] = "radio_unconfirmed"
                self.uncertain.add(peer)
                return {"state": "uncertain"}
            if action == "reboot":
                diagnostic["stage"] = "restart_submitted"
                self.logins.pop(peer, None)
                return {
                    "state": "submitted",
                    "text": "Restart submitted. The server sends no reply; log in again after it restarts.",
                }
            diagnostic["stage"] = "waiting_for_server"
            try:
                async with asyncio.timeout(self.TIMEOUT):
                    while not future.done():
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(future), self.CLI_POLL_INTERVAL
                            )
                        except TimeoutError:
                            # A missed BLE message-waiting push must not strand a
                            # reply in the companion queue. Fetch only; never resend.
                            async with self.session._lock:
                                self.messages._check()
                                diagnostic["queue_polls"] = (
                                    diagnostic.get("queue_polls", 0) + 1
                                )
                                polling = True
                                try:
                                    for _ in range(16):
                                        if (
                                            future.done()
                                            or not await self.messages._fetch_message()
                                        ):
                                            break
                                finally:
                                    polling = False
                    text = future.result()
            except TimeoutError:
                diagnostic["stage"] = "server_timeout"
                self.uncertain.add(peer)
                return {"state": "uncertain"}
            if action == "hash":
                mode = text.strip().removeprefix(">").strip()
                if mode in ("0", "1", "2"):
                    size = int(mode) + 1
                    text = f"Path hash size: {size} {'byte' if size == 1 else 'bytes'}"
                else:
                    text = "Path hash size unavailable: unexpected server response."
            diagnostic.update(stage="admin_response", matching_responses=1)
            return {"state": "admin_response", "text": text}
        except BaseException as error:
            diagnostic.update(stage="local_error", error_type=type(error).__name__)
            if may_have_sent:
                self.uncertain.add(peer)
            raise
        finally:
            subscription.unsubscribe()
            if not future.done():
                future.cancel()

    async def send_room(self, peer, text, *, request_id):
        peer = public_key(peer)
        row = await self._contact(peer)
        if row["kind"] != 3 or peer not in self.snapshot():
            raise ValueError("Log in to the room server before posting")
        return await self.messages.send_direct(
            peer, text, request_id=request_id, room=True
        )
