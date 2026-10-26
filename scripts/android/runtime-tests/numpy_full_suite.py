# ruff: noqa: S101 - this is an instrumentation test payload.
import json
import os
import pathlib
import shutil
import sys
import tempfile
import zipfile

root = pathlib.Path(globals()["TEST_ROOT"])
scratch = root / "scratch"
pytest_tmp = root / "pytest-tmp"
for folder in [scratch, pytest_tmp]:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
tempfile.tempdir = str(scratch)
os.environ["TMPDIR"] = str(scratch)
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
os.environ["NPY_AVAILABLE_MEM"] = "256MB"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
for wheel in root.glob("*.whl"):
    sys.path.insert(0, str(wheel))
source = root / "upstream"
source.mkdir(exist_ok=True)
with zipfile.ZipFile(root / "numpy-tests.zip") as z:
    z.extractall(source)
import hashlib
from pathlib import Path

import numpy as np

_native_path = Path(np.core._multiarray_umath.__file__)
with _native_path.open("rb") as _native_stream:
    assert _native_stream.read(4) == b"\x7fELF"
    _native_stream.seek(0)
    _native_sha256 = hashlib.file_digest(_native_stream, "sha256").hexdigest()
# Keep test logging independent of Java proxy collection during gc tests.
import ctypes

import pytest

_native_log = ctypes.CDLL("liblog.so").__android_log_write
_native_log.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
_native_log.restype = ctypes.c_int


class AndroidLog:
    @staticmethod
    def i(tag, message):
        return _native_log(4, tag.encode(), str(message).encode())


AndroidLog.i(
    "MeshchatNextNumpyBuild", json.dumps({"native_multiarray_sha256": _native_sha256})
)


# Keep production imports intact; collect upstream tests from ordinary files.
class Results:
    def __init__(self):
        self.counts = {}
        self.failures = []

    def pytest_runtest_logstart(self, nodeid, location):
        if globals().get("TRACE_TESTS", False):
            AndroidLog.i("MeshchatNextNumpyCase", nodeid)

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or report.failed:
            key = report.outcome
            self.counts[key] = self.counts.get(key, 0) + 1
            if sum(self.counts.values()) % 1000 == 0:
                AndroidLog.i("MeshchatNextNumpyProgress", str(self.counts))
            if report.failed:
                self.failures.append(
                    {"test": report.nodeid, "detail": str(report.longrepr)[-5000:]}
                )

    def pytest_sessionfinish(self, session, exitstatus):
        self.collected = session.testscollected
        reporter = session.config.pluginmanager.getplugin("terminalreporter")
        if reporter is not None:
            self.counts = {
                key: len(value) for key, value in reporter.stats.items() if key
            }

    def pytest_collectreport(self, report):
        if report.failed:
            self.failures.append(
                {"collection": report.nodeid, "detail": str(report.longrepr)[-5000:]}
            )


diagnostic = None
if globals().get("TRACE_TESTS", False) and globals().get("TEST_DIAGNOSTIC_FILE"):
    import faulthandler

    diagnostic = open(globals()["TEST_DIAGNOSTIC_FILE"], "w")
    faulthandler.dump_traceback_later(60, repeat=True, file=diagnostic)
results = Results()
targets = [str(source / "numpy")]
selected = json.loads(globals().get("SELECTED_TESTS", "[]"))
if globals().get("TEST_MODE") == "subset":
    assert selected
    for node in selected:
        relative = pathlib.PurePosixPath(node.split("::")[0])
        assert (
            not relative.is_absolute()
            and ".." not in relative.parts
            and relative.parts[0] == "numpy"
        )
        assert (source / relative).is_file()
    targets = [str(source / node) for node in selected]
log = root / "numpy-upstream-output.txt"
with log.open("w") as out:
    previous_out, previous_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = out
    try:
        code = pytest.main(
            targets
            + [
                "--rootdir=" + str(source),
                "--import-mode=importlib",
                "--continue-on-collection-errors",
                "--tb=short",
                "--disable-warnings",
                "--basetemp=" + str(pytest_tmp),
                "-q",
                "--available-memory=256MB",
                "--junitxml=" + str(root / "numpy-upstream.xml"),
            ]
            + (["--collect-only"] if globals().get("TEST_MODE") == "collect" else []),
            plugins=["hypothesis.extra.pytestplugin", results],
        )
    finally:
        sys.stdout, sys.stderr = previous_out, previous_err
if diagnostic is not None:
    faulthandler.cancel_dump_traceback_later()
    diagnostic.close()
summary = {
    "numpy": np.__version__,
    "native_multiarray_sha256": _native_sha256,
    "pytest_exit_code": int(code),
    "outcomes": results.counts,
    "collected": getattr(results, "collected", 0),
    "failures": results.failures,
    "scope": (
        "entire upstream test tree shipped in exact NumPy wheel; no selected test exclusions; 256MB advertised memory limit"
        if not selected
        else "explicitly selected upstream cases"
    ),
    "selected_tests": selected,
}
(root / "numpy-upstream-results.json").write_text(json.dumps(summary, indent=2))
RESULT = json.dumps({k: v for k, v in summary.items() if k != "failures"})
for folder in [scratch, pytest_tmp]:
    shutil.rmtree(folder, ignore_errors=True)
