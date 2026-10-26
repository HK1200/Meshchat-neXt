"""Regression for SONAME links created before their targets are unpacked."""

import os
import textwrap
from pathlib import Path


def test_soname_guard_handles_dangling_and_valid_links(tmp_path):
    source = (
        Path(__file__).parents[1] / "scripts/build-android-wheels-local.sh"
    ).read_text()
    # Execute the actual code inserted into Chaquopy, including its guard.
    guard = source.split("    guarded = (", 1)[1].split("    text = text.replace", 1)[0]
    namespace = {}
    exec("guarded = (" + guard, namespace)
    code = textwrap.dedent(namespace["guarded"])
    library = tmp_path / "libpython.so"
    library.symlink_to("libpython3.11.so")
    calls = []
    env = {
        "os": os,
        "reqs_lib_dir": str(tmp_path),
        "filename": "libpython3.11.so",
        "link_filename": library.name,
        "run": calls.append,
    }
    exec(code, env)
    assert calls == []
    (tmp_path / "libpython3.11.so").write_bytes(b"library")
    exec(code, env)
    assert calls == []
    library.unlink()
    exec(code, env)
    assert calls == [f"ln -s libpython3.11.so {library}"]
