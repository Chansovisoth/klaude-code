"""Serialized, coalescing atomic settings writes outside the UI thread."""

from __future__ import annotations

import threading
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from klaude_core.settings_store import DELETE, update_settings


def public_tool_settings(value: dict[str, Any]) -> dict[str, dict[str, bool]]:
    """Return only bounded boolean preferences, never arbitrary saved data."""
    result = {}
    for group in ("tool_validation", "tool_availability", "web_provider_availability"):
        raw = value.get(group)
        if isinstance(raw, dict):
            result[group] = {
                name: enabled for name, enabled in list(raw.items())[:256]
                if isinstance(name, str) and len(name) <= 256 and isinstance(enabled, bool)
            }
    display = value.get("display")
    if isinstance(display, dict):
        enabled = display.get("activity_updates", display.get("reasoning_activity"))
        if isinstance(enabled, bool):
            result["display"] = {"activity_updates": enabled}
    return result


def merge_intent(
    earlier: dict[tuple[str, ...], object], later: dict[tuple[str, ...], object]
) -> dict[tuple[str, ...], object]:
    """Retain chronological parent/child operations and freeze mutable input."""
    result = dict(earlier)
    for keys, replacement in later.items():
        for previous in list(result):
            if previous[:len(keys)] == keys:
                del result[previous]
        result[keys] = DELETE if replacement is DELETE else deepcopy(replacement)
    return result


class SettingsWriter:
    """One file/worker; accepted writes drain on close and are never cancelled."""

    def __init__(
        self, path: Path, emit, *,
        prepare: Callable[[dict[str, Any]], None] | None = None,
        publish_permissions: bool = True,
        publish_tools: bool = False,
    ):
        self.path = path
        self.emit = emit
        self.prepare = prepare
        self.publish_permissions = publish_permissions
        self.publish_tools = publish_tools
        self._condition = threading.Condition()
        self._pending: dict[tuple[str, ...], object] = {}
        self._revision = 0
        self._ready = False
        self._closed = False
        self._thread: threading.Thread | None = None

    def submit(self, changes: dict[tuple[str, ...], object]) -> int:
        with self._condition:
            if self._closed:
                raise RuntimeError("Settings writer is closed")
            self._pending = merge_intent(self._pending, changes)
            self._revision += 1
            self._ready = True
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name="klaude-settings-writer"
                )
                self._thread.start()
            self._condition.notify()
            return self._revision

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._ready or self._closed)
                if not self._ready:
                    return
                changes, self._pending = self._pending, {}
                revision = self._revision
                self._ready = False
            saved = False
            permissions = None
            tool_settings = None
            try:
                result = (
                    update_settings(self.path, changes)
                    if self.prepare is None
                    else update_settings(self.path, changes, prepare=self.prepare)
                )
                saved = True
                if self.publish_tools:
                    tool_settings = public_tool_settings(result)
                raw = result.get("permissions", {})
                if self.publish_permissions and isinstance(raw, dict) and (
                    raw or any(keys and keys[0] == "permissions" for keys in changes)
                ):
                    permissions = {
                        name: policy for name, policy in list(raw.items())[:4096]
                        if isinstance(name, str) and len(name) <= 256
                        and isinstance(policy, str) and policy in {"ask", "allow", "deny"}
                    }
            except Exception:
                # Retain failed intent for the next explicit save; newer values
                # win. Do not spin/retry indefinitely on unavailable storage.
                with self._condition:
                    self._pending = merge_intent(changes, self._pending)
            self.emit("settings_saved", (revision, saved))
            if permissions is not None:
                self.emit("settings_permissions", (revision, permissions))
            if tool_settings:
                self.emit("settings_tools", (revision, tool_settings))

    def close(self, *, wait: bool = False) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify()
        if wait and self._thread is not None:
            self._thread.join(2)
        with self._condition:
            return (self._thread is None or not self._thread.is_alive()) and not self._pending
