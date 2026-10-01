"""Bounded cross-process settings transactions for the canonical Linux host.

Locks have a stable inode separate from the atomically replaced data file.
All cooperating writers lock before reading, modify only their intended fields,
and publish a private, durable replacement. Never unlink the lock file.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import stat
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DELETE = object()


class SettingsConflictError(OSError):
    """A stale update would overwrite a newer value; reload and retry."""


@contextmanager
def settings_lock(path: Path, *, timeout: float = 0.2) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        path.with_name(f".{path.name}.lock"),
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise PermissionError("Unsafe settings lock file")
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise OSError(
                        errno.EBUSY, "Settings are busy in another client; retry"
                    ) from None
                time.sleep(0.005)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def atomic_write_private(path: Path, payload: str) -> None:
    """Publish inside an already-held transaction; never use a shared temp name."""
    if path.is_symlink():
        raise PermissionError("Refusing to replace symlinked settings")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def read_settings(path: Path) -> dict[str, Any]:
    """Writes fail closed on corrupt settings, rather than replacing them with defaults."""
    if path.is_symlink():
        raise PermissionError("Refusing symlinked settings")
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except UnicodeError:
        raise OSError("Settings are invalid; repair the file before saving") from None
    try:
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError
    except (ValueError, UnicodeError):
        raise OSError("Settings are invalid; repair the file before saving") from None
    return value


def update_settings(
    path: Path,
    changes: Mapping[tuple[str, ...], object],
    *,
    prepare: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Apply explicit field assignments/deletions to the latest locked document.

    Independent fields merge; the last serialized assignment wins for a shared
    field. Callers must not pass unrelated fields from stale in-memory snapshots.
    """
    with settings_lock(path):
        value = read_settings(path)
        if prepare is not None:
            prepare(value)
        for keys, replacement in changes.items():
            if not keys:
                raise ValueError("A settings update requires a field path")
            current = value
            for key in keys[:-1]:
                child = current.get(key)
                if not isinstance(child, dict):
                    child = {}
                    current[key] = child
                current = child
            if replacement is DELETE:
                current.pop(keys[-1], None)
            else:
                current[keys[-1]] = replacement
        atomic_write_private(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")
        return value
