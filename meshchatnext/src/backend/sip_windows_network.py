# SPDX-License-Identifier: MIT
"""Bounded, read-only Windows IPv4 adapters/routes from IP Helper APIs."""

import ctypes as ct
import ipaddress


class _IpString(ct.Structure):
    pass


_IpString._fields_ = [
    ("next", ct.POINTER(_IpString)),
    ("address", ct.c_char * 16),
    ("mask", ct.c_char * 16),
    ("context", ct.c_uint32),
]


class _Adapter(ct.Structure):
    pass


_Adapter._fields_ = [
    ("next", ct.POINTER(_Adapter)),
    ("combo", ct.c_uint32),
    ("name", ct.c_char * 260),
    ("description", ct.c_char * 132),
    ("address_length", ct.c_uint32),
    ("hardware_address", ct.c_ubyte * 8),
    ("index", ct.c_uint32),
    ("type", ct.c_uint32),
    ("dhcp", ct.c_uint32),
    ("current_ip", ct.POINTER(_IpString)),
    ("ip", _IpString),
    ("gateway", _IpString),
]


class _Route(ct.Structure):
    _fields_ = [
        (name, ct.c_uint32)
        for name in (
            "destination",
            "mask",
            "policy",
            "next_hop",
            "index",
            "type",
            "protocol",
            "age",
            "next_hop_as",
            "metric",
            "metric2",
            "metric3",
            "metric4",
            "metric5",
        )
    ]


def candidates(adapters, routes):
    """Unknown/tunnel interface types and missing/default-less IPs fail closed."""
    result = []
    by_index = {row["index"]: row for row in adapters}
    for route in sorted(routes, key=lambda row: row["metric"]):
        row = by_index.get(route["index"])
        if (
            not row
            or route["destination"]
            or route["mask"]
            or route["type"] == 2
            or route["metric"] == 0xFFFFFFFF
        ):
            continue
        kind = {6: "ethernet", 71: "wifi", 243: "mobile", 244: "mobile"}.get(
            row["type"]
        )
        try:
            address = ipaddress.IPv4Address(row["address"])
        except (ValueError, KeyError):
            continue
        if (
            not kind
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
        ):
            continue
        if any(entry["interface"] == str(row["index"]) for entry in result):
            continue
        result.append(
            {
                "interface": str(row["index"]),
                "address": str(address),
                "kind": kind,
                "metric": route["metric"],
            }
        )
    return result


def available_networks():
    try:
        api = ct.WinDLL("Iphlpapi.dll")
        api.GetAdaptersInfo.argtypes = [ct.c_void_p, ct.POINTER(ct.c_uint32)]
        api.GetAdaptersInfo.restype = ct.c_uint32
        api.GetIpForwardTable.argtypes = [
            ct.c_void_p,
            ct.POINTER(ct.c_uint32),
            ct.c_int,
        ]
        api.GetIpForwardTable.restype = ct.c_uint32

        def query(function, *extra):
            size = ct.c_uint32(0)
            function(None, ct.byref(size), *extra)
            for _ in range(3):
                if not 0 < size.value <= 1024 * 1024:
                    raise ValueError("Invalid IP Helper response size")
                buffer = ct.create_string_buffer(size.value)
                code = function(buffer, ct.byref(size), *extra)
                if code == 0:
                    return buffer
                if code not in (111, 122):
                    raise OSError("IP Helper request failed")
            raise OSError("IP Helper response changed repeatedly")

        adapter_buffer = query(api.GetAdaptersInfo)
        pointer = ct.cast(adapter_buffer, ct.POINTER(_Adapter))
        adapters = []
        while pointer and len(adapters) < 256:
            row = pointer.contents
            adapters.append(
                {
                    "index": row.index,
                    "type": row.type,
                    "address": bytes(row.ip.address).decode("ascii"),
                }
            )
            pointer = row.next
        route_buffer = query(api.GetIpForwardTable, 0)
        count = ct.cast(route_buffer, ct.POINTER(ct.c_uint32)).contents.value
        if count > 4096 or 4 + count * ct.sizeof(_Route) > ct.sizeof(route_buffer):
            return []
        rows = (_Route * count).from_buffer(route_buffer, 4)
        routes = [
            {
                name: getattr(row, name)
                for name in ("destination", "mask", "index", "type", "metric")
            }
            for row in rows
        ]
        return candidates(adapters, routes)
    except (OSError, ValueError, AttributeError):
        return []
