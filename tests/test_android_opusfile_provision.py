"""Safety checks for the Android OpusFile provisioner (no Android SDK required)."""

import hashlib
import importlib.util
import io
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/android/provision-opusfile.py"
spec = importlib.util.spec_from_file_location("android_opusfile_provision", SCRIPT)
opusfile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opusfile)


def elf(abi):
    header = bytearray(64)
    header[:7] = b"\x7fELF" + bytes([opusfile.ABIS[abi][0], 1, 1])
    struct.pack_into("<HH", header, 16, 3, opusfile.ABIS[abi][1])
    return header


class OpusFileProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_download_recovers_transport_failure_without_caching_partial_bytes(self):
        payload = b"verified source fixture"
        digest = hashlib.sha256(payload).hexdigest()
        cache = self.root / "source.tar.gz"
        calls = []
        temporary_paths = []

        def response(url, timeout):
            calls.append((url, timeout))
            self.assertFalse(cache.exists())
            self.assertTrue(all(not p.exists() for p in temporary_paths))
            current = list(self.root.iterdir())
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0].stat().st_size, 0)
            temporary_paths.append(current[0])
            if len(calls) == 1:
                raise opusfile.urllib.error.URLError("interrupted TLS fixture")
            return io.BytesIO(payload)

        with (
            patch.object(opusfile.urllib.request, "urlopen", side_effect=response),
            patch.object(opusfile.time, "sleep") as sleep,
        ):
            self.assertEqual(
                opusfile.obtain(None, cache, opusfile.SOURCE_URL, digest), cache
            )
        self.assertEqual(cache.read_bytes(), payload)
        self.assertEqual(calls, [(opusfile.SOURCE_URL, 60)] * 2)
        sleep.assert_called_once_with(1)
        self.assertEqual(list(self.root.iterdir()), [cache])

    def test_download_checksum_failure_is_not_retried_or_cached(self):
        cache = self.root / "source.tar.gz"
        with (
            patch.object(
                opusfile.urllib.request,
                "urlopen",
                return_value=io.BytesIO(b"wrong bytes"),
            ) as fetch,
            patch.object(opusfile.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                opusfile.obtain(None, cache, opusfile.SOURCE_URL, "0" * 64)
        fetch.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_download_transport_retries_are_bounded_and_leave_no_cache(self):
        cache = self.root / "source.tar.gz"
        with (
            patch.object(
                opusfile.urllib.request,
                "urlopen",
                side_effect=opusfile.urllib.error.URLError("offline fixture"),
            ) as fetch,
            patch.object(opusfile.time, "sleep") as sleep,
        ):
            with self.assertRaises(opusfile.urllib.error.URLError):
                opusfile.obtain(None, cache, opusfile.SOURCE_URL, "0" * 64)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(1,), (2,)])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_download_not_found_is_not_retried(self):
        cache = self.root / "source.tar.gz"
        error = opusfile.urllib.error.HTTPError(
            opusfile.SOURCE_URL, 404, "not found", {}, None
        )
        with (
            patch.object(
                opusfile.urllib.request, "urlopen", side_effect=error
            ) as fetch,
            patch.object(opusfile.time, "sleep") as sleep,
        ):
            with self.assertRaises(opusfile.urllib.error.HTTPError):
                opusfile.obtain(None, cache, opusfile.SOURCE_URL, "0" * 64)
        fetch.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_architectures_and_wrong_abi(self):
        path = self.root / "lib.so"
        for abi in opusfile.ABIS:
            path.write_bytes(elf(abi))
            opusfile.verify_elf(path, abi)
            wrong = next(other for other in opusfile.ABIS if other != abi)
            with self.assertRaises(ValueError):
                opusfile.verify_elf(path, wrong)
        path.write_bytes(b"not an ELF")
        with self.assertRaises(ValueError):
            opusfile.verify_elf(path, "x86_64")

    def test_source_checksum_rejected(self):
        archive = self.root / "source.tar.gz"
        archive.write_bytes(b"corrupt archive")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            opusfile.verify_source(archive)

    def test_archive_rejects_traversal_and_links(self):
        for name, kind in [
            ("opusfile-0.12/../../escape", tarfile.REGTYPE),
            ("opusfile-0.12/link", tarfile.SYMTYPE),
            ("/absolute", tarfile.REGTYPE),
        ]:
            archive = self.root / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "/tmp/escape"
                output.addfile(info)
            with self.assertRaises(ValueError):
                opusfile.extract_source(archive, self.root / "extract")
            self.assertFalse((self.root / "extract").exists())

    def test_publish_never_replaces_existing_file(self):
        built, target = self.root / "built.so", self.root / "lib.so"
        built.write_bytes(elf("x86_64"))
        opusfile.publish_missing(built, target, "x86_64")
        original = bytes(elf("x86_64")) + b"original payload"
        target.write_bytes(original)
        opusfile.publish_missing(built, target, "x86_64")
        self.assertEqual(target.read_bytes(), original)
        target.write_bytes(b"invalid existing file")
        with self.assertRaises(ValueError):
            opusfile.publish_missing(built, target, "x86_64")
        self.assertEqual(target.read_bytes(), b"invalid existing file")

    def test_publish_does_not_replace_dangling_symlink(self):
        built, target = self.root / "built.so", self.root / "lib.so"
        built.write_bytes(elf("x86_64"))
        target.symlink_to(self.root / "missing")
        with self.assertRaises(OSError):
            opusfile.publish_missing(built, target, "x86_64")
        self.assertTrue(target.is_symlink())

    def test_verify_only_missing_is_read_only(self):
        with (
            patch.object(opusfile, "ROOT", self.root),
            patch.object(
                sys,
                "argv",
                ["provision-opusfile.py", "--verify-only", "--abis", "x86_64"],
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Missing OpusFile"):
                opusfile.main()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_library_needs_no_sdk_or_download(self):
        target = self.root / "android/app/src/main/jniLibs/x86_64/libopusfile.so"
        target.parent.mkdir(parents=True)
        original = elf("x86_64")
        target.write_bytes(original)
        with (
            patch.object(opusfile, "ROOT", self.root),
            patch.object(sys, "argv", ["provision-opusfile.py", "--abis", "x86_64"]),
            patch.object(
                opusfile.urllib.request,
                "urlopen",
                side_effect=AssertionError("download"),
            ),
        ):
            opusfile.main()
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.root / ".local").exists())


if __name__ == "__main__":
    unittest.main()
