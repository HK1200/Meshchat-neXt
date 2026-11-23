# SPDX-License-Identifier: 0BSD
"""Private streamed RNCP imports, separate from remotely fetchable shared files."""

from __future__ import annotations

import asyncio
import errno
import os
import re
import shutil
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from meshchatnext.src.backend.http.uploads import write_field_to_path

MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_FILES = 16
FREE_RESERVE_BYTES = 32 * 1024 * 1024
_ID = re.compile(r"[a-f0-9]{32}")


class ImportBusyError(ValueError):
    """An import or transfer currently owns this imported copy."""


class RNCPUploads:
    def __init__(self, storage_dir):
        self.root = Path(storage_dir).resolve() / "rncp_uploads"
        self._upload = asyncio.Lock()
        self._lock = RLock()
        self._leases = Counter()

    def _root(self, *, create=False):
        if create:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise PermissionError("Invalid RNCP import directory")
        if self.root.exists() and not self.root.is_dir():
            raise PermissionError("Invalid RNCP import directory")
        return self.root

    def _record(self, identifier):
        if not isinstance(identifier, str) or _ID.fullmatch(identifier) is None:
            raise ValueError("Invalid imported file")
        folder = self._root() / identifier
        if folder.is_symlink() or not folder.is_dir():
            raise FileNotFoundError("Imported file not found")
        entries = list(folder.iterdir())
        if len(entries) != 1 or entries[0].is_symlink() or not entries[0].is_file():
            raise ValueError("Imported file is incomplete or invalid")
        file = entries[0]
        incomplete = file.name == ".part"
        return {
            "id": identifier,
            "name": "Interrupted import" if incomplete else file.name,
            "size": file.stat().st_size,
            "incomplete": incomplete,
            "file_path": None if incomplete else str(file),
        }

    def list(self):
        root = self._root()
        if not root.exists():
            return []
        result = []
        for folder in sorted(root.iterdir()):
            if _ID.fullmatch(folder.name) is None or folder.is_symlink():
                continue
            try:
                result.append(self._record(folder.name))
            except (FileNotFoundError, ValueError):
                # Never remove or follow content whose provenance is uncertain.
                continue
        return result

    @staticmethod
    def filename(value):
        if (
            not isinstance(value, str)
            or not value
            or value in {".", "..", ".part"}
            or len(value.encode("utf-8")) > 240
            or "/" in value
            or "\\" in value
            or any(ord(c) < 32 or c in '<>:"|?*' for c in value)
            or value.endswith((" ", "."))
        ):
            raise ValueError("Choose a file with a valid name")
        return value

    async def import_field(self, field):
        name = self.filename(field.filename)
        if self._upload.locked():
            raise ImportBusyError("Wait for the current file import to finish")
        async with self._upload:
            with self._lock:
                root = self._root(create=True)
                records = self.list()
                if len(records) >= MAX_FILES:
                    raise ValueError(
                        "Remove an imported copy before adding another file"
                    )
                remaining = MAX_TOTAL_BYTES - sum(row["size"] for row in records)
                available = shutil.disk_usage(root).free - FREE_RESERVE_BYTES
                if remaining <= 0 or available <= 0:
                    raise OSError(
                        errno.ENOSPC, "Not enough free space for an imported file"
                    )
                limit = min(MAX_FILE_BYTES, remaining, available)
                identifier = uuid.uuid4().hex
                folder = root / identifier
                folder.mkdir(mode=0o700)
                self._leases[identifier] += 1
            staged = folder / ".part"
            finished = False
            try:
                # The chunked helper writes off the event loop and removes partial
                # files on oversize, cancellation and ordinary disk errors.
                size = await write_field_to_path(field, staged, limit)
                if size == 0:
                    raise ValueError("Choose a non-empty file")
                staged.chmod(0o600)
                # Keep publication atomic with respect to task cancellation.
                os.replace(staged, folder / name)
                finished = True
                return self._record(identifier)
            finally:
                with self._lock:
                    self._leases[identifier] -= 1
                    if not self._leases[identifier]:
                        del self._leases[identifier]
                    if not finished:
                        staged.unlink(missing_ok=True)
                        folder.rmdir()

    @contextmanager
    def lease(self, file_path):
        """Fence deletion during pathfinding as well as the resource transfer."""
        if not isinstance(file_path, str) or not file_path:
            yield
            return
        lexical = Path(os.path.expanduser(file_path))
        if not lexical.is_absolute():
            lexical = self.root.parent / lexical
        real = lexical.resolve()
        try:
            relative = real.relative_to(self.root)
        except ValueError:
            # Ordinary native desktop files retain the existing RNCP jail checks.
            if lexical.is_relative_to(self.root):
                raise PermissionError("Invalid imported file path") from None
            yield
            return
        if len(relative.parts) != 2:
            raise ValueError("Invalid imported file")
        identifier = relative.parts[0]
        with self._lock:
            record = self._record(identifier)
            if record["incomplete"] or record["file_path"] != str(real):
                raise ValueError("Imported file is not ready")
            self._leases[identifier] += 1
        try:
            yield
        finally:
            with self._lock:
                self._leases[identifier] -= 1
                if not self._leases[identifier]:
                    del self._leases[identifier]

    def delete(self, identifier):
        with self._lock:
            record = self._record(identifier)
            if self._leases[identifier]:
                raise ImportBusyError(
                    "Wait for this file's current transfer to finish or cancel it"
                )
            folder = self.root / identifier
            file = folder / (".part" if record["incomplete"] else record["name"])
            file.unlink()
            folder.rmdir()
