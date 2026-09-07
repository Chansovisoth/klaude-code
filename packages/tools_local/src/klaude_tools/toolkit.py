"""Built-in tools, returned as klaude_core.Tool objects.

Design rules:
- fs tools are jailed to the workspace root (no ../../ escapes).
- edit_file is exact-string replacement (predictable, diff-friendly).
- git tools implement the work-branch discipline: klaude never commits to
  your branch; write operations auto-commit on klaude/<task> so every agent
  action is one revertible commit — and VS Code's diff UI works for free.
"""

from __future__ import annotations

import fcntl
import fnmatch
import os
import re
import shlex
import subprocess
import sys
import tempfile
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from klaude_core import Tool

MAX_READ = 60_000
SHELL_TIMEOUT = 120
GIT_TIMEOUT = 60
GIT_ERROR_OUTPUT_LIMIT = 2_000

READ_ONLY_COMMANDS = {
    "cat",
    "file",
    "find",
    "grep",
    "head",
    "ls",
    "pwd",
    "rg",
    "stat",
    "tail",
}
TEST_BUILD_COMMANDS = {
    "bash",
    "cargo",
    "make",
    "mypy",
    "npm",
    "pytest",
    "python",
    "python3",
    "ruff",
    "uv",
}
WORKSPACE_WRITING_COMMANDS = {
    "chmod",
    "cp",
    "install",
    "mkdir",
    "mv",
    "sed",
    "tee",
    "touch",
}
DESTRUCTIVE_COMMANDS = {
    "rm",
    "rmdir",
    "shred",
    "truncate",
}
READ_ONLY_GIT_SUBCOMMANDS = {"status", "diff", "log", "show"}
GIT_MUTATION_SUBCOMMANDS = {
    "add",
    "am",
    "apply",
    "bisect",
    "branch",
    "cherry-pick",
    "commit",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "restore",
    "revert",
    "switch",
    "tag",
}
DESTRUCTIVE_GIT_SUBCOMMANDS = {"clean", "gc", "reset"}
SHELL_EXECUTABLES = {"bash", "dash", "fish", "ksh", "sh", "zsh"}
SAFE_EXTERNAL_PATHS = {Path("/dev/null")}
SENSITIVE_ENV_NAME_RE = re.compile(r"(?i)(?:api[_-]?key|token|secret|password|credential)")
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|"
    r"AIza[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._~+/-]{12,})"
)


@dataclass(frozen=True)
class CommandClassification:
    argv: list[str]
    risk: str
    uses_shell: bool
    reason: str


@dataclass(frozen=True)
class GitCommandError(RuntimeError):
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str

    def __str__(self) -> str:
        parts = [
            f"git command failed: argv={self.argv!r}",
            f"exit_code={self.exit_code}",
        ]
        stderr = self.stderr.strip()
        stdout = self.stdout.strip()
        if stderr:
            parts.append(f"stderr={stderr[:GIT_ERROR_OUTPUT_LIMIT]}")
        if stdout:
            parts.append(f"stdout={stdout[:GIT_ERROR_OUTPUT_LIMIT]}")
        return "; ".join(parts)


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _has_shell_syntax(command: str, argv: list[str]) -> bool:
    if re.search(r"(\|\||&&|[|;<>()]|[<>]{1,2}|`|\$\()", command):
        return True
    if argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
        return True
    return any(any(char in token for char in "*?[") for token in argv)


def _git_subcommand(argv: list[str]) -> str:
    for token in argv[1:]:
        if token == "--":
            return ""
        if token.startswith("-"):
            continue
        return token
    return ""


