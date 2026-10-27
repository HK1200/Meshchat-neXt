# SPDX-License-Identifier: MIT
import socket
from types import SimpleNamespace

import pytest

from meshchatnext.src.backend.sip_desktop_network import (
    available_networks,
    interface_kind,
    select_network,
)


def test_interface_classification_does_not_treat_vpn_or_unknown_as_wifi(tmp_path):
    for name in ("enp1s0", "tun0", "wg0", "docker0"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "type").write_text("1")
    assert interface_kind("enp1s0", tmp_path) == "ethernet"
    assert interface_kind("wlan0", tmp_path) == "wifi"
    assert interface_kind("wwan0", tmp_path) == "mobile"
    assert interface_kind("unknown", tmp_path) is None
    assert interface_kind("../bad", tmp_path) is None
    assert all(
        interface_kind(n, tmp_path) is None for n in ("tun0", "wg0", "docker0", "lo")
    )


def test_selection_honours_allowed_network_and_metric_and_skips_down(tmp_path):
    for name in ("enp1s0", "wlan0", "wwan0"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "type").write_text("1")
    routes = "Iface Destination Gateway Flags RefCnt Use Metric Mask\n" + "\n".join(
        f"{name} 00000000 0100007F 0003 0 0 {metric} 00000000"
        for name, metric in [("wlan0", 10), ("enp1s0", 5), ("wwan0", 20)]
    )
    addresses = {
        n: [SimpleNamespace(family=socket.AF_INET, address=f"10.0.{i}.2")]
        for i, n in enumerate(("enp1s0", "wlan0", "wwan0"))
    }
    stats = {n: SimpleNamespace(isup=True) for n in addresses}
    candidates = available_networks(
        route_text=routes, addresses=addresses, stats=stats, sysfs=tmp_path
    )
    assert select_network(["wifi"], candidates)["interface"] == "wlan0"
    assert select_network(["wifi", "ethernet"], candidates)["interface"] == "enp1s0"
    stats["wlan0"].isup = False
    candidates = available_networks(
        route_text=routes, addresses=addresses, stats=stats, sysfs=tmp_path
    )
    assert select_network(["wifi"], candidates) is None
    assert select_network(["wifi", "mobile"], candidates)["interface"] == "wwan0"


def test_bad_routes_and_unavailable_interfaces_do_not_select_a_network(tmp_path):
    assert (
        available_networks(
            route_text="header\nbad route", addresses={}, stats={}, sysfs=tmp_path
        )
        == []
    )
    with pytest.raises(ValueError):
        select_network(["i2p"], [])
    assert select_network(["wifi"], []) is None
