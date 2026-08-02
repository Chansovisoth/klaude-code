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
        entry for entry in memory.search_facts("User uses")
        if entry.fact == "User uses Go"
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
