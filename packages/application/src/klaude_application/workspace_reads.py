"""Bounded, read-only workspace operations for untrusted presentation clients.

The workspace binding is supplied by a trusted application composition path.
These methods do not authorize a browser principal or expose mutation tools.
"""

from __future__ import annotations

import os
import select
import signal
import stat
import subprocess
import time
from itertools import islice
from pathlib import Path

from klaude_tools import Workspace
from klaude_tools.toolkit import SENSITIVE_ENV_NAME_RE, SENSITIVE_VALUE_RE

_GIT_EXCLUSIONS = (
    ":(exclude,glob)**/.env", ":(exclude,glob)**/.env.*",
    ":(exclude,glob)**/searxng.env", ":(exclude,glob)**/credentials.json",
    ":(exclude,glob)**/id_rsa", ":(exclude,glob)**/id_ed25519",
    ":(exclude,glob)**/webui-accounts.json", ":(exclude,glob)**/webui-admin-password.txt",
    ":(exclude,glob)**/*.pem", ":(exclude,glob)**/*.key",
    ":(exclude,glob)**/*.p12", ":(exclude,glob)**/*.pfx",
)


class WorkspaceReadService:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def read_file(self, path: str, offset: int | None = None,
                  limit: int | None = None) -> str:
        """Read an approved regular file through an owned, bounded descriptor."""
        return bounded_read(self.workspace, path, offset, limit)

    def grep(self, pattern: str, path: str = ".") -> str:
        return bounded_grep(self.workspace, pattern, path)

    def list_dir(self, path: str = ".") -> str:
        return bounded_list_dir(self.workspace, path)

    def git_status(self) -> str:
        return bounded_git(self.workspace, "status")

    def git_diff(self) -> str:
        return bounded_git(self.workspace, "diff")


def bounded_read(workspace: Workspace, path: str, offset: int | None = None,
                 limit: int | None = None) -> str:
    """Read a regular workspace file through an owned descriptor, capped before decoding."""
    if offset is not None and not 1 <= offset <= 1_000_000:
        raise ValueError("invalid offset")
    if limit is not None and not 1 <= limit <= 500:
        raise ValueError("invalid limit")
    target = workspace._jail(path)
    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        actual = Path(f"/proc/self/fd/{descriptor}").resolve()
        if not actual.is_relative_to(workspace.root) or workspace._is_sensitive_path(actual):
            raise PermissionError("file is outside the approved workspace or protected")
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
            raise ValueError("only regular files up to 1 MiB can be read in the WebUI")
        data = os.read(descriptor, 1_048_577)
        if len(data) > 1_048_576:
            raise ValueError("file grew beyond the WebUI read limit")
    finally:
        os.close(descriptor)
    text = data.decode("utf-8", errors="replace")
    if offset is None and limit is None:
        return text[:20_000] + ("\n...[truncated]" if len(text) > 20_000 else "")
    start, count = offset or 1, limit or 200
    lines = text.splitlines()
    if start > len(lines):
        return f"{path}: offset {start} exceeds {len(lines)} lines"
    end = min(start + count - 1, len(lines))
    page = "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
    result = f"{path}: lines {start}-{end} of {len(lines)}\n{page}"
    return result[:20_000] + ("\n...[truncated]" if len(result) > 20_000 else "")


def bounded_list_dir(workspace: Workspace, path: str = ".") -> str:
    target = workspace._jail(path)
    descriptor = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        actual = Path(f"/proc/self/fd/{descriptor}").resolve()
        if not actual.is_relative_to(workspace.root):
            raise PermissionError("directory is outside the approved workspace")
        with os.scandir(descriptor) as scan:
            entries = list(islice(scan, 2_001))
            if len(entries) > 2_000:
                raise ValueError("directory exceeds bounded listing limit")
            rows = [
                (entry.is_dir(follow_symlinks=False), entry.name)
                for entry in entries
                if entry.name not in {".git", "node_modules", "__pycache__", ".venv"}
                and not workspace._is_sensitive_path(Path(entry.name))
            ]
    finally:
        os.close(descriptor)
    rows.sort(key=lambda row: (not row[0], row[1]))
    prefix = target.relative_to(workspace.root)
    return "\n".join(
        f"{'d' if directory else 'f'} {prefix / name}"
        for directory, name in rows[:300]
    ) or "(empty)"


def bounded_grep(workspace: Workspace, pattern: str, path: str = ".") -> str:
    if not isinstance(pattern, str) or not pattern or len(pattern) > 256:
        raise ValueError("pattern must contain 1-256 characters")
    target = workspace._jail(path)
    if workspace._is_sensitive_path(target):
        raise PermissionError("protected search path")
    descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        actual = Path(f"/proc/self/fd/{descriptor}").resolve()
        info = os.fstat(descriptor)
        if (
            not actual.is_relative_to(workspace.root)
            or workspace._is_sensitive_path(actual)
            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
        ):
            raise PermissionError("search path is outside the approved workspace or protected")
        return _grep_descriptor(pattern, target, descriptor)
    finally:
        os.close(descriptor)


