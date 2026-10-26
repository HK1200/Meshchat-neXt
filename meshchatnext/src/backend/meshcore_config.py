# SPDX-License-Identifier: MIT
"""Companion JSON import parsing and review. Never logs or persists source secrets."""

from __future__ import annotations

import hashlib
import json
import math

from meshchatnext.src.backend.meshcore_identity import derive_public
from meshchatnext.src.backend.meshcore_settings import integer, validate_changes
from meshchatnext.src.backend.meshcore_store import public_key

MAX_CONFIG_BYTES = 2 * 1024 * 1024
SECTIONS = {"name", "radio", "identity", "contacts", "channels"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _hex(value, size):
    if not isinstance(value, str) or len(value) != size * 2:
        raise ValueError("Invalid backup key length")
    try:
        result = bytes.fromhex(value)
    except ValueError:
        raise ValueError("Invalid backup key encoding") from None
    if len(result) != size:
        raise ValueError("Invalid backup key encoding")
    return result


def _name(value):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError("Backup names must contain 1-31 UTF-8 bytes")
    try:
        if len(value.encode()) > 31:
            raise ValueError("Backup names must contain 1-31 UTF-8 bytes")
    except UnicodeError:
        raise ValueError("Invalid backup name encoding") from None
    return value


def _coordinate(value, bound):
    if isinstance(value, bool):
        raise ValueError("Invalid contact position")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid contact position") from None
    if not math.isfinite(number) or abs(number) > bound:
        raise ValueError("Invalid contact position")
    return number


def parse_config(text, password=None):
    if not isinstance(text, str):
        raise ValueError("Config file must be JSON text")
    try:
        encoded = text.encode()
    except UnicodeError:
        raise ValueError("Invalid config text encoding") from None
    if len(encoded) > MAX_CONFIG_BYTES:
        raise ValueError("Config file exceeds 2 MiB")
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_object,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Invalid JSON number")
            ),
        )
    except (json.JSONDecodeError, RecursionError):
        raise ValueError("Invalid config JSON") from None
    if not isinstance(raw, dict):
        raise ValueError("Config must be a JSON object")
    plan = {
        "contacts": [],
        "channels": [],
        "unsupported": [],
        "present": [],
        "source_digest": hashlib.sha256(text.encode()).hexdigest(),
    }
    if raw.get("format") in (
        "meshchatnext-meshcore-identity-v1",
        "meshchatx-meshcore-identity-v1",
    ):
        from meshchatnext.src.backend.meshcore_identity import decrypt_backup

        owner, private = decrypt_backup(raw, password)
        plan.update(public_key=owner, private=private, present=["identity"])
        return plan
    known = {
        "name",
        "public_key",
        "private_key",
        "radio_settings",
        "channels",
        "contacts",
    }
    plan["unsupported"] += [key for key in raw if key not in known]
    if "name" in raw:
        plan["name"] = _name(raw["name"])
        plan["present"].append("name")
    if "public_key" in raw:
        plan["public_key"] = public_key(raw["public_key"])
    if "private_key" in raw:
        private = _hex(raw["private_key"], 64)
        derived = derive_public(private)
        if plan.get("public_key") != derived:
            raise ValueError("Backup identity keys do not match")
        plan["private"] = private
        plan["present"].append("identity")
    if "radio_settings" in raw:
        radio = raw["radio_settings"]
        if not isinstance(radio, dict):
            raise ValueError("Invalid radio settings")
        mapping = {
            "frequency": "frequency_mhz",
            "bandwidth": "bandwidth_khz",
            "spreading_factor": "sf",
            "coding_rate": "cr",
            "tx_power": "tx_power_dbm",
        }
        converted = {}
        for key, value in radio.items():
            if key not in mapping:
                plan["unsupported"].append("radio_settings." + key)
                continue
            if key in ("frequency", "bandwidth"):
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("Invalid backup radio units")
                value /= 1000  # Official companion exports use kHz and Hz respectively.
            converted[mapping[key]] = value
        plan["radio"] = validate_changes(converted, 127)
        if converted:
            plan["present"].append("radio")
    for section, maximum in (("contacts", 4096), ("channels", 256)):
        rows = raw.get(section, [])
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError("Invalid backup section size")
        if section in raw:
            plan["present"].append(section)
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid backup entry")
            if section == "channels":
                name = row.get("name", "")
                key = _hex(row.get("secret"), 16)
                if not name and key == bytes(16):
                    continue
                name = _name(name)
                if key == bytes(16):
                    raise ValueError("Invalid empty channel key")
                if (
                    row.get("region_scope_key") is not None
                    or row.get("region_scope_name") is not None
                ):
                    plan["unsupported"].append("Scoped channel skipped: " + name)
                    continue  # Never silently turn a scoped channel into an unscoped one.
                identity = hashlib.sha256(key).hexdigest()
                if identity in seen:
                    raise ValueError("Duplicate backup channel key")
                seen.add(identity)
                plan[section].append({"name": name, "key": key, "channel_id": identity})
                known_row = {"name", "secret", "region_scope_key", "region_scope_name"}
            else:
                peer = public_key(row.get("public_key"))
                if peer in seen:
                    raise ValueError("Duplicate backup contact")
                seen.add(peer)
                plan[section].append(
                    {
                        "public_key": peer,
                        "type": integer(row.get("type", 1), 1, 4, "type"),
                        "flags": integer(row.get("flags", 0), 0, 255, "flags"),
                        "adv_name": _name(row.get("name")),
                        "adv_lat": _coordinate(row.get("latitude", 0), 90),
                        "adv_lon": _coordinate(row.get("longitude", 0), 180),
                        "last_advert": integer(
                            row.get("last_advert", 0), 0, 0xFFFFFFFF, "last_advert"
                        ),
                        "out_path": "",
                        "out_path_len": -1,
                        "out_path_hash_mode": -1,
                    }
                )
                known_row = {
                    "public_key",
                    "type",
                    "flags",
                    "name",
                    "latitude",
                    "longitude",
                    "last_advert",
                    "last_modified",
                }
            for key, value in row.items():
                if key not in known_row and value is not None:
                    plan["unsupported"].append(section + "." + key)
    if not plan["present"]:
        raise ValueError("No supported companion configuration sections found")
    plan["unsupported"] = sorted(set(plan["unsupported"]))
    return plan


