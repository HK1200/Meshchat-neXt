# SPDX-License-Identifier: MIT
"""Application-owned MeshCore lifecycle, separate from every Reticulum context."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from meshchatnext.src.backend.meshcore_channels import MeshCoreChannels
from meshchatnext.src.backend.meshcore_messaging import MeshCoreMessaging
from meshchatnext.src.backend.meshcore_session import MeshCoreSession
from meshchatnext.src.backend.meshcore_store import MeshCoreStore
from meshchatnext.src.backend.meshcore_transport import transport_platform


class IdentityChanged(ConnectionError):
    pass


def _save(path, selection):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with os.fdopen(
        os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w"
    ) as stream:
        json.dump(selection, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_selection(value):
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "target",
        "receive",
        "auto_reconnect",
        "owner",
    }:
        raise ValueError("Invalid MeshCore connection selection")
    if (
        value["kind"] not in ("ble", "usb")
        or not isinstance(value["target"], str)
        or not value["target"].strip()
        or len(value["target"]) > 256
    ):
        raise ValueError("Select an explicit USB device or BLE address")
    if type(value["receive"]) is not bool or type(value["auto_reconnect"]) is not bool:
        raise ValueError("Connection options must be booleans")
    if value["owner"] is not None:
        from meshchatnext.src.backend.meshcore_store import public_key

        public_key(value["owner"])
    return {**value, "target": value["target"].strip()}


class MeshCoreService:
    def __init__(
        self,
        folder,
        *,
        session_factory=MeshCoreSession,
        messenger_factory=MeshCoreMessaging,
        channel_factory=MeshCoreChannels,
        store_factory: Callable[[Path], MeshCoreStore] = MeshCoreStore,
        poll_interval=1,
        retry_max=30,
        notification_sink=None,
        state_folder=None,
        identity_claim=None,
    ):
        self.folder = Path(folder)
        self._state_folder = Path(state_folder) if state_folder else self.folder
        self._path = self._state_folder / "connection.json"
        self._identity_claim = identity_claim
        self._known_owner = None
        self._session_factory = session_factory
        self._messenger_factory = messenger_factory
        self._channel_factory = channel_factory
        self._store_factory = store_factory
        self._poll = poll_interval
        self._retry_max = retry_max
        self._lock = asyncio.Lock()
        self._task = None
        self._selection = None
        self._state = "disconnected"
        self._connection_id = None
        self._last_connection_issue = None
        self._store = None
        self.session = self.messages = self.channels = self.nodes = self.tools = None
        self.voice = None
        self.tactical = None
        self._closed = False
        self._notification_sink = notification_sink
        self._notification_task = None
        self._notifications = {}
        self._notification_waiting = asyncio.Event()

    async def _persist(self, selection):
        task = asyncio.create_task(asyncio.to_thread(_save, self._path, selection))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def start(self):
        async with self._lock:
            if self._task is not None or self._closed:
                return
            try:
                raw = await asyncio.to_thread(self._path.read_text)
                selection = json.loads(raw)
                self._selection = (
                    None if selection is None else validate_selection(selection)
                )
            except FileNotFoundError:
                pass
            except (ValueError, TypeError, OSError):
                self._state = "invalid_selection"
            from meshchatnext.src.backend.meshcore_store import public_key

            try:
                self._known_owner = public_key(
                    json.loads(
                        await asyncio.to_thread(
                            (self._state_folder / "ui-owner.json").read_text
                        )
                    )
                )
            except (FileNotFoundError, ValueError, TypeError, OSError):
                self._known_owner = None
            self._task = asyncio.create_task(self._watch())
            if self._notification_sink is not None:
                self._notification_task = asyncio.create_task(self._notify_loop())

    def _queue_notification(self, event):
        if self._closed or self._notification_sink is None:
            return
        key = event["owner"] + ":" + event["id"]
        if len(self._notifications) >= 256 and key not in self._notifications:
            self._notifications.pop(next(iter(self._notifications)))
        self._notifications[key] = event
        self._notification_waiting.set()

    def _notification_allowed(self, event):
        if event.get("kind") == "tactical":
            from meshchatnext.src.backend.meshcore_tactical import team_notification

            saved = team_notification(
                self.folder, event["owner"], event["notification_key"]
            )
            return bool(
                self.tactical
                and self.tactical.owner == event["owner"]
                and saved
                and saved["id"] == event["id"]
            )
        return self._store.notification_allowed(event)

    async def _notify_loop(self):
        while True:
            await self._notification_waiting.wait()
            await asyncio.sleep(0.05)
            pending, self._notifications = self._notifications, {}
            self._notification_waiting.clear()
            allowed = {}
            for event in pending.values():
                try:
                    if self._store and await asyncio.to_thread(
                        self._notification_allowed, event
                    ):
                        allowed[event["notification_key"]] = event
                except Exception:
                    pass
            for event in allowed.values():
                try:
                    # Recheck preferences/read markers immediately before dispatch.
                    if self._store and await asyncio.to_thread(
                        self._notification_allowed, event
                    ):
                        async with asyncio.timeout(5):
                            sink = self._notification_sink
                            if sink is not None:
                                await sink(event)
                except Exception:
                    pass  # No message payloads in logs; alerts never stop reception.

    def status(self):
        healthy = (
            self._state == "connected"
            and self.session is not None
            and self.session.is_connected
        )
        if self.messages is not None:
            healthy = healthy and not self.messages.status()["processing_failed"]
        return {
            "available": True,
            "bluetooth_discovery_supported": transport_platform()
            in ("android", "linux"),
            "radio_platform": transport_platform(),
            "state": ("connection_lost" if self._state == "connected" else self._state)
            if not healthy
            else "connected",
            "connected": bool(healthy),
            "connection_issue": None
            if healthy
            else (
                getattr(self.session, "connection_issue", None)
                or self._last_connection_issue
            ),
            "connection_id": self._connection_id if healthy else None,
            "selected": self._selection is not None,
            "connection": {
                "kind": self._selection["kind"],
                "target": self._selection["target"],
            }
            if self._selection
            else None,
            "receiving": bool(
                healthy and self._selection and self._selection["receive"]
            ),
            "auto_reconnect": bool(
                self._selection and self._selection["auto_reconnect"]
            ),
        }

    async def _close_connection(self):
        messages, session = self.messages, self.session
        if self.tactical is not None:
            await self.tactical.beacon_stop()
            await self.tactical.cot.close()
        if self.voice is not None:
            await self.voice.close()
            self.voice = None
        if self.tools is not None:
            await self.tools.close()
        self._last_connection_issue = self._last_connection_issue or getattr(
            session, "connection_issue", None
        )
        self.messages = self.session = self.channels = self.nodes = self.tools = None
        self.tactical = None
        if messages is not None:
            await messages.close()
        elif session is not None:
            await session.disconnect()

    async def _dial(self):
        await self._close_connection()
        self._state = "connecting"
        selection = self._selection
        session = self._session_factory()
        self.session = session
        try:
            await session.connect(selection["kind"], selection["target"])
            identity = await session.read_identity()
            if (
                selection["owner"] is not None
                and identity["public_key"] != selection["owner"]
            ):
                raise IdentityChanged("Selected device identity changed")
            if self._identity_claim is not None:
                await self._identity_claim(identity["public_key"])
            if self._store is None:
                self._store = await asyncio.to_thread(
                    self._store_factory, self.folder / "history.sqlite"
                )
            self.messages = self._messenger_factory(session, self._store)
            self.messages.on_message = self._queue_notification
            await self.messages.open()
            from meshchatnext.src.backend.meshcore_credentials import NodePasswords
            from meshchatnext.src.backend.meshcore_nodes import MeshCoreNodes

            self.nodes = MeshCoreNodes(self.messages, NodePasswords())
            from meshchatnext.src.backend.meshcore_tools import MeshCoreTools

            self.tools = MeshCoreTools(self.messages, self.nodes)
            if (
                getattr(getattr(self.messages, "_types", None), "RAW_DATA", None)
                is not None
            ):
                from meshchatnext.src.backend.meshcore_voice import MeshCoreVoice

                self.voice = MeshCoreVoice(self.messages, self.folder)
                self.messages.voice = self.voice
            self.channels = self._channel_factory(self.messages)
            self.messages.channels = self.channels
            await self.channels.refresh()
            if callable(
                getattr(
                    getattr(getattr(self.messages, "_client", None), "commands", None),
                    "send_channel_data",
                    None,
                )
            ):
                from meshchatnext.src.backend.meshcore_tactical import MeshCoreTactical

                self.tactical = MeshCoreTactical(
                    self.messages, self.channels, self.folder
                )
                self.messages.tactical = self.tactical
                self.tactical.on_notification = self._queue_notification
            self._known_owner = identity["public_key"]
            selection["owner"] = identity["public_key"]
            await asyncio.to_thread(
                _save, self._state_folder / "ui-owner.json", identity["public_key"]
            )
            await self._persist(selection)
            if selection["receive"]:
                await self.messages.start_receiving()
            self._connection_id = uuid.uuid4().hex
            self._state = "connected"
            self._last_connection_issue = None
            auto = await asyncio.to_thread(
                self._store.region_automation, self.messages.owner
            )
            if auto["enabled"]:
                await self.tools.start_region_scan(automatic=True)
        except BaseException as error:
            await self._close_connection()
            self._state = (
                "identity_changed"
                if isinstance(error, IdentityChanged)
                else "connection_lost"
            )
            raise

    async def connect(self, kind, target, *, receive=False, auto_reconnect=True):
        selection = validate_selection(
            {
                "kind": kind,
                "target": target,
                "receive": receive,
                "auto_reconnect": auto_reconnect,
                "owner": None,
            }
        )
        async with self._lock:
            if self._closed:
                raise RuntimeError("MeshCore service is closed")
            self._selection = selection
            await self._persist(selection)
            await self._dial()
            return self.status()

    async def disconnect(self):
        async with self._lock:
            self._selection = None
            await self._persist(None)
            await self._close_connection()
            self._state = "disconnected"
            return self.status()

    async def _watch(self):
        delay = self._poll
        while True:
            await asyncio.sleep(delay)
            async with self._lock:
                selection = self._selection
                if (
                    selection is None
                    or not selection["auto_reconnect"]
                    or self._state == "identity_changed"
                ):
                    delay = self._poll
                    continue
                if self.status()["connected"]:
                    delay = self._poll
                    continue
                try:
                    await self._dial()
                    delay = self._poll
                except Exception:
                    delay = min(self._retry_max, max(self._poll, delay * 2))

    async def ui(
        self,
        account,
        *,
        peer=None,
        read_through=None,
        contact=None,
        link_peer=None,
        linking=False,
        expected_owner=None,
        channel=None,
        ui_action=None,
        ui_body=None,
    ):
        from meshchatnext.src.backend.meshcore_store import notification_key, public_key

        async with self._lock:
            owner = self._selection.get("owner") if self._selection else None
            if owner is None:
                try:
                    owner = public_key(
                        json.loads(
                            await asyncio.to_thread(
                                (self._state_folder / "ui-owner.json").read_text
                            )
                        )
                    )
                except FileNotFoundError:
                    if linking or read_through is not None or ui_action is not None:
                        raise ConnectionError(
                            "No MeshCore identity is selected"
                        ) from None
                    return {
                        **self.status(),
                        "owner": None,
                        "contacts": [],
                        "links": [],
                        "conversations": [],
                        "announces": [],
                        "channels": [],
                        "nodes": [],
                        "channel_banishments": [],
                        "channel_messages": [],
                        "messages": [],
                    }
            if self._store is None:
                self._store = await asyncio.to_thread(
                    self._store_factory, self.folder / "history.sqlite"
                )
            if expected_owner is not None and expected_owner != owner:
                raise ValueError("MeshCore identity changed; refresh before editing")
            if linking:
                await asyncio.to_thread(
                    self._store.link_contact, owner, account, contact, link_peer
                )
            if read_through is not None:
                await asyncio.to_thread(
                    self._store.mark_read, owner, peer, read_through
                )
            if ui_action is not None:
                methods = {
                    "channel-read": "channel_preference",
                    "channel-order": "reorder_channels",
                    "channel-mute": "channel_preference",
                    "channel-scope": "channel_scope",
                    "channel-visibility": "channel_visibility",
                    "node-save": "node_preference",
                    "node-remove": "node_preference",
                    "channel-banish": "banish_channel_sender",
                    "channel-unbanish": "unbanish_channel_sender",
                }
                if ui_action not in methods:
                    raise ValueError("Invalid UI action")
                if not isinstance(ui_body, dict):
                    raise ValueError("Invalid UI action body")
                body = dict(ui_body)
                if ui_action.startswith("node-"):
                    body["saved"] = ui_action == "node-save"
                await asyncio.to_thread(
                    getattr(self._store, methods[ui_action]), owner, **body
                )
            result = await asyncio.to_thread(self._store.ui_snapshot, owner, account)
            result["regions"] = await asyncio.to_thread(self._store.regions, owner)
            result["channel_default_scope"] = await asyncio.to_thread(
                self._store.region_default, owner
            )
            result["region_auto_scan"] = (
                await asyncio.to_thread(self._store.region_automation, owner)
            )["enabled"]
            result["region_scan"] = (
                dict(self.tools.region_scan) if self.tools else {"state": "idle"}
            )
            result.update(self.status())
            result["voice_jobs"] = dict(self.voice.jobs) if self.voice else {}
            result["node_sessions"] = self.nodes.snapshot() if self.nodes else {}
            result["node_operations"] = (
                dict(self.nodes.operations) if self.nodes else {}
            )
            client = getattr(self.session, "_client", None)
            if client is not None:
                cached_contacts = getattr(client, "contacts", {})
                for node in result["nodes"]:
                    cached = cached_contacts.get(node["peer"], {})
                    hops = cached.get("out_path_len")
                    mode = cached.get("out_path_hash_mode")
                    if type(hops) is int and -1 <= hops <= 63:
                        node["outbound_hops"] = hops
                    if type(mode) is int and -1 <= mode <= 2:
                        node["outbound_hash_bytes"] = max(mode, 0) + 1
            result["account"] = account
            if peer is not None:
                result["messages"] = await asyncio.to_thread(
                    self._store.history, owner, peer, 1000
                )
            if channel is not None:
                result["channel_messages"] = await asyncio.to_thread(
                    self._store.channel_history, owner, public_key(channel), 1000
                )
            if peer is not None or channel is not None:
                result["message_view"] = await asyncio.to_thread(
                    self._store.message_view,
                    owner,
                    "channel" if channel is not None else "direct",
                    channel if channel is not None else peer,
                )
            if peer is not None or channel is not None:
                result["active_notification_key"] = notification_key(
                    owner,
                    "channel" if channel is not None else "direct",
                    channel if channel is not None else peer,
                )
            return result

    async def notification_target(self, account, key):
        snapshot = await self.ui(account)
        if not snapshot.get("owner"):
            return None
        from meshchatnext.src.backend.meshcore_tactical import team_notification

        event = await asyncio.to_thread(
            team_notification, self.folder, snapshot["owner"], key
        )
        if event:
            return {
                "owner": snapshot["owner"],
                "kind": "tactical",
                "target": event["target"],
                **(
                    {"shape": event["shape"]}
                    if "shape" in event
                    else {"item": event["item"]}
                ),
            }
        return await asyncio.to_thread(
            self._store.notification_target, snapshot["owner"], key
        )

    async def message_window(
        self, account, kind, target, *, expected_owner, anchor=None, after=None
    ):
        snapshot = await self.ui(account)
        if not snapshot.get("owner") or snapshot.get("owner") != expected_owner:
            raise ValueError("MeshCore identity changed")
        return await asyncio.to_thread(
            self._store.message_window,
            expected_owner,
            kind,
            target,
            anchor=anchor,
            after=after,
        )

    async def message_details(
        self, account, kind, target, message_id, *, expected_owner
    ):
        snapshot = await self.ui(account)
        if not expected_owner or snapshot.get("owner") != expected_owner:
            raise ValueError("MeshCore identity changed")
        result = await asyncio.to_thread(
            self._store.message_details, expected_owner, kind, target, message_id
        )
        if (await self.ui(account)).get("owner") != expected_owner:
            raise ValueError("MeshCore identity changed")
        return result

    async def cached_voice(self, peer, sid, direction, expected_owner):
        from meshchatnext.src.backend.meshcore_store import public_key
        from meshchatnext.src.backend.meshcore_voice import play_cached

        async with self._lock:
            owner = self._selection.get("owner") if self._selection else None
            if owner is None:
                owner = public_key(
                    json.loads(
                        await asyncio.to_thread(
                            (self._state_folder / "ui-owner.json").read_text
                        )
                    )
                )
            if public_key(expected_owner) != owner:
                raise ValueError("MeshCore identity changed")
            return await asyncio.to_thread(
                play_cached, self.folder, owner, peer, sid, direction
            )

    async def map_snapshot(self, account):
        # ui() resolves the saved selected owner even when the radio is offline.
        result = await self.ui(account)
        owner = result.get("owner")
        nodes = (
            await asyncio.to_thread(self._store.map_nodes, owner)
            if owner and self._store
            else []
        )
        from meshchatnext.src.backend.meshcore_tactical import snapshot as team_snapshot

        tactical = (
            await asyncio.to_thread(team_snapshot, self.folder, owner)
            if owner
            else None
        )
        # Reject a stale snapshot if the selected radio changed while reading disk.
        latest = await self.ui(account)
        if latest.get("owner") != owner:
            raise ValueError("MeshCore identity changed; refresh map")
        return {
            "owner": owner,
            "connected": latest.get("connected", False),
            "nodes": nodes,
            "tactical": tactical,
            "contacts": latest.get("contacts", []),
            "team_supported": self.tactical is not None,
            "channel_default_scope": latest.get("channel_default_scope"),
            "channels": latest.get("channels", []),
        }

    async def call(self, component, method, *args, **kwargs):
        async with self._lock:
            if not self.status()["connected"]:
                raise ConnectionError("MeshCore is disconnected")
            expected_owner = kwargs.pop("expected_owner", None)
            if expected_owner is not None and expected_owner != self.messages.owner:
                raise ValueError("MeshCore identity changed; refresh before sending")
            if component not in (
                "session",
                "messages",
                "channels",
                "nodes",
                "tools",
                "voice",
                "tactical",
            ):
                raise ValueError("Invalid MeshCore component")
            target = getattr(self, component)
            if target is None:
                raise ValueError("This MeshCore capability is unavailable")
            result = await getattr(target, method)(*args, **kwargs)
            if (
                component == "session"
                and method in ("set_name", "read_identity")
                and self._store
            ):
                await asyncio.to_thread(
                    self._store.update_profile_name,
                    result["public_key"],
                    result["name"],
                )
            return result

    async def set_receiving(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Receiving must be a boolean")
        async with self._lock:
            if self._selection is None:
                raise ConnectionError("No MeshCore device is selected")
            self._selection["receive"] = enabled
            # Rebuild to stop/start workers without cancelling a commit in flight.
            await self._dial()
            return self.status()

    async def restore(self, backup, password, *, expected_current_public_key):
        from meshchatnext.src.backend.meshcore_identity import decrypt_backup

        await asyncio.to_thread(decrypt_backup, backup, password)
        async with self._lock:
            return await self._restore_locked(
                backup,
                password,
                expected_current_public_key=expected_current_public_key,
            )

    async def _restore_locked(self, backup, password, *, expected_current_public_key):
        if not self.status()["connected"]:
            raise ConnectionError("MeshCore is disconnected")
        # Keep all queued messages on the old account before changing keys.
        async with self.session._lock:
            await self.messages._drain_pending()
            await self.messages._stop()
        try:
            identity = await self.session.restore_identity(
                backup,
                password,
                expected_current_public_key=expected_current_public_key,
            )
            self._selection["owner"] = identity["public_key"]
            await self._persist(self._selection)
        except BaseException:
            # A missing response may hide an applied identity change. Pin the
            # old owner, stop workers, and inspect on reconnect; never retry import.
            await self._close_connection()
            self._state = "connection_lost"
            raise
        await self._dial()
        return identity

    async def config_result(self, owner, request_id):
        import uuid

        from meshchatnext.src.backend.meshcore_store import public_key

        owner = public_key(owner)
        if str(uuid.UUID(request_id)) != request_id:
            raise ValueError("Invalid import request ID")
        if self._store is None:
            self._store = await asyncio.to_thread(
                self._store_factory, self.folder / "history.sqlite"
            )
        return await asyncio.to_thread(
            self._store.config_import_result, owner, request_id
        )

    async def config_preview(self, text, password=None):
        from meshchatnext.src.backend.meshcore_config import live_review, parse_config

        plan = await asyncio.to_thread(parse_config, text, password)
        async with self._lock:
            return await live_review(self, plan)

    async def config_apply(
        self,
        text,
        sections,
        expected_owner,
        preview_id,
        request_id,
        replace_identity=False,
        password=None,
    ):
        from meshchatnext.src.backend.meshcore_config import apply_config, parse_config

        plan = await asyncio.to_thread(parse_config, text, password)
        async with self._lock:
            return await apply_config(
                self,
                plan,
                sections,
                expected_owner,
                preview_id,
                request_id,
                replace_identity,
            )

    async def close(self):
        self._closed = True
        if self._notification_task is not None:
            self._notification_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._notification_task
            self._notification_task = None
        self._notifications.clear()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        async with self._lock:
            await self._close_connection()
            self._state = "stopped"
