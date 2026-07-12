"""Built-in tools, returned as klaude_core.Tool objects.

Design rules:
- fs tools are jailed to the workspace root (no ../../ escapes).
- edit_file is exact-string replacement (predictable, diff-friendly).
- git tools implement the work-branch discipline: klaude never commits to
  your branch; write operations auto-commit on klaude/<task> so every agent
  action is one revertible commit — and VS Code's diff UI works for free.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from klaude_core import Tool

MAX_READ = 60_000
SHELL_TIMEOUT = 120


class Workspace:
    def __init__(self, root: Path, auto_commit: bool = True):
        self.root = root.resolve()
        self.auto_commit = auto_commit
        self.write_enabled = True

    # --- helpers ---------------------------------------------------------
    def _jail(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root):
            raise PermissionError(f"path escapes workspace: {rel}")
        return p

    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, timeout=60
        )
        return (out.stdout + out.stderr).strip()

    def _is_repo(self) -> bool:
        return (self.root / ".git").exists()

    def ensure_work_branch(self, task_slug: str = "session") -> str:
        """Called once at session start: refuse dirty trees, branch off."""
        if not self._is_repo():
            return "not a git repo — edits will not be auto-committed"
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
        return f"working on branch {branch}"

    def _require_write_enabled(self) -> None:
        if not self.write_enabled:
            raise PermissionError(
                "working tree is dirty; commit or stash your changes before AI edits"
            )

    def _commit(self, message: str) -> None:
        if self.auto_commit and self._is_repo():
            self._git("add", "-A")
            self._git("commit", "-m", f"klaude: {message}")

    # --- tool implementations ---------------------------------------------
    def read_file(self, path: str) -> str:
        text = self._jail(path).read_text()
        return text[:MAX_READ] + ("\n...[truncated]" if len(text) > MAX_READ else "")

    def write_file(self, path: str, content: str) -> str:
        self._require_write_enabled()
        p = self._jail(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self._commit(f"write {path}")
        return f"wrote {len(content)} chars to {path}"

    def edit_file(self, path: str, old_str: str, new_str: str) -> str:
        self._require_write_enabled()
        p = self._jail(path)
        text = p.read_text()
        n = text.count(old_str)
        if n == 0:
            return "error: old_str not found in file"
        if n > 1:
            return f"error: old_str appears {n} times — make it unique"
        p.write_text(text.replace(old_str, new_str, 1))
        self._commit(f"edit {path}")
        return f"edited {path}"

    def list_dir(self, path: str = ".") -> str:
        p = self._jail(path)
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = [f"{'d' if e.is_dir() else 'f'} {e.relative_to(self.root)}" for e in entries
                 if e.name not in {".git", "node_modules", "__pycache__", ".venv"}]
        return "\n".join(lines[:300]) or "(empty)"

    def grep(self, pattern: str, path: str = ".") -> str:
        out = subprocess.run(
            ["grep", "-rIn", "--max-count=3",
             "--exclude-dir=.git", "--exclude-dir=node_modules",
             "--exclude-dir=__pycache__", "--exclude-dir=.venv",
             pattern, str(self._jail(path))],
            capture_output=True, text=True, timeout=30,
        )
        text = out.stdout.strip()
        return text[:10_000] if text else "(no matches)"

    def run_shell(self, command: str) -> str:
        out = subprocess.run(
            command, shell=True, cwd=self.root,
            capture_output=True, text=True, timeout=SHELL_TIMEOUT,
        )
        result = f"exit={out.returncode}\n{out.stdout}{out.stderr}"
        return result[:12_000]

    def git_status(self) -> str:
        return self._git("status", "--short", "--branch") or "(clean)"

    def git_diff(self) -> str:
        return self._git("diff", "HEAD~1", "--stat") + "\n\n" + self._git("diff", "HEAD~1")

    def git_commit(self, message: str) -> str:
        self._require_write_enabled()
        self._git("add", "-A")
        return self._git("commit", "-m", message)


def build_tools(ws: Workspace) -> list[Tool]:
    S = {"type": "string"}

    def obj(props: dict, required: list[str]) -> dict:
        return {"type": "object", "properties": props, "required": required}

    return [
        Tool("read_file", "Read a file from the workspace.",
             obj({"path": S}, ["path"]), ws.read_file),
        Tool("list_dir", "List files in a workspace directory.",
             obj({"path": S}, []), ws.list_dir),
        Tool("grep", "Search file contents for a pattern (recursive).",
             obj({"pattern": S, "path": S}, ["pattern"]), ws.grep),
        Tool("write_file", "Create or overwrite a file with content.",
             obj({"path": S, "content": S}, ["path", "content"]), ws.write_file,
             detail=lambda a: f"write {a.get('path')} ({len(a.get('content', ''))} chars)"),
        Tool("edit_file",
             "Edit a file by replacing an exact unique string with a new string.",
             obj({"path": S, "old_str": S, "new_str": S}, ["path", "old_str", "new_str"]),
             ws.edit_file,
             detail=lambda a: f"edit {a.get('path')}: '{str(a.get('old_str'))[:60]}...'"),
        Tool("run_shell", "Run a shell command in the workspace. Returns exit code and output.",
             obj({"command": S}, ["command"]), ws.run_shell,
             detail=lambda a: f"$ {a.get('command')}"),
        Tool("git_status", "Show git status.", obj({}, []), ws.git_status),
        Tool("git_diff", "Show the diff of the last commit.", obj({}, []), ws.git_diff),
        Tool("git_commit", "Commit all current changes with a message.",
             obj({"message": S}, ["message"]), ws.git_commit,
             detail=lambda a: f"git commit -m '{a.get('message')}'"),
    ]
