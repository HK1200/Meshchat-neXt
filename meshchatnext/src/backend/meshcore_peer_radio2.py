# SPDX-License-Identifier: MIT
"""Decode the optional Cascade v1 discovery trailer; never infer peer support.

Source: https://mikecarper.github.io/MeshCore/radio_profiles/#discover-the-local-radio2-profile
Input is the trailer AFTER a discovery response's full public key. Identity,
request-tag correlation and freshness belong to the caller, not this decoder.
Discovery is public/unauthenticated: these are reported settings, not proof.
"""

import struct


def decode_discovery_radio2(trailer):
    """Return unknown for legacy/malformed/future replies; no RF side effects."""
    unknown = {"state": "unknown", "source": "nearby_discovery"}
    if not isinstance(trailer, bytes) or len(trailer) not in (2, 12):
        return unknown
    if trailer[0] != 1:
        return unknown
    flags = trailer[1]
    if flags == 0 and len(trailer) == 2:
        # Off, unsupported and foreign-protocol ownership share this reply.
        return {**unknown, "state": "unavailable"}
    mode = (flags >> 1) & 3
    if len(trailer) != 12 or flags & 0xF0 or not flags & 1 or mode not in (1, 2):
        return unknown
    frequency, bandwidth, sf, cr = struct.unpack("<IIBB", trailer[2:])
    if (
        not 100000 <= frequency <= 2500000
        or bandwidth
        not in (
            7800,
            10400,
            15600,
            20800,
            31250,
            41700,
            62500,
            125000,
            250000,
            500000,
        )
        or not 5 <= sf <= 12
        or not 5 <= cr <= 8
    ):
        return unknown
    return {
        "state": "enabled",
        "source": "nearby_discovery",
        "mode": "rx" if mode == 1 else "rxtx",
        "temporary": bool(flags & 8),
        "frequency_mhz": frequency / 1000,
        "bandwidth_khz": bandwidth / 1000,
        "sf": sf,
        "cr": cr,
    }
