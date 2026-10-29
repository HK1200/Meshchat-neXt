# SPDX-License-Identifier: MIT
"""Desktop SIP routes under the normal authentication/CSRF/IP middleware."""

import asyncio
import contextlib
import ctypes
import sys
from pathlib import Path

from aiohttp import web

from meshchatnext.src.backend.constants import API_V1_PREFIX
from meshchatnext.src.backend.http.uploads import (
    PayloadTooLargeError,
    read_json_limited,
)
from meshchatnext.src.backend.privacy_mode import privacy_mode_enabled

HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def native_executable():
    if sys.platform == "win32":
        path = (
            (Path(sys.executable).parent / "bin/meshchatnext-sip.exe")
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parents[3]
            / ".local/windows-sip/meshchatnext-sip.exe"
        )
        return path if path.is_file() else None
    if not sys.platform.startswith("linux"):
        return None
    path = (
        (Path(sys.executable).parent / "bin/meshchatnext-sip")
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[3] / ".local/linux-sip/meshchatnext-sip"
    )
    return path if path.is_file() else None


def native_support_error():
    if sys.platform == "win32":
        return None  # The packaged native helper uses Windows WASAPI.
    try:
        ctypes.CDLL("libpulse.so.0")
    except OSError:
        return "Desktop SIP requires the PulseAudio client library (libpulse0 on Mint/Ubuntu); other services remain available"
    return None


def register_sip_desktop_routes(routes, owner):
    async def status(request):
        service = getattr(owner, "sip_desktop_service", None)
        snapshot = (
            service.status()
            if service
            else {
                "available": False,
                "platform": "unsupported",
                "state": "unavailable",
                "accounts": [],
                "registered": False,
                "call_state": "idle",
            }
        )
        if service is None and getattr(owner, "sip_desktop_error", None):
            snapshot["error"] = owner.sip_desktop_error
        return web.json_response(snapshot, headers=HEADERS)

    async def command(request):
        service = getattr(owner, "sip_desktop_service", None)
        if service is None:
            return web.json_response(
                {"message": "Desktop SIP is unavailable in this build"},
                status=503,
                headers=HEADERS,
            )
        try:
            body = await read_json_limited(request, max_bytes=16 * 1024)
            if not isinstance(body, dict):
                raise ValueError("Invalid SIP request")
            op = body.pop("op", None)
            if op == "feature":
                if type(body.get("enabled")) is not bool or set(body) != {"enabled"}:
                    raise ValueError("Invalid SIP feature setting")
                service.store.feature_enabled = body["enabled"]
                await asyncio.to_thread(service.store.persist)
                await service.reconcile()
                result = service.status()
            else:
                result = await service.command(op, **body)
            return web.json_response(result, headers=HEADERS)
        except PayloadTooLargeError:
            return web.json_response(
                {"message": "SIP request is too large"}, status=413, headers=HEADERS
            )
        except (ValueError, TypeError, KeyError):
            return web.json_response(
                {
                    "message": "SIP action could not be completed; check the account and connection settings"
                },
                status=400,
                headers=HEADERS,
            )
        except (OSError, RuntimeError):
            return web.json_response(
                {"message": "SIP service is unavailable; reconnect before retrying"},
                status=503,
                headers=HEADERS,
            )

    routes.get(API_V1_PREFIX + "/sip/status")(status)
    routes.post(API_V1_PREFIX + "/sip/command")(command)


def install_sip_desktop_lifecycle(app, owner):
    async def start(_):
        executable = native_executable()
        if executable is None:
            return
        owner.sip_desktop_error = native_support_error()
        if owner.sip_desktop_error:
            return
        from meshchatnext.src.backend.sip_desktop_service import DesktopSipService
        from meshchatnext.src.backend.sip_desktop_store import SipAccounts

        try:
            store = SipAccounts(Path(owner.storage_dir) / "sip/accounts.json")
        except (ValueError, OSError, TypeError, KeyError):
            # SIP configuration damage must not stop independent mesh services.
            # Preserve the original file so it can be recovered.
            owner.sip_desktop_error = "SIP account settings could not be opened; other services remain available"
            return
        owner.sip_desktop_service = DesktopSipService(
            store,
            executable,
            permitted=lambda: not privacy_mode_enabled(getattr(owner, "config", None)),
        )
        await owner.sip_desktop_service.start()

    async def stop(_):
        service = getattr(owner, "sip_desktop_service", None)
        if service:
            with contextlib.suppress(Exception):
                await service.close()

    app.on_startup.append(start)
    app.on_shutdown.append(stop)
