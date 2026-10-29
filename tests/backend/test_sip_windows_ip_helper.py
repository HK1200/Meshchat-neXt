# SPDX-License-Identifier: MIT
"""Exercise read-only IP Helper parsing without loading a DLL or an adapter."""

import ctypes as ct
from unittest.mock import Mock

import pytest

from meshchatnext.src.backend import sip_windows_network as network


def fake_api(monkeypatch, *, adapter_size=None, adapter_codes=(), route_count=1):
    adapter = network._Adapter()
    adapter.index, adapter.type = 7, 71
    adapter.ip.address = b"192.0.2.10"
    route_buffer = ct.create_string_buffer(4 + ct.sizeof(network._Route))
    ct.cast(route_buffer, ct.POINTER(ct.c_uint32)).contents.value = route_count
    route = network._Route.from_buffer(route_buffer, 4)
    route.index, route.type, route.metric = 7, 4, 10
    errors = iter(adapter_codes)

    def adapters(buffer, size):
        size = ct.cast(size, ct.POINTER(ct.c_uint32))
        size.contents.value = (
            ct.sizeof(adapter) if adapter_size is None else adapter_size
        )
        if buffer is None:
            return 111
        code = next(errors, 0)
        if code == 0:
            ct.memmove(buffer, ct.byref(adapter), ct.sizeof(adapter))
        return code

    def routes(buffer, size, order):
        assert order == 0
        ct.cast(size, ct.POINTER(ct.c_uint32)).contents.value = ct.sizeof(route_buffer)
        if buffer is None:
            return 122
        ct.memmove(buffer, route_buffer, ct.sizeof(route_buffer))
        return 0

    api = Mock()
    api.GetAdaptersInfo = Mock(side_effect=adapters)
    api.GetIpForwardTable = Mock(side_effect=routes)
    monkeypatch.setattr(network.ct, "WinDLL", lambda name: api, raising=False)
    return api


def test_native_ip_helper_buffers_produce_a_default_wifi_route(monkeypatch):
    api = fake_api(monkeypatch)
    assert network.available_networks() == [
        {"interface": "7", "address": "192.0.2.10", "kind": "wifi", "metric": 10}
    ]
    assert api.GetAdaptersInfo.call_count == 2
    assert api.GetIpForwardTable.call_count == 2


def test_native_ip_helper_retries_only_documented_buffer_resize_codes(monkeypatch):
    api = fake_api(monkeypatch, adapter_codes=(111, 122, 0))
    assert network.available_networks()[0]["interface"] == "7"
    assert api.GetAdaptersInfo.call_count == 4


@pytest.mark.parametrize("size", [0, 1024 * 1024 + 1])
def test_native_ip_helper_rejects_unbounded_or_empty_allocations(monkeypatch, size):
    api = fake_api(monkeypatch, adapter_size=size)
    assert network.available_networks() == []
    assert api.GetAdaptersInfo.call_count == 1
    api.GetIpForwardTable.assert_not_called()


@pytest.mark.parametrize("codes", [(5,), (111, 122, 111)])
def test_native_ip_helper_errors_or_unstable_sizes_fail_closed(monkeypatch, codes):
    api = fake_api(monkeypatch, adapter_codes=codes)
    assert network.available_networks() == []
    assert api.GetAdaptersInfo.call_count <= 4
    api.GetIpForwardTable.assert_not_called()


@pytest.mark.parametrize("count", [2, 4097])
def test_native_ip_helper_rejects_truncated_or_oversized_route_tables(
    monkeypatch, count
):
    fake_api(monkeypatch, route_count=count)
    assert network.available_networks() == []


def test_native_ip_helper_unavailable_dll_fails_closed(monkeypatch):
    def unavailable(name):
        raise OSError("DLL unavailable")

    monkeypatch.setattr(network.ct, "WinDLL", unavailable, raising=False)
    assert network.available_networks() == []
