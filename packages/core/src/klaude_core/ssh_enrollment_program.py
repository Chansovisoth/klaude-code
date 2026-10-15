"""Self-contained reviewed append of one public key to this SSH account."""

from __future__ import annotations

import base64
import errno
import fcntl
import hashlib
import json
import os
import signal
import stat
import sys
import time
from pathlib import Path

LIMIT = 262_144


def public_key(value: str) -> str:
    fields = value.split()
    if len(fields) != 2 or fields[0] != "ssh-ed25519":
        raise ValueError("Choose an Ed25519 public key")
    blob = base64.b64decode(fields[1], validate=True)
    if len(blob) != 51 or blob[:15] != b"\0\0\0\x0bssh-ed25519" or blob[15:19] != b"\0\0\0\x20":
        raise ValueError("Invalid Ed25519 public key")
    return "ssh-ed25519 " + base64.b64encode(blob).decode()


def present(data: bytes, key: str) -> bool:
    import shlex

    kind, blob = key.split()
    for raw in data.decode("utf8", "strict").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            tokens = shlex.split(raw)
        except ValueError:
            if blob in raw:
                raise ValueError(
                    "Existing key policy is ambiguous; inspect authorized_keys"
                ) from None
            continue
        for index in (0, 1):
            if tokens[index : index + 2] == [kind, blob]:
                return True
        if blob in tokens:
            raise ValueError("Existing key policy is ambiguous; inspect authorized_keys")
    return False


def safe(info: os.stat_result, directory: bool = False) -> None:
    if (
        info.st_uid != os.getuid()
        or info.st_mode & 0o022
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or not directory
        and (info.st_size > LIMIT or info.st_nlink != 1)
    ):
        raise ValueError("Use account-owned regular SSH files without unsafe write permissions")


def read(directory: int | None) -> tuple[bytes, tuple | None]:
    if directory is None:
        return b"", None
    try:
        fd = os.open(
            "authorized_keys", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
    except FileNotFoundError:
        return b"", None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        safe(info)
        data = stream.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("authorized_keys exceeded its limit")
    return data, (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_mode,
        info.st_uid,
    )


def snapshot(home: Path, home_info: os.stat_result, data: bytes, identity: tuple | None) -> str:
    metadata = (str(home), home_info.st_dev, home_info.st_ino, home_info.st_uid, identity)
    return hashlib.sha256(repr(metadata).encode() + b"\0" + data).hexdigest()


def execute(request: dict) -> dict:
    key = public_key(request["public_key"])
    home = Path.home().resolve(strict=True)
    if len(str(home)) > 4000 or not str(home).isprintable():
        raise ValueError("Unsupported remote account home")
    home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    folder = None
    lock = None
    try:
        home_info = os.fstat(home_fd)
        safe(home_info, True)
        try:
            folder = os.open(".ssh", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
            safe(os.fstat(folder), True)
        except FileNotFoundError:
            pass
        data, identity = read(folder)
        revision = snapshot(home, home_info, data, identity)
        found = present(data, key)
        result = {
            "version": 1,
            "connected": True,
            "target": str(home / ".ssh/authorized_keys"),
            "revision": revision,
            "present": found,
            "bytes": len(data),
        }
        if request["operation"] == "review":
            return result
        if request["operation"] != "enroll" or request["revision"] != revision:
            raise ValueError("Remote SSH files changed; review enrollment again")
        if found:
            return {**result, "effect": "already_present"}
        if folder is None:
            os.mkdir(".ssh", mode=0o700, dir_fd=home_fd)
            folder = os.open(".ssh", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
        safe(os.fstat(folder), True)
        lock = os.open(
            ".klaude-authorized-keys.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=folder,
        )
        safe(os.fstat(lock))
        deadline = time.monotonic() + 0.2
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError("Remote enrollment busy; review again") from None
                time.sleep(0.005)
        current, current_identity = read(folder)
        if snapshot(home, home_info, current, current_identity) != revision:
            raise ValueError("Remote SSH files changed; review enrollment again")
        addition = b"\n" if data and not data.endswith(b"\n") else b""
        addition += (key + " klaude-enrolled\n").encode()
        if len(data) + len(addition) > LIMIT:
            raise ValueError("authorized_keys size limit reached")
        flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK
        if identity is None:
            flags |= os.O_CREAT | os.O_EXCL
        fd = os.open("authorized_keys", flags, 0o600, dir_fd=folder)
        try:
            info = os.fstat(fd)
            safe(info)
            current_stat = (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_mode,
                info.st_uid,
            )
            if identity and current_stat != identity:
                raise ValueError("Remote SSH files changed; review again")
            # One O_APPEND write preserves existing bytes and concurrent appenders.
            try:
                if os.write(fd, addition) != len(addition):
                    raise OSError("Short enrollment write")
                os.fsync(fd)
                os.fsync(folder)
                updated, updated_identity = read(folder)
                folder_info = os.fstat(folder)
                visible_folder = os.stat(".ssh", dir_fd=home_fd, follow_symlinks=False)
                if (
                    not updated.startswith(data)
                    or not present(updated, key)
                    or not updated_identity
                    or updated_identity[:2] != (info.st_dev, info.st_ino)
                    or (visible_folder.st_dev, visible_folder.st_ino)
                    != (folder_info.st_dev, folder_info.st_ino)
                ):
                    raise OSError("Enrollment receipt unavailable")
            except (OSError, ValueError):
                return {**result, "effect": "unconfirmed"}
        finally:
            os.close(fd)
        return {**result, "effect": "appended", "present": True}
    finally:
        if lock is not None:
            os.close(lock)
        if folder is not None:
            os.close(folder)
        os.close(home_fd)


def main() -> None:
    def timeout(*_) -> None:
        raise TimeoutError("Enrollment deadline reached")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(10)
    try:
        request = json.loads(sys.stdin.buffer.read(8193))
        result = execute(request)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        code = "changed" if isinstance(exc, ValueError) else "files"
        if isinstance(exc, OSError) and exc.errno == errno.ELOOP:
            code = "unsafe"
        result = {"version": 1, "connected": True, "error": code}
    finally:
        signal.alarm(0)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
