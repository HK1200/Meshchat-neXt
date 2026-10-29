#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local Windows readiness probe; does not connect radios or use app identities."""

import argparse
import asyncio
import json
import platform
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credential-self-test",
        action="store_true",
        help="Create/read/delete one random temporary Credential Manager test slot",
    )
    parser.add_argument(
        "--scan-bluetooth",
        action="store_true",
        help="Scan UART-service advertisements for five seconds; never connect",
    )
    parser.add_argument(
        "--sip-ipc-test",
        action="store_true",
        help="Launch the native helper in loopback-only test mode, ping and stop; no accounts or external calls",
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run this probe from native Windows, not Linux or WSL")
    from meshchatnext.src.backend.meshcore_desktop_transport import (
        attached_devices,
        discover_devices,
    )

    report = {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "serial_devices": attached_devices(),
        "radio_connections_opened": False,
        "sip_available": False,
    }
    if args.credential_self_test:
        from meshchatnext.src.backend.meshcore_windows_credentials import (
            WindowsNodePasswords,
        )

        provider = WindowsNodePasswords()
        owner, peer, value = (
            secrets.token_hex(32),
            secrets.token_hex(32),
            secrets.token_urlsafe(24),
        )
        try:
            provider.save(owner, peer, "member", value)
            if (
                not provider.has(owner, peer, "member")
                or provider.load(owner, peer, "member") != value
            ):
                raise RuntimeError("Credential Manager round-trip failed")
        finally:
            provider.forget(owner, peer, "member")
        if provider.has(owner, peer, "member"):
            raise RuntimeError("Temporary credential was not removed")
        report["credential_self_test"] = "passed; temporary slot removed"
    if args.scan_bluetooth:
        report["bluetooth_devices"] = asyncio.run(discover_devices())
    from meshchatnext.src.backend.sip_desktop_http import native_executable

    helper = native_executable()
    report["sip_helper_present"] = helper is not None
    if args.sip_ipc_test:
        if helper is None:
            raise RuntimeError("Build the Windows SIP helper first")
        from meshchatnext.src.backend.sip_desktop_engine import DesktopSipEngine

        async def check_ipc():
            engine = DesktopSipEngine(helper, test_audio=True, timeout=15)
            try:
                await engine.launch()
                replies = await asyncio.gather(
                    *(engine.command("ping") for _ in range(20))
                )
                if len({row["id"] for row in replies}) != 20:
                    raise RuntimeError("SIP IPC response correlation failed")
            finally:
                await engine.close()
            return "passed; 20 private IPC pings; stopped; no registration or calls"

        report["sip_ipc_test"] = asyncio.run(check_ipc())
    from meshchatnext.src.backend.sip_windows_network import available_networks

    report["sip_network_candidates"] = available_networks()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
