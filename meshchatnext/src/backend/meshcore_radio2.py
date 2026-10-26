# SPDX-License-Identifier: MIT
"""Local Radio2 controls. No arbitrary CLI, retries or radio identity exports."""

import re

from meshchatnext.src.backend.meshcore_settings import RADIO_FIELDS, validate_changes

MEDIAMESH_DEFAULTS = {"frequency_mhz": 911.150, "bandwidth_khz": 250, "sf": 7, "cr": 5}


async def _cli(session, command, *, probe=False):
    try:
        event = await session._client.commands.run_cli_command(command)
        if event is not None and event.is_error():
            if probe and event.payload.get("error_code") == 1:
                return None
            raise ConnectionError("Radio2 command was not confirmed")
        text = event.payload.get("text") if event is not None else None
        if not isinstance(text, str):
            raise ConnectionError("Invalid Radio2 response")
        if probe and (
            "unknown command" in text.lower() or "unsupported" in text.lower()
        ):
            return None
        if text.startswith("Error"):
            raise ConnectionError("Radio2 command rejected")
        return text
    except BaseException:
        # Local CLI replies have no request ID. Close after uncertainty so a late
        # reply cannot be mistaken for the result of a subsequent command.
        await session._close()
        raise


def decode_profile(text):
    if re.match(r"^> off(?:$|[ ;(])", text):
        return {"enabled": False, "profile": None, "mode": "off"}
    match = re.match(
        r"^> ([\d.]+),([\d.]+),(\d+),(\d+),(rx|rxtx),(\d+)(?:$|[ ;(])", text
    )
    if not match:
        raise ConnectionError("Unrecognized Radio2 profile")
    freq, bw, sf, cr, mode, preamble = match.groups()
    profile = validate_changes(
        {
            "frequency_mhz": float(freq),
            "bandwidth_khz": float(bw),
            "sf": int(sf),
            "cr": int(cr),
        },
        127,
    )
    return {
        "enabled": True,
        "profile": profile,
        "mode": mode,
        "preamble_symbols": int(preamble),
        "automatic_preamble": "(auto)" in text,
    }


async def read_radio2(session):
    if not session.is_connected or session._client is None:
        raise ConnectionError("MeshCore is disconnected")
    device = session._payload(await session._client.commands.send_device_query())
    base = {"supported": False, "defaults": dict(MEDIAMESH_DEFAULTS)}
    if device.get("fw ver", 0) < 14:
        return base
    text = await _cli(session, "get radio2", probe=True)
    if text is None:
        return base
    result = {**base, "supported": True, **decode_profile(text)}
    crossing = await _cli(session, "get radio2.cross")
    policy = await _cli(session, "get tx.media")
    if crossing not in ("> off", "> on"):
        raise ConnectionError("Unrecognized Radio2 crossing response")
    if policy is None:
        raise ConnectionError("Missing Radio2 media routing response")
    match = re.match(r"^> tx.media (auto|radio|radio2|both|off)(?:$|[ ;])", policy)
    if not match:
        raise ConnectionError("Unrecognized Radio2 media routing response")
    result.update(
        crossing=crossing == "> on",
        media_policy=match[1],
        timing_pending="timing self-test pending" in text,
    )
    return result


async def apply_radio2(session, *, enabled, **changes):
    if type(enabled) is not bool or set(changes) - set(RADIO_FIELDS):
        raise ValueError("Invalid Radio2 settings")
    if not enabled and changes:
        raise ValueError("Disable Radio2 without changing its profile")
    requested = validate_changes(changes, 127)
    current = await read_radio2(session)
    if not current["supported"]:
        raise ValueError("This firmware does not support Radio2")
    primary = await session._read_settings()
    target = {**(current.get("profile") or MEDIAMESH_DEFAULTS), **requested}
    if enabled and target["frequency_mhz"] == primary["frequency_mhz"]:
        raise ValueError("Radio2 needs a different frequency from the primary profile")
    try:
        if enabled:
            for command in ("set radio2.cross off", "set tx.media radio2"):
                if not (await _cli(session, command)).startswith("OK"):
                    raise ConnectionError("Radio2 policy update unverified")
            command = "set radio2 {frequency_mhz:.3f},{bandwidth_khz:.3f},{sf},{cr},rxtx,auto".format(
                **target
            )
        else:
            command = "set radio2 off"
        if not (await _cli(session, command)).startswith("OK"):
            raise ConnectionError("Radio2 update unverified")
        result = await read_radio2(session)
        after = await session._read_settings()
        if any(
            primary[k] != after[k]
            for k in (*RADIO_FIELDS, "tx_power_dbm", "path_hash_bytes")
        ):
            raise ConnectionError("Primary radio settings changed unexpectedly")
        if result["enabled"] != enabled or (
            enabled
            and (
                result["profile"] != target
                or result["mode"] != "rxtx"
                or result["crossing"]
                or result["media_policy"] != "radio2"
            )
        ):
            raise ConnectionError("Radio2 readback mismatch")
        return result
    except BaseException:
        await session._close()
        raise
