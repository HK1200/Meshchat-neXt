# SPDX-License-Identifier: 0BSD
"""The public call status uses LXST profiles, not codec-internal preset IDs."""

import json
from types import SimpleNamespace

import pytest
import RNS
from aiohttp import web
from LXST.Primitives.Telephony import Profiles

from meshchatnext.src.backend.http.routes.telephone import register_telephone_routes


def status_app(profile):
    identity = RNS.Identity()
    call = SimpleNamespace(
        hash=b"\x7c" * 16,
        is_incoming=False,
        get_remote_identity=lambda: identity,
        profile=profile,
    )
    phone = SimpleNamespace(
        active_call=call,
        call_status=6,
        busy=True,
        transmit_codec=Profiles.get_codec(profile),
        target_frame_time_ms=Profiles.get_frame_time(profile),
    )
    manager = SimpleNamespace(
        telephone=phone,
        get_name_for_identity_hash=None,
        get_active_mode_id=lambda: Profiles.MODE_FULL_DUPLEX,
        is_half_duplex=lambda: False,
        is_transmit_squelched=lambda: False,
        transmit_muted=False,
        receive_muted=False,
        is_recording=False,
        ptt_active=False,
        call_start_time=0.0,
        call_stats={},
        initiation_target_hash=None,
        initiation_status=None,
        preferred_mode_id=Profiles.MODE_FULL_DUPLEX,
        resolve_call_mode_id=lambda value: value,
    )
    misc = SimpleNamespace(
        get_user_icon=lambda value: None,
        get_unread_notification_count_by_type=lambda value: 0,
    )
    voicemails = SimpleNamespace(
        get_unread_count=lambda: 0, get_latest_voicemail_id=lambda: None
    )
    return SimpleNamespace(
        telephone_manager=manager,
        database=SimpleNamespace(misc=misc, voicemails=voicemails),
        _resolve_contact_for_hash=lambda value: None,
        get_lxst_telephony_hash_for_identity_hash=lambda value: "7d" * 16,
        voicemail_manager=SimpleNamespace(is_recording=False),
        config=SimpleNamespace(
            telephone_web_audio_enabled=SimpleNamespace(get=lambda: False),
            telephone_web_audio_allow_fallback=SimpleNamespace(get=lambda: False),
        ),
        web_audio_required=lambda: False,
        web_audio_bridge=SimpleNamespace(clients=[], get_diagnostics=lambda: {}),
    )


async def status(app):
    routes = web.RouteTableDef()
    register_telephone_routes(routes, app)
    handler = next(
        row.handler
        for row in routes
        if row.method == "GET" and row.path == "/api/v1/telephone/status"
    )
    response = await handler(SimpleNamespace())
    assert response.status == 200
    return json.loads(response.body)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", Profiles.available_profiles())
async def test_status_reports_the_negotiated_profile_for_every_real_codec(profile):
    app = status_app(profile)
    result = await status(app)
    assert result["active_call"]["audio_profile_id"] == profile
    assert result["web_audio"]["frame_ms"] == Profiles.get_frame_time(profile)


@pytest.mark.asyncio
async def test_idle_status_has_no_active_profile():
    app = status_app(Profiles.QUALITY_MEDIUM)
    app.telephone_manager.telephone.active_call = None
    app.telephone_manager.telephone.call_status = 3
    app.telephone_manager.telephone.busy = False
    result = await status(app)
    assert result["active_call"] is None
