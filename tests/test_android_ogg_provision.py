"""Safety checks for the Android Ogg provisioner (no Android SDK required)."""

import importlib.util
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/android/provision-ogg.py"
spec = importlib.util.spec_from_file_location("android_ogg_provision", SCRIPT)
ogg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ogg)


def elf(abi):
    header = bytearray(64)
    header[:7] = b"\x7fELF" + bytes([ogg.ABIS[abi][0], 1, 1])
    struct.pack_into("<HH", header, 16, 3, ogg.ABIS[abi][1])
    return header


class OggProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_architectures_and_wrong_abi(self):
        path = self.root / "lib.so"
        for abi in ogg.ABIS:
            path.write_bytes(elf(abi))
            ogg.verify_elf(path, abi)
            wrong = next(other for other in ogg.ABIS if other != abi)
            with self.assertRaises(ValueError):
                ogg.verify_elf(path, wrong)
        path.write_bytes(b"not an ELF")
        with self.assertRaises(ValueError):
            ogg.verify_elf(path, "x86_64")

    def test_source_checksum_rejected(self):
        archive = self.root / "source.tar.gz"
        archive.write_bytes(b"corrupt archive")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            ogg.verify_source(archive)

    def test_archive_rejects_traversal_and_links(self):
        for name, kind in [
            ("libogg-1.3.6/../../escape", tarfile.REGTYPE),
            ("libogg-1.3.6/link", tarfile.SYMTYPE),
            ("/absolute", tarfile.REGTYPE),
        ]:
            archive = self.root / "bad.tar.gz"
            with tarfile.open(archive, "w:xz") as output:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "/tmp/escape"
                output.addfile(info)
            with self.assertRaises(ValueError):
                ogg.extract_source(archive, self.root / "extract")
            self.assertFalse((self.root / "extract").exists())

    def test_publish_never_replaces_existing_file(self):
        built, target = self.root / "built.so", self.root / "lib.so"
        built.write_bytes(elf("x86_64"))
        ogg.publish_missing(built, target, "x86_64")
        original = bytes(elf("x86_64")) + b"original payload"
        target.write_bytes(original)
        ogg.publish_missing(built, target, "x86_64")
        self.assertEqual(target.read_bytes(), original)
        target.write_bytes(b"invalid existing file")
        with self.assertRaises(ValueError):
            ogg.publish_missing(built, target, "x86_64")
        self.assertEqual(target.read_bytes(), b"invalid existing file")

    def test_publish_does_not_replace_dangling_symlink(self):
        built, target = self.root / "built.so", self.root / "lib.so"
        built.write_bytes(elf("x86_64"))
        target.symlink_to(self.root / "missing")
        with self.assertRaises(OSError):
            ogg.publish_missing(built, target, "x86_64")
        self.assertTrue(target.is_symlink())

    def test_verify_only_missing_is_read_only(self):
        with (
            patch.object(ogg, "ROOT", self.root),
            patch.object(
                sys, "argv", ["provision-ogg.py", "--verify-only", "--abis", "x86_64"]
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Missing Ogg"):
                ogg.main()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_library_needs_no_sdk_or_download(self):
        target = self.root / "android/app/src/main/jniLibs/x86_64/libogg.so"
        target.parent.mkdir(parents=True)
        original = elf("x86_64")
        target.write_bytes(original)
        with (
            patch.object(ogg, "ROOT", self.root),
            patch.object(sys, "argv", ["provision-ogg.py", "--abis", "x86_64"]),
            patch.object(
                ogg.urllib.request, "urlopen", side_effect=AssertionError("download")
            ),
        ):
            ogg.main()
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.root / ".local").exists())


if __name__ == "__main__":
    unittest.main()
