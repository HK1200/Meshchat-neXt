# SPDX-License-Identifier: 0BSD
"""Ensure LXST vendored pyogg exports ctypes aliases Opus needs.

Upstream ogg.py defines c_int_p and related names only inside
if PYOGG_OGG_AVAIL. When libopus loads but libogg does not, opus.py
still references those names and raises NameError on import.

Docker and Taskfile run a post-install disk patch. Plain pip install
does not, so Meshchat neXt applies the same fix before importing LXST.
"""

from __future__ import annotations

import importlib.abc
import importlib.metadata
import importlib.util
import sys
from ctypes import POINTER, c_char_p, c_float, c_int, c_ubyte
from pathlib import Path

_MARKER = "# meshchatnext-lxst-pyogg-ctypes-compat (do not remove; idempotency)\n"

_LEGACY_MARKER = (
    "# meshchatnext-lxst-pyogg-ctypes-pointer-aliases (do not remove; idempotency)\n"
)

_LEGACY_BLOCK = (
    _LEGACY_MARKER
    + "c_int_p = POINTER(c_int)\n"
    + "c_float_p = POINTER(c_float)\n"
    + "c_uchar_p = POINTER(c_ubyte)\n"
    + "c_char_p_p = POINTER(c_char_p)\n"
)

_INSERT = (
    _MARKER
    + "c_int_p = POINTER(c_int)\n"
    + "c_float_p = POINTER(c_float)\n"
    + "c_uchar_p = POINTER(c_ubyte)\n"
    + "c_char_p_p = POINTER(c_char_p)\n"
    + "c_uchar = c_ubyte\n"
)

_NEEDLE = (
    "from ctypes import c_int, c_int8, c_int16, c_int32, c_int64, c_uint, c_uint8, "
    "c_uint16, c_uint32, c_uint64, c_float, c_long, c_ulong, c_char, c_char_p, "
    "c_ubyte, c_longlong, c_ulonglong, c_size_t, c_void_p, c_double, POINTER, "
    "pointer, cast\n"
)

_OGG_MODULE = "LXST.Codecs.libs.pyogg.ogg"
_HOOK_INSTALLED = False

_ALIAS_VALUES = {
    "c_int_p": POINTER(c_int),
    "c_float_p": POINTER(c_float),
    "c_uchar_p": POINTER(c_ubyte),
    "c_char_p_p": POINTER(c_char_p),
    "c_uchar": c_ubyte,
}


def find_ogg_py() -> Path | None:
    """Locate LXST bundled pyogg ogg.py without importing LXST."""
    try:
        dist = importlib.metadata.distribution("lxst")
    except importlib.metadata.PackageNotFoundError:
        return None
    for rel in dist.files or ():
        parts = rel.parts
        if len(parts) >= 2 and parts[-2] == "pyogg" and parts[-1] == "ogg.py":
            return Path(str(dist.locate_file(rel)))
    return None


def repair_ogg_stream_state(ogg_module) -> bool:
    """Match Xiph's pointer fields before any Ogg stream is instantiated.

    The legacy binding uses scalar fields for lacing_vals and granule_vals.
    Windows LLP64 then allocates eight bytes less than libogg writes. Replace
    the type and every native argument referencing it; never resize an instance.
    """
    from ctypes import Structure

    old = getattr(ogg_module, "ogg_stream_state", None)
    library = getattr(ogg_module, "libogg", None)
    if old is None or library is None:
        return False
    expected = {
        "lacing_vals": POINTER(c_int),
        "granule_vals": POINTER(ogg_module.ogg_int64_t),
    }
    fields = dict(old._fields_)
    if all(fields.get(name) is kind for name, kind in expected.items()):
        return False
    if (
        fields.get("lacing_vals") is not c_int
        or fields.get("granule_vals") is not ogg_module.ogg_int64_t
    ):
        raise RuntimeError("Unsupported libogg stream-state binding layout")
    old_pointer = ogg_module.os_p
    fixed = type(
        "ogg_stream_state",
        (Structure,),
        {
            "__module__": ogg_module.__name__,
            "_fields_": [
                (name, expected.get(name, kind)) for name, kind in old._fields_
            ],
        },
    )
    new_pointer = POINTER(fixed)
    for function in vars(library).values():
        arguments = getattr(function, "argtypes", None)
        if isinstance(arguments, (list, tuple)) and any(
            arg is old_pointer for arg in arguments
        ):
            function.argtypes = [
                new_pointer if arg is old_pointer else arg for arg in arguments
            ]
    ogg_module.ogg_stream_state = fixed
    ogg_module.os_p = new_pointer
    return True


