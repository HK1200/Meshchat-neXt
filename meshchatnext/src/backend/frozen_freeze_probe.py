# SPDX-License-Identifier: 0BSD

"""Import probes for cx_Freeze desktop builds.

Invoked from CI and build-backend via:

  MeshchatNext --meshchatnext-run-module meshchatnext.src.backend.frozen_freeze_probe
"""

from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path


def _lxst_filterlib_path() -> Path | None:
    spec = importlib.util.find_spec("LXST")
    if spec is None or not spec.submodule_search_locations:
        return None
    root = Path(next(iter(spec.submodule_search_locations)))
    if not root.is_dir():
        return None
    ext = sysconfig.get_config_var("EXT_SUFFIX") or ""
    candidates: list[Path] = []
    if sys.platform == "win32":
        candidates.append(root / "filterlib.dll")
    if ext:
        candidates.append(root / f"filterlib{ext}")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _mapped_library_paths(maps_text: str, library: str) -> list[str]:
    """Preserve spaces in the pathname field of Linux process mappings."""
    paths = []
    for line in maps_text.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and library in fields[5]:
            paths.append(fields[5])
    return paths


def main() -> None:
    import email.header
    import email.message
    import email.policy  # noqa: F401

    import aiohttp  # noqa: F401
    import LXST  # noqa: F401
    import RNS.vendor.umsgpack as umsgpack

    packed = umsgpack.packb({"probe": True})
    if umsgpack.unpackb(packed).get("probe") is not True:
        raise SystemExit("frozen-freeze-probe: RNS.vendor.umsgpack roundtrip failed")

    native = _lxst_filterlib_path()
    if native is None:
        raise SystemExit("frozen-freeze-probe: LXST filterlib native artifact missing")

    if sys.platform == "darwin":
        # The macOS slices ship libcodec2 for the ctypes binding. The pycodec2
        # extension is not part of the freeze.
        from meshchatnext import pycodec2_ctypes

        codec = pycodec2_ctypes.Codec2(1600)
        if codec.samples_per_frame() <= 0:
            raise SystemExit(
                "frozen-freeze-probe: codec2 ctypes binding returned no samples"
            )

    if sys.platform == "win32":
        import numpy as np
        import pycodec2
        from bleak.backends.winrt.scanner import BleakScannerWinRT  # noqa: F401
        from meshcore.ble_cx import BLEConnection
        from meshcore.serial_cx import SerialConnection

        from meshchatnext.src.backend.meshcore_windows_credentials import (
            WindowsNodePasswords,  # noqa: F401
        )

        # Exercise the bundled codec without microphones, speakers or radios.
        codec = pycodec2.Codec2(1200)
        count = codec.samples_per_frame()
        decoded = codec.decode(codec.encode(np.zeros(count, dtype=np.int16)))
        if len(decoded) != count or not np.isfinite(decoded).all():
            raise SystemExit("frozen-freeze-probe: Windows Codec2 roundtrip failed")
        if getattr(sys, "frozen", False):
            helper = Path(sys.executable).resolve().parent / "bin/meshchatnext-sip.exe"
            if not helper.is_file():
                raise SystemExit("frozen-freeze-probe: Windows SIP helper missing")

    if sys.platform.startswith("linux"):
        # Compiled D-Bus serializers import private modules dynamically. A plain
        # Bleak import does not exercise them; serialize without opening any bus
        # or scanning a user's Bluetooth devices.
        from dbus_fast import Message

        dbus_probe = Message(
            destination="org.bluez",
            path="/",
            interface="org.freedesktop.DBus.Peer",
            member="Ping",
        )
        if not dbus_probe._marshall(False):
            raise SystemExit(
                "frozen-freeze-probe: Bluetooth D-Bus serialization failed"
            )
        import jeepney  # noqa: F401
        import numpy as np
        import pycodec2
        import secretstorage  # noqa: F401
        from meshcore.ble_cx import BLEConnection  # noqa: F401
        from meshcore.serial_cx import SerialConnection  # noqa: F401

        from meshchatnext.src.backend.meshcore_desktop_transport import (
            DesktopConnection,
        )

        # Constructing an adapter must not connect or probe a user's radio.
        DesktopConnection("usb", "/dev/meshchatnext-unopened-probe")
        import base64

        from meshchatnext.src.backend.meshcore_images import decode_image, encode_image

        rgb = bytes(
            v for y in range(32) for x in range(32) for v in (x * 8, y * 8, 128)
        )
        photo, _aspect, preview = encode_image(base64.b64encode(rgb).decode(), 32, 32)
        decoded_photo = decode_image(photo)
        if decoded_photo["png_base64"] != preview["png_base64"]:
            raise SystemExit("frozen-freeze-probe: AV1 photo roundtrip failed")
        if getattr(sys, "frozen", False):
            photo_paths = _mapped_library_paths(
                Path("/proc/self/maps").read_text(), "libvox_av1"
            )
            root = Path(sys.executable).resolve().parent
            if not photo_paths or any(
                not Path(p).resolve().is_relative_to(root) for p in photo_paths
            ):
                raise SystemExit(
                    "frozen-freeze-probe: photo codec resolved outside bundle"
                )
        codec = pycodec2.Codec2(1200)
        count = codec.samples_per_frame()
        decoded = codec.decode(codec.encode(np.zeros(count, dtype=np.int16)))
        if len(decoded) != count or not np.isfinite(decoded).all():
            raise SystemExit("frozen-freeze-probe: Codec2 roundtrip failed")
        if getattr(sys, "frozen", False):
            # Prove we are not accidentally passing against a host-installed
            # libcodec2 while shipping an incomplete desktop bundle.
            root = Path(sys.executable).resolve().parent
            mappings = _mapped_library_paths(
                Path("/proc/self/maps").read_text(), "libcodec2"
            )
            if not mappings or any(
                not Path(p).resolve().is_relative_to(root) for p in mappings
            ):
                raise SystemExit("frozen-freeze-probe: Codec2 resolved outside bundle")

    print("frozen-freeze-probe ok", flush=True)


if __name__ == "__main__":
    main()
