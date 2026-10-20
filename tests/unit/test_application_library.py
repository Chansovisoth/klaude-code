"""The moved Library worker keeps read-only behavior and CLI compatibility."""

from __future__ import annotations

import json
import queue

from klaude_application.background_jobs import OwnedBackgroundJobs as ApplicationJobs
from klaude_application.library_inventory import execute_library, session_inventory
from klaude_application.library_knowledge import source_inventory
from klaude_application.model_capabilities import read_capabilities
from klaude_application.model_catalog import read_inventory
from klaude_cli.background_jobs import OwnedBackgroundJobs as TerminalJobs
from klaude_cli.library_inventory import execute_library as cli_execute_library
from klaude_cli.library_knowledge import source_inventory as cli_source_inventory
from klaude_cli.model_capabilities import read_capabilities as cli_read_capabilities
from klaude_cli.model_settings import read_inventory as cli_read_inventory
from klaude_core.memory import Memory


def test_shared_library_inventory_does_not_publish_private_model_content(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.log_turn("saved", "user", "Public session question",
                        model_content={"private": "hidden-provider-state"})
        assert cli_execute_library is execute_library
        assert session_inventory(memory.sessions_db)["items"][0]["id"] == "saved"
        result = execute_library({"operation": "sessions", "database": str(memory.sessions_db)})
        assert result["items"][0]["title"] == "Public session question"
        assert "hidden-provider-state" not in repr(result)
    finally:
        memory.db.close()


def test_shared_managed_source_inventory_never_opens_a_knowledge_engine(tmp_path):
    root = tmp_path / "docs-sources"
    assert source_inventory(root)["items"] == []
    assert not root.exists()
    item = root / "example"
    item.mkdir(parents=True)
    (item / "manifest.json").write_text(json.dumps({
        "name": "example", "library": "react", "llms_url": "https://example.test/llms.txt",
        "files": ["llms.txt"], "checked_at": "2026-10-18",
    }))
    assert cli_source_inventory is source_inventory
    result = source_inventory(root, "react")
    assert result["items"][0]["library"] == "react"
    assert result["items"][0]["files"] == 1
    assert source_inventory(root, "other")["items"] == []


def test_application_worker_dispatches_library_without_terminal_import(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("saved", "user", "Public request", model_content={"secret": "private"})
    memory.db.close()
    events: queue.Queue[tuple[str, object]] = queue.Queue()
    jobs = ApplicationJobs(lambda kind, payload: events.put((kind, payload)))
    try:
        request = {"kind": "library", "operation": "sessions",
                   "database": str(tmp_path / "sessions.db")}
        assert jobs.worker_module_for_request(request) == "klaude_application.background_worker"
        assert TerminalJobs(lambda *_: None).worker_module_for_request(request) == (
            "klaude_application.background_worker"
        )
        identity = jobs.submit("sessions", request, timeout=10)
        kind, payload = events.get(timeout=12)
        assert kind == "background_result"
        assert payload[1] == identity
        assert payload[3] == ""
        assert payload[2]["items"][0]["title"] == "Public request"
        assert "private" not in repr(payload)
    finally:
        jobs.close(wait=True)
    assert not jobs._active


def test_model_metadata_reads_use_shared_implementations():
    assert cli_read_capabilities is read_capabilities
    assert cli_read_inventory is read_inventory
    jobs = TerminalJobs(lambda *_: None)
    for kind in ("model_capabilities", "model_settings_inventory", "model_settings_test"):
        assert jobs.worker_module_for_request({"kind": kind}) == (
            "klaude_application.background_worker"
        )
