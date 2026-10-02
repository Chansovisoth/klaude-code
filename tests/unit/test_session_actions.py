import queue
import sqlite3
import threading

from klaude_cli.session_actions import (
    AutomaticMemoryUpdate,
    SessionActionWriter,
    SessionSettingUpdate,
)
from klaude_core.memory import Memory


def test_setting_history_and_event_are_atomic(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.db.execute(
            "CREATE TRIGGER reject_event BEFORE INSERT ON session_events "
            "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
        )
        memory.db.commit()
        try:
            memory.record_session_update("session", "client", "model change")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Expected transaction failure")
        assert memory.load_session("session") == []
        assert memory.session_events_since("session", 0) == []
        memory.db.execute("DROP TRIGGER reject_event")
        memory.db.commit()
        memory.record_session_update("session", "client", "model change")
        assert len(memory.load_session("session")) == 1
        event = memory.session_events_since("session", 0)[0]
        assert event["kind"] == "session_update"
        assert event["payload"] == {"detail": "model change"}
    finally:
        memory.db.close()


def test_actions_are_ordered_keep_original_scope_and_drain_on_exit(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    entered, release = threading.Event(), threading.Event()
    events = queue.Queue()
    original = Memory.record_session_update

    def blocked(connection, session, client, detail):
        if detail == "first":
            entered.set()
            assert release.wait(2)
        original(connection, session, client, detail)

    monkeypatch.setattr(Memory, "record_session_update", blocked)
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    actions = [SessionSettingUpdate("old", "client", "first"),
               SessionSettingUpdate("old", "client", "second"),
               SessionSettingUpdate("new", "client", "third")]
    try:
        assert writer.submit(actions[0])
        assert entered.wait(2)
        assert writer.submit(actions[1]) and writer.submit(actions[2])
        writer.close()
        release.set()
        assert writer.close(wait=True)
        assert [events.get_nowait() for _ in actions] == [
            ("session_setting_saved", (action, True)) for action in actions
        ]
        assert [event["payload"]["detail"] for event in memory.session_events_since("old", 0)] == [
            "first", "second",
        ]
        assert len(memory.load_session("new")) == 1
        assert not writer.submit(SessionSettingUpdate("new", "client", "rejected"))
    finally:
        release.set()
        writer.close(wait=True)
        memory.db.close()


def test_locked_storage_fails_once_without_unsupported_history_or_event(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    lock = sqlite3.connect(memory.sessions_db)
    lock.execute("BEGIN IMMEDIATE")
    events = queue.Queue()
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    action = SessionSettingUpdate("session", "client", "change")
    try:
        assert writer.submit(action)
        assert events.get(timeout=2) == ("session_setting_saved", (action, False))
        lock.rollback()
        assert not writer.close(wait=True)
        assert events.empty()
        assert memory.load_session("session") == []
        assert memory.session_events_since("session", 0) == []
    finally:
        lock.close()
        writer.close(wait=True)
        memory.db.close()


def test_action_queue_is_bounded_and_reports_rejection(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    entered, release = threading.Event(), threading.Event()
    original = Memory.record_session_update

    def blocked(connection, *args):
        entered.set()
        assert release.wait(2)
        original(connection, *args)

    monkeypatch.setattr(Memory, "record_session_update", blocked)
    writer = SessionActionWriter(memory, lambda *_: None)
    action = SessionSettingUpdate("session", "client", "change")
    try:
        assert writer.submit(action) and entered.wait(2)
        assert all(writer.submit(action) for _ in range(128))
        assert not writer.submit(action)
    finally:
        release.set()
        assert not writer.close(wait=True)
        memory.db.close()


def test_missing_database_fails_accepted_action_and_rejects_later_submissions(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.db.close()
    memory.sessions_db.unlink()
    events = queue.Queue()
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    action = SessionSettingUpdate("session", "client", "change")
    assert writer.submit(action)
    assert events.get(timeout=2) == ("session_setting_saved", (action, False))
    assert not writer.submit(action)
    assert not writer.close(wait=True)
    assert not memory.sessions_db.exists()


def test_memory_updates_preserve_order_and_do_not_create_transcript_rows(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    events = queue.Queue()
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    actions = [AutomaticMemoryUpdate("session", "client", i, enabled)
               for i, enabled in enumerate((False, True, False), 1)]
    for action in actions:
        assert writer.submit(action)
    assert writer.close(wait=True)
    assert [events.get_nowait() for _ in actions] == [
        ("memory_setting_saved", (action, True)) for action in actions
    ]
    assert memory.auto_memory_enabled() is False
    assert memory.load_session("session") == []
    memory.set_auto_memory_override(True)
    assert memory.auto_memory_enabled() is True
    memory.set_auto_memory_override(None)
    assert memory.auto_memory_enabled() is False
    memory.db.close()


def test_memory_fact_updates_are_ordered_and_survive_writer_close(tmp_path):
    from klaude_cli.session_actions import MemoryFactUpdate
    from klaude_core.memory import Memory

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.remember("Prefer uv")
    entry = memory.search_facts("Prefer uv")[0]
    results = []
    writer = SessionActionWriter(memory, lambda kind, payload: results.append((kind, payload)))
    edit = MemoryFactUpdate("session", "client", entry.id, "Prefer uv and pytest")
    stale_delete = MemoryFactUpdate("session", "client", entry.id, None)
    assert writer.submit(edit)
    assert writer.submit(stale_delete)
    assert not writer.close(wait=True)  # stale deletion is rejected, not acknowledged as saved
    assert results == [("memory_fact_saved", (edit, True)),
                       ("memory_fact_saved", (stale_delete, False))]
    assert memory.search_facts("Prefer uv and pytest")
    memory.db.close()
