"""Serialized, coalescing shared-session I/O, isolated from TUI rendering."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SessionIORequest:
    session_id: str
    client_id: str
    turn_id: str
    cursor: int
    renew: bool = False
    draft: str | None = None
    queue: tuple[str, ...] = ()
    was_watching: bool = False
    list_sessions: bool = False


@dataclass
class SessionIOResult:
    live: dict[str, Any]
    clients: list[dict[str, Any]]
    events: list[dict[str, Any]]
    renewed: bool | None = None
    renewed_at: float = 0.0
    recovered: bool = False
    sessions: list[dict[str, Any]] | None = None
    # Local model replay only; never render, serialize, or publish this field.
    history: Any = field(default=None, repr=False)


def collect_session_io(memory, request: SessionIORequest) -> SessionIOResult:
    renewed = (
        memory.renew_session_lease(request.session_id, request.client_id, request.turn_id)
        if request.renew else None
    )
    renewed_at = time.monotonic() if renewed else 0.0
    if request.draft is not None:
        memory.update_session_client(
            request.session_id, request.client_id, draft=request.draft, queue=list(request.queue)
        )
    live = memory.session_live_state(request.session_id)
    remote = (
        live["state"] == "running" and live["owner_client_id"] != request.client_id
        and float(live["owner_lease_until"]) > time.time()
    )
    recovered = False
    if request.was_watching and not remote and live["state"] == "running":
        snapshot = memory.session_snapshot(request.session_id)
        live = snapshot["live"]
        recovered = bool(snapshot.get("recovered_turn_ids"))
    events = memory.session_events_since(request.session_id, request.cursor)
    history = (
        memory.load_session(request.session_id)
        if any(event["kind"] == "turn_done" and event["client_id"] != request.client_id
               for event in events) else None
    )
    return SessionIOResult(
        live, memory.session_client_states(request.session_id), events,
        renewed, renewed_at, recovered,
        memory.resumable_sessions() if request.list_sessions else None, history,
    )


class SessionIOCoordinator:
    """One connection/worker, at most one pending snapshot, ordered scope cleanup."""

    def __init__(self, memory, emit):
        self.memory = memory
        self.emit = emit
        self._condition = threading.Condition()
        self._pending: SessionIORequest | None = None
        self._scope: tuple[str, str] | None = None
        self._cleanup: set[tuple[str, str]] = set()
        self._closed = False
        self._thread: threading.Thread | None = None

    def submit(self, request: SessionIORequest) -> None:
        with self._condition:
            if self._closed:
                return
            scope = (request.session_id, request.client_id)
            if self._scope is not None and self._scope != scope:
                self._cleanup.add(self._scope)
            self._scope = scope
            self._pending = request
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name="klaude-session-io"
                )
                self._thread.start()
            self._condition.notify()

    def switch_scope(self, session_id: str, client_id: str) -> None:
        with self._condition:
            scope = (session_id, client_id)
            if self._scope is not None and self._scope != scope:
                self._cleanup.add(self._scope)
            self._scope = scope
            self._pending = None
            self._condition.notify()

    def _run(self) -> None:
        memory = None
        try:
            memory = self.memory.open_session_io()
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._pending or self._cleanup)
                    cleanup = set(self._cleanup)
                    self._cleanup.clear()
                    if self._closed:
                        if self._scope is not None:
                            cleanup.add(self._scope)
                        request = None
                    else:
                        request, self._pending = self._pending, None
                # Always after any in-flight old write, before any new-scope write.
                for session, client in cleanup:
                    try:
                        memory.clear_session_client(session, client)
                    except Exception:
                        if not self._closed:
                            with self._condition:
                                self._cleanup.add((session, client))
                                if request is not None and self._pending is None:
                                    self._pending = request
                            request = None
                            # Avoid spinning when storage fails without a busy wait.
                            with self._condition:
                                self._condition.wait(timeout=0.05)
                if self._closed:
                    break
                if request is None:
                    continue
                with self._condition:
                    if (request.session_id, request.client_id) != self._scope:
                        continue
                try:
                    result = collect_session_io(memory, request)
                except Exception:
                    self.emit("session_io", (
                        request, None, "Session storage busy/unavailable; retrying"
                    ))
                else:
                    self.emit("session_io", (request, result, ""))
        except Exception:
            self.emit("session_io_unavailable", "Session I/O unavailable; restart the chat")
        finally:
            if memory is not None:
                memory.db.close()

    def close(self, *, wait: bool = False) -> None:
        with self._condition:
            self._closed = True
            self._pending = None
            self._condition.notify()
        if wait and self._thread is not None:
            self._thread.join(2)
