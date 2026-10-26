# SPDX-License-Identifier: 0BSD
"""Make the packaged Android Opus, Ogg and OpusFile libraries discoverable to LXST PyOgg."""

from __future__ import annotations

import ctypes
import importlib.abc
import importlib.machinery
import sys
from pathlib import Path

from meshchatnext.src.env_utils import env_str

_TARGET = "LXST.Codecs.libs.pyogg.library_loader"
_installed = False


class _OpusLoader(importlib.abc.Loader):
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        if hasattr(self.original, "create_module"):
            return self.original.create_module(spec)
        return None

    def exec_module(self, module):
        self.original.exec_module(module)

        original_load = module.Library.load

        def load(names, paths=None, tests=()):
            if names.get("external") in ("opus", "ogg", "opusfile"):
                native_dir = env_str("MESHCHAT_NATIVE_LIB_DIR")
                if native_dir:
                    path = Path(native_dir) / f"lib{names['external']}.so"
                    if path.is_file():
                        try:
                            lib = ctypes.CDLL(str(path))
                            if not tests or all(test(lib) for test in tests):
                                return lib
                        except OSError:
                            pass

            return original_load(names, paths, tests)

        module.Library.load = staticmethod(load)


class _OpusFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname != _TARGET:
            return None

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None

        spec.loader = _OpusLoader(spec.loader)
        return spec


def ensure_android_opus() -> bool:
    """Install the Android-only PyOgg audio-library discovery hook."""
    global _installed

    if _installed:
        return True

    native_dir = env_str("MESHCHAT_NATIVE_LIB_DIR")
    if not native_dir:
        return False

    library = Path(native_dir) / "libopus.so"
    if not library.is_file():
        return False

    sys.meta_path.insert(0, _OpusFinder())
    _installed = True
    return True
