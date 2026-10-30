# SPDX-License-Identifier: 0BSD

"""Meshchat neXt - A mesh network communications app."""

# Synced from package.json via scripts/sync_version.js (also writes meshchatnext/src/version.py).
__version__ = "0.1.5"
# LXST vendored pyogg can NameError on import when libopus is present but
# libogg is not. Apply before any meshchatnext module imports LXST.
try:
    from meshchatnext.src.backend.lxst_pyogg_ctypes_compat import (
        ensure_lxst_pyogg_ctypes_compat,
    )

    ensure_lxst_pyogg_ctypes_compat()
except (ImportError, OSError, ValueError):
    pass

# On Android, LXST's PyOgg must discover the packaged libopus.so
# before its first import. Desktop platforms retain normal discovery.
try:
    from meshchatnext.android_opus import ensure_android_opus

    ensure_android_opus()
except (ImportError, OSError, ValueError):
    pass
