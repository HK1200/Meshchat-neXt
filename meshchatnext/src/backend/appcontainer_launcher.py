# SPDX-License-Identifier: 0BSD

"""Supervisor that launches the Meshchat neXt backend inside an AppContainer.

Invoked as:

  MeshchatNext.exe --meshchatnext-run-module meshchatnext.src.backend.appcontainer_launcher --headless ...

After --meshchatnext-run-module stripping, argv is the real backend argv.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

from meshchatnext.src.backend.appcontainer_sandbox import (
    _run_unsandboxed_child,
    appcontainer_forced,
    appcontainer_requested,
    appcontainer_supported,
    is_appcontainer_child,
    launch_backend_sandboxed,
)
from meshchatnext.src.env_utils import env_str

logger = logging.getLogger("meshchatnext.appcontainer.launcher")


def _parse_dir_flag(argv: list[str], flag: str) -> str | None:
    value = None
    for i, arg in enumerate(argv):
        if arg == flag and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith(flag + "="):
            value = arg.split("=", 1)[1]
    return value


def _resolve_paths(argv: list[str]) -> tuple[str | None, str | None, str | None]:
    storage = _parse_dir_flag(argv, "--storage-dir") or env_str(
        "MESHCHAT_STORAGE_DIR",
    )
    reticulum = _parse_dir_flag(argv, "--reticulum-config-dir") or env_str(
        "MESHCHAT_RETICULUM_CONFIG_DIR",
    )
    from meshchatnext.src.path_utils import resolve_meshchat_data_roots

    storage, reticulum = resolve_meshchat_data_roots(
        data_dir=_parse_dir_flag(argv, "--data-dir"),
        storage_dir=storage,
        reticulum_config_dir=reticulum,
    )
    storage = os.path.abspath(storage or "storage")
    reticulum = os.path.abspath(reticulum or os.path.expanduser("~/.reticulum"))
    log_dir = env_str("MESHCHAT_LOG_DIR")
    if not log_dir and storage:
        log_dir = os.path.join(storage, "logs")
    return storage, reticulum, log_dir


def run_launcher(argv: list[str] | None = None) -> int:
    """Launch the backend under AppContainer and return its exit code."""
    if argv is None:
        argv = sys.argv[1:]

    if is_appcontainer_child():
        print(
            "error: appcontainer_launcher must not run inside an AppContainer child",
            file=sys.stderr,
        )
        return 2

    if sys.platform != "win32":
        print(
            "error: AppContainer launcher is only supported on Windows",
            file=sys.stderr,
        )
        return 2

    if not appcontainer_supported() and appcontainer_forced():
        print(
            "error: MESHCHAT_APPCONTAINER=1 but AppContainer APIs are unavailable",
            file=sys.stderr,
        )
        return 2

    exe = sys.executable
    if not exe:
        print("error: sys.executable is unset", file=sys.stderr)
        return 2

    storage_dir, reticulum_config_dir, log_dir = _resolve_paths(argv)
    # Ensure temp exists before ACL grant.
    try:
        tempfile.gettempdir()
    except Exception:
        pass

    if appcontainer_requested() and appcontainer_supported():
        from meshchatnext.src.backend.appcontainer_broker import launch_brokered_backend

        result = launch_brokered_backend(
            exe,
            list(argv),
            storage_dir=storage_dir,
            reticulum_config_dir=reticulum_config_dir,
            log_dir=log_dir,
        )
        if not result.ok and not appcontainer_forced():
            result = _run_unsandboxed_child(exe, list(argv))
    else:
        result = launch_backend_sandboxed(
            exe,
            list(argv),
            storage_dir=storage_dir,
            reticulum_config_dir=reticulum_config_dir,
            log_dir=log_dir,
            forced=appcontainer_forced(),
        )

    if result.fell_back:
        logger.warning(
            "AppContainer unavailable, ran unsandboxed backend (exit=%s)",
            result.exit_code,
        )
    elif result.used_appcontainer:
        logger.info("Backend exited from AppContainer (exit=%s)", result.exit_code)

    if not result.ok:
        print(
            f"error: AppContainer launch failed: {result.error}",
            file=sys.stderr,
        )
        return 1

    return int(result.exit_code if result.exit_code is not None else 0)


def main() -> None:
    raise SystemExit(run_launcher())


if __name__ == "__main__":
    main()
