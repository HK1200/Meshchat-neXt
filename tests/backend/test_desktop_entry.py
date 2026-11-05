# SPDX-License-Identifier: 0BSD

"""Verify bootstrap ordering without importing the real backend or spawning."""

import builtins
import runpy
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ENTRY = Path(__file__).resolve().parents[2] / "meshchatnext" / "desktop_entry.py"


class DesktopEntryTests(unittest.TestCase):
    def test_freeze_dispatch_precedes_backend_import_and_start(self):
        calls = []
        mp = ModuleType("multiprocessing")
        mp.freeze_support = lambda: calls.append("freeze")
        backend = ModuleType("meshchatnext.meshchat")
        backend.main = lambda: calls.append("main")
        original_import = builtins.__import__

        def checked_import(name, *args, **kwargs):
            if name == "meshchatnext.meshchat":
                self.assertEqual(calls, ["freeze"])
                calls.append("backend-import")
            return original_import(name, *args, **kwargs)

        with (
            patch.dict(
                sys.modules, {"multiprocessing": mp, "meshchatnext.meshchat": backend}
            ),
            patch("builtins.__import__", checked_import),
        ):
            runpy.run_path(str(ENTRY), run_name="__main__")
        self.assertEqual(calls, ["freeze", "backend-import", "main"])

    def test_importing_entry_does_not_start_backend(self):
        mp = ModuleType("multiprocessing")
        mp.freeze_support = lambda: self.fail("Import must not dispatch workers")
        with patch.dict(sys.modules, {"multiprocessing": mp}):
            runpy.run_path(str(ENTRY), run_name="desktop_entry_import_only")


if __name__ == "__main__":
    unittest.main()
