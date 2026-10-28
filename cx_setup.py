# SPDX-License-Identifier: 0BSD

import importlib.util
import os
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_vendor_lxmfy = ROOT / "vendor" / "lxmfy"
if _vendor_lxmfy.is_dir() and (_vendor_lxmfy / "lxmfy").is_dir():
    sys.path.insert(0, str(_vendor_lxmfy))
_vendor_rns_filesync = ROOT / "vendor" / "rns_filesync"
if _vendor_rns_filesync.is_dir() and (_vendor_rns_filesync / "rns_filesync").is_dir():
    sys.path.insert(0, str(_vendor_rns_filesync))

from cx_Freeze import Executable, setup

from meshchatnext.src.version import __version__

PUBLIC_DIR = ROOT / "meshchatnext" / "public"

target_name = os.environ.get("CX_FREEZE_TARGET_NAME", "MeshchatNext")
build_exe_dir = os.environ.get("CX_FREEZE_BUILD_EXE", "build/exe")

include_files = []

changelog_path = ROOT / "CHANGELOG.md"
if changelog_path.exists():
    include_files.append((str(changelog_path), "CHANGELOG.md"))

frontend_licenses_path = (
    ROOT / "meshchatnext" / "src" / "backend" / "data" / "licenses_frontend.json"
)
if frontend_licenses_path.exists():
    include_files.append((str(frontend_licenses_path), "licenses_frontend.json"))

backend_licenses_path = (
    ROOT / "meshchatnext" / "src" / "backend" / "data" / "licenses_backend.json"
)
if backend_licenses_path.exists():
    include_files.append((str(backend_licenses_path), "licenses_backend.json"))

third_party_notices_path = (
    ROOT / "meshchatnext" / "src" / "backend" / "data" / "THIRD_PARTY_NOTICES.txt"
)
if third_party_notices_path.exists():
    include_files.append((str(third_party_notices_path), "THIRD_PARTY_NOTICES.txt"))

if PUBLIC_DIR.exists() and PUBLIC_DIR.is_dir():
    include_files.append((str(PUBLIC_DIR), "public"))

logo_dir = ROOT / "logo"
if logo_dir.exists() and logo_dir.is_dir():
    include_files.append(("logo", "logo"))

bin_dir = ROOT / "bin"
if bin_dir.exists() and bin_dir.is_dir():
    include_files.append(("bin", "bin"))

linux_sip = ROOT / ".local/linux-sip/meshchatnext-sip"
if sys.platform.startswith("linux") and linux_sip.is_file():
    include_files.append((str(linux_sip), "bin/meshchatnext-sip"))
    native_licenses = linux_sip.parent / "licenses"
    if native_licenses.is_dir():
        include_files.append((str(native_licenses), "licenses/linux-sip"))

linux_av1 = ROOT / ".local/av1/libvox_av1.so"
if not linux_av1.is_file():
    linux_av1 = ROOT / "temp-tests/av1-build/libvox_av1.so"
if sys.platform.startswith("linux") and linux_av1.is_file():
    include_files.append((str(linux_av1), "lib/libvox_av1.so"))
    include_files.extend(
        (str(linux_av1.parent / "aom" / notice), "licenses/av1/" + notice)
        for notice in ("LICENSE", "PATENTS")
    )

# macOS slices skip the pycodec2 extension and ship libcodec2 at the
# site-packages root for meshchatnext/pycodec2_ctypes.py to dlopen. When the
# extension is installed (Linux, Windows) the package is traced normally;
# when only the dylib exists it is bundled into lib/ instead.
pycodec2_installed = importlib.util.find_spec("pycodec2") is not None
if not pycodec2_installed:
    for _codec2_name in ("libcodec2.dylib", "libcodec2.so"):
        _codec2_lib = Path(sysconfig.get_paths()["purelib"]) / _codec2_name
        if _codec2_lib.is_file():
            include_files.append((str(_codec2_lib), f"lib/{_codec2_name}"))
            break

packages = (
    [
        "RNS",
        "RNS.Interfaces",
        # Vendored u-msgpack is used by RNS Identity ratchet persist and LXMF.
        # Name it explicitly so cx_Freeze cannot drop it from desktop freezes.
        "RNS.vendor",
        "LXMF",
        "LXST",
    ]
    + (["pycodec2"] if pycodec2_installed else [])
    + (
        ["secretstorage", "jeepney", "dbus_fast"]
        if sys.platform.startswith("linux")
        else []
    )
    + [
        "lxmfy",
        "rns_filesync",
        "websockets",
        "pycparser",
        "cffi",
        "bleak",
        "landlockpy",
        "seccompy",
        # aiohttp pulls stdlib email at runtime. Keep the full tree out of library.zip
        # so relative imports like email._policybase -> email.header work on Windows.
        "email",
    ]
)

# Keep FS sandbox helpers even when import tracing is incomplete (Windows
# launcher is entered via --meshchatnext-run-module and must stay in the freeze).
includes = [
    "meshchatnext.src.backend.landlock_sandbox",
    "meshchatnext.src.backend.appcontainer_sandbox",
    "meshchatnext.src.backend.appcontainer_launcher",
    "meshchatnext.src.backend.seccomp_sandbox",
    "meshchatnext.src.backend.frozen_freeze_probe",
    "meshchatnext.src.backend.host_audio_probe",
    "RNS.vendor.umsgpack",
    "RNS.vendor.configobj",
]

if sys.version_info >= (3, 13):
    packages.append("audioop")

setup(
    name="MeshchatNext",
    version=__version__,
    description="A simple mesh network communications app powered by the Reticulum Network Stack",
    executables=[
        Executable(
            script="meshchatnext/meshchat.py",
            base=None,
            target_name=target_name,
            shortcut_name="MeshchatNext",
            shortcut_dir="ProgramMenuFolder",
            icon="logo/icon.ico",
        ),
    ],
    options={
        "build_exe": {
            "packages": packages,
            "includes": includes,
            "include_files": include_files,
            "excludes": [
                "PIL",
                "tkinter",
                "pydoc",
                "pydoc_data",
                "setuptools",
                "distutils",
                "pkg_resources",
            ],
            "zip_exclude_packages": ["email"],
            "optimize": 2,
            "build_exe": build_exe_dir,
            "replace_paths": [
                ("*", ""),
            ],
        },
    },
)
