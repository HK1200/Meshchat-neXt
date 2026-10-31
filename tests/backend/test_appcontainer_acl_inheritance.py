import ctypes
import ntpath
import unittest
from unittest.mock import patch

from meshchatnext.src.backend import appcontainer_sandbox as ac


class FakeApi:
    def __init__(self):
        self.entries = []

    def GetNamedSecurityInfoW(self, *args):
        return 0

    def SetEntriesInAclW(self, count, entries, existing, output):
        entry = ctypes.cast(entries, ctypes.POINTER(ac._EXPLICIT_ACCESS_W)).contents
        self.entries.append((entry.grfInheritance, entry.grfAccessPermissions))
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(1)
        return 0

    def SetNamedSecurityInfoW(self, *args):
        return 0


class ParentAclTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.sid = ctypes.c_void_p(1)
        self.loader = patch.object(ctypes, "WinDLL", return_value=self.api, create=True)
        self.no_propagation = patch.object(
            ac, "_set_directory_dacl_without_propagation", return_value=0
        )
        self.no_propagation_mock = self.no_propagation.start()
        self.addCleanup(self.no_propagation.stop)
        self.free = patch.object(ac, "_local_free")
        self.loader.start()
        self.free.start()
        self.addCleanup(self.loader.stop)
        self.addCleanup(self.free.stop)

    def test_windows_ancestors_include_drive_root_once(self):
        self.assertEqual(
            list(ac._ancestor_directories(r"D:\a\build\public", path_module=ntpath)),
            [r"D:\a\build", r"D:\a", "D:\\"],
        )

    def test_volume_root_grant_is_traverse_only_and_noninheriting(self):
        ac.grant_execute_access(self.sid, "D:\\")
        self.assertEqual(self.api.entries, [(0, ac._GENERIC_EXECUTE)])
        self.no_propagation_mock.assert_called_once()

    def test_parent_traverse_does_not_inherit(self):
        ac.grant_execute_access(self.sid, r"E:\Projects")
        self.assertEqual(self.api.entries, [(0, ac._GENERIC_EXECUTE)])
        self.no_propagation_mock.assert_called_once()

    def test_read_root_still_inherits(self):
        ac.grant_path_access(self.sid, r"E:\candidate", write=False)
        self.assertEqual(
            self.api.entries,
            [
                (
                    ac._SUB_CONTAINERS_AND_OBJECTS_INHERIT,
                    ac._GENERIC_READ | ac._GENERIC_EXECUTE,
                )
            ],
        )

    def test_parent_revoke_does_not_inherit(self):
        ac.revoke_path_access(self.sid, r"E:\Projects", inherit=False)
        self.assertEqual(self.api.entries[0][0], 0)

    def test_root_revoke_still_inherits(self):
        ac.revoke_path_access(self.sid, r"E:\candidate")
        self.assertEqual(self.api.entries[0][0], ac._SUB_CONTAINERS_AND_OBJECTS_INHERIT)

    def test_write_root_still_inherits(self):
        ac.grant_path_access(self.sid, r"E:\test-profile", write=True)
        self.assertEqual(
            self.api.entries,
            [
                (
                    ac._SUB_CONTAINERS_AND_OBJECTS_INHERIT,
                    ac._GENERIC_READ
                    | ac._GENERIC_WRITE
                    | ac._GENERIC_EXECUTE
                    | ac._GENERIC_ALL,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
