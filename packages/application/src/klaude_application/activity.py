"""Deterministic public activity projection of the existing execution events.

Activities describe work in progress, never a claim that its effect succeeded.
The turn lifecycle remains authoritative for completion, failure and cancellation.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePath
from typing import Any


class Activity(StrEnum):
    WRITING_CODE = "Writing code"
    EDITING = "Editing"
    APPLYING_CHANGES = "Applying changes"
    GENERATING_IMAGES = "Generating images"
    CREATING_FILES = "Creating files"
    ANALYZING_DATA = "Analyzing data"
    RUNNING_TESTS = "Running tests"
    VALIDATING = "Validating"
    WAITING = "Waiting"
    GENERATING_RESPONSE = "Generating response"
    DONE = "Done"
    ERROR = "Error"
    NEEDS_INPUT = "Needs input"


_SOURCE_SUFFIXES = frozenset(
    ".py .pyi .js .jsx .ts .tsx .html .css .scss .rs .go .c .h .cpp .hpp .java "
    ".kt .swift .rb .php .sh .bash .zsh .sql .lua .vue .svelte .ex .exs .cs .r".split()
)


def classify_activity(
    tool: str, arguments: dict[str, Any], metadata: dict[str, Any] | None = None,
) -> Activity:
    """Only exact known operations qualify; arbitrary MCP names stay generic."""
    if tool == "write_file":
        if (metadata or {}).get("file_operation") == "overwrite":
            return Activity.EDITING
        path = arguments.get("path")
        return (Activity.WRITING_CODE if isinstance(path, str)
                and PurePath(path).suffix.casefold() in _SOURCE_SUFFIXES
                else Activity.CREATING_FILES)
    known = {
        "edit_file": Activity.EDITING,
        "apply_patch": Activity.APPLYING_CHANGES,
        "generate_image": Activity.GENERATING_IMAGES,
        "edit_image": Activity.GENERATING_IMAGES,
        "image_generation": Activity.GENERATING_IMAGES,
        "analyze_data": Activity.ANALYZING_DATA,
        "run_tests": Activity.RUNNING_TESTS,
        "validate": Activity.VALIDATING,
        "http_probe": Activity.VALIDATING,
    }
    if tool in known:
        return known[tool]
    if tool != "run_shell":
        return Activity.WAITING
    command = arguments.get("command")
    if not isinstance(command, str) or len(command) > 8192:
        return Activity.WAITING
    try:
        # Shell syntax is deliberately not interpreted. A quoted test name or
        # echo containing 'pytest' is not evidence of running tests.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return Activity.WAITING
    if any(any(char in word for char in ";&|<>`$\n") for word in words):
        return Activity.WAITING
    if words[:2] == ["uv", "run"]:
        words = words[2:]
        while words and words[0] in {"--frozen", "--offline", "--no-sync"}:
            words.pop(0)
    if not words:
        return Activity.WAITING
    executable = PurePath(words[0]).name
    if executable in {"python", "python3", "python3.11", "python3.12", "python3.13"}:
        if len(words) < 3 or words[1] != "-m":
            return Activity.WAITING
        words = words[2:]
        executable = words[0]
    if any(word in {"--help", "-h", "--version"} for word in words[1:]):
        return Activity.WAITING
    if executable in {"pytest", "unittest", "vitest", "jest"}:
        if "--collect-only" in words[1:] or "--listTests" in words[1:]:
            return Activity.VALIDATING
        return Activity.RUNNING_TESTS
    if executable == "ruff":
        if words[1:2] == ["format"] and "--check" not in words[2:]:
            return Activity.EDITING
        if "--fix" in words[2:]:
            return Activity.EDITING
        return Activity.VALIDATING if words[1:2] in (["check"], ["format"]) else Activity.WAITING
    if executable in {"mypy", "py_compile", "compileall"}:
        return Activity.VALIDATING
    pair = (executable, words[1] if len(words) > 1 else "")
    if executable == "make" and len(words) != 2:
        return Activity.WAITING  # Multiple targets may perform unrelated effects.
    if pair in {("make", "test"), ("npm", "test"), ("pnpm", "test"),
                ("yarn", "test"), ("cargo", "test"), ("go", "test")}:
        return Activity.RUNNING_TESTS
    if pair in {("make", "check"), ("make", "lint"), ("make", "typecheck"),
                ("git", "diff")}:
        if pair != ("git", "diff") or "--check" in words[2:]:
            return Activity.VALIDATING
    if pair == ("git", "apply"):
        inspection = {"--check", "--stat", "--numstat", "--summary"}
        return (Activity.VALIDATING if inspection.intersection(words[2:])
                else Activity.APPLYING_CHANGES)
    return Activity.WAITING


def tool_outcome(result: object, metadata: dict[str, Any]) -> str:
    """Report a tool outcome separately from the overall turn outcome."""
    text = str(result).lstrip().casefold()
    if (metadata.get("error_type") or metadata.get("status") in {"failed", "error"}
            or metadata.get("is_error") is True or metadata.get("isError") is True
            or (type(metadata.get("exit_code")) is int and metadata["exit_code"] != 0)
            or text.startswith(("error:", "tool error:"))):
        return "failed"
    if metadata.get("executed") is not True:
        return "rejected"
    return "succeeded"


@dataclass
class ActivityState:
    """Small replayable read model, keyed by turn/execution/interaction IDs.

    Child tool events are never promoted to the parent's activity. Delegation
    remains a pending parent operation; its detailed existing history is separate.
    """

    turn_id: str = ""
    lifecycle: str = "idle"
    base: str = ""
    recoverable: bool = False
    active: dict[str, dict[str, str]] = field(default_factory=dict)
    interactions: list[str] = field(default_factory=list)
    timeline: list[dict[str, str]] = field(default_factory=list)

    def observe(self, turn_id: str, kind: str, **event: Any) -> None:
        if kind in {"turn.accepted", "turn.started"} and turn_id != self.turn_id:
            self.turn_id = turn_id
            self.lifecycle = "running"
            self.base = (Activity.GENERATING_RESPONSE.value if kind == "turn.started"
                         else Activity.WAITING.value)
            self.recoverable = False
            self.active.clear()
            self.interactions.clear()
            self.timeline.clear()
        if not turn_id or turn_id != self.turn_id:
            return
        if kind.startswith("turn.") and kind.split(".", 1)[1] in {
            "completed", "partial", "failed", "cancelled", "interrupted",
        }:
            self.lifecycle = kind.split(".", 1)[1]
            self.active.clear()
            self.interactions.clear()
            self.recoverable = False
            self.base = {"completed": Activity.DONE.value,
                         "failed": Activity.ERROR.value, "partial": Activity.ERROR.value}.get(
                             self.lifecycle, "")
        elif self.lifecycle != "running":
            return
        elif kind == "turn.started":
            self.base = Activity.GENERATING_RESPONSE.value
        elif kind.endswith(".required") and kind.startswith(("approval.", "user_input.")):
            identity = str(event.get("interaction_id") or "")
            if identity and identity not in self.interactions:
                self.interactions.append(identity)
        elif kind.endswith(".resolved") and kind.startswith(("approval.", "user_input.")):
            identity = str(event.get("interaction_id") or "")
            if identity in self.interactions:
                self.interactions.remove(identity)
            self.base = Activity.WAITING.value
        elif kind == "tool.started":
            identity = str(event.get("execution_id") or "")
            if identity:
                self.active.setdefault(identity, {
                    "tool": str(event.get("tool") or "")[:128],
                    "activity": self._safe_activity(event.get("activity")),
                })
            self.recoverable = False
        elif kind == "tool.finished":
            identity = str(event.get("execution_id") or "")
            finished = self.active.pop(identity, None)
            if finished and not event.get("tool"):
                event["tool"] = finished["tool"]
            self.recoverable = event.get("status") == "failed"
            self.base = Activity.ERROR.value if self.recoverable else Activity.WAITING.value
        elif kind == "tool.requested":
            self.base = Activity.WAITING.value
            self.recoverable = False
        elif kind in {"message.delta", "activity.changed"}:
            self.base = (self._safe_activity(event.get("activity"))
                         if kind == "activity.changed" else Activity.GENERATING_RESPONSE.value)
            self.recoverable = False
        if kind in {"tool.requested", "tool.started", "tool.finished", "activity.changed",
                    "approval.required", "approval.resolved", "user_input.required",
                    "user_input.resolved", "turn.completed", "turn.partial", "turn.failed",
                    "turn.cancelled", "turn.interrupted"}:
            row = {key: str(event.get(key) or "")[:128]
                   for key in ("tool", "execution_id", "interaction_id", "status")}
            row.update(kind=kind, label=self.label)
            self.timeline.append(row)
            self.timeline = self.timeline[-80:]

    @staticmethod
    def _safe_activity(value: object) -> str:
        allowed = {item.value for item in Activity} - {
            Activity.DONE.value, Activity.ERROR.value, Activity.NEEDS_INPUT.value,
        }
        return value if isinstance(value, str) and value in allowed else Activity.WAITING.value

    @property
    def label(self) -> str:
        if self.interactions:
            return Activity.NEEDS_INPUT.value
        if self.active:
            # Keep the oldest active execution until it finishes. Later starts
            # and unrelated finishes cannot steal its label.
            return next(iter(self.active.values()))["activity"]
        return self.base

    def public(self, *, timeline: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "turn_id": self.turn_id, "label": self.label, "lifecycle": self.lifecycle,
            "recoverable": self.recoverable, "active_count": len(self.active),
        }
        if timeline:
            result["timeline"] = self.timeline
        return result
