"""Cross-process crash recovery through the real SQLite session store."""

from __future__ import annotations

import subprocess
import sys
import time

from klaude_core.memory import Memory


def test_killed_worker_is_recovered_by_a_new_process(tmp_path):
    memory_file = tmp_path / "memory.md"
    database = tmp_path / "sessions.db"
    child_code = f"""
import time
from pathlib import Path
from klaude_core.memory import Memory

memory = Memory(Path({str(memory_file)!r}), Path({str(database)!r}))
assert memory.acquire_session_lease("shared", "killed-worker", "turn-1")
memory.start_session_turn("shared", "killed-worker", "turn-1", "Long task")
memory.publish_session_event(
    "shared", "killed-worker", "assistant_delta", {{"text": "Durable partial"}},
    turn_id="turn-1",
)
memory.publish_session_event(
    "shared", "killed-worker", "tool_audit",
    {{"tool": "read_file", "phase": "start", "execution_id": "execution-1"}},
    turn_id="turn-1",
)
memory.update_session_live("shared", owner_lease_until=time.time() + 0.2)
print("READY", flush=True)
time.sleep(60)
"""
    worker = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert worker.stdout is not None
        assert worker.stdout.readline().strip() == "READY"
        worker.kill()
        assert worker.wait(timeout=5) != 0
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)

    time.sleep(0.25)
    observer = Memory(memory_file, database)
    snapshot = observer.session_snapshot("shared")

    assert snapshot["recovered_turn_ids"] == ["turn-1"]
    assert snapshot["live"]["state"] == "interrupted"
    assert snapshot["live"]["owner_client_id"] == ""
    assert any(
        turn["role"] == "assistant" and turn["content"] == "Durable partial"
        for turn in snapshot["turns"]
    )
    events = observer.session_events_since("shared", 0)
    audits = [event["payload"] for event in events if event["kind"] == "tool_audit"]
    assert audits == [
        {"tool": "read_file", "phase": "start", "execution_id": "execution-1"}
    ]
    assert not any(event["kind"] == "activity_update" for event in events)
    assert sum(event["kind"] == "turn_done" for event in events) == 1

    second_process = Memory(memory_file, database)
    second_snapshot = second_process.session_snapshot("shared")
    assert second_snapshot["recovered_turn_ids"] == []
    assert second_snapshot["turns"] == snapshot["turns"]
