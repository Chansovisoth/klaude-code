import json
import queue
import sqlite3
import time

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.background_worker import execute
from klaude_cli.settings_overview import SettingsOverviewSnapshot
from klaude_core.memory import Memory


def test_overview_snapshot_initial_loading_success_and_age():
    snapshot = SettingsOverviewSnapshot()
    assert snapshot.labels(loading=False, now=100) == ("not loaded", "not loaded")
    assert snapshot.labels(loading=True, now=100) == ("loading…", "loading…")
    snapshot = snapshot.refreshed({"memory_enabled": False, "mcp_enabled": 1, "mcp_total": 2}, 100)
    assert snapshot.labels(loading=False, now=110) == ("off", "1/2 enabled")
    assert snapshot.labels(loading=True, now=140) == (
        "off · cached 40s ago · refreshing…",
        "1/2 enabled · cached 40s ago · refreshing…"
    )


def test_overview_partial_failure_retains_true_snapshot_age():
    snapshot = SettingsOverviewSnapshot().refreshed(
        {"memory_enabled": True, "mcp_enabled": 1, "mcp_total": 3}, 100
    )
    snapshot = snapshot.refreshed({"memory_enabled": False}, 145)
    assert snapshot.memory_loaded_at == 145
    assert snapshot.mcp_loaded_at == 100
    assert snapshot.labels(loading=False, now=150) == (
        "off", "1/3 enabled · cached 50s ago · unavailable"
    )
    failed = snapshot.refreshed(None, 160)
    assert failed.memory_loaded_at == 145
    assert failed.mcp_loaded_at == 100


@pytest.mark.parametrize("enabled,total", [(True, 2), (-1, 2), (3, 2), (1, 100001), (1, "2")])
def test_overview_invalid_worker_counts_never_become_success(enabled, total):
    result = SettingsOverviewSnapshot().refreshed({"mcp_enabled": enabled, "mcp_total": total}, 100)
    assert result.mcp_counts is None
    assert result.mcp_failed
    assert result.labels(loading=False, now=110) == ("unavailable", "unavailable")


def test_overview_worker_returns_only_flag_and_counts_without_execution(tmp_path, monkeypatch):
    from klaude_core.mcp_client import MCPClient

    db = tmp_path / "sessions.db"
    mcp = tmp_path / "mcp.json"
    memory = Memory(tmp_path / "memory.md", db)
    memory.set_auto_memory(False)
    memory.log_turn("session", "user", "private transcript")
    memory.db.close()
    mcp.write_text(json.dumps({"servers": {
        "private-name": {"command": "node", "args": ["private-arg"], "enabled": True},
        "other": {"command": "node", "enabled": False},
    }}))
    before = (db.read_bytes(), mcp.read_bytes())
    monkeypatch.setattr(MCPClient, "discover", lambda *args: pytest.fail("Must not connect"))
    result = execute({"kind": "settings_overview", "sessions_db": str(db), "mcp_file": str(mcp)})
    assert result == {"memory_enabled": False, "mcp_enabled": 1, "mcp_total": 2}
    assert (db.read_bytes(), mcp.read_bytes()) == before
    assert "private" not in json.dumps(result)


def test_overview_missing_storage_is_not_created_and_mcp_can_succeed_independently(tmp_path):
    db, mcp = tmp_path / "missing.db", tmp_path / "missing.json"
    assert execute({"kind": "settings_overview", "sessions_db": str(db), "mcp_file": str(mcp)}) == {
        "memory_enabled": None, "mcp_enabled": 0, "mcp_total": 0,
    }
    assert not db.exists() and not mcp.exists()


def test_overview_rejects_symlinks_and_hides_parse_errors(tmp_path):
    actual = tmp_path / "actual.json"
    actual.write_text("private error detail")
    link = tmp_path / "linked.json"
    link.symlink_to(actual)
    for path in (actual, link):
        result = execute({
            "kind": "settings_overview", "sessions_db": str(path), "mcp_file": str(path)
        })
        assert result == {"memory_enabled": None, "mcp_enabled": None, "mcp_total": None}
        assert "private" not in json.dumps(result)


def test_overview_sqlite_contention_is_bounded_and_does_not_hide_mcp_counts(tmp_path):
    db = tmp_path / "sessions.db"
    memory = Memory(tmp_path / "memory.md", db)
    memory.db.execute("PRAGMA journal_mode=DELETE")
    memory.db.close()
    lock = sqlite3.connect(db)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        start = time.monotonic()
        result = execute({
            "kind": "settings_overview", "sessions_db": str(db),
            "mcp_file": str(tmp_path / "missing.json"),
        })
        assert time.monotonic() - start < 1
        assert result == {"memory_enabled": None, "mcp_enabled": 0, "mcp_total": 0}
    finally:
        lock.rollback()
        lock.close()


def test_real_owned_overview_job_reads_private_inventory_in_background(tmp_path):
    db = tmp_path / "sessions.db"
    memory = Memory(tmp_path / "memory.md", db)
    memory.db.close()
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, payload: events.put(payload))
    try:
        start = time.monotonic()
        identity = jobs.submit("settings-overview", {
            "kind": "settings_overview", "sessions_db": str(db),
            "mcp_file": str(tmp_path / "missing.json"),
        }, timeout=8)
        assert time.monotonic() - start < 0.25
        key, returned, result, error = events.get(timeout=8)
        assert (key, returned, error) == ("settings-overview", identity, "")
        assert result == {"memory_enabled": True, "mcp_enabled": 0, "mcp_total": 0}
    finally:
        jobs.close(wait=True)
    assert not jobs._active


def test_overview_counts_saved_facts_without_returning_contents(tmp_path):
    db, facts, mcp = tmp_path / "sessions.db", tmp_path / "memory.md", tmp_path / "mcp.json"
    memory = Memory(facts, db)
    memory.remember("Prefer a private test value", source="test")
    memory.db.close()
    result = execute({
        "kind": "settings_overview", "sessions_db": str(db),
        "memory_file": str(facts), "mcp_file": str(mcp),
    })
    assert result["memory_count"] == 1
    assert "private test value" not in json.dumps(result)
    assert SettingsOverviewSnapshot().refreshed(result, 100).memory_count == 1
