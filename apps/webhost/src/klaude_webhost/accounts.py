"""Private local-owner credentials, independent of HTTP and terminal presentation.

The versioned credential record and revision are the authentication boundary for
future factors. This initial implementation has one administrator, not multi-user
workspace ACLs. Scrypt parameters follow OWASP's 32 MiB / r=8 / p=3 profile.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from klaude_core.settings_store import atomic_write_private, settings_lock


@dataclass(frozen=True)
class AccountIdentity:
    username: str
    revision: int
    role: str = "user"


def _private_read(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'r', encoding='utf-8') as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 8192):
            raise PermissionError('Unsafe Web UI account file')
        value = source.read(8193)
        if len(value) > 8192:
            raise ValueError('Web UI account file is too large')
        return value


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode('utf-8'), salt=salt,
                          n=32768, r=8, p=3, dklen=32, maxmem=64 * 1024 * 1024)


class AccountStore:
    """One private owner account. Credentials never enter public agent data."""

    def __init__(self, config_dir: Path) -> None:
        self.path = config_dir / 'webui-accounts.json'
        self.initial_password_path = config_dir / 'webui-admin-password.txt'

    def _record(self) -> dict[str, Any]:
        try:
            record = json.loads(_private_read(self.path))
            if (not isinstance(record, dict) or record.get('version') != 1
                    or record.get('username') != 'admin' or record.get('algorithm') != 'scrypt'
                    or record.get('role', 'admin') not in {'admin', 'user'}
                    or record.get('parameters') != {'n': 32768, 'r': 8, 'p': 3}
                    or type(record.get('revision')) is not int or record['revision'] < 1
                    or len(bytes.fromhex(record['salt'])) != 16
                    or len(bytes.fromhex(record['hash'])) != 32):
                raise ValueError
            # Only the original v1 singleton record can omit its role. Its
            # generated administrator remains compatible without a credential reset.
            record.setdefault('role', 'admin')
            return record
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ValueError('Web UI account file is invalid; use local account recovery') from None

    def initialize(self) -> None:
        """First-run creation is locked; a crash cannot silently replace an account."""
        with settings_lock(self.path, timeout=5):
            try:
                self._record()
                return
            except FileNotFoundError:
                pass
            try:
                password = _private_read(self.initial_password_path).rstrip('\n')
                self.validate_password(password)
            except FileNotFoundError:
                password = secrets.token_urlsafe(24)
                atomic_write_private(self.initial_password_path, password + '\n')
            self._save(password, 1, role="admin")

    def _save(self, password: str, revision: int, *, role: str) -> None:
        salt = secrets.token_bytes(16)
        record = {'version': 1, 'username': 'admin', 'role': role, 'revision': revision,
                  'algorithm': 'scrypt', 'parameters': {'n': 32768, 'r': 8, 'p': 3},
                  'salt': salt.hex(), 'hash': _derive(password, salt).hex()}
        atomic_write_private(self.path, json.dumps(record, indent=2) + '\n')

    @staticmethod
    def validate_password(password: str) -> None:
        if not 12 <= len(password) <= 256 or len(password.encode('utf-8')) > 1024:
            raise ValueError('Use a password between 12 and 256 characters')

    @staticmethod
    def _matches(record: dict[str, Any], password: str) -> bool:
        if not password or len(password) > 256 or len(password.encode('utf-8')) > 1024:
            return False
        return hmac.compare_digest(_derive(password, bytes.fromhex(record['salt'])),
                                   bytes.fromhex(record['hash']))

    def verify(self, username: str, password: str) -> AccountIdentity | None:
        record = self._record()
        # Unknown usernames still run the same password verifier.
        valid = self._matches(record, password)
        if not valid or username != record['username']:
            return None
        return AccountIdentity(record['username'], record['revision'], record['role'])

    def identity(self, username: str) -> AccountIdentity | None:
        """Revalidate the server-owned principal, including role changes."""
        record = self._record()
        if username != record['username']:
            return None
        return AccountIdentity(record['username'], record['revision'], record['role'])

    def revision(self) -> int:
        return int(self._record()['revision'])

    def initial_password(self) -> str | None:
        try:
            password = _private_read(self.initial_password_path).rstrip('\n')
        except FileNotFoundError:
            return None
        return password if self._matches(self._record(), password) else None

    def change_password(self, current: str, replacement: str, *, revision: int) -> bool:
        self.validate_password(replacement)
        with settings_lock(self.path, timeout=5):
            record = self._record()
            if record['revision'] != revision or not self._matches(record, current):
                return False
            self._save(replacement, revision + 1, role=record['role'])
            self.initial_password_path.unlink(missing_ok=True)
            return True

    def reset_password(self) -> str:
        """Explicit local recovery rotates credentials and invalidates all sessions."""
        with settings_lock(self.path, timeout=5):
            record = self._record()
            password = secrets.token_urlsafe(24)
            atomic_write_private(self.initial_password_path, password + '\n')
            self._save(password, record['revision'] + 1, role=record['role'])
            return password


class LoginLimited(Exception):
    """The caller should retry after the bounded login window."""


class LoginLimiter:
    """Bound failed/successful authentication work and memory per host process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: dict[str, deque[float]] = {}
        self._global: deque[float] = deque()
        self.workers = threading.BoundedSemaphore(2)

    def admit(self, peer: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._attempts = {key: values for key, values in self._attempts.items()
                              if values and now - values[-1] < 60}
            for values in [self._global, *self._attempts.values()]:
                while values and now - values[0] >= 60:
                    values.popleft()
            if len(self._global) >= 30:
                raise LoginLimited
            attempts = self._attempts.setdefault(peer, deque())
            if len(attempts) >= 5:
                raise LoginLimited
            attempts.append(now)
            self._global.append(now)
