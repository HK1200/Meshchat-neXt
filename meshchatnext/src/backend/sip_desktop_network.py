# SPDX-License-Identifier: MIT
"""Read-only Linux interface selection; the native engine enforces device binding."""

import ipaddress
import socket
import sys
from pathlib import Path

import psutil


def interface_kind(name, sysfs=Path("/sys/class/net")):
    if not isinstance(name, str) or not name or "/" in name or len(name) > 15:
        return None
    if name == "lo" or name.startswith(
        ("tun", "tap", "wg", "veth", "docker", "virbr", "br-")
    ):
        return None
    if (sysfs / name / "wireless").is_dir() or name.startswith(("wl", "wlan")):
        return "wifi"
    if name.startswith(("wwan", "rmnet", "ccmni", "pdp")):
        return "mobile"
    try:
        if (sysfs / name / "type").read_text().strip() == "1":
            return "ethernet"
    except OSError:
        pass
    return None


def default_routes(text):
    if len(text) > 65536:
        return []
    result = []
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8 or fields[1] != "00000000" or fields[7] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
            metric = int(fields[6])
        except ValueError:
            continue
        if flags & 1 and metric >= 0:
            result.append((metric, fields[0]))
    return sorted(set(result))


def available_networks(
    *, route_text=None, addresses=None, stats=None, sysfs=Path("/sys/class/net")
):
    if (
        sys.platform == "win32"
        and route_text is None
        and addresses is None
        and stats is None
    ):
        from meshchatnext.src.backend.sip_windows_network import (
            available_networks as windows_networks,
        )

        return windows_networks()
    try:
        if route_text is None:
            route_text = Path("/proc/net/route").read_text()
        if addresses is None:
            addresses = psutil.net_if_addrs()
        if stats is None:
            stats = psutil.net_if_stats()
    except OSError:
        return []
    result = []
    seen = set()
    for metric, name in default_routes(route_text):
        if name in seen:
            continue
        seen.add(name)
        kind = interface_kind(name, sysfs)
        status = stats.get(name)
        if not kind or not status or not status.isup:
            continue
        for address in addresses.get(name, []):
            if address.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.ip_address(address.address)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
                continue
            result.append(
                {"interface": name, "kind": kind, "address": str(ip), "metric": metric}
            )
            break
    return result


def select_network(allowed, candidates):
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(n not in ("wifi", "mobile", "ethernet") for n in allowed)
    ):
        raise ValueError("Select supported SIP connections")
    for network in candidates:
        if network["kind"] in allowed:
            return dict(network)
    return None
