"""Library lifecycle, cross-client safety, read-only projections and navigation."""

import json
import queue
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_cli.background_worker import execute
from klaude_cli.library_inventory import (
    knowledge_inventory,
    knowledge_search,
    session_inventory,
    session_preview,
)
from klaude_cli.main import sessions_archive, sessions_restore
from klaude_cli.session_actions import LibrarySessionChange, SessionActionWriter
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.memory import Memory

from .test_cli_commands import _fake_persistent_tui


@pytest.fixture
def memory(tmp_path):
    item = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    item.log_turn("saved", "user", "Discuss widget architecture")
    item.log_turn("saved", "assistant", "Widget public reply", model_content="private-attachment")
    item.rename_session("saved", "Widget design")
    item.publish_session_event("saved", "client", "milestone", {"text": "Checked"})
    item.log_turn("recent", "user", "Recent conversation")
    yield item
    item.db.close()


def test_archive_restore_preserves_content_events_names_and_recall(memory):
    content = memory.load_session("saved", timestamps=True)
    events = memory.session_events_since("saved", 0)
    memory.change_session_archive("saved", "archive")
    assert memory.session_archived("saved")
    assert memory.load_session("saved", timestamps=True) == content
    assert memory.session_events_since("saved", 0) == events
    assert memory.session_title("saved") == "Widget design"
    assert [item["session_id"] for item in memory.recent_sessions()] == ["recent"]
    assert [item["session_id"] for item in memory.resumable_sessions()] == ["recent"]
    assert any(item["session_id"] == "saved" for item in memory.search_sessions("widget"))
    assert memory.session_counts() == {"sessions": 2, "turns": 3}
    memory.change_session_archive("recent", "archive")
    assert memory.last_session_id() is None
    memory.change_session_archive("saved", "restore")
    assert not memory.session_archived("saved")
    assert memory.last_session_id() == "saved"
    assert memory.load_session("saved", timestamps=True) == content


def test_archive_and_worker_lease_exclude_each_other_across_clients(memory):
    client = memory.open_session_io()
    try:
        assert client.acquire_session_lease("saved", "worker", "turn")
        with pytest.raises(ValueError, match="active worker"):
            memory.change_session_archive("saved", "archive")
        assert not memory.session_archived("saved")
        client.release_session_lease("saved", "worker", "turn")
        memory.change_session_archive("saved", "archive")
        assert not client.acquire_session_lease("saved", "worker", "next")
        memory.change_session_archive("saved", "restore")
        assert client.acquire_session_lease("saved", "worker", "next")
    finally:
        client.db.close()


def test_stale_confirmation_cannot_delete_restored_or_active_session(memory):
    memory.change_session_archive("saved", "archive")
    client = memory.open_session_io()
    try:
        client.change_session_archive("saved", "restore")
        with pytest.raises(ValueError, match="state changed"):
            memory.change_session_archive("saved", "delete")
        assert memory.load_session("saved")
        memory.change_session_archive("saved", "archive")
        # Defensive against an old client which does not know archive semantics.
        client.update_session_live("saved", state="idle")
        client.db.execute(
            "UPDATE session_live SET owner_client_id='legacy', "
            "owner_lease_until=? WHERE session_id='saved'",
            (time.time() + 30,),
        )
        client.db.commit()
        with pytest.raises(ValueError, match="active worker"):
            memory.change_session_archive("saved", "delete")
    finally:
        client.db.close()


def test_permanent_delete_and_legacy_clear_remove_archive_metadata_only(memory):
    memory.remember("Prefer concise progress updates")
    facts = memory.facts()
    memory.change_session_archive("saved", "archive")
    memory.change_session_archive("saved", "delete")
    assert not memory.load_session("saved")
    assert not memory.session_events_since("saved", 0)
    assert not memory.session_archived("saved")
    assert memory.facts() == facts
    with pytest.raises(ValueError, match="no longer exists"):
        memory.change_session_archive("saved", "restore")
    memory.change_session_archive("recent", "archive")
    memory.clear_sessions()
    assert not memory.session_archived("recent")


