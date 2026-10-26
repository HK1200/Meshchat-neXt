# SPDX-License-Identifier: MIT
"""Validated MeshCore settings and exact companion-protocol encoding.

Units: frequency in MHz, bandwidth in kHz, power in dBm, CR as denominator
(5 means 4/5), path hashes in bytes. Firmware modes 0/1/2 map to 1/2/3 bytes.
Bounds follow the upstream companion handler; hardware may support a subset.
"""

from decimal import Decimal, InvalidOperation

RADIO_FIELDS = ("frequency_mhz", "bandwidth_khz", "sf", "cr")
WRITABLE_FIELDS = (*RADIO_FIELDS, "tx_power_dbm", "path_hash_bytes")


def integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def wire_units(value, minimum, maximum, name):
    if isinstance(value, (str, bool)) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not Decimal(minimum) <= number <= Decimal(maximum):
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        ticks = number * 1000
        if ticks != ticks.to_integral_value():
            raise ValueError(f"{name} supports at most three decimal places")
        return int(ticks)
    except InvalidOperation as error:
        raise ValueError(f"Invalid {name}") from error


def validate_changes(changes, max_power):
    unknown = set(changes) - set(WRITABLE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown MeshCore settings: {', '.join(sorted(unknown))}")
    result = dict(changes)
    for name, low, high in (
        ("frequency_mhz", "150", "2500"),
        ("bandwidth_khz", "7", "500"),
    ):
        if name in result:
            result[name] = wire_units(result[name], low, high, name) / 1000
    for name, low, high in (
        ("sf", 5, 12),
        ("cr", 5, 8),
        ("tx_power_dbm", -9, max_power),
        ("path_hash_bytes", 1, 3),
    ):
        if name in result:
            result[name] = integer(result[name], low, high, name)
    return result


def decode_settings(own, device):
    """Return only radio settings; never expose keys, pairing PINs or identity data."""
    maximum = integer(own["max_tx_power"], 0, 127, "max_tx_power")
    power = integer(own["tx_power"], 0, 255, "tx_power")
    if power > 127:  # Upstream parser reads the firmware's int8 as uint8.
        power -= 256
    values = validate_changes(
        {
            "frequency_mhz": own["radio_freq"],
            "bandwidth_khz": own["radio_bw"],
            "sf": own["radio_sf"],
            "cr": own["radio_cr"],
            "tx_power_dbm": power,
        },
        maximum,
    )
    version = integer(device["fw ver"], 0, 255, "protocol_version")
    mode = device.get("path_hash_mode")
    supported = version >= 10 and type(mode) is int and mode in (0, 1, 2)
    repeat = device.get("repeat") if version >= 9 else None
    if repeat is not None and type(repeat) is not bool:
        raise ValueError("Invalid companion repeat setting")
    values.update(
        path_hash_bytes=mode + 1 if supported else None,
        path_hash_supported=supported,
        max_tx_power_dbm=maximum,
        protocol_version=version,
        client_repeat=repeat,
    )
    return values


def radio_frame(settings):
    frame = b"\x0b"
    frame += wire_units(
        settings["frequency_mhz"], "150", "2500", "frequency_mhz"
    ).to_bytes(4, "little")
    frame += wire_units(
        settings["bandwidth_khz"], "7", "500", "bandwidth_khz"
    ).to_bytes(4, "little")
    frame += bytes((settings["sf"], settings["cr"]))
    if settings["protocol_version"] >= 9:
        if type(settings["client_repeat"]) is not bool:
            raise ValueError("Cannot preserve missing companion repeat setting")
        frame += bytes((int(settings["client_repeat"]),))
    return frame


class SettingsApplyError(ConnectionError):
    """A write may have applied; current readback and completed fields are explicit."""

    def __init__(self, attempted_fields, verified_fields, current_settings):
        super().__init__("MeshCore settings update failed or did not match readback")
        self.attempted_fields = tuple(attempted_fields)
        self.verified_fields = tuple(verified_fields)
        self.current_settings = current_settings