def _classify_git(argv: list[str]) -> tuple[str, str]:
    subcommand = _git_subcommand(argv)
    if subcommand in DESTRUCTIVE_GIT_SUBCOMMANDS:
        return "destructive", f"git {subcommand}"
    if subcommand == "checkout" and any(token in {"-f", "--force"} for token in argv):
        return "destructive", "git checkout force"
    if subcommand == "push" and any(fnmatch.fnmatch(token, "--force*") for token in argv):
        return "destructive", "git push force"
    if subcommand in READ_ONLY_GIT_SUBCOMMANDS:
        return "read-only inspection", f"git {subcommand}"
    if subcommand in GIT_MUTATION_SUBCOMMANDS or subcommand == "checkout":
        return "Git mutation", f"git {subcommand}"
    return "shell-composed or unknown", "unknown git operation"


def classify_command(command: str) -> CommandClassification:
    argv = _split_command(command)
    if not argv:
        return CommandClassification([], "shell-composed or unknown", True, "parse error")
    if _has_shell_syntax(command, argv):
        return CommandClassification(argv, "shell-composed or unknown", True, "shell syntax")
    name = Path(argv[0]).name
    if name in SHELL_EXECUTABLES and "-c" in argv:
        command_index = argv.index("-c") + 1
        if command_index < len(argv):
            nested = classify_command(argv[command_index])
            if nested.risk == "destructive":
                return CommandClassification(
                    argv, "destructive", True, "destructive nested shell command"
                )
    lowered = command.casefold()
    if re.search(
        r"(?:^|[;&|()\s])(?:sudo\s+)?(?:\S*/)?(?:rm|rmdir|shred|truncate)(?:\s|$)",
        lowered,
    ):
        return CommandClassification(argv, "destructive", True, "destructive nested command")
    if name == "git":
        risk, reason = _classify_git(argv)
        if risk == "read-only inspection" and any(
            token == "--output" or token.startswith("--output=") for token in argv
        ):
            risk, reason = "workspace-writing", "git output file"
    elif name == "find" and any(
        token in {"-delete", "-exec", "-execdir", "-ok", "-okdir"} for token in argv
    ):
        risk, reason = "destructive", "find action"
    elif name in READ_ONLY_COMMANDS:
        risk, reason = "read-only inspection", name
    elif name in DESTRUCTIVE_COMMANDS:
        risk, reason = "destructive", name
    elif name in WORKSPACE_WRITING_COMMANDS:
        risk, reason = "workspace-writing", name
    elif name in TEST_BUILD_COMMANDS:
        risk, reason = "test/build", name
    else:
        risk, reason = "shell-composed or unknown", name
    return CommandClassification(argv, risk, False, reason)


