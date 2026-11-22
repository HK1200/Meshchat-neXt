# SPDX-License-Identifier: 0BSD
"""Explicit per-contact recipient mailbox-alert routes; no provider requests."""

import re
from dataclasses import asdict
from pathlib import Path

from aiohttp import web

from meshchatnext.src.backend.constants import API_V1_PREFIX
from meshchatnext.src.backend.http.errors import (
    http_bad_request,
    http_error,
    parse_int_param,
)
from meshchatnext.src.backend.http.uploads import (
    PayloadTooLargeError,
    read_json_limited,
)
from meshchatnext.src.backend.mailbox_push import route_for, save_route


def contact_address(contact):
    value = contact.get("lxmf_address") if contact else None
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", value):
        raise web.HTTPBadRequest(text="Choose a saved Reticulum messaging contact")
    return value.lower()


def remove_contact_alert_route(app, contact):
    context = getattr(app, "current_context", None)
    if context is None or not contact or not contact.get("lxmf_address"):
        return
    save_route(Path(context.storage_path), contact_address(dict(contact)), None)


def register_mailbox_alert_routes(routes, app):
    def resolve(request):
        context = getattr(app, "current_context", None)
        if context is None or getattr(context, "database", None) is None:
            raise web.HTTPServiceUnavailable(text="The current identity is not ready")
        contact_id = parse_int_param(
            request.match_info["id"], minimum=1, maximum=2**63 - 1
        )
        if contact_id is None or contact_id < 1:
            raise web.HTTPBadRequest(text="Invalid contact id")
        contact = context.database.contacts.get_contact(contact_id)
        if contact is None:
            raise web.HTTPNotFound(text="Contact not found")
        return context, contact_id, contact_address(dict(contact))

    @routes.get(API_V1_PREFIX + "/telephone/contacts/{id}/mailbox-alert-route")
    async def get_route(request):
        context, _, address = resolve(request)
        route = route_for(Path(context.storage_path), address)
        return web.json_response({"route": asdict(route) if route else None})

    @routes.post(API_V1_PREFIX + "/telephone/contacts/{id}/mailbox-alert-route")
    async def set_route(request):
        context, contact_id, address = resolve(request)
        try:
            body = await read_json_limited(request, max_bytes=4096)
            if not isinstance(body, dict) or set(body) != {"route"}:
                raise ValueError("Choose a recipient alert route")
            current, current_id, current_address = resolve(request)
            if (
                current is not context
                or current_id != contact_id
                or current_address != address
            ):
                raise web.HTTPConflict(
                    text="The identity or contact changed. Reopen the contact"
                )
            route = save_route(Path(context.storage_path), address, body["route"])
            return web.json_response({"route": asdict(route) if route else None})
        except PayloadTooLargeError:
            raise web.HTTPRequestEntityTooLarge(
                max_size=4096, actual_size=request.content_length or 4097
            ) from None
        except ValueError as error:
            return http_bad_request(str(error), code="invalid_mailbox_alert_route")
        except OSError:
            return http_error(
                503,
                "Could not save alert settings. The previous route is unchanged.",
                code="mailbox_alert_storage_unavailable",
            )

    @routes.delete(API_V1_PREFIX + "/telephone/contacts/{id}/mailbox-alert-route")
    async def delete_route(request):
        context, _, address = resolve(request)
        try:
            save_route(Path(context.storage_path), address, None)
        except (OSError, ValueError):
            return http_error(
                503,
                "Could not remove the saved alert route. Try again.",
                code="mailbox_alert_storage_unavailable",
            )
        return web.json_response({"route": None})