def _grep_descriptor(pattern: str, target: Path, descriptor: int) -> str:
    fd_path = f"/proc/self/fd/{descriptor}"
    command = [
        "rg", "--line-number", "--no-heading", "--max-count", "3",
        "--max-columns", "512", "--max-filesize", "1M",
        "--glob", "!**/.env", "--glob", "!**/credentials.json",
        "--glob", "!**/searxng.env", "--glob", "!**/id_rsa",
        "--glob", "!**/id_ed25519",
        "--glob", "!**/webui-accounts.json", "--glob", "!**/webui-admin-password.txt",
        "--glob", "!**/*.{pem,key,p12,pfx}",
        "--glob", "!**/node_modules/**", "--glob", "!**/.git/**",
        "--", pattern, fd_path,
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True, pass_fds=(descriptor,),
    )
    assert process.stdout is not None
    deadline = time.monotonic() + 10
    output = bytearray()
    truncated = False
    completed = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("workspace search timed out")
            if not select.select([process.stdout], [], [], remaining)[0]:
                raise RuntimeError("workspace search timed out")
            chunk = os.read(process.stdout.fileno(), min(4096, 10_001 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) >= 10_001:
                truncated = True
                break
        if not truncated and process.wait(
            timeout=max(0.01, deadline - time.monotonic())
        ) not in (0, 1):
            raise RuntimeError("workspace search failed")
        completed = not truncated
        text = output[:10_000].decode("utf-8", errors="replace")
        text = "".join(
            str(target) + line[len(fd_path):] if line.startswith(fd_path) else line
            for line in text.splitlines(keepends=True)
        )
        truncated = truncated or len(text) > 10_000
        text = text[:10_000]
        return (text + "\n...[truncated]" if truncated else text) or "(no matches)"
    finally:
        if not completed:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        process.stdout.close()


def bounded_git(workspace: Workspace, operation: str) -> str:
    """Return capped git output without invoking configured external diff helpers."""
    if operation not in {"status", "diff"}:
        raise ValueError("unsupported workspace git read")
    args = (["status", "--short", "--branch"] if operation == "status"
            else ["diff", "--no-ext-diff", "--no-textconv"])
    args.extend(["--", ".", *_GIT_EXCLUSIONS])
    descriptor = os.open(workspace.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if Path(f"/proc/self/fd/{descriptor}").resolve() != workspace.root:
            raise PermissionError("workspace changed during git read")
        process = subprocess.Popen(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
            cwd=f"/proc/self/fd/{descriptor}",
            pass_fds=(descriptor,),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    finally:
        os.close(descriptor)
    assert process.stdout is not None
    deadline = time.monotonic() + 10
    output = bytearray()
    truncated = False
    completed = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise RuntimeError("workspace git read timed out")
            chunk = os.read(process.stdout.fileno(), min(4096, 12_001 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) >= 12_001:
                truncated = True
                break
        if not truncated and process.wait(
            timeout=max(0.01, deadline - time.monotonic())
        ) != 0:
            raise RuntimeError("workspace git read failed")
        completed = not truncated
        result = _redact_git_output(workspace, output[:12_000].decode("utf-8", errors="replace"))
        return (result + "\n...[truncated]" if truncated else result) or "(clean)"
    finally:
        if not completed:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        process.stdout.close()


def _redact_git_output(workspace: Workspace, value: str) -> str:
    secrets = {
        item for name, item in os.environ.items()
        if SENSITIVE_ENV_NAME_RE.search(name) and len(item) >= 8
    }
    for relative in (".env", "config/.env", "config/searxng.env"):
        path = workspace.root / relative
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            continue
        try:
            info = os.fstat(descriptor)
            actual = Path(f"/proc/self/fd/{descriptor}").resolve()
            if (
                not actual.is_relative_to(workspace.root)
                or not stat.S_ISREG(info.st_mode)
                or info.st_size > 65_536
            ):
                raise ValueError(
                    "workspace secret source is unsafe or exceeds browser redaction limit"
                )
            raw = os.read(descriptor, 65_537)
            if len(raw) > 65_536:
                raise ValueError("workspace secret source exceeds browser redaction limit")
        finally:
            os.close(descriptor)
        for line in raw.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                item = stripped.split("=", 1)[1].strip().strip("\"'")
                if len(item) >= 8:
                    secrets.add(item)
    for item in sorted(secrets, key=len, reverse=True):
        value = value.replace(item, "[REDACTED]")
    return SENSITIVE_VALUE_RE.sub("[REDACTED]", value)
