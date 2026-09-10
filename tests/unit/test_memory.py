import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from klaude_core.memory import (
    Memory,
    auto_memory_candidates,
    explicit_memory_candidate,
    is_sensitive_memory,
)


def test_memory_remember_list_forget_and_dedupe(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert memory.remember("I prefer local-first tools", source="test") is True
    assert memory.remember("I prefer local-first tools", source="test") is False
    assert len(memory.list_facts()) == 1
    entry = memory.search_facts("local-first")[0]
    assert entry.raw.startswith("- [memory:")
    assert "local-first" in entry.fact

    ambiguous = memory.forget("local-first")
    assert ambiguous.removed == 0
    assert ambiguous.matches == [entry]

    assert memory.forget(entry.id) == 1
    assert memory.list_facts() == []


def test_memory_rejects_secret_values(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert is_sensitive_memory("API_KEY=abcd1234secret")
    assert memory.remember("API_KEY=abcd1234secret", source="test") is False
    assert memory.facts() == ""


@pytest.mark.parametrize(
    "text",
    [
        "remember that my API key is sk-proj-example123456",
        "please remember that my token was ghp_example123456789",
        "remember Bearer example.token.value12345",
    ],
)
def test_memory_rejects_natural_language_and_known_secret_formats(tmp_path, text):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert is_sensitive_memory(text)
    assert explicit_memory_candidate(text) is None
    assert memory.remember(text, source="test") is False


def test_memory_files_are_private(tmp_path):
    memory_file = tmp_path / "memory.md"
    sessions_db = tmp_path / "sessions.db"
    memory = Memory(memory_file, sessions_db)
    memory.remember("User prefers local tools", source="test")

    assert sessions_db.stat().st_mode & 0o777 == 0o600
    assert memory_file.stat().st_mode & 0o777 == 0o600
    memory.log_turn("session", "user", "private turn")
    assert (tmp_path / "sessions.db-wal").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "sessions.db-shm").stat().st_mode & 0o777 == 0o600


def test_session_search_and_recent_sessions(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("s1", "user", "I asked about DanTDM yesterday")
    memory.log_turn("s1", "assistant", "We discussed his YouTube channel.")
    memory.log_turn("s2", "user", "React hooks")

    hits = memory.search_sessions("DanTDM")
    assert len(hits) == 1
    assert hits[0]["session_id"] == "s1"

    recent = memory.recent_sessions()
    assert recent[0]["session_id"] == "s2"
    assert recent[1]["session_id"] == "s1"


def test_session_search_ignores_question_scaffolding_and_tolerates_word_suffix_typo(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("past", "user", "Please remembermy favorite fruit is mangosteen")

    hits = memory.search_sessions("what is something I remembered in my other sessions?")

    assert hits
    assert hits[0]["session_id"] == "past"


def test_session_keeps_private_model_context_separate_from_visible_turn(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn(
        "s1",
        "user",
        "Review the attachment",
        model_content="Review the attachment\n\n[attached file]\nprivate contents",
    )

    turn = memory.load_session("s1")[0]
    assert turn["content"] == "Review the attachment"
    assert "private contents" in turn["model_content"]
    assert memory.search_sessions("private contents") == []


def test_session_events_are_ordered_and_cursor_based(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    first = memory.publish_session_event("s1", "client-a", "activity", {"text": "thinking"})
    second = memory.publish_session_event(
        "s1", "client-a", "assistant_delta", {"text": "hello"}, turn_id="turn-a"
    )

    assert second > first
    assert [event["id"] for event in memory.session_events_since("s1", first)] == [second]
    assert memory.latest_session_event_id("s1") == second


def test_session_event_replay_is_bounded_without_deleting_saved_turns(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("s1", "user", "durable transcript")
    for index in range(1_005):
        memory.publish_session_event("s1", "client", "activity", {"text": str(index)})

    removed = memory.prune_session_events("s1", max_events=1_000)

    assert removed == 5
    assert len(memory.session_events_since("s1", 0, limit=2_000)) == 1_000
    assert memory.load_session("s1")[0]["content"] == "durable transcript"


def test_session_worker_lease_is_exclusive_renewable_and_releasable(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert memory.acquire_session_lease("s1", "client-a", "turn-a")
    assert not memory.acquire_session_lease("s1", "client-b", "turn-b")
    assert memory.renew_session_lease("s1", "client-a", "turn-a")
    assert memory.release_session_lease("s1", "client-a", "turn-a")
    assert memory.acquire_session_lease("s1", "client-b", "turn-b")


def test_session_live_schema_migrates_and_tracks_the_shared_turn_start(tmp_path):
    database = tmp_path / "sessions.db"
    legacy = sqlite3.connect(database)
    legacy.execute(
        """CREATE TABLE session_live (
            session_id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL DEFAULT 0,
            owner_client_id TEXT NOT NULL DEFAULT '',
            owner_lease_until REAL NOT NULL DEFAULT 0,
            turn_id TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'idle',
            draft_client_id TEXT NOT NULL DEFAULT '',
            draft TEXT NOT NULL DEFAULT '',
            activity TEXT NOT NULL DEFAULT 'ready',
            partial TEXT NOT NULL DEFAULT '',
            queue_json TEXT NOT NULL DEFAULT '[]',
            updated_at REAL NOT NULL
        )"""
    )
    legacy.commit()
    legacy.close()

    memory = Memory(tmp_path / "memory.md", database)
    assert "turn_started_at" in {
        row[1] for row in memory.db.execute("PRAGMA table_info(session_live)").fetchall()
    }
    assert memory.acquire_session_lease("s1", "client-a", "turn-a")
    live = memory.session_live_state("s1")

    assert live["turn_started_at"] > 0
    assert memory.release_session_lease("s1", "client-a", "turn-a")
    assert memory.session_live_state("s1")["turn_started_at"] == 0


def test_session_live_state_has_monotonic_revisions_and_shared_draft(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    first = memory.update_session_live(
        "s1", draft_client_id="client-a", draft="hel", queue_json=["next"]
    )
    second = memory.update_session_live("s1", draft="hello")

    assert second["revision"] > first["revision"]
    assert second["draft"] == "hello"
    assert second["queue"] == ["next"]


def test_session_clients_keep_independent_drafts_and_queues(tmp_path):
    database = tmp_path / "sessions.db"
    first = Memory(tmp_path / "memory.md", database)
    second = Memory(tmp_path / "memory.md", database)

    first.update_session_client("shared", "client-a", draft="hello", queue=["one"])
    second.update_session_client("shared", "client-b", draft="world", queue=["two"])

    states = {state["client_id"]: state for state in first.session_client_states("shared")}
    assert states["client-a"]["draft"] == "hello"
    assert states["client-a"]["queue"] == ["one"]
    assert states["client-b"]["draft"] == "world"
    assert states["client-b"]["queue"] == ["two"]


def test_concurrent_memory_clients_deduplicate_atomic_writes(tmp_path):
    memory_file = tmp_path / "memory.md"
    database = tmp_path / "sessions.db"
    clients = [Memory(memory_file, database), Memory(memory_file, database)]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda client: client.remember("One durable fact"), clients))

    assert sorted(results) == [False, True]
    assert memory_file.read_text().count("One durable fact") == 1


def test_two_memory_clients_share_atomic_turn_snapshot_and_stream(tmp_path):
    database = tmp_path / "sessions.db"
    owner = Memory(tmp_path / "memory.md", database)
    watcher = Memory(tmp_path / "memory.md", database)

    assert owner.acquire_session_lease("shared", "owner", "turn-1")
    assert not watcher.acquire_session_lease("shared", "watcher", "turn-2")
    event_id = owner.start_session_turn(
        "shared",
        "owner",
        "turn-1",
        "Review this",
        model_content="Review this\n\n[Attached file]\nprivate",
    )
    owner.publish_session_event(
        "shared", "owner", "assistant_delta", {"text": "Working"}, turn_id="turn-1"
    )

    snapshot = watcher.session_snapshot("shared")

    assert snapshot["event_cursor"] > event_id
    assert snapshot["turns"][0]["content"] == "Review this"
    assert "private" in snapshot["turns"][0]["model_content"]
    assert snapshot["live"]["partial"] == "Working"
    assert snapshot["live"]["owner_client_id"] == "owner"
    assert watcher.resumable_sessions()[0]["active"] is True
    assert watcher.recent_sessions()[0]["active"] is True

    owner.log_turn("shared", "assistant", "Working")
    owner.publish_session_event(
        "shared", "owner", "turn_done", {"suffix": "worked"}, turn_id="turn-1"
    )
    assert owner.release_session_lease("shared", "owner", "turn-1")
    assert watcher.resumable_sessions()[0]["active"] is False
    assert watcher.recent_sessions()[0]["active"] is False
    assert watcher.acquire_session_lease("shared", "watcher", "turn-2")


def test_delete_one_session_removes_only_that_session(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("s1", "user", "first")
    memory.log_turn("s1", "assistant", "reply")
    memory.log_turn("s2", "user", "second")

    assert memory.delete_session("s1") == 2

    assert memory.load_session("s1") == []
    assert [session["session_id"] for session in memory.recent_sessions()] == ["s2"]
    assert memory.delete_session("missing") == 0


def test_clear_sessions_removes_all_session_turns(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("s1", "user", "first")
    memory.log_turn("s1", "assistant", "reply")
    memory.log_turn("s2", "user", "second")

    assert memory.session_counts() == {"sessions": 2, "turns": 3}
    assert memory.clear_sessions() == {"sessions": 2, "turns": 3}

    assert memory.recent_sessions() == []
    assert memory.search_sessions("first") == []
    assert memory.clear_sessions() == {"sessions": 0, "turns": 0}


def test_activity_records_replay_without_polluting_dialogue_counts_or_search(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("s1", "user", "Inspect the parser")
    memory.log_turn(
        "s1",
        "system",
        {"event": "activity_update", "label": "explored", "detail": "Read secret-parser.py"},
    )
    memory.log_turn("s1", "assistant", "The parser is sound.")

    assert memory.session_counts() == {"sessions": 1, "turns": 2}
    assert memory.recent_sessions()[0]["turns"] == 2
    assert memory.recent_sessions()[0]["preview"] == "The parser is sound."
    assert memory.search_sessions("secret-parser") == []
    assert memory.session_tail("s1") == [
        {"role": "user", "content": "Inspect the parser"},
        {"role": "assistant", "content": "The parser is sound."},
    ]
    assert memory.delete_session("s1") == 2
    assert memory.load_session("s1") == []


def test_session_names_persist_and_forks_remain_independent(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("original", "user", "A question")
    memory.rename_session("original", "Named conversation")
    memory.fork_session("original", "fork")
    memory.log_turn("fork", "assistant", "Fork response")
    memory.db.close()
    reopened = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    titles = {s["session_id"]: s["title"] for s in reopened.resumable_sessions()}
    assert titles == {"original": "Named conversation", "fork": "Named conversation (fork)"}
    recent_titles = {s["session_id"]: s["title"] for s in reopened.recent_sessions()}
    assert recent_titles == titles
    assert reopened.session_title("original") == "Named conversation"
    assert reopened.session_title("fork") == "Named conversation (fork)"
    assert reopened.session_title("missing") == "Untitled session"
    reopened.log_turn("derived", "user", "  First user message\nwith extra spacing  ")
    assert reopened.session_title("derived") == "First user message with extra spacing"
    assert len(reopened.load_session("original")) == 1
    assert len(reopened.load_session("fork")) == 2
    reopened.delete_session("original")
    assert reopened.db.execute("SELECT session_id FROM session_names").fetchall() == [("fork",)]
    reopened.clear_sessions()
    assert reopened.db.execute("SELECT * FROM session_names").fetchall() == []


def test_auto_memory_toggle_and_candidates(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    saved = memory.auto_remember_turn("I prefer full technology names in environment variables")
    assert saved == ["I prefer full technology names in environment variables"]

    memory.set_auto_memory(False)
    assert memory.auto_memory_enabled() is False
    assert memory.auto_remember_turn("I prefer Python") == []


def test_explicit_memory_parser_skips_questions_and_broad_requests():
    assert explicit_memory_candidate("remember that I prefer uv") == ("I prefer uv", False)
    assert explicit_memory_candidate("do you remember me asking about DanTDM?") is None
    assert explicit_memory_candidate("remember this") == ("this", True)
    assert auto_memory_candidates("remember API_KEY=abcd1234secret") == []


def test_exact_memory_dedupe_does_not_create_duplicates(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert memory.remember("User prefers uv", source="test")
    assert not memory.remember("  User prefers uv.  ", source="test")

    assert len(memory.list_facts()) == 1


def test_substring_collision_does_not_block_distinct_memory(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert memory.remember("User uses Google Drive", source="test")
    assert memory.remember("User uses Go", source="test")

    assert len(memory.list_facts()) == 2


def test_forgetting_one_memory_id_removes_only_that_memory(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.remember("User uses Go", source="test")
    memory.remember("User uses Google Drive", source="test")
    target = next(
        entry for entry in memory.search_facts("User uses") if entry.fact == "User uses Go"
    )

    result = memory.forget(f"memory:{target.id}")

    assert result.removed == 1
    remaining = [entry.fact for entry in memory.search_facts("User uses")]
    assert remaining == ["User uses Google Drive"]


def test_ambiguous_substring_forget_does_not_delete_anything(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.remember("User prefers Python", source="test")
    memory.remember("User prefers Rust", source="test")

    result = memory.forget("prefers")

    assert result.removed == 0
    assert {entry.fact for entry in result.matches} == {
        "User prefers Python",
        "User prefers Rust",
    }
    assert len(memory.list_facts()) == 2


def test_legacy_memory_lines_migrate_without_losing_facts(tmp_path):
    memory_file = tmp_path / "memory.md"
    memory_file.write_text(
        "- 2026-07-30 [manual]: User prefers local-first tools\n"
        "- User likes concise status updates\n"
    )
    memory = Memory(memory_file, tmp_path / "sessions.db")

    facts = memory.list_facts()

    assert len(facts) == 2
    assert all(fact.startswith("- [memory:") for fact in facts)
    assert "User prefers local-first tools" in facts[0]
    assert "User likes concise status updates" in facts[1]