def review_config(plan, owner, identity, settings, contacts, channels, device):
    existing_contacts = {row["peer"] for row in contacts if row.get("active", True)}
    existing_channels = {row["channel_id"] for row in channels if row["channel_id"]}
    new_contacts = [
        row for row in plan["contacts"] if row["public_key"] not in existing_contacts
    ]
    new_channels = [
        row for row in plan["channels"] if row["channel_id"] not in existing_channels
    ]
    free_channels = sum(row["slot"] != 0 and row["kind"] == "empty" for row in channels)
    maximum = device.get("max_contacts")
    maximum = maximum if type(maximum) is int and maximum > 0 else None
    errors = {}
    if any(
        new["name"] == old["name"] and new["channel_id"] != old["channel_id"]
        for new in new_channels
        for old in channels
        if old["channel_id"]
    ):
        errors["channels"] = (
            "A channel name is already used with another key. Resolve the conflict before importing channels."
        )
    if len(new_channels) > free_channels:
        errors["channels"] = (
            "Not enough empty non-default channel slots. Existing channels will not be overwritten."
        )
    if new_contacts and (
        maximum is None or len(existing_contacts) + len(new_contacts) > maximum
    ):
        errors["contacts"] = (
            "Contact capacity is unknown or insufficient. Existing contacts will not be overwritten."
        )
    try:
        validate_changes(plan.get("radio", {}), settings["max_tx_power_dbm"])
    except ValueError:
        errors["radio"] = "Backup settings exceed this radio's supported limits."
    fingerprint = {
        "source": plan["source_digest"],
        "owner": owner,
        "identity": identity,
        "settings": settings,
        "contacts": sorted(existing_contacts),
        "channels": channels,
        "max_contacts": maximum,
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True).encode()
    ).hexdigest()
    return {
        "preview_id": digest,
        "owner": owner,
        "backup_public_key": plan.get("public_key"),
        "identity_replacement": "private" in plan and plan["public_key"] != owner,
        "name": plan.get("name"),
        "radio": plan.get("radio", {}),
        "sections": plan["present"],
        "contacts": {
            "new": len(new_contacts),
            "existing": len(plan["contacts"]) - len(new_contacts),
            "capacity": maximum,
        },
        "channels": {
            "new": len(new_channels),
            "existing": len(plan["channels"]) - len(new_channels),
            "free_slots": free_channels,
        },
        "unsupported": plan["unsupported"],
        "errors": errors,
    }


