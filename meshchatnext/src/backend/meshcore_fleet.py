# SPDX-License-Identifier: MIT
"""Independent MeshCore companion lifecycles and explicit per-request routing."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from pathlib import Path

from meshchatnext.src.backend.meshcore_service import (
    IdentityChanged,
    MeshCoreService,
    _save,
    validate_selection,
)
from meshchatnext.src.backend.meshcore_store import MeshCoreStore, notification_key


class MeshCoreFleet:
    MAX_RADIOS = 8

    def __init__(
        self, folder, *, notification_sink=None, service_factory=MeshCoreService
    ):
        self.folder = Path(folder)
        self._path = self.folder / "radios.json"
        self._factory = service_factory
        self._sink = notification_sink
        self._radios = {}
        self._labels = {}
        self._claims = {}
        self._lock = asyncio.Lock()
        self._claim_lock = asyncio.Lock()
        self._store = None
        self._store_lock = threading.Lock()
        self._active = "default"
        self._view = "combined"
        self._closed = False
        self._started = False
        self._config_error = None
        self._initial_tasks = set()
        self._reservations = {}
        self._connection_locks = {}

    def _shared_store(self, path):
        with self._store_lock:
            if self._store is None:
                self._store = MeshCoreStore(path)
            return self._store

    def _create(self, radio_id, label):
        async def claim(owner):
            async with self._claim_lock:
                existing = self._claims.get(owner)
                if existing is not None and existing != radio_id:
                    raise IdentityChanged(
                        "Another saved radio already uses this MeshCore identity"
                    )
                self._claims = {
                    key: value
                    for key, value in self._claims.items()
                    if value != radio_id
                }
                self._claims[owner] = radio_id

        async def notify(event):
            if self._sink is not None:
                await self._sink(
                    {
                        **event,
                        "radio_id": radio_id,
                        "radio_label": self._labels[radio_id],
                    }
                )

        service = self._factory(
            self.folder,
            state_folder=self.folder
            if radio_id == "default"
            else self.folder / "radios" / radio_id,
            identity_claim=claim,
            notification_sink=notify if self._sink is not None else None,
            store_factory=self._shared_store,
        )
        self._connection_locks[radio_id] = asyncio.Lock()
        self._radios[radio_id] = service
        self._labels[radio_id] = label
        return service

    async def _persist(self):
        await asyncio.to_thread(
            _save,
            self._path,
            {
                "schema": 1,
                "active": self._active,
                "view": self._view,
                "radios": [
                    {"id": key, "label": self._labels[key]} for key in self._radios
                ],
            },
        )

    @staticmethod
    def _label(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 80:
            raise ValueError("Give the radio a name of up to 80 characters")
        return value.strip()

    async def start(self):
        if self._started or self._closed:
            return
        self._started = True
        entries = [{"id": "default", "label": "MeshCore radio"}]
        try:
            data = json.loads(await asyncio.to_thread(self._path.read_text))
            if (
                not isinstance(data, dict)
                or set(data) != {"schema", "active", "view", "radios"}
                or data["schema"] != 1
                or data["view"] not in ("combined", "separate")
                or not isinstance(data["radios"], list)
                or not 1 <= len(data["radios"]) <= self.MAX_RADIOS
            ):
                raise ValueError("Invalid saved radios")
            seen = set()
            for row in data["radios"]:
                if not isinstance(row, dict) or set(row) != {"id", "label"}:
                    raise ValueError("Invalid saved radio")
                key = row["id"]
                if key != "default" and (
                    not isinstance(key, str)
                    or len(key) != 32
                    or uuid.UUID(hex=key).hex != key
                ):
                    raise ValueError("Invalid saved radio identifier")
                if key in seen:
                    raise ValueError("Duplicate saved radio")
                seen.add(key)
                self._label(row["label"])
            if "default" not in seen or data["active"] not in seen:
                raise ValueError("Invalid active radio")
            entries = data["radios"]
            self._active, self._view = data["active"], data["view"]
        except FileNotFoundError:
            pass  # Existing connection.json remains in place without migration.
        except (ValueError, TypeError, KeyError, OSError):
            self._config_error = "Saved radio list could not be read; the original radio remains available"
        for row in entries:
            self._create(row["id"], row["label"])
        await asyncio.gather(*(service.start() for service in self._radios.values()))

    @staticmethod
    def _owner(service):
        return (service._selection or {}).get("owner") or service._known_owner

    def resolve(self, radio_id=None, expected_owner=None):
        if radio_id is not None:
            if radio_id not in self._radios:
                raise ValueError("Select a saved MeshCore radio")
            service = self._radios[radio_id]
            if expected_owner is not None:
                if self._owner(service) != expected_owner:
                    raise ValueError("The selected radio identity changed")
            return service
        if expected_owner is not None:
            matches = [
                service
                for service in self._radios.values()
                if self._owner(service) == expected_owner
            ]
            if len(matches) != 1:
                raise ValueError("Select the radio for this MeshCore identity")
            return matches[0]
        return self._radios[self._active]

    def _id(self, service):
        return next(key for key, value in self._radios.items() if value is service)

    def radio_rows(self):
        return [
            {
                "id": key,
                "label": self._labels[key],
                **service.status(),
                "owner": self._owner(service),
            }
            for key, service in self._radios.items()
        ]

    def status(self, radio_id=None):
        if not self._radios:
            return {"available": True, "connected": False, "radios": []}
        key = radio_id or self._active
        return {
            **self.resolve(key).status(),
            "radio_id": key,
            "radio_label": self._labels[key],
            "radios": self.radio_rows(),
            "inbox_mode": self._view,
            "radios_error": self._config_error,
        }

    async def configure(self, *, radio_id=None, label=None, view=None, active=None):
        async with self._lock:
            if label is not None:
                self.resolve(radio_id)
                self._labels[radio_id or self._active] = self._label(label)
            if view is not None:
                if view not in ("combined", "separate"):
                    raise ValueError("Select combined or separate radio views")
                self._view = view
            if active is not None:
                self.resolve(active)
                self._active = active
            await self._persist()
        return self.status()

    @staticmethod
    def _endpoint(kind, target):
        if not isinstance(target, str):
            raise ValueError("Select a radio device")
        return kind, target.strip().casefold() if kind == "ble" else os.path.realpath(
            target.strip()
        )

    async def add(self, *, kind, target, label, auto_reconnect=True, receive=True):
        selection = validate_selection(
            {
                "kind": kind,
                "target": target,
                "owner": None,
                "auto_reconnect": auto_reconnect,
                "receive": receive,
            }
        )
        label = self._label(label)
        async with self._lock:
            if self._closed:
                raise RuntimeError("MeshCore is stopped")
            if len(self._radios) >= self.MAX_RADIOS:
                raise ValueError("Too many saved radios")
            endpoint = self._endpoint(kind, target)
            for radio_id, service in self._radios.items():
                saved = service._selection
                if (
                    saved and self._endpoint(saved["kind"], saved["target"]) == endpoint
                ) or self._reservations.get(radio_id) == endpoint:
                    raise ValueError("This device is already saved")
            key = uuid.uuid4().hex
            service = self._create(key, label)
            # Save intent before the first attempt, including when the radio is away.
            service._selection = selection
            await service._persist(selection)
            await self._persist()
            await service.start()
        if not auto_reconnect:
            task = asyncio.create_task(self._connect_once(service))
            self._initial_tasks.add(task)
            task.add_done_callback(self._initial_tasks.discard)
        # Each child's watcher connects; one absent radio cannot block another.
        return {**self.status(), "added_radio_id": key}

    async def _connect_once(self, service):
        try:
            async with service._lock:
                if not service._closed:
                    await service._dial()
        except (ConnectionError, OSError, RuntimeError, ValueError):
            pass

    async def connect(self, *, radio_id=None, **options):
        service = self.resolve(radio_id)
        key = self._id(service)
        async with self._connection_locks[key]:
            validated = validate_selection(
                {
                    "kind": options.get("kind"),
                    "target": options.get("target"),
                    "owner": None,
                    "receive": options.get("receive", False),
                    "auto_reconnect": options.get("auto_reconnect", True),
                }
            )
            target = self._endpoint(validated["kind"], validated["target"])
            for other_id, other in self._radios.items():
                saved = other._selection
                if other is not service and (
                    (saved and self._endpoint(saved["kind"], saved["target"]) == target)
                    or self._reservations.get(other_id) == target
                ):
                    raise ValueError("This device is already saved")
            self._reservations[key] = target
            try:
                return await service.connect(**options)
            finally:
                self._reservations.pop(key, None)

    async def set_enabled(self, radio_id, enabled):
        if type(enabled) is not bool:
            raise ValueError("Enabled must be a boolean")
        async with self._lock:
            service = self.resolve(radio_id)
            if service._selection is None:
                raise ValueError("Select a device for this radio first")
            # Stop a slow out-of-range attempt before taking the child lock.
            task = service._task if not enabled else None
            restart_watch = task is not None
            if task is not None:
                service._task = None
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            async with service._lock:
                service._selection["auto_reconnect"] = enabled
                await service._persist(service._selection)
                if not enabled:
                    await service._close_connection()
                    service._state = "disconnected"
            if restart_watch and not service._closed:
                service._task = asyncio.create_task(service._watch())
        return self.status()

    async def remove(self, radio_id):
        async with self._lock:
            service = self.resolve(radio_id)
            if radio_id == "default":
                raise ValueError(
                    "Disconnect the original radio instead; its saved history is retained"
                )
            await service.close()
            await service.disconnect()
            del self._radios[radio_id]
            del self._labels[radio_id]
            self._connection_locks.pop(radio_id, None)
            self._claims = {
                key: value for key, value in self._claims.items() if value != radio_id
            }
            if self._active == radio_id:
                self._active = "default"
            await self._persist()
        return self.status()

    async def _saved_ui(self, service, account, *, peer=None, channel=None):
        """An unavailable companion must not hold other radios' inboxes hostage."""
        owner = self._owner(service)
        if owner is None:
            return {
                **service.status(),
                "owner": None,
                "contacts": [],
                "links": [],
                "conversations": [],
                "messages": [],
                "channels": [],
                "nodes": [],
                "announces": [],
                "channel_messages": [],
                "channel_banishments": [],
                "voice_jobs": {},
                "node_sessions": {},
                "node_operations": {},
                "regions": [],
                "channel_default_scope": None,
                "region_auto_scan": False,
                "region_scan": {"state": "idle"},
                "profile_name": None,
            }

        def read():
            store = self._shared_store(self.folder / "history.sqlite")
            data = store.ui_snapshot(owner, account)
            data.update(
                regions=store.regions(owner),
                channel_default_scope=store.region_default(owner),
                region_auto_scan=store.region_automation(owner)["enabled"],
                region_scan={"state": "idle"},
                voice_jobs={},
                node_sessions={},
                node_operations={},
                account=account,
            )
            if peer is not None:
                data["messages"] = store.history(owner, peer, 1000)
            if channel is not None:
                data["channel_messages"] = store.channel_history(owner, channel, 1000)
            if peer is not None or channel is not None:
                data["message_view"] = store.message_view(
                    owner,
                    "channel" if channel is not None else "direct",
                    channel if channel is not None else peer,
                )
                data["active_notification_key"] = notification_key(
                    owner,
                    "channel" if channel is not None else "direct",
                    channel if channel is not None else peer,
                )
            return data

        return {**await asyncio.to_thread(read), **service.status()}

    async def ui(
        self, account, *, peer=None, channel=None, radio_id=None, expected_owner=None
    ):
        service = self.resolve(radio_id, expected_owner)
        key = self._id(service)
        if service._lock.locked() and not service.status()["connected"]:
            result = await self._saved_ui(service, account, peer=peer, channel=channel)
        else:
            result = await service.ui(account, peer=peer, channel=channel)
        result.update(
            radio_id=key,
            radio_label=self._labels[key],
            radios=self.radio_rows(),
            inbox_mode=self._view,
            radios_error=self._config_error,
        )
        if self._view == "combined" and peer is None and channel is None:
            rows = []
            for radio, child in list(self._radios.items()):
                snapshot = (
                    result if child is service else await self._saved_ui(child, account)
                )
                rows.extend(
                    {
                        **row,
                        "radio_id": radio,
                        "radio_label": self._labels[radio],
                        "owner": snapshot.get("owner"),
                    }
                    for row in snapshot["conversations"]
                )
            result["conversations"] = sorted(
                rows,
                key=lambda row: row.get("created", row.get("timestamp", 0)),
                reverse=True,
            )
        else:
            result["conversations"] = [
                {
                    **row,
                    "radio_id": key,
                    "radio_label": self._labels[key],
                    "owner": result.get("owner"),
                }
                for row in result["conversations"]
            ]
        return result

    async def notification_target(self, account, key):
        from meshchatnext.src.backend.meshcore_tactical import team_notification

        for radio_id, service in list(self._radios.items()):
            owner = self._owner(service)
            if owner is None:
                continue
            event = await asyncio.to_thread(team_notification, self.folder, owner, key)
            if event:
                return {
                    **event,
                    "owner": owner,
                    "kind": "tactical",
                    "radio_id": radio_id,
                }
            store = await asyncio.to_thread(
                self._shared_store, self.folder / "history.sqlite"
            )
            target = await asyncio.to_thread(store.notification_target, owner, key)
            if target is not None:
                return {**target, "radio_id": radio_id}
        return None

    async def close(self):
        self._closed = True
        tasks = list(self._initial_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(service.close() for service in self._radios.values()))
