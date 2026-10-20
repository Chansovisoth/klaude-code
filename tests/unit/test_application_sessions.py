"""Shared session discovery keeps terminal behavior and private state separate."""

from __future__ import annotations

import pytest
from klaude_application.sessions import (
    SessionArchiveChange,
    SessionDeleteChange,
    SessionDirectory,
    SessionForkChange,
    SessionMessageForkChange,
    SessionRenameChange,
    SessionsClearChange,
)
from klaude_core.memory import Memory


def test_session_directory_projects_public_history_and_bounds_queries(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("session-a", "user", "Find the project notes")
        memory.log_turn(
            "session-a",
            "assistant",
            "Project notes are ready",
            model_content={"private_provider_token": "never-publish-this"},
        )
        directory = SessionDirectory(memory)

        summaries = directory.recent()
        assert len(summaries) == 1
        assert summaries[0].session_id == "session-a"
        assert summaries[0].turns == 2
        assert summaries[0].preview == "Project notes are ready"
        assert summaries[0].title == "Find the project notes"
        matches = directory.search("project notes")
        assert matches and {item.role for item in matches} <= {"user", "assistant"}
        assert not directory.search("never-publish-this")
        assert "never-publish-this" not in repr((summaries, matches))

        with pytest.raises(ValueError, match="page size"):
            directory.recent(101)
        with pytest.raises(ValueError, match="page size"):
            directory.search("project", 0)
        with pytest.raises(ValueError, match="query"):
            directory.search("x" * 501)
    finally:
        memory.db.close()


def test_public_message_is_exact_bounded_and_never_reads_private_content(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("first", "assistant", "Public reply" + "x" * 20_000,
                        model_content={"secret": "private-canary"})
        row_id = memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
        memory.log_turn("first", "tool", "private-tool-output")
        tool_id = memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
        directory = SessionDirectory(memory)
        message = directory.public_message("first", row_id)
        assert message is not None and message.id == f"stored:{row_id}"
        assert message.role == "assistant" and message.content.startswith("Public reply")
        assert len(message.content) == 16_000
        assert "private-canary" not in repr(message)
        assert directory.public_message("second", row_id) is None
        assert directory.public_message("first", tool_id) is None
        assert directory.public_message("first", tool_id + 1) is None
        for invalid in (0, -1, True, 2**63):
            with pytest.raises(ValueError, match="message ID"):
                directory.public_message("first", invalid)
    finally:
        memory.db.close()


def test_terminal_session_views_use_shared_directory(tmp_path):
    from klaude_cli.main import (
        _format_recent_sessions,
        _format_session_hits,
        _recent_session_records,
        _session_search_records,
    )

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("session-b", "user", "Remember the bridge")
        recent = _recent_session_records(memory)
        matches = _session_search_records(memory, "bridge")
        assert "session-b" in _format_recent_sessions(recent)
        assert "Remember the bridge" in _format_session_hits(matches)
        assert recent[0]["session_id"] == matches[0]["session_id"]
    finally:
        memory.db.close()


def test_session_archive_service_preserves_history_and_respects_active_lease(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    client = memory.open_session_io()
    try:
        memory.log_turn("session-a", "user", "Keep this conversation")
        directory = SessionDirectory(memory)
        assert client.acquire_session_lease("session-a", "worker", "turn")
        with pytest.raises(ValueError, match="active worker"):
            directory.change_archive(SessionArchiveChange("session-a", "archive"))
        client.release_session_lease("session-a", "worker", "turn")

        receipt = directory.change_archive(SessionArchiveChange("session-a", "archive"))
        assert receipt.state == "archived"
        assert memory.load_session("session-a")
        assert not directory.recent()

        receipt = directory.change_archive(SessionArchiveChange("session-a", "restore"))
        assert receipt.state == "active"
        assert directory.recent()[0].session_id == "session-a"
        with pytest.raises(ValueError, match="Invalid session archive action"):
            SessionArchiveChange.from_values("session-a", "clear")
    finally:
        client.db.close()
        memory.db.close()


def test_session_rename_and_fork_service_reuse_memory_guards(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("original", "user", "Keep this history")
        directory = SessionDirectory(memory)
        assert directory.rename(SessionRenameChange("original", "  New   name  ")) == "New name"
        assert memory.session_title("original") == "New name"
        assert directory.fork(SessionForkChange("original", "copy")) == "copy"
        assert memory.load_session("copy") == memory.load_session("original")
        assert memory.session_title("copy") == "New name (fork)"
        with pytest.raises(ValueError, match="already exists"):
            directory.fork(SessionForkChange("original", "copy"))
    finally:
        memory.db.close()


def test_message_branch_exact_boundary_and_retry_preserve_original(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("source", "user", "First question")
        memory.log_turn("source", "assistant", "First answer", model_content={"private": "one"})
        first = memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
        memory.log_turn("source", "user", "Second question")
        memory.log_turn("source", "assistant", "Second answer", model_content={"private": "two"})
        second = memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
        original = memory.load_session("source")
        directory = SessionDirectory(memory)
        assert directory.fork_message(SessionMessageForkChange("source", "branch", first)) is None
        assert memory.load_session("branch") == original[:2]
        prompt = directory.fork_message(SessionMessageForkChange("source", "retry", second, True))
        assert prompt == "Second question"
        assert memory.load_session("retry") == original[:2]
        assert (
            directory.fork_message(SessionMessageForkChange("source", "first-retry", first, True))
            == "First question"
        )
        assert memory.load_session("first-retry") == []
        assert memory.load_session("source") == original
        memory.log_turn("foreign", "assistant", "Other workspace")
        foreign = memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
        with pytest.raises(ValueError, match="not found"):
            directory.fork_message(SessionMessageForkChange("source", "invalid", foreign))
        assert memory.load_session("invalid") == []
        with pytest.raises(ValueError, match="boundary"):
            directory.fork_message(SessionMessageForkChange("source", "invalid", 2**63))
        client = memory.open_session_io()
        try:
            assert client.acquire_session_lease("source", "owner", "turn")
            with pytest.raises(ValueError, match="unresolved"):
                directory.fork_message(SessionMessageForkChange("source", "busy", first))
        finally:
            client.db.close()
    finally:
        memory.db.close()


def test_session_delete_and_clear_service_respect_unresolved_work(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    client = memory.open_session_io()
    try:
        memory.log_turn("first", "user", "Keep first")
        memory.log_turn("second", "user", "Keep second")
        directory = SessionDirectory(memory)
        assert client.acquire_session_lease("first", "worker", "turn")
        with pytest.raises(ValueError, match="unresolved work"):
            directory.delete(SessionDeleteChange("first"))
        with pytest.raises(ValueError, match="unresolved work"):
            directory.clear()
        assert memory.session_counts() == {"sessions": 2, "turns": 2}
        client.release_session_lease("first", "worker", "turn")

        receipt = directory.delete(SessionDeleteChange("first"))
        assert receipt.session_id == "first" and receipt.removed_turns == 1
        receipt_all = directory.clear()
        assert receipt_all.removed_sessions == 1 and receipt_all.removed_turns == 1
        assert memory.session_counts() == {"sessions": 0, "turns": 0}
    finally:
        client.db.close()
        memory.db.close()


def test_reviewed_session_deletion_rejects_cross_client_changes(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    client = memory.open_session_io()
    try:
        memory.log_turn("first", "user", "Original")
        directory = SessionDirectory(memory)
        reviewed_turns = len(memory.load_session("first"))
        client.log_turn("first", "assistant", "Arrived after review")
        with pytest.raises(ValueError, match="changed; review deletion again"):
            directory.delete(SessionDeleteChange("first", reviewed_turns))
        assert len(memory.load_session("first")) == 2

        reviewed = memory.session_counts()
        client.log_turn("second", "user", "Another session")
        with pytest.raises(ValueError, match="history changed"):
            directory.clear(SessionsClearChange(reviewed["sessions"], reviewed["turns"]))
        assert memory.session_counts() == {"sessions": 2, "turns": 3}
    finally:
        client.db.close()
        memory.db.close()


def test_shared_markdown_export_excludes_private_model_content_and_matches_cli(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace

    from klaude_cli.main import _export_session

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("export", "user", "Public question")
        memory.log_turn(
            "export",
            "assistant",
            "Public answer",
            model_content={"private_provider_token": "never-publish-this"},
        )
        memory.log_turn(
            "export",
            "system",
            {
                "event": "activity_update",
                "label": "Explored",
                "detail": "Read notes",
                "elapsed_seconds": 3,
            },
        )
        memory.log_turn("export", "system", "private runtime continuation")
        memory.log_turn("export", "system", {"event": "tool_audit", "secret": "internal"})
        projected = memory.public_session_records("export")
        assert len(projected) == 3
        assert all("model_content" not in row for row in projected)
        monkeypatch.setattr(
            memory,
            "load_session",
            lambda *_args, **_kwargs: pytest.fail("export loaded private model continuation"),
        )
        expected = "".join(SessionDirectory(memory).markdown_chunks("export"))
        path = _export_session(
            memory,
            "export",
            SimpleNamespace(workdir=tmp_path),
            SimpleNamespace(data_dir=tmp_path),
            "public.md",
        )
        assert path.read_text() == expected
        assert "Public answer" in expected and "[explored] (3s) Read notes" in expected
        assert "never-publish-this" not in expected
        assert "private runtime continuation" not in expected and "internal" not in expected
        with pytest.raises(FileExistsError):
            _export_session(
                memory,
                "export",
                SimpleNamespace(workdir=tmp_path),
                SimpleNamespace(data_dir=tmp_path),
                "public.md",
            )
    finally:
        memory.db.close()
