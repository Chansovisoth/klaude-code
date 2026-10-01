"""Ordered, bounded session-setting writes, separate from coalesced snapshots."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionSettingUpdate:
    session_id: str
    client_id: str
    detail: str


@dataclass(frozen=True)
class AutomaticMemoryUpdate:
    session_id: str
    client_id: str
    revision: int
    enabled: bool


class SessionActionWriter:
    """Accepted actions retain their original scope and drain on close."""

    def __init__(self, memory, emit):
        self.memory = memory
        self.emit = emit
        self._condition = threading.Condition()
        self._pending: deque[SessionSettingUpdate | AutomaticMemoryUpdate] = deque()
        self._closed = False
        self._failed = False
        self._unavailable = False
        self._thread: threading.Thread | None = None

    def submit(self, update: SessionSettingUpdate | AutomaticMemoryUpdate) -> bool:
        with self._condition:
            if self._closed or self._unavailable or len(self._pending) >= 128:
                self._failed = True
                return False
            if isinstance(update, SessionSettingUpdate) and (
                not update.detail or len(update.detail) > 2048
            ):
                self._failed = True
                return False
            self._pending.append(update)
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name="klaude-session-actions"
                )
                self._thread.start()
            self._condition.notify()
            return True

    def _run(self) -> None:
        connection = None
        try:
            connection = self.memory.open_session_io()
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._pending)
                    if not self._pending:
                        return
                    update = self._pending.popleft()
                saved = False
                try:
                    if isinstance(update, AutomaticMemoryUpdate):
                        connection.set_auto_memory(update.enabled)
                    else:
                        connection.record_session_update(
                            update.session_id, update.client_id, update.detail
                        )
                    saved = True
                except Exception:
                    # Never blindly retry a possibly published transaction.
                    with self._condition:
                        self._failed = True
                self.emit(
                    "memory_setting_saved" if isinstance(update, AutomaticMemoryUpdate)
                    else "session_setting_saved", (update, saved)
                )
        except Exception:
            with self._condition:
                self._failed = self._unavailable = True
                updates = list(self._pending)
                self._pending.clear()
            for update in updates:
                self.emit(
                    "memory_setting_saved" if isinstance(update, AutomaticMemoryUpdate)
                    else "session_setting_saved", (update, False)
                )
        finally:
            if connection is not None:
                connection.db.close()

    def close(self, *, wait: bool = False) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify()
        if wait and self._thread is not None:
            self._thread.join(2)
        with self._condition:
            return (
                not self._failed and not self._pending
                and (self._thread is None or not self._thread.is_alive())
            )
