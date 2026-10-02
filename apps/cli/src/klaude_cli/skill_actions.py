"""Owned ordered skill mutations; navigation cannot discard accepted work."""

from __future__ import annotations

import copy
import queue
import threading
import time
from dataclasses import dataclass

from klaude_core import Config
from klaude_core.skill_drop import SkillDropDetector


@dataclass(frozen=True)
class SkillAction:
    kind: str
    name: str = ""
    identity: str = ""


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
            if self._closed or action.kind not in {"delete", "import", "prepare"}:
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
            try:
                from klaude_knowledge.skill_management import (
                    delete_installed_skill,
                    import_skill_inbox,
                )

                if action.kind == "prepare":
                    self.cfg.skills_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                elif action.kind == "delete":
                    delete_installed_skill(self.cfg, action.name, action.identity)
                    message = "Skill deleted"
                else:
                    imported, failed = import_skill_inbox(self.cfg)
                    message = (
                        f"Imported {imported} skills · {failed} skipped/failed (originals retained)"
                        if imported or failed else
                        f"No new skill file. Add it to {self.cfg.skills_dir}"
                    )
                success = True
            except Exception:
                self._failed = True
                success = False
                message = "Skill change unconfirmed; refresh and review before retrying"
            self.emit("skill_action_done", (action, success, message))
            self._queue.task_done()

    def close(self, *, wait: bool = False) -> bool:
        with self._lock:
            self._closed = True
            self._wake.set()
            thread = self._thread
        if wait and thread is not None:
            thread.join(2)
        return not self._failed and self._queue.unfinished_tasks == 0
