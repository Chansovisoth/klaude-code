"""Fail-closed Linux Landlock runner for model-initiated shell commands.

This module is launched in a fresh process so applying an irreversible Landlock
policy cannot affect Klaude itself.  Keep it dependency-free: it is part of the
security boundary and must work before project dependencies are imported.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import platform
import sys
from pathlib import Path

_CREATE_RULESET = 444
_ADD_RULE = 445
_RESTRICT_SELF = 446
_CREATE_RULESET_VERSION = 1
_RULE_PATH_BENEATH = 1
_PR_SET_NO_NEW_PRIVS = 38

_EXECUTE = 1 << 0
_WRITE_FILE = 1 << 1
_READ_FILE = 1 << 2
_READ_DIR = 1 << 3
_REMOVE_DIR = 1 << 4
_REMOVE_FILE = 1 << 5
_MAKE_CHAR = 1 << 6
_MAKE_DIR = 1 << 7
_MAKE_REG = 1 << 8
_MAKE_SOCK = 1 << 9
_MAKE_FIFO = 1 << 10
_MAKE_BLOCK = 1 << 11
_MAKE_SYM = 1 << 12
_REFER = 1 << 13
_TRUNCATE = 1 << 14
_IOCTL_DEV = 1 << 15

_READ_ACCESS = _EXECUTE | _READ_FILE | _READ_DIR
_WRITE_ACCESS = (
    _WRITE_FILE
    | _REMOVE_DIR
    | _REMOVE_FILE
    | _MAKE_CHAR
    | _MAKE_DIR
    | _MAKE_REG
    | _MAKE_SOCK
    | _MAKE_FIFO
    | _MAKE_BLOCK
    | _MAKE_SYM
    | _REFER
    | _TRUNCATE
)


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


def _supported_access(abi: int) -> int:
    access = _READ_ACCESS | _WRITE_ACCESS
    if abi < 2:
        access &= ~_REFER
    if abi < 3:
        access &= ~_TRUNCATE
    if abi >= 5:
        access |= _IOCTL_DEV
    return access


def _syscall_number(value: int) -> int:
    machine = platform.machine().casefold()
    if machine not in {"x86_64", "amd64", "aarch64", "arm64", "riscv64"}:
        raise RuntimeError(f"unsupported Linux architecture for Landlock: {machine}")
    return value


def _call(libc, number: int, *args) -> int:
    result = int(libc.syscall(_syscall_number(number), *args))
    if result < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return result


def _landlock_abi(libc) -> int:
    try:
        return _call(
            libc,
            _CREATE_RULESET,
            ctypes.c_void_p(),
            ctypes.c_size_t(0),
            ctypes.c_uint32(_CREATE_RULESET_VERSION),
        )
    except OSError as exc:
        if exc.errno in {errno.ENOSYS, errno.EOPNOTSUPP, errno.EINVAL}:
            raise RuntimeError("Landlock is unavailable or disabled") from exc
        raise


def _add_path_rule(libc, ruleset_fd: int, path: Path, access: int) -> None:
    if not path.exists():
        return
    if not path.is_dir():
        access &= _EXECUTE | _READ_FILE | _WRITE_FILE | _TRUNCATE | _IOCTL_DEV
    if not access:
        return
    flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_CLOEXEC
    parent_fd = os.open(path, flags)
    try:
        attr = _PathBeneathAttr(access, parent_fd)
        _call(
            libc,
            _ADD_RULE,
            ctypes.c_int(ruleset_fd),
            ctypes.c_int(_RULE_PATH_BENEATH),
            ctypes.byref(attr),
            ctypes.c_uint32(0),
        )
    finally:
        os.close(parent_fd)


def restrict_filesystem(workspace: Path, temporary: Path, *, writable: bool) -> None:
    if sys.platform != "linux":
        raise RuntimeError("secure shell execution currently requires Linux Landlock")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = _landlock_abi(libc)
    handled = _supported_access(abi)
    attr = _RulesetAttr(handled)
    ruleset_fd = _call(
        libc,
        _CREATE_RULESET,
        ctypes.byref(attr),
        ctypes.c_size_t(ctypes.sizeof(attr)),
        ctypes.c_uint32(0),
    )
    try:
        runtime_paths = (
            "/usr",
            "/bin",
            "/lib",
            "/lib64",
            "/proc",
            "/sys",
            "/etc/ld.so.cache",
            "/etc/ssl",
            "/etc/ca-certificates",
            "/etc/resolv.conf",
            "/etc/hosts",
            "/etc/nsswitch.conf",
            "/dev/null",
            "/dev/urandom",
            "/dev/random",
        )
        for raw in runtime_paths:
            runtime_access = _READ_ACCESS
            if raw == "/dev/null":
                runtime_access |= _WRITE_FILE | _IOCTL_DEV
            _add_path_rule(libc, ruleset_fd, Path(raw), runtime_access & handled)
        workspace_access = _READ_ACCESS | (_WRITE_ACCESS if writable else 0)
        _add_path_rule(libc, ruleset_fd, workspace, workspace_access & handled)
        _add_path_rule(
            libc,
            ruleset_fd,
            temporary,
            (_READ_ACCESS | _WRITE_ACCESS) & handled,
        )
        if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
        _call(
            libc,
            _RESTRICT_SELF,
            ctypes.c_int(ruleset_fd),
            ctypes.c_uint32(0),
        )
    finally:
        os.close(ruleset_fd)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--temporary", required=True)
    parser.add_argument("--writable", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print("klaude sandbox: missing command", file=sys.stderr)
        return 126
    workspace = Path(args.workspace).resolve(strict=True)
    temporary = Path(args.temporary).resolve(strict=True)
    try:
        restrict_filesystem(workspace, temporary, writable=args.writable)
        os.chdir(workspace)
        os.execvpe(command[0], command, os.environ)
    except (OSError, RuntimeError) as exc:
        print(f"klaude sandbox: {exc}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
