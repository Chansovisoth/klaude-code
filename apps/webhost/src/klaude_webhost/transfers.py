"""Private, session-scoped staging for browser file transfer."""

from __future__ import annotations

import hashlib
import io
import os
import secrets
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

MAX_UPLOAD = 32 * 1024 * 1024
MAX_STAGED = 64 * 1024 * 1024
MAX_FILES = 8
UPLOAD_LIFETIME = 24 * 60 * 60


@dataclass(frozen=True)
class StagedFile:
    id: str
    owner: str
    size: int
    sha256: str
    filename: str
    expires_at: float


def display_filename(raw: str) -> str:
    """Use untrusted names for display only, never for filesystem access."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isascii() and (
        char.isalnum() or char in ".-_"
    ))[:100]
    return name if name not in {"", ".", ".."} else "upload.bin"


class BrowserTransfers:
    """Own only temporary uploaded bytes; Library import is a separate review."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise PermissionError("Unsafe browser staging directory")
        self._directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._lock = threading.RLock()
        self._records: dict[str, StagedFile] = {}
        try:
            # A restarted host has no authenticated owner for earlier staging.
            with os.scandir(self._directory) as entries:
                for count, entry in enumerate(entries):
                    if count >= 128:
                        raise PermissionError("Browser staging directory exceeds safety limit")
                    info = entry.stat(follow_symlinks=False)
                    if (len(entry.name) != 32
                            or any(char not in "0123456789abcdef" for char in entry.name)
                            or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                            or info.st_nlink != 1):
                        raise PermissionError("Unsafe browser staging entry")
                    os.unlink(entry.name, dir_fd=self._directory)
        except BaseException:
            os.close(self._directory)
            raise

    def close(self) -> None:
        with self._lock:
            if self._directory < 0:
                return
            self.revoke_all()
            os.close(self._directory)
            self._directory = -1

    def _purge(self) -> None:
        now = time.time()
        for identity, record in tuple(self._records.items()):
            if record.expires_at <= now:
                self._records.pop(identity, None)
                os.unlink(identity, dir_fd=self._directory)

    def revoke(self, owner: str) -> None:
        with self._lock:
            for identity, record in tuple(self._records.items()):
                if record.owner == owner:
                    self._records.pop(identity, None)
                    os.unlink(identity, dir_fd=self._directory)

    def revoke_all(self) -> None:
        with self._lock:
            for identity in tuple(self._records):
                self._records.pop(identity, None)
                os.unlink(identity, dir_fd=self._directory)

    def discard(self, owner: str, identity: str) -> None:
        """Release a staged file after a reviewed service captures its own copy."""
        with self._lock:
            record = self._records.get(identity)
            if record is not None and record.owner == owner:
                self._records.pop(identity)
                os.unlink(identity, dir_fd=self._directory)

    def upload(
        self, owner: str, source: io.BufferedIOBase, length: int, filename: str,
    ) -> StagedFile:
        if not 0 < length <= MAX_UPLOAD:
            raise ValueError("Invalid upload size")
        with self._lock:
            self._purge()
            if (len(self._records) >= MAX_FILES
                    or sum(item.size for item in self._records.values()) + length > MAX_STAGED):
                raise ValueError("Browser staging quota reached")
            identity = secrets.token_hex(16)
            fd = os.open(identity, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                         0o600, dir_fd=self._directory)
            digest = hashlib.sha256()
            remaining = length
            deadline = time.monotonic() + 30
            try:
                with os.fdopen(fd, "wb", closefd=True) as destination:
                    while remaining:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Upload deadline exceeded")
                        chunk = source.read(min(65536, remaining))
                        if not chunk:
                            raise ValueError("Upload ended early")
                        if len(chunk) > remaining:
                            raise ValueError("Upload exceeded declared size")
                        destination.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                record = StagedFile(
                    identity, owner, length, digest.hexdigest(),
                    display_filename(filename), time.time() + UPLOAD_LIFETIME,
                )
                self._records[identity] = record
                return record
            except BaseException:
                os.unlink(identity, dir_fd=self._directory)
                raise

    def open_download(self, owner: str, identity: str) -> tuple[StagedFile, BinaryIO]:
        if len(identity) != 32 or any(char not in "0123456789abcdef" for char in identity):
            raise FileNotFoundError("Staged file unavailable")
        with self._lock:
            self._purge()
            record = self._records.get(identity)
            if record is None or record.owner != owner:
                raise FileNotFoundError("Staged file unavailable")
            fd = os.open(identity, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._directory)
            source = os.fdopen(fd, "rb", closefd=True)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_nlink != 1 or info.st_size != record.size):
                    raise ValueError("Staged file changed")
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(65536), b""):
                    digest.update(chunk)
                if digest.hexdigest() != record.sha256:
                    raise ValueError("Staged file changed")
                source.seek(0)
                return record, source
            except BaseException:
                source.close()
                raise