def inject_ctypes_aliases(ogg_module) -> list[str]:
    """Set missing ctypes aliases on a loaded ogg module. Returns names set."""
    added: list[str] = []
    for name, value in _ALIAS_VALUES.items():
        if not hasattr(ogg_module, name):
            setattr(ogg_module, name, value)
            added.append(name)
    repair_ogg_stream_state(ogg_module)
    return added


def apply_disk_patch(ogg: Path | None = None) -> str:
    """Patch ogg.py on disk. Returns status token."""
    target = ogg if ogg is not None else find_ogg_py()
    if target is None:
        return "missing"
    text = target.read_text(encoding="utf-8")
    if _MARKER in text:
        return "already"
    if _LEGACY_BLOCK in text:
        target.write_text(text.replace(_LEGACY_BLOCK, _INSERT, 1), encoding="utf-8")
        return "upgraded"
    if _NEEDLE not in text:
        return "unexpected"
    target.write_text(text.replace(_NEEDLE, _NEEDLE + _INSERT, 1), encoding="utf-8")
    return "patched"


class _OggCompatLoader(importlib.abc.Loader):
    """Load ogg.py then inject module-level ctypes aliases."""

    def __init__(self, origin: Path):
        self.origin = origin

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        source = self.origin.read_text(encoding="utf-8")
        code = compile(source, str(self.origin), "exec")
        exec(code, module.__dict__)  # noqa: S102 - module loader requires exec
        inject_ctypes_aliases(module)


class _AndroidOggCompatLoader(importlib.abc.Loader):
    """Wrap the original importer and supply missing PyOgg aliases."""

    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        if hasattr(self.original, "create_module"):
            return self.original.create_module(spec)
        return None

    def exec_module(self, module):
        self.original.exec_module(module)
        inject_ctypes_aliases(module)


class _OggCompatFinder(importlib.abc.MetaPathFinder):
    """Intercept LXST pyogg ogg import when disk patch is unavailable."""

    def find_spec(self, fullname, path, target=None):
        if fullname != _OGG_MODULE:
            return None
        if fullname in sys.modules:
            return None
        ogg = find_ogg_py()
        if ogg is None or not ogg.is_file():
            for finder in sys.meta_path:
                if finder is self:
                    continue
                find_spec = getattr(finder, "find_spec", None)
                if find_spec is None:
                    continue
                spec = find_spec(fullname, path, target)
                if spec is not None:
                    if spec.loader is not None:
                        spec.loader = _AndroidOggCompatLoader(spec.loader)
                    return spec
            return None
        try:
            ogg.read_text(encoding="utf-8")
        except OSError:
            return None
        loader = _OggCompatLoader(ogg)
        return importlib.util.spec_from_file_location(
            fullname,
            ogg,
            loader=loader,
            submodule_search_locations=None,
        )


def install_import_hook() -> bool:
    """Install a one-shot meta path finder for read-only site-packages."""
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return False
    for finder in sys.meta_path:
        if isinstance(finder, _OggCompatFinder):
            _HOOK_INSTALLED = True
            return False
    sys.meta_path.insert(0, _OggCompatFinder())
    _HOOK_INSTALLED = True
    return True


def ensure_lxst_pyogg_ctypes_compat() -> str:
    """Disk-patch when possible and install an import hook as fallback.

    Safe to call repeatedly. Does not import LXST.
    """
    status = "skipped"
    try:
        status = apply_disk_patch()
    except OSError:
        status = "readonly"
    install_import_hook()
    existing = sys.modules.get(_OGG_MODULE)
    if existing is not None:
        inject_ctypes_aliases(existing)
    return status


def patch_cli() -> int:
    """CLI used by scripts/patch_lxst_pyogg_ogg_ctypes.py."""
    try:
        status = apply_disk_patch()
    except OSError as exc:
        print(f"patch_lxst_pyogg_ogg_ctypes: write failed ({exc})", file=sys.stderr)
        return 1
    ogg = find_ogg_py()
    if status == "missing":
        print(
            "patch_lxst_pyogg_ogg_ctypes: lxst not installed, nothing to do",
            file=sys.stderr,
        )
        return 0
    if status == "already":
        print(f"patch_lxst_pyogg_ogg_ctypes: already applied ({ogg})")
        return 0
    if status == "upgraded":
        print(f"patch_lxst_pyogg_ogg_ctypes: upgraded legacy block ({ogg})")
        return 0
    if status == "unexpected":
        print(
            "patch_lxst_pyogg_ogg_ctypes: unexpected ogg.py layout. "
            f"manual check required ({ogg})",
            file=sys.stderr,
        )
        return 1
    print(f"patch_lxst_pyogg_ogg_ctypes: patched {ogg}")
    return 0
