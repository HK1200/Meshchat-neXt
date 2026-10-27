from pathlib import Path

from meshchatnext.src.backend.frozen_freeze_probe import _mapped_library_paths


def test_bundle_check_preserves_normal_linux_install_path_with_spaces():
    root = Path("/opt/Meshchat neXt/resources/backend")
    library = root / "lib/libvox_av1.so"
    maps = f"7f00-7f10 r-xp 00000000 08:01 12345 {library}\n"
    paths = _mapped_library_paths(maps, "libvox_av1")
    assert paths == [str(library)]
    assert all(Path(path).is_relative_to(root) for path in paths)


def test_bundle_check_still_identifies_external_library_with_spaces():
    root = Path("/opt/Meshchat neXt/resources/backend")
    external = "/home/user/other install/libcodec2.so"
    maps = f"7f00-7f10 r-xp 00000000 08:01 42 {external}\n"
    paths = _mapped_library_paths(maps, "libcodec2")
    assert paths == [external]
    assert not Path(paths[0]).is_relative_to(root)


def test_anonymous_and_unrelated_mappings_are_not_library_paths():
    maps = (
        "7f00-7f10 rw-p 00000000 00:00 0\n"
        "7f00-7f10 r-xp 00000000 08:01 42 /usr/lib/libother.so\n"
    )
    assert _mapped_library_paths(maps, "libcodec2") == []
