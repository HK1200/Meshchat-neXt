# SPDX-License-Identifier: MIT
"""Internal API; registered behind the application's auth, CSRF and IP middleware."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
from pathlib import Path

from aiohttp import web

from meshchatnext.src.backend.constants import API_V1_PREFIX
from meshchatnext.src.backend.http.uploads import (
    PayloadTooLargeError,
    read_json_limited,
)
from meshchatnext.src.backend.meshcore_fleet import MeshCoreFleet
from meshchatnext.src.backend.meshcore_voice import VoiceCapabilityError
from meshchatnext.src.backend.privacy_mode import (
    OutboundHttpBlockedError,
    ensure_outbound_http_allowed,
)

HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


async def _read(service, owner, request, action):
    radio_context = None
    if isinstance(service, MeshCoreFleet):
        if action == "ui":
            return await service.ui(
                owner.identity.hash.hex(),
                peer=request.query.get("peer"),
                channel=request.query.get("channel_id"),
                radio_id=request.query.get("radio"),
                expected_owner=request.query.get("owner"),
            )
        if action == "notification-target":
            return await service.notification_target(
                owner.identity.hash.hex(), request.query.get("key")
            )
        selected = service.resolve(
            request.query.get("radio"), request.query.get("owner")
        )
        radio_context = service._id(selected)
        service = selected
    reads = {
        "identity": ("session", "read_identity"),
        "clock": ("session", "read_clock"),
        "battery": ("session", "read_battery"),
        "settings": ("session", "read_settings"),
        "radio2": ("session", "read_radio2"),
        "contacts": ("messages", "sync_contacts"),
        "channels": ("channels", "refresh"),
    }
    if action == "notification-target":
        result = await service.notification_target(
            owner.identity.hash.hex(), request.query.get("key")
        )
    elif action == "message-details":
        result = await service.message_details(
            owner.identity.hash.hex(),
            request.query.get("kind"),
            request.query.get("target"),
            request.query.get("id"),
            expected_owner=request.query.get("owner"),
        )
    elif action == "message-window":
        result = await service.message_window(
            owner.identity.hash.hex(),
            request.query.get("kind"),
            request.query.get("target"),
            expected_owner=request.query.get("owner"),
            anchor=request.query.get("anchor"),
            after=request.query.get("after"),
        )
    elif action == "config-result":
        result = await service.config_result(
            request.query.get("owner"), request.query.get("request_id")
        )
    elif action == "usb-devices":
        from meshchatnext.src.backend.meshcore_transport import (
            attached_usb_devices,
        )

        result = await asyncio.to_thread(attached_usb_devices)
    elif action == "bluetooth-devices":
        from meshchatnext.src.backend.meshcore_transport import (
            available_ble_devices,
        )

        result = await available_ble_devices()
    elif action == "tak-status":
        if not request.query.get("owner"):
            raise ValueError("Select an identity")
        result = await service.call(
            "tactical", "cot_status", expected_owner=request.query["owner"]
        )
    elif action == "topology":
        result = await service.topology_snapshot(owner.identity.hash.hex())
        if radio_context is not None:
            result["radio_id"] = radio_context
    elif action == "map":
        result = await service.map_snapshot(owner.identity.hash.hex())
        if radio_context is not None:
            result["radio_id"] = radio_context
    elif action == "ui":
        result = await service.ui(
            owner.identity.hash.hex(),
            peer=request.query.get("peer"),
            channel=request.query.get("channel_id"),
        )
    elif action in reads:
        result = await service.call(*reads[action])
    elif action == "history":
        result = await service.call(
            "messages",
            "history",
            request.query.get("peer"),
            limit=int(request.query.get("limit", "100")),
        )
    elif action == "channel-history":
        result = await service.call(
            "channels",
            "history",
            request.query.get("channel_id"),
            limit=int(request.query.get("limit", "100")),
        )
    else:
        raise web.HTTPNotFound()
    return result


async def _write(service, owner, request, action):
    body = await read_json_limited(
        request,
        max_bytes=16 * 1024 * 1024
        if action == "tak-package-upload"
        else 4 * 1024 * 1024
        if action
        in (
            "config-preview",
            "config-apply",
            "voice-prepare",
            "image-prepare",
            "team-attachment-prepare",
            "tak-connect",
            "tak-enroll",
            "tak-package-upload",
        )
        else 16384,
    )
    specs: dict[str, tuple[set[str], set[str]]] = {
        "config-preview": ({"text"}, {"password"}),
        "config-apply": (
            {
                "text",
                "sections",
                "expected_owner",
                "preview_id",
                "request_id",
            },
            {"replace_identity", "password"},
        ),
        "usb-permission": ({"path"}, set()),
        "connect": ({"kind", "target"}, {"receive", "auto_reconnect"}),
        "radio-add": ({"kind", "target", "label"}, {"receive", "auto_reconnect"}),
        "radio-configure": (set(), {"radio_id", "label", "view", "active"}),
        "radio-remove": ({"radio_id"}, set()),
        "radio-enabled": ({"radio_id", "enabled"}, set()),
        "team-attachment-prepare": (
            {"pcm_base64", "request_id", "expected_owner", "expected_channel_id"},
            set(),
        ),
        "team-attachment-fetch": (
            {
                "peer",
                "kind",
                "item_id",
                "alias",
                "expected_owner",
                "expected_channel_id",
            },
            set(),
        ),
        "team-shape-preview": ({"record", "expected_owner"}, set()),
        "team-configure": (
            {"enabled", "expected_owner"},
            {
                "channel_id",
                "callsign",
                "role",
                "color",
                "status",
                "monitor_geofences",
                "notify_team_alerts",
            },
        ),
        "team-beacon-start": (
            {"expected_owner", "interval", "expected_channel_id", "expected_scope"},
            {"source", "duration_minutes"},
        ),
        "team-beacon-stop": ({"expected_owner"}, {"token"}),
        "team-beacon-status": ({"expected_owner"}, set()),
        "team-beacon-position": (
            {
                "expected_owner",
                "token",
                "latitude",
                "longitude",
                "accuracy",
                "timestamp",
            },
            set(),
        ),
        "tak-connect": (
            {"expected_owner", "host", "port"},
            {
                "ca",
                "certificate",
                "private_key",
                "auto_protocol",
                "https_port",
                "username",
                "password",
            },
        ),
        "tak-enroll": (
            {"expected_owner", "host", "port", "username", "password"},
            {"ca"},
        ),
        "tak-package-search": ({"expected_owner"}, {"keywords"}),
        "tak-package-download": ({"expected_owner", "digest"}, set()),
        "tak-package-upload": ({"expected_owner", "zip_base64", "name"}, {"private"}),
        "tak-disconnect": ({"expected_owner"}, set()),
        "tak-send": ({"expected_owner", "record"}, set()),
        "team-send": (
            {
                "record",
                "request_id",
                "expected_owner",
                "expected_channel_id",
                "expected_scope",
            },
            set(),
        ),
        "contact-link": ({"contact", "peer"}, {"expected_owner"}),
        "contact-add": ({"peer", "name"}, {"expected_owner"}),
        "read": ({"peer", "through"}, {"expected_owner"}),
        "voice-prepare": (
            {"peer", "pcm_base64", "request_id", "expected_owner"},
            set(),
        ),
        "image-prepare": (
            {"peer", "rgb_base64", "width", "height", "request_id", "expected_owner"},
            set(),
        ),
        "media-channel-send": (
            {"channel_id", "sid", "request_id", "expected_owner", "expected_scope"},
            set(),
        ),
        "media-channel-fetch": (
            {"channel_id", "message_id", "expected_owner", "expected_scope"},
            set(),
        ),
        "voice-send": (
            {"peer", "sid", "request_id", "expected_owner"},
            set(),
        ),
        "voice-fetch": ({"peer", "message_id", "expected_owner"}, set()),
        "voice-play": (
            {"peer", "sid", "direction", "expected_owner"},
            set(),
        ),
        "voice-discard": ({"peer", "sid", "expected_owner"}, set()),
        "node-login": (
            {"peer", "expected_owner"},
            {"password", "remember", "use_saved_role"},
        ),
        "node-password-status": ({"peer", "expected_owner"}, set()),
        "node-password-save": (
            {"peer", "role", "password", "expected_owner"},
            set(),
        ),
        "node-password-forget": ({"peer", "role", "expected_owner"}, set()),
        "node-logout": ({"peer", "expected_owner"}, set()),
        "node-status": ({"peer", "expected_owner"}, set()),
        "node-admin": (
            {"peer", "expected_owner", "action"},
            {"value", "confirmed"},
        ),
        "node-route": ({"peer", "expected_owner"}, set()),
        "room-message": (
            {"peer", "text", "request_id", "expected_owner"},
            set(),
        ),
        "disconnect": (set(), set()),
        "receiving": ({"enabled"}, set()),
        "name": ({"name"}, {"expected_owner"}),
        "backup": ({"password", "expected_public_key"}, set()),
        "restore": (
            {"backup", "password", "expected_current_public_key"},
            set(),
        ),
        "radio2": (
            {"enabled", "expected_owner"},
            {"frequency_mhz", "bandwidth_khz", "sf", "cr"},
        ),
        "settings": (
            set(),
            {
                "expected_owner",
                "frequency_mhz",
                "bandwidth_khz",
                "sf",
                "cr",
                "tx_power_dbm",
                "path_hash_bytes",
            },
        ),
        "announce": ({"expected_owner", "flood"}, set()),
        "tool-radio-stats": ({"expected_owner"}, set()),
        "tool-rx-log": ({"expected_owner"}, set()),
        "tool-trace": ({"expected_owner", "path"}, set()),
        "regions-scan": ({"expected_owner"}, set()),
        "regions-auto": ({"expected_owner", "enabled"}, set()),
        "regions-read": ({"expected_owner"}, set()),
        "regions-add": ({"expected_owner", "name"}, set()),
        "regions-default": ({"expected_owner", "scope"}, set()),
        "regions-discover": ({"expected_owner", "peer"}, set()),
        "channel-scope": ({"expected_owner", "channel", "scope"}, set()),
        "channel-visibility": (
            {"expected_owner", "channel", "hidden"},
            set(),
        ),
        "node-discover": ({"expected_owner"}, set()),
        "node-save": ({"peer", "expected_owner"}, set()),
        "node-remove": ({"peer", "expected_owner"}, set()),
        "channel-order": ({"channels", "expected_owner"}, set()),
        "channel-read": ({"channel", "through", "expected_owner"}, set()),
        "channel-mute": (
            {"channel", "muted", "expected_owner"},
            {"mentions_only"},
        ),
        "channel-banish": ({"channel", "message", "expected_owner"}, set()),
        "channel-unbanish": (
            {"channel", "sender", "expected_owner"},
            set(),
        ),
        "message": ({"peer", "text", "request_id"}, {"expected_owner"}),
        "channel-add": ({"name", "private"}, {"key_hex", "expected_owner"}),
        "channel-remove": (
            {"slot", "expected_channel_id", "expected_owner"},
            set(),
        ),
        "channel-key": ({"slot", "expected_channel_id"}, set()),
        "channel-message": (
            {"slot", "text", "expected_channel_id", "request_id"},
            {"expected_owner"},
        ),
    }
    if action not in specs:
        raise web.HTTPNotFound()
    required, optional = specs[action]
    if not required <= body.keys() or body.keys() - required - optional:
        raise ValueError("Invalid request fields")
    if isinstance(service, MeshCoreFleet):
        radio_id = request.query.get("radio")
        if action == "radio-add":
            return await service.add(**body)
        if action == "radio-configure":
            return await service.configure(**body)
        if action == "radio-remove":
            return await service.remove(**body)
        if action == "radio-enabled":
            return await service.set_enabled(**body)
        if action == "connect":
            return await service.connect(radio_id=radio_id, **body)
        service = service.resolve(
            radio_id,
            body.get("expected_owner") or body.get("expected_current_public_key"),
        )
    if "expected_owner" in required or action in (
        "radio2",
        "announce",
        "node-discover",
        "tool-radio-stats",
        "tool-rx-log",
        "tool-trace",
        "regions-scan",
        "regions-auto",
        "regions-read",
        "regions-add",
        "regions-default",
        "regions-discover",
        "channel-scope",
        "channel-visibility",
    ):
        from meshchatnext.src.backend.meshcore_store import public_key

        public_key(body["expected_owner"])
    if action in {
        "tak-connect",
        "tak-send",
        "tak-enroll",
        "tak-package-search",
        "tak-package-download",
        "tak-package-upload",
    }:
        ensure_outbound_http_allowed(
            getattr(owner, "config", None), feature="TAK server access"
        )
    if action == "usb-permission":
        from meshchatnext.src.backend.meshcore_transport import (
            permit_usb_device,
        )

        result = await asyncio.to_thread(permit_usb_device, body["path"])
    elif action == "voice-play":
        result = await service.cached_voice(**body)
    elif action == "config-preview":
        result = await service.config_preview(**body)
    elif action == "config-apply":
        result = await service.config_apply(**body)
    elif action in {
        "node-save",
        "node-remove",
        "channel-read",
        "channel-scope",
        "channel-visibility",
        "channel-order",
        "channel-mute",
        "channel-banish",
        "channel-unbanish",
    }:
        expected_owner = body.pop("expected_owner")
        from meshchatnext.src.backend.meshcore_store import public_key

        public_key(expected_owner)
        result = await service.ui(
            owner.identity.hash.hex(),
            ui_action=action,
            ui_body=body,
            expected_owner=expected_owner,
        )
    elif action == "contact-link":
        contact_id = body["contact"]
        if type(contact_id) is not int or (
            body["peer"] is not None
            and owner.database.contacts.get_contact(contact_id) is None
        ):
            raise ValueError("Select an existing Reticulum contact")
        result = await service.ui(
            owner.identity.hash.hex(),
            contact=contact_id,
            link_peer=body["peer"],
            linking=True,
            expected_owner=body.get("expected_owner"),
        )
    elif action == "read":
        result = await service.ui(
            owner.identity.hash.hex(),
            peer=body["peer"],
            read_through=body["through"],
            expected_owner=body.get("expected_owner"),
        )
    elif action == "connect":
        result = await service.connect(**body)
    elif action == "disconnect":
        result = await service.disconnect()
    elif action == "receiving":
        result = await service.set_receiving(body["enabled"])
    elif action == "restore":
        result = await service.restore(**body)
    elif action == "channel-add":
        private = body["private"]
        if type(private) is not bool or ("key_hex" in body and not private):
            raise ValueError("Invalid channel mode")
        options = {"key": bytes.fromhex(body["key_hex"])} if "key_hex" in body else {}
        result = await service.call(
            "channels",
            "add_private" if private else "add_public",
            body["name"],
            expected_owner=body.get("expected_owner"),
            **options,
        )
    else:
        methods = {
            "announce": ("tools", "announce"),
            "tool-radio-stats": ("tools", "radio_stats"),
            "tool-rx-log": ("tools", "rx_log"),
            "tool-trace": ("tools", "trace"),
            "regions-scan": ("tools", "start_region_scan"),
            "regions-auto": ("tools", "set_region_auto"),
            "regions-read": ("tools", "read_regions"),
            "regions-add": ("tools", "add_region"),
            "regions-default": ("tools", "set_default_region"),
            "regions-discover": ("tools", "discover_regions"),
            "node-discover": ("nodes", "discover"),
            "image-prepare": ("voice", "prepare_image"),
            "media-channel-send": ("voice", "send_channel"),
            "media-channel-fetch": ("voice", "fetch_channel"),
            "voice-prepare": ("voice", "prepare"),
            "voice-send": ("voice", "send"),
            "team-attachment-prepare": ("tactical", "prepare_attachment"),
            "team-attachment-fetch": ("tactical", "fetch_attachment"),
            "team-shape-preview": ("tactical", "preview_shape"),
            "team-configure": ("tactical", "configure"),
            "tak-connect": ("tactical", "cot_connect"),
            "tak-enroll": ("tactical", "cot_enroll"),
            "tak-package-search": ("tactical", "cot_package_search"),
            "tak-package-download": ("tactical", "cot_package_download"),
            "tak-package-upload": ("tactical", "cot_package_upload"),
            "tak-disconnect": ("tactical", "cot_disconnect"),
            "tak-send": ("tactical", "cot_send"),
            "team-send": ("tactical", "send"),
            "team-beacon-start": ("tactical", "beacon_start"),
            "team-beacon-stop": ("tactical", "beacon_stop"),
            "team-beacon-status": ("tactical", "beacon_status"),
            "team-beacon-position": ("tactical", "beacon_position"),
            "voice-fetch": ("voice", "fetch"),
            "voice-play": ("voice", "play"),
            "voice-discard": ("voice", "discard"),
            "node-login": ("nodes", "login"),
            "node-password-status": ("nodes", "password_status"),
            "node-password-save": ("nodes", "password_save"),
            "node-password-forget": ("nodes", "password_forget"),
            "node-logout": ("nodes", "logout"),
            "node-status": ("nodes", "status"),
            "node-admin": ("nodes", "admin"),
            "node-route": ("nodes", "route"),
            "room-message": ("nodes", "send_room"),
            "name": ("session", "set_name"),
            "backup": ("session", "backup_identity"),
            "settings": ("session", "apply_settings"),
            "radio2": ("session", "apply_radio2"),
            "message": ("messages", "send_direct"),
            "contact-add": ("messages", "add_contact"),
            "channel-remove": ("channels", "remove"),
            "channel-key": ("channels", "export_key"),
            "channel-message": ("channels", "send"),
        }
        result = await service.call(*methods[action], **body)
        if action == "channel-key":
            result = {"key_hex": result.hex()}
    return result


def register_meshcore_routes(routes, owner):
    async def handle(request):
        service = getattr(owner, "meshcore_service", None)
        action = request.match_info["action"]
        if request.method == "GET" and action == "status":
            try:
                status = (
                    service.status(request.query.get("radio"))
                    if isinstance(service, MeshCoreFleet)
                    else service.status()
                    if service
                    else {"available": False, "connected": False}
                )
                return web.json_response(status, headers=HEADERS)
            except (ValueError, TypeError):
                return web.json_response(
                    {"message": "Select a saved MeshCore radio"},
                    status=400,
                    headers=HEADERS,
                )
        if service is None:
            return web.json_response(
                {"message": "MeshCore is unavailable in this build"},
                status=503,
                headers=HEADERS,
            )
        try:
            result = await (
                _read(service, owner, request, action)
                if request.method == "GET"
                else _write(service, owner, request, action)
            )
            return web.json_response({"result": result}, headers=HEADERS)
        except PayloadTooLargeError:
            return web.json_response(
                {"message": "MeshCore request exceeds size limit"},
                status=413,
                headers=HEADERS,
            )
        except OutboundHttpBlockedError as error:
            return web.json_response(
                {"message": str(error)}, status=403, headers=HEADERS
            )
        except VoiceCapabilityError as error:
            return web.json_response(
                {"message": str(error)}, status=400, headers=HEADERS
            )
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
            message = (
                str(error)
                if isinstance(error, ValueError)
                and action
                in {"radio-add", "radio-configure", "radio-remove", "radio-enabled"}
                else "Invalid MeshCore request"
            )
            return web.json_response({"message": message}, status=400, headers=HEADERS)
        except PermissionError:
            return web.json_response(
                {"message": "Firmware disables this identity operation"},
                status=409,
                headers=HEADERS,
            )
        except (ConnectionError, RuntimeError, OSError):
            return web.json_response(
                {
                    "message": "MeshCore operation unavailable; inspect connection status before retrying"
                },
                status=503,
                headers=HEADERS,
            )

    routes.get(API_V1_PREFIX + "/meshcore/{action}")(handle)
    routes.post(API_V1_PREFIX + "/meshcore/{action}")(handle)


def install_meshcore_lifecycle(web_app, owner):
    async def start(_app):
        if importlib.util.find_spec("meshcore") is None:
            return
        from meshchatnext.src.backend.meshcore_notifications import deliver_notification

        async def notify(event):
            await deliver_notification(owner, event)

        owner.meshcore_service = MeshCoreFleet(
            Path(owner.storage_dir) / "meshcore", notification_sink=notify
        )
        await owner.meshcore_service.start()

    async def stop(_app):
        service = getattr(owner, "meshcore_service", None)
        if service is not None:
            # MeshCore teardown must not prevent the subsequent RNS shutdown.
            with contextlib.suppress(Exception):
                async with asyncio.timeout(30):
                    await service.close()

    web_app.on_startup.append(start)
    web_app.on_shutdown.append(stop)