async def live_review(service, plan):
    if not service.status()["connected"]:
        raise ConnectionError("MeshCore is disconnected")
    identity = await service.session.read_identity()
    owner = service.messages.owner
    if identity["public_key"] != owner:
        raise ValueError("Connected identity changed")
    settings = await service.session.read_settings()
    contacts = await service.messages.sync_contacts()
    channels = await service.channels.refresh()
    return review_config(
        plan,
        owner,
        identity,
        settings,
        contacts,
        channels,
        {"max_contacts": service.session._device_info.get("max_contacts")},
    )


async def apply_config(
    service, plan, sections, expected_owner, preview_id, request_id, replace_identity
):
    import asyncio
    import secrets
    import uuid

    from meshchatnext.src.backend.meshcore_identity import encrypt_backup

    expected_owner = public_key(expected_owner)
    if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
        raise ValueError("Invalid import request ID")
    if (
        not isinstance(sections, list)
        or not sections
        or len(set(sections)) != len(sections)
        or not set(sections) <= set(plan["present"]) & SECTIONS
    ):
        raise ValueError("Choose supported import sections")
    if (
        type(replace_identity) is not bool
        or not isinstance(preview_id, str)
        or len(preview_id) != 64
    ):
        raise ValueError("Invalid import review")
    digest = hashlib.sha256(
        (
            plan["source_digest"]
            + json.dumps(sorted(sections))
            + preview_id
            + str(replace_identity)
        ).encode()
    ).hexdigest()
    if service._store is None:
        raise ConnectionError("No connected MeshCore store")
    previous = await asyncio.to_thread(
        service._store.config_import_run, expected_owner, request_id, digest
    )
    if previous is not None:
        return previous  # Never replay an interrupted, failed or completed operation.
    review = await live_review(service, plan)
    if review["owner"] != expected_owner or review["preview_id"] != preview_id:
        raise ValueError("Radio configuration changed; review the import again")
    if any(section in review["errors"] for section in sections):
        raise ValueError("Selected sections cannot fit this radio")
    if (
        "identity" in sections
        and review["identity_replacement"]
        and not replace_identity
    ):
        raise ValueError("Explicit identity replacement confirmation required")
    # Prepare all identity cryptography before any firmware write.
    encrypted = None
    if "identity" in sections and review["identity_replacement"]:
        password = secrets.token_urlsafe(32)
        encrypted = await asyncio.to_thread(
            encrypt_backup, plan["private"], plan["public_key"], password
        )
    await asyncio.to_thread(
        service._store.config_import_run, expected_owner, request_id, digest, claim=True
    )
    result = {
        "state": "complete",
        "completed": [],
        "contacts_added": 0,
        "channels_added": 0,
    }
    current_section = None
    try:
        for current_section in ("name", "radio", "contacts", "channels", "identity"):
            if current_section not in sections:
                continue
            if current_section == "name":
                identity = await service.session.set_name(plan["name"])
                await asyncio.to_thread(
                    service._store.update_profile_name, expected_owner, identity["name"]
                )
            elif current_section == "radio":
                await service.session.apply_settings(**plan["radio"])
            elif current_section == "contacts":
                for contact in plan["contacts"]:
                    result["contacts_added"] += int(
                        await service.messages.import_contact(contact)
                    )
            elif current_section == "channels":
                for channel in plan["channels"]:
                    result["channels_added"] += int(
                        await service.channels.import_channel(
                            channel["name"], channel["key"]
                        )
                    )
            elif encrypted is not None:
                await service._restore_locked(
                    encrypted, password, expected_current_public_key=expected_owner
                )
                result["identity_replaced"] = True
            result["completed"].append(current_section)
    except BaseException as error:
        result.update(
            state="uncertain",
            stopped_at=current_section,
            message="Import stopped. Completed changes remain; inspect the radio and make a new preview before any further import.",
        )
        await asyncio.shield(
            asyncio.to_thread(
                service._store.config_import_run,
                expected_owner,
                request_id,
                digest,
                result=result,
            )
        )
        if isinstance(error, asyncio.CancelledError):
            raise
        return result
    await asyncio.to_thread(
        service._store.config_import_run,
        expected_owner,
        request_id,
        digest,
        result=result,
    )
    return result