class Workspace:
    def __init__(self, root: Path, auto_commit: bool = True):
        self.root = root.resolve()
        self.repo_root = self._discover_repo_root()
        self.auto_commit = auto_commit
        self.write_enabled = True

    # --- helpers ---------------------------------------------------------
    def _discover_repo_root(self) -> Path | None:
        out = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        if out.returncode != 0:
            return None
        top = out.stdout.strip()
        return Path(top).resolve() if top else None

    def _jail(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root):
            raise PermissionError(f"path escapes workspace: {rel}")
        return p

    def _git(self, *args: str) -> str:
        argv = ["git", *args]
        cwd = self.repo_root or self.root
        out = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT)
        if out.returncode != 0:
            raise GitCommandError(argv, out.returncode, out.stdout, out.stderr)
        return (out.stdout + out.stderr).strip()

    def _status_paths(self) -> list[str]:
        """Return literal dirty paths without C-style quoting ambiguities."""
        raw = self._git("status", "--porcelain=v1", "-z")
        records = raw.split("\0") if raw else []
        paths: list[str] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4:
                raise RuntimeError("could not parse Git status safely")
            status = record[:2]
            paths.append(record[3:])
            if "R" in status or "C" in status:
                if index >= len(records) or not records[index]:
                    raise RuntimeError("could not parse Git rename safely")
                paths.append(records[index])
                index += 1
        return paths

    def _is_repo(self) -> bool:
        return self.repo_root is not None

    def ensure_work_branch(self, task_slug: str = "session") -> str:
        """Called once at session start: refuse dirty trees, branch off."""
        self.write_enabled = True
        if not self._is_repo():
            return "not a git repo — edits will not be auto-committed"
        try:
            if self._git("status", "--porcelain"):
                self.write_enabled = False
                return (
                    "WORKING TREE IS DIRTY — commit or stash your changes first; "
                    "klaude will not mix its edits with yours"
                )
            branch = f"klaude/{task_slug}"
            existing = self._git("branch", "--list", branch)
            if existing:
                self._git("switch", branch)
            else:
                self._git("switch", "-c", branch)
        except GitCommandError as exc:
            self.write_enabled = False
            return f"git setup failed: {exc}"
        return f"working on branch {branch}"

    def _require_write_enabled(self) -> None:
        if not self.write_enabled:
            raise PermissionError(
                "working tree is dirty; commit or stash your changes before AI edits"
            )

    def _require_clean_repo(self) -> None:
        self._require_write_enabled()
        if self._is_repo() and self._git("status", "--porcelain"):
            self.write_enabled = False
            raise PermissionError(
                "working tree changed after Klaude started; commit or stash those changes "
                "before AI edits"
            )

    @contextmanager
    def _mutation_lock(self):
        if not self._is_repo():
            yield
            return
        git_dir = self._git("rev-parse", "--git-dir")
        lock_path = Path(git_dir)
        if not lock_path.is_absolute():
            repo_root = self.repo_root
            if repo_root is None:
                raise RuntimeError("Git repository root disappeared during mutation")
            lock_path = (repo_root / lock_path).resolve()
        lock_path.mkdir(parents=True, exist_ok=True)
        with (lock_path / "klaude-agent.lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _require_command_allowed(self, classification: CommandClassification) -> None:
        if classification.risk == "destructive":
            raise PermissionError(
                f"destructive command denied: {' '.join(classification.argv) or '<unparsed>'}"
            )
        if classification.risk != "read-only inspection":
            self._require_write_enabled()

    def _commit(self, message: str, path: Path) -> None:
        if self.auto_commit and self._is_repo():
            repo_root = self.repo_root
            if repo_root is None:
                return
            relative = path.resolve().relative_to(repo_root).as_posix()
            unexpected = [changed for changed in self._status_paths() if changed != relative]
            if unexpected:
                self.write_enabled = False
                raise PermissionError(
                    "concurrent workspace changes detected; Klaude left its edit uncommitted "
                    "to avoid capturing user-owned work"
                )
            self._git("add", "--", relative)
            self._git("commit", "--only", "-m", f"klaude: {message}", "--", relative)

    def _commit_all(self, message: str) -> None:
        if not self.auto_commit or not self._is_repo():
            return
        paths = list(dict.fromkeys(self._status_paths()))
        if not paths:
            return
        self._git("add", "-A", "--", *paths)
        self._git("commit", "--only", "-m", f"klaude: {message}", "--", *paths)

    @staticmethod
    def _is_sensitive_path(path: Path) -> bool:
        name = path.name.casefold()
        if name.endswith(".example") or name.endswith(".sample"):
            return False
        return name in {
            ".env",
            "searxng.env",
            "credentials.json",
            "id_rsa",
            "id_ed25519",
        } or name.endswith((".pem", ".key", ".p12", ".pfx"))

    def _sensitive_values(self) -> set[str]:
        values = {
            value
            for name, value in os.environ.items()
            if SENSITIVE_ENV_NAME_RE.search(name) and len(value) >= 8
        }
        for path in (
            self.root / ".env",
            self.root / "config/.env",
            self.root / "config/searxng.env",
        ):
            if not path.is_file():
                continue
            try:
                lines = path.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                value = stripped.split("=", 1)[1].strip().strip("\"'")
                if len(value) >= 8:
                    values.add(value)
        return values

    def _redact(self, text: str) -> str:
        for value in sorted(self._sensitive_values(), key=len, reverse=True):
            text = text.replace(value, "[REDACTED]")
        return SENSITIVE_VALUE_RE.sub("[REDACTED]", text)

    def _validate_command_paths(self, argv: list[str]) -> None:
        for index, token in enumerate(argv):
            if index == 0 or "://" in token:
                continue
            candidate = token.split("=", 1)[1] if token.startswith("-") and "=" in token else token
            candidate_path = Path(candidate)
            if self._is_sensitive_path(candidate_path):
                raise PermissionError(f"shell access to secret file denied: {candidate}")
            if candidate.startswith("/"):
                path = Path(candidate).resolve()
                if path in SAFE_EXTERNAL_PATHS or path.is_relative_to(self.root):
                    continue
                raise PermissionError(f"shell path escapes workspace: {candidate}")
            if candidate == ".." or candidate.startswith("../") or "/../" in candidate:
                path = (self.root / candidate).resolve()
                if not path.is_relative_to(self.root):
                    raise PermissionError(f"shell path escapes workspace: {candidate}")

    # --- tool implementations ---------------------------------------------
    def read_file(self, path: str) -> str:
        target = self._jail(path)
        if self._is_sensitive_path(target):
            raise PermissionError(f"access to secret file denied: {path}")
        text = target.read_text()
        return text[:MAX_READ] + ("\n...[truncated]" if len(text) > MAX_READ else "")

    def write_file(self, path: str, content: str) -> str:
        with self._mutation_lock():
            self._require_clean_repo()
            p = self._jail(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            self._commit(f"write {path}", p)
        return f"wrote {len(content)} chars to {path}"

    def edit_file(self, path: str, old_str: str, new_str: str) -> str:
        with self._mutation_lock():
            self._require_clean_repo()
            p = self._jail(path)
            text = p.read_text()
            n = text.count(old_str)
            if n == 0:
                return "error: old_str not found in file"
            if n > 1:
                return f"error: old_str appears {n} times — make it unique"
            p.write_text(text.replace(old_str, new_str, 1))
            self._commit(f"edit {path}", p)
        return f"edited {path}"

    def list_dir(self, path: str = ".") -> str:
        p = self._jail(path)
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = [
            f"{'d' if e.is_dir() else 'f'} {e.relative_to(self.root)}"
            for e in entries
            if e.name not in {".git", "node_modules", "__pycache__", ".venv"}
        ]
        return "\n".join(lines[:300]) or "(empty)"

    def grep(self, pattern: str, path: str = ".") -> str:
        out = subprocess.run(
            [
                "grep",
                "-rIn",
                "--max-count=3",
                "--exclude-dir=.git",
                "--exclude-dir=node_modules",
                "--exclude-dir=__pycache__",
                "--exclude-dir=.venv",
                "--exclude=.env",
                "--exclude=searxng.env",
                "--exclude=*.pem",
                "--exclude=*.key",
                pattern,
                str(self._jail(path)),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = self._redact(out.stdout.strip())
        return text[:10_000] if text else "(no matches)"

    def run_shell(self, command: str) -> str:
        classification = classify_command(command)
        self._require_command_allowed(classification)
        self._validate_command_paths(classification.argv)
        argv = ["/bin/bash", "-lc", command] if classification.uses_shell else classification.argv
        writable = classification.risk != "read-only inspection"
        lock = self._mutation_lock() if writable else nullcontext()
        with lock:
            if writable:
                self._require_clean_repo()
            with tempfile.TemporaryDirectory(prefix="klaude-shell-") as temporary:
                safe_environment = {
                    name: value
                    for name, value in os.environ.items()
                    if not SENSITIVE_ENV_NAME_RE.search(name)
                }
                env = {
                    **safe_environment,
                    "HOME": temporary,
                    "TMPDIR": temporary,
                    "XDG_CACHE_HOME": f"{temporary}/cache",
                    "XDG_CONFIG_HOME": f"{temporary}/config",
                }
                sandbox_argv = [
                    sys.executable,
                    "-m",
                    "klaude_tools.sandbox",
                    "--workspace",
                    str(self.root),
                    "--temporary",
                    temporary,
                ]
                if writable:
                    sandbox_argv.append("--writable")
                sandbox_argv.extend(["--", *argv])
                out = subprocess.run(
                    sandbox_argv,
                    shell=False,
                    cwd=self.root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=SHELL_TIMEOUT,
                )
            if out.returncode == 0 and writable:
                self._commit_all(f"run {classification.reason}")
            elif out.returncode != 0 and writable and self._is_repo() and self._status_paths():
                self.write_enabled = False
        result = self._redact(f"exit={out.returncode}\n{out.stdout}{out.stderr}")
        return result[:12_000]

    def git_status(self) -> str:
        try:
            return self._git("status", "--short", "--branch") or "(clean)"
        except GitCommandError as exc:
            return f"git error: {exc}"

    def git_diff(self) -> str:
        try:
            return self._git("diff", "--stat") + "\n\n" + self._git("diff")
        except GitCommandError as exc:
            return f"git error: {exc}"

    def git_commit(self, message: str) -> str:
        self._require_write_enabled()
        before = ""
        try:
            before = self._git("rev-parse", "HEAD")
        except GitCommandError:
            pass
        self._git("add", "-A")
        output = self._git("commit", "-m", message)
        after = self._git("rev-parse", "HEAD")
        if not after or after == before:
            raise RuntimeError("git commit did not create a new commit")
        return f"{output}\ncommit={after}"

    def workspace_info(self) -> str:
        lines = [
            f"working_directory: {self.root}",
            (
                f"repository_root: {self.repo_root}"
                if self.repo_root
                else "repository_root: (not a git repository)"
            ),
            f"write_tools: {'enabled' if self.write_enabled else 'disabled'}",
        ]
        return "\n".join(lines)


def build_tools(ws: Workspace) -> list[Tool]:
    S = {"type": "string"}

    def obj(props: dict, required: list[str]) -> dict:
        return {"type": "object", "properties": props, "required": required}

    return [
        Tool(
            "read_file", "Read a file from the workspace.", obj({"path": S}, ["path"]), ws.read_file
        ),
        Tool("list_dir", "List files in a workspace directory.", obj({"path": S}, []), ws.list_dir),
        Tool(
            "workspace_info",
            "Show only the current working directory and repository root. "
            "Use for where-am-I and pwd questions; omit hardware/system specs.",
            obj({}, []),
            ws.workspace_info,
        ),
        Tool(
            "grep",
            "Search file contents for a pattern (recursive).",
            obj({"pattern": S, "path": S}, ["pattern"]),
            ws.grep,
        ),
        Tool(
            "write_file",
            "Create or overwrite a file with content.",
            obj({"path": S, "content": S}, ["path", "content"]),
            ws.write_file,
            detail=lambda a: f"write {a.get('path')} ({len(a.get('content', ''))} chars)",
        ),
        Tool(
            "edit_file",
            "Edit a file by replacing an exact unique string with a new string.",
            obj({"path": S, "old_str": S, "new_str": S}, ["path", "old_str", "new_str"]),
            ws.edit_file,
            detail=lambda a: f"edit {a.get('path')}: '{str(a.get('old_str'))[:60]}...'",
        ),
        Tool(
            "run_shell",
            "Run a command in the workspace. Returns exit code and output.",
            obj({"command": S}, ["command"]),
            ws.run_shell,
            detail=lambda a: (
                f"$ {a.get('command')}\nrisk={classify_command(str(a.get('command', ''))).risk}"
            ),
        ),
        Tool("git_status", "Show git status.", obj({}, []), ws.git_status),
        Tool("git_diff", "Show the current working-tree diff.", obj({}, []), ws.git_diff),
        Tool(
            "git_commit",
            "Commit all current changes with a message.",
            obj({"message": S}, ["message"]),
            ws.git_commit,
            detail=lambda a: f"git commit -m '{a.get('message')}'",
        ),
    ]