def test_inventory_search_paging_and_preview_never_expose_model_content(memory):
    before = memory.db.total_changes
    for index in range(105):
        memory.log_turn(f"bulk-{index:03}", "user", f"Other conversation {index}")
    before = memory.db.total_changes
    data = session_inventory(memory.sessions_db)
    assert len(data["items"]) == 100 and data["more"]
    second = session_inventory(memory.sessions_db, offset=100)
    assert len(second["items"]) == 7 and not second["more"]
    assert not {item["id"] for item in data["items"]} & {item["id"] for item in second["items"]}
    assert session_inventory(memory.sessions_db, query="Widget design")["items"][0]["id"] == "saved"
    assert session_inventory(memory.sessions_db, query="public reply")["items"][0]["id"] == "saved"
    assert not session_inventory(memory.sessions_db, query="private-attachment")["items"]
    assert not session_inventory(memory.sessions_db, query="% OR 1=1")["items"]
    preview = session_preview(memory.sessions_db, "saved")
    assert "Widget public reply" in str(preview) and "private-attachment" not in str(preview)
    assert memory.db.total_changes == before
    memory.change_session_archive("saved", "archive")
    assert not session_inventory(memory.sessions_db, query="Widget")["items"]
    assert session_inventory(memory.sessions_db, archived=True, query="Widget")["items"]


def test_readonly_empty_and_legacy_stores_do_not_initialize_or_migrate(tmp_path):
    missing = tmp_path / "missing.db"
    assert session_inventory(missing)["items"] == []
    assert not missing.exists()
    root = tmp_path / "knowledge.lance"
    assert knowledge_inventory(root)["items"] == [] and not root.exists()
    root.mkdir()
    (root / "legacy.lance").mkdir()
    assert knowledge_inventory(root)["items"] == [{"id": "legacy", "sources": None, "chunks": None}]
    assert not (root / "fts.db").exists()
    db = sqlite3.connect(tmp_path / "old.db")
    db.execute("CREATE TABLE turns(session_id TEXT, ts REAL, role TEXT, content TEXT)")
    db.execute("INSERT INTO turns VALUES ('old',1,'user','legacy hello')")
    db.commit()
    assert session_inventory(tmp_path / "old.db")["items"][0]["id"] == "old"
    assert not session_inventory(tmp_path / "old.db", archived=True)["items"]
    assert {row[0] for row in db.execute("SELECT name FROM sqlite_master")} == {"turns"}
    db.close()
    (tmp_path / "link.db").symlink_to(tmp_path / "old.db")
    with pytest.raises(ValueError):
        session_inventory(tmp_path / "link.db")


def test_knowledge_projection_only_searches_active_enabled_sources(tmp_path):
    from klaude_knowledge.store import KnowledgeStore

    root = tmp_path / "knowledge.lance"
    store = KnowledgeStore(root)
    db = store.fts
    for version, owner, source, text, active in (
        ("v1", "docs:one", "guide", "Widget source currently active", True),
        ("v0", "docs:one", "guide", "Widget obsolete text", False),
        ("vs", "skill:hidden", "skill", "Widget disabled skill", True),
    ):
        db.execute(
            "INSERT INTO source_versions VALUES (?, 'widgets', ?, ?, '', ?, 1, '', 1, 1, NULL)",
            (version, owner, source, "active" if active else "retired"),
        )
        db.execute(
            "INSERT INTO chunks_v2 VALUES (?, 'widgets', ?, ?, ?, ?)",
            (version, owner, source, version, text),
        )
        if active:
            db.execute(
                "INSERT INTO active_sources VALUES ('widgets', ?, ?, ?)", (owner, source, version)
            )
    db.execute("INSERT INTO disabled_skills VALUES ('hidden')")
    db.execute("INSERT INTO chunks VALUES ('legacy', 'old', 'legacy-url', 'Widget legacy text')")
    db.commit()
    store._register_legacy_active_sources()
    db.commit()
    before = db.total_changes
    inventory = knowledge_inventory(root)
    assert inventory["items"] == [
        {"id": "old", "sources": 1, "chunks": 1},
        {"id": "widgets", "sources": 1, "chunks": 1},
    ]
    result = knowledge_search(root, "widgets", "Widget")
    assert len(result["hits"]) == 1 and "currently active" in str(result)
    assert "obsolete" not in str(result) and "disabled skill" not in str(result)
    assert "legacy text" in str(knowledge_search(root, "old", "Widget"))
    assert db.total_changes == before
    db.close()


def test_action_lane_orders_archive_restore_and_protects_current_session(memory):
    events = queue.Queue()
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    changes = [
        LibrarySessionChange("recent", "a", "saved", "archive"),
        LibrarySessionChange("recent", "b", "saved", "restore"),
        LibrarySessionChange("recent", "c", "recent", "archive"),
    ]
    for change in changes:
        assert writer.submit(change)
    assert writer.close(wait=True)
    results = [events.get_nowait() for _ in changes]
    assert results[:2] == [("library_session_saved", (change, "")) for change in changes[:2]]
    assert "Open another session" in results[2][1][1]
    assert not memory.session_archived("saved") and not memory.session_archived("recent")


