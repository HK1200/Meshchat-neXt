"""Repeated Android packaging must preserve checksum-pinned wheel inputs."""

import importlib.util
import zipfile
from pathlib import Path


def test_existing_codec2_wheel_is_not_rewritten(tmp_path):
    script = Path(__file__).parents[1] / "scripts/repack-android-pycodec2-wheels.py"
    spec = importlib.util.spec_from_file_location("codec2_repack", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    library = tmp_path / "libcodec2.so"
    library.write_bytes(b"codec2")
    wheel = tmp_path / "pycodec2.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("pycodec2/libcodec2.so", library.read_bytes())
    before = wheel.read_bytes()
    assert module.repack_pycodec2_wheel(wheel, library)
    assert module.repack_pycodec2_wheel(wheel, library)
    assert wheel.read_bytes() == before
