import queue
import sqlite3
import threading
import time

import pytest
from klaude_cli.session_io import SessionIOCoordinator, SessionIORequest, collect_session_io
from klaude_core.memory import Memory


def test_session_connection_is_separate_bounded_and_does_not_create_database(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    connection = memory.open_session_io()
    assert connection.db is not memory.db
    assert connection.db.execute("PRAGMA busy_timeout").fetchone()[0] == 200
    assert memory.db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    connection.db.close()
    memory.db.close()
    (tmp_path / "sessions.db").unlink()
    with pytest.raises(sqlite3.OperationalError):
        memory.open_session_io()
    assert not (tmp_path / "sessions.db").exists()


def test_session_io_renewal_and_other_client_drafts_are_preserved(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.acquire_session_lease("session", "owner", "turn")
    memory.update_session_client("session", "other", draft="other draft", queue=[])
    result = collect_session_io(memory, SessionIORequest(
        "session", "owner", "turn", 0, renew=True, draft="owner draft"
    ))
    assert result.renewed is True
    assert result.renewed_at > 0
    assert {client["draft"] for client in result.clients} == {"other draft", "owner draft"}
    denied = collect_session_io(memory, SessionIORequest(
        "session", "other", "wrong", 0, renew=True
    ))
    assert denied.renewed is False
    memory.db.close()


def test_coordinator_coalesces_and_cleans_old_scope_after_inflight_write(tmp_path, monkeypatch):
    import klaude_cli.session_io as module

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    entered, release = threading.Event(), threading.Event()
    events = queue.Queue()
    seen = []
    original = module.collect_session_io

    def controlled(connection, request):
        seen.append(request.draft)
        if request.draft == "first":
            entered.set()
            assert release.wait(2)
        return original(connection, request)

    monkeypatch.setattr(module, "collect_session_io", controlled)
    worker = SessionIOCoordinator(memory, lambda kind, payload: events.put((kind, payload)))
    try:
        worker.submit(SessionIORequest("old", "client", "", 0, draft="first"))
        assert entered.wait(2)
        for draft in ("discard one", "discard two"):
            worker.submit(SessionIORequest("old", "client", "", 0, draft=draft))
        worker.switch_scope("new", "client")
        worker.submit(SessionIORequest("new", "client", "", 0, draft="latest"))
        release.set()
        assert events.get(timeout=2)[1][0].session_id == "old"
        assert events.get(timeout=2)[1][0].session_id == "new"
        assert seen == ["first", "latest"]
        assert memory.session_client_states("old") == []
        assert memory.session_client_states("new")[0]["draft"] == "latest"
    finally:
        release.set()
        worker.close(wait=True)
    assert not worker._thread.is_alive()
    assert memory.session_client_states("new") == []
    memory.db.close()


def test_sqlite_lock_does_not_block_submit_and_recovers(tmp_path):
    database = tmp_path / "sessions.db"
    memory = Memory(tmp_path / "memory.md", database)
    lock = sqlite3.connect(database)
    lock.execute("BEGIN IMMEDIATE")
    events = queue.Queue()
    worker = SessionIOCoordinator(memory, lambda kind, payload: events.put((kind, payload)))
    request = SessionIORequest("session", "client", "", 0, draft="public")
    try:
        started = time.monotonic()
        worker.submit(request)
        assert time.monotonic() - started < 0.25
        kind, (returned, result, error) = events.get(timeout=2)
        assert kind == "session_io" and returned == request
        assert result is None and error == "Session storage busy/unavailable; retrying"
        lock.rollback()
        worker.submit(request)
        assert events.get(timeout=2)[1][1] is not None
    finally:
        lock.rollback()
        lock.close()
        worker.close(wait=True)
        memory.db.close()