def library_host(memory):
    host = _fake_persistent_tui()
    host.memory = memory
    calls = []
    host._background_jobs = SimpleNamespace(
        submit=lambda key, request, **kwargs: (
            calls.append((key, request, kwargs)) or str(len(calls))
        ),
        cancel=lambda _key: None,
        current=lambda *_args: True,
    )
    host._library.open("sessions")
    return host, calls


def accept_latest(host, calls):
    request = calls[-1][1]
    identity = host._library.pending[0]
    host._library.accept(identity, execute(request), "")


def act(host, kind, target=""):
    host._apply_panel_action(PanelAction("library-" + kind, target))


def test_workspace_preserves_filter_focus_draft_and_confirmation_default(memory):
    host, calls = library_host(memory)
    host._panel_composer_draft = ("unsent project draft", [])
    accept_latest(host, calls)
    host._panel.filter("Widget")
    host._panel.picker.focus("record:saved")
    host._apply_picker_state()
    act(host, "record", "saved")
    act(host, "back", "sessions")
    assert host._panel.picker.query == "widget"
    assert host._panel.picker.selected_id == "record:saved"
    act(host, "back", "home")
    assert host._panel.picker.selected_id == "sessions"
    assert [row.label for row in host._panel.page.rows[:6]] == [
        "Sessions",
        "Knowledge",
        "Documents",
        "Research",
        "Media",
        "Archive",
    ]
    act(host, "view", "documents")
    assert "Import document" in str(host._panel.page)
    host._cancel_choice()
    act(host, "close")
    assert host.input.text == "unsent project draft" and host._choice_kind is None
    memory.change_session_archive("saved", "archive")
    host._library.open("archive")
    accept_latest(host, calls)
    act(host, "record", "saved")
    act(host, "confirm")
    assert host._panel.picker.selected_id == "back"
    host._cancel_choice()
    assert host._library.view == "detail"


def test_settings_library_link_returns_to_its_row_and_preserves_chat_entry(memory):
    host, _calls = library_host(memory)
    host._panel_composer_draft = ("unsent project draft", [])
    host._begin_choice("settings", host._settings_categories(), "library")
    labels = [row.label for row in host._panel.page.rows]
    assert labels[labels.index("Memory") + 1] == "Library"
    host._accept_choice()
    assert host._choice_kind == "library home"
    assert [row.label for row in host._panel.page.rows[:6]] == [
        "Sessions", "Knowledge", "Documents", "Research", "Media", "Archive",
    ]
    act(host, "view", "documents")
    host._cancel_choice()
    assert host._choice_kind == "library home"
    assert host._panel.page.rows[-1].label == "Back"
    host._cancel_choice()
    assert host._choice_kind == "settings"
    assert host._panel.picker.selected_id == "category:library"
    host._cancel_choice()
    assert host.input.text == "unsent project draft"
    host._library.open()
    assert host._panel.page.rows[-1].label == "Close"
    act(host, "close")
    assert host._choice_kind is None


def test_stale_reads_errors_and_navigation_never_publish_wrong_store(memory):
    host, calls = library_host(memory)
    identity = host._library.pending[0]
    act(host, "view", "knowledge")
    host._library.accept(identity, {"items": [{"id": "wrong"}]}, "")
    assert "wrong" not in str(host._panel.page)
    host._library.accept(host._library.pending[0], None, "timeout")
    assert "Unavailable" in str(host._panel.page)
    act(host, "reload")
    accept_latest(host, calls)
    assert host._library.error == ""
    act(host, "view", "sessions")
    accept_latest(host, calls)
    stamp = host._library.cache[host._library.key()][1]
    act(host, "reload")
    host._library.accept(host._library.pending[0], None, "timeout")
    assert host._library.cache[host._library.key()][1] == stamp
    assert "Widget design" in str(host._panel.page)
    act(host, "reload")
    identity = host._library.pending[0]
    host.session_id = "different"
    host._library.accept(identity, {"items": []}, "")
    assert "Widget design" in str(host._panel.page)
    host._library.leave()
    assert host._library.pending is None


@pytest.mark.parametrize("width", [40, 70, 120])
def test_library_wrapped_pages_fit_terminal_width(memory, width):
    from prompt_toolkit.utils import get_cwidth

    host, calls = library_host(memory)
    accept_latest(host, calls)
    memory.rename_session("saved", "Unicode 設計 " + "very long project title " * 5)
    act(host, "reload")
    accept_latest(host, calls)
    page = host._panel.page
    body = render_body(PanelState(page), width)
    assert all(get_cwidth("".join(text for _, text in line)) <= width for line in body.lines)


