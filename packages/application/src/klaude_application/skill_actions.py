"""Owned ordered skill mutations; navigation cannot discard accepted work."""

from __future__ import annotations

import copy
import queue
import re
import threading
import time
from dataclasses import dataclass

from klaude_core import Config
from klaude_core.skill_catalog import STATUS_TEXT, CatalogFailure, SkillRecord
from klaude_core.skill_drop import SkillDropDetector


@dataclass(frozen=True)
class SkillAction:
    kind: str
    name: str = ""
    identity: str = ""
    record: SkillRecord | None = None
    enabled: bool | None = None
    expected_manifest_identity: str = ""


class SkillActionWriter:
    def __init__(self, cfg: Config, emit):
        self.cfg = copy.deepcopy(cfg)
        self.emit = emit
        self._queue: queue.Queue[SkillAction] = queue.Queue(4)
        self._lock = threading.Lock()
        self._closed = False
        self._failed = False
        self._thread: threading.Thread | None = None
        self._watching = False
        self._drop_snapshot: tuple[str, ...] | None = None
        self._wake = threading.Event()
        self._detector = SkillDropDetector()

    def watch(self) -> None:
        """Start metadata polling on the same ordered mutation lane."""
        with self._lock:
            if self._closed:
                return
            self._watching = True
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="klaude-skills")
                self._thread.start()
            self._wake.set()

    def submit(self, action: SkillAction) -> bool:
        with self._lock:
            if self._closed or action.kind not in {
                "delete", "import", "prepare", "install-remote", "update-remote", "set-enabled"
            }:
                return False
            if action.kind in {"install-remote", "update-remote"} and (
                action.record is None or action.record.identity != action.identity
                or not action.record.canonical_identity
            ):
                return False
            if action.kind == "update-remote" and (
                not action.name or action.record is None or action.record.name != action.name
                or not re.fullmatch(r"[a-f0-9]{64}", action.expected_manifest_identity)
            ):
                return False
            if action.kind == "set-enabled" and (
                not action.name or not action.identity or type(action.enabled) is not bool
            ):
                return False
            try:
                self._queue.put_nowait(action)
            except queue.Full:
                return False
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="klaude-skills")
                self._thread.start()
            self._wake.set()
            return True

    def refresh(self) -> None:
        """Wake the metadata-only drop scan without importing anything."""
        self._wake.set()

    def _poll(self) -> None:
        try:
            ready = self._detector.ready(self.cfg.skills_dir, time.monotonic())
        except OSError:
            return
        names = tuple("".join(c for c in source.name if c.isprintable())[:128]
                      for source, _signature in ready)
        if names != self._drop_snapshot:
            self._drop_snapshot = names
            self.emit("skill_drop_inventory", names)

    def _run(self) -> None:
        while True:
            with self._lock:
                try:
                    action = self._queue.get_nowait()
                except queue.Empty:
                    if self._closed or not self._watching:
                        self._thread = None
                        return
                    action = None
            if action is None:
                self._poll()
                self._wake.wait(1)
                self._wake.clear()
                continue
            message = ""
            tone = "success"
            try:
                from klaude_knowledge.skill_management import (
                    delete_installed_skill,
                    import_remote_skill,
                    import_skill_inbox,
                    set_installed_skill_enabled,
                )

                if action.kind == "prepare":
                    self.cfg.skills_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                elif action.kind == "delete":
                    delete_installed_skill(self.cfg, action.name, action.identity)
                    message = "Skill deleted"
                elif action.kind == "set-enabled":
                    assert action.enabled is not None
                    set_installed_skill_enabled(
                        self.cfg, action.name, action.identity, action.enabled
                    )
                    message = "Skill enabled" if action.enabled else "Skill disabled"
                elif action.kind == "install-remote":
                    if action.record is None or action.record.identity != action.identity:
                        raise ValueError("Skill selection changed; review it again")
                    installed, _count = import_remote_skill(self.cfg, action.record)
                    message = f"Installed {installed.name}"
                elif action.kind == "update-remote":
                    if action.record is None or action.record.name != action.name:
                        raise ValueError("Skill update changed; review it again")
                    installed, _count = import_remote_skill(
                        self.cfg, action.record, overwrite=True,
                        expected_identity=action.expected_manifest_identity,
                    )
                    message = f"Updated {installed.name}"
                else:
                    imported, failed = import_skill_inbox(self.cfg)
                    tone = "warning" if failed else "success" if imported else "neutral"
                    message = (
                        f"Imported {imported} skills · {failed} skipped/failed (originals retained)"
                        if imported or failed else
                        "No new skill file."
                    )
                success = True
            except CatalogFailure as exc:
                self._failed = True
                success = False
                tone = "error"
                reason = STATUS_TEXT.get(exc.status, "Source unavailable")
                message = f"Skill update failed: {reason}" if action.kind == (
                    "update-remote"
                ) else f"Skill install failed: {reason}"
            except FileExistsError:
                self._failed = True
                success = False
                tone = "warning"
                message = "Skill already installed; existing files were kept"
            except ValueError as exc:
                self._failed = True
                success = False
                tone = "error" if action.kind in {"update-remote", "install-remote"} else "warning"
                message = f"Skill update failed: {str(exc)[:160]}" if action.kind == (
                    "update-remote"
                ) else f"Skill install failed: {str(exc)[:160]}" if action.kind == (
                    "install-remote"
                ) else "Skill change unconfirmed; refresh and review before retrying"
            except Exception:
                self._failed = True
                success = False
                tone = "warning"
                message = "Skill change unconfirmed; refresh and review before retrying"
            self.emit("skill_action_done", (action, success, message, tone))
            self._queue.task_done()

    def close(self, *, wait: bool = False) -> bool:
        with self._lock:
            self._closed = True
            self._wake.set()
            thread = self._thread
        if wait and thread is not None:
            thread.join(2)
        return not self._failed and self._queue.unfinished_tasks == 0