def test_archive_cli_uses_shared_lifecycle_and_failure_exit(memory, monkeypatch, capsys):
    import klaude_cli.main as main

    # Separate connections match CLI ownership; do not close the test's connection.
    monkeypatch.setattr(main, "_memory_store", memory.open_session_io)
    sessions_archive("saved")
    assert memory.session_archived("saved")
    sessions_restore("saved")
    assert not memory.session_archived("saved")
    with pytest.raises(main.typer.Exit) as error:
        sessions_restore("missing")
    assert error.value.exit_code == 1
    assert "content retained" in capsys.readouterr().out


def test_worker_projection_does_not_change_database(memory):
    schema = list(memory.db.execute("SELECT sql FROM sqlite_master ORDER BY name"))
    result = execute(
        {"kind": "library", "operation": "sessions", "database": str(memory.sessions_db)}
    )
    assert "private-attachment" not in json.dumps(result)
    assert list(memory.db.execute("SELECT sql FROM sqlite_master ORDER BY name")) == schema
    assert not (Path(memory.sessions_db).parent / "knowledge.lance").exists()


def test_long_unicode_previews_and_structured_attachments_remain_bounded(memory):
    memory.log_turn("unicode", "user", "設計 " * 2000)
    memory.log_turn("structured", "user", [{"attachment": "sensitive-path" * 2000}])
    items = {item["id"]: item for item in session_inventory(memory.sessions_db)["items"]}
    assert items["unicode"]["title"].startswith("設計")
    assert len(items["unicode"]["title"]) <= 160
    assert (
        session_preview(memory.sessions_db, "structured")["turns"][0]["text"]
        == "[Structured content]"
    )
    assert not session_inventory(memory.sessions_db, query="sensitive-path")["items"]
    assert len(session_preview(memory.sessions_db, "unicode")["turns"][0]["text"]) <= 800


def test_loading_footer_clears_when_owned_result_arrives(memory):
    host, calls = library_host(memory)
    assert "Loading Library" in str(host._panel_feedback)
    accept_latest(host, calls)
    assert host._panel_feedback is None


def test_search_editor_cancel_and_errors_preserve_private_input_and_parent(memory):
    host, calls = library_host(memory)
    accept_latest(host, calls)
    messages = list(host.agent.messages)
    act(host, "search")
    assert host._settings_input_is_single_line()
    host._answer_settings_input("x" * 201)
    assert host._settings_input_request is not None
    assert "1–200" in host.status_error
    host._answer_settings_input(None)
    assert host._library.view == "sessions" and host.input.text == ""
    assert host.agent.messages == messages


def test_mutation_acknowledgement_does_not_steal_new_navigation(memory):
    host, calls = library_host(memory)
    accept_latest(host, calls)
    change = LibrarySessionChange(host.session_id, "change", "saved", "archive")
    host._library.changes[change.identity] = change
    act(host, "view", "media")
    host._library.saved(change, "")
    assert host._library.view == "media"
    assert "Session archived" in str(host._panel_feedback)


def test_storage_failure_is_unconfirmed_and_never_retried_blindly(memory, monkeypatch):
    calls = []

    def failed(*args):
        calls.append(args)
        raise sqlite3.OperationalError("private diagnostic")

    monkeypatch.setattr(Memory, "change_session_archive", failed)
    events = queue.Queue()
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    change = LibrarySessionChange("recent", "change", "saved", "archive")
    assert writer.submit(change)
    assert not writer.close(wait=True)
    kind, (returned, error) = events.get_nowait()
    assert kind == "library_session_saved" and returned == change
    assert "unconfirmed" in error and "private diagnostic" not in error
    assert len(calls) == 1 and events.empty()
    assert not memory.session_archived("saved")


def test_idle_client_of_externally_archived_session_does_not_watch_phantom_worker(memory):
    host, _calls = library_host(memory)
    act(host, "back", "home")
    act(host, "close")
    memory.log_turn(host.session_id, "user", "Older public turn")
    memory.change_session_archive(host.session_id, "archive")
    host.pending.append("Inspect the project after restore")
    host._start_next()
    assert not host.running and not host._watching_remote and not host.pending
    assert host.input.text == "Inspect the project after restore"
    assert "this prompt was not run" in host.output.text


def test_empty_later_page_keeps_previous_navigation_and_truthful_count(memory):
    host, calls = library_host(memory)
    accept_latest(host, calls)
    host._library.offset["sessions"] = 100
    host._library.load(force=True)
    accept_latest(host, calls)
    page = host._panel.page
    assert "This page is empty" in str(page) and "No records on this page" in str(page)
    assert any(row.id == "previous" for row in page.rows)
    assert "0–100" not in str(page)
    assert "SPACE toggle" not in str(host._panel_footer_fragments())
