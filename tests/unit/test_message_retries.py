"""Same-session regenerations retain public responses and fenced admissions."""

import json
import threading

import pytest
from klaude_application import HeadlessApplication
from klaude_application.sessions import SessionDeleteChange
from klaude_core import AgentEvent
from klaude_core.session_runtime import capture
from klaude_tools.toolkit import Workspace
from klaude_webhost.host import LocalWebHost

from tests.unit.test_webhost import _app


def fixture_app(tmp_path):
    app = _app(tmp_path)
    app.agent.workdir = tmp_path
    app.agent.workspace = Workspace(tmp_path)
    app.turns.bind_workspace(app.session_id, str(tmp_path), expected_revision=0)
    app.memory.log_turn(app.session_id, "user", "Original question")
    app.memory.log_turn(app.session_id, "assistant", "Original response")
    return app, int(app.snapshot()["messages"][-1]["id"].split(":")[1])


def test_repeated_retry_groups_survive_new_application_and_deduplicate_requests(tmp_path):
    app, source = fixture_app(tmp_path)
    session = app.session_id
    first = app.retry_message(source, request_id="retry-one", controller_id="browser")
    assert first.finished.wait(5)
    assert first.state == "completed"
    replacement = int(app.snapshot()["messages"][-1]["id"].split(":")[1])
    second = app.retry_message(replacement, request_id="retry-two", controller_id="browser")
    assert second.finished.wait(5)
    messages = app.snapshot()["messages"]
    assert app.session_id == session
    assert [m["role"] for m in messages] == ["user", "assistant", "assistant", "assistant"]
    assert [m["previous_response"] for m in messages[1:]] == [True, True, False]
    assert {m["retry_root"] for m in messages[1:]} == {f"stored:{source}"}
    assert messages[1]["content"] == "Original response"
    assert app.memory.db.execute("SELECT COUNT(DISTINCT session_id) FROM turns").fetchone()[0] == 1

    reopened = HeadlessApplication(app.agent, app.memory, session)
    assert reopened.snapshot()["messages"] == messages
    replay = reopened.retry_message(replacement, request_id="retry-two", controller_id="other")
    assert replay.detached and replay.finished.is_set()
    assert replay.turn_id == second.turn_id
    assert reopened.snapshot()["messages"] == messages
    with pytest.raises(ValueError, match="different input"):
        reopened.retry_message(source, request_id="retry-two", controller_id="other")
    target, _ = app.branch_message(int(messages[-1]["id"].split(":")[1]))
    assert target != session
    branched = app.snapshot()["messages"]
    assert [m["content"] for m in branched] == [m["content"] for m in messages]
    assert [m["previous_response"] for m in branched[1:]] == [True, True, False]
    assert {m["retry_root"] for m in branched[1:]} == {branched[1]["id"]}


def test_retry_failure_and_cancellation_keep_original_and_partial(tmp_path):
    app, source = fixture_app(tmp_path)

    def fail(_text, scope=None):
        yield AgentEvent("error", {"message": "Fixture failure"})

    app.agent.run = fail
    failed = app.retry_message(source, request_id="retry-failed", controller_id="browser")
    assert failed.finished.wait(5)
    assert failed.state == "failed"
    assert app.snapshot()["messages"][-1]["content"] == "Original response"
    assert app.snapshot()["messages"][-1]["previous_response"] is True

    waiting = threading.Event()
    release = threading.Event()

    def partial(_text, scope=None):
        yield AgentEvent("text_delta", {"content": "Partial replacement"})
        waiting.set()
        release.wait(5)

    app.agent.run = partial
    cancelled = app.retry_message(source, request_id="retry-cancelled", controller_id="browser")
    try:
        assert waiting.wait(5)
        cancelled.cancel()
    finally:
        release.set()
    assert cancelled.finished.wait(5)
    assert cancelled.state == "cancelled"
    messages = app.snapshot()["messages"]
    assert messages[1]["content"] == "Original response"
    assert messages[-1]["content"] == "Partial replacement"
    assert messages[-1]["retry_root"] == f"stored:{source}"
    assert messages[-1]["previous_response"] is False


def test_retry_rechecks_queue_and_controller_before_admission(tmp_path):
    app, source = fixture_app(tmp_path)
    with app.memory._db_lock, app.memory.db:
        app.memory.db.execute(
            "INSERT INTO application_control VALUES (?,?,1,0)", (app.session_id, app.controller_id)
        )
    epoch = app.take_control("browser", expected_epoch=1)
    app.take_control("other", expected_epoch=epoch)
    with pytest.raises(ValueError, match="control changed"):
        app.retry_message(
            source, request_id="stale-retry", controller_id="browser", control_epoch=epoch
        )
    assert (
        app.memory.db.execute("SELECT COUNT(*) FROM application_message_retries").fetchone()[0] == 0
    )
    app.enqueue("Later", request_id="queued")
    with pytest.raises(RuntimeError, match="queued work"):
        app.retry_message(source, request_id="queued-retry", controller_id="other")
    assert len(app.snapshot()["messages"]) == 2
    with pytest.raises(ValueError, match="unavailable"):
        app.retry_message(source - 1, request_id="user-retry", controller_id="other")


def test_retry_reuses_private_prepared_input_without_public_leak(tmp_path):
    app, source = fixture_app(tmp_path)
    prepared = {
        "kind": "chat_image_input",
        "version": 1,
        "request": "Original question",
        "content": "PRIVATE attachment content",
        "image_inputs": [],
    }
    with app.memory._db_lock, app.memory.db:
        app.memory.db.execute(
            "UPDATE turns SET model_content=? WHERE rowid=?", (json.dumps(prepared), source - 1)
        )
    seen = []

    def run(text, scope=None):
        seen.append(text)
        yield AgentEvent("text", {"content": "Replacement"})

    app.agent.run = run
    retry = app.retry_message(source, request_id="private-retry", controller_id="browser")
    assert retry.finished.wait(5)
    assert seen == [prepared]
    assert "PRIVATE" not in json.dumps(app.snapshot())
    assert app.memory.load_session(app.session_id)[-2]["model_content"] == prepared


def test_expired_retry_preserves_its_group_and_requires_reconciliation(tmp_path):
    app, source = fixture_app(tmp_path)
    admitted = app.turns.admit(
        request_id="expired-retry",
        session_id=app.session_id,
        turn_id="retry-turn",
        worker_id="expired-worker",
        text="Original question",
        scope="standard",
        runtime=capture(app.agent),
        input_key=f"retry:{source}",
        retry_source_row_id=source,
    )
    with app.memory._db_lock, app.memory.db:
        app.memory.db.execute(
            "UPDATE session_live SET partial='Saved partial',owner_lease_until=0 "
            "WHERE session_id=?",
            (app.session_id,),
        )
    with pytest.raises(RuntimeError, match="outcome unknown"):
        app.turns.admit(
            request_id="other-request",
            session_id=app.session_id,
            turn_id="other-turn",
            worker_id="worker",
            text="Other",
            scope="standard",
            runtime=capture(app.agent),
        )
    snapshot = app.snapshot()
    assert snapshot["state"] == "interrupted"
    assert snapshot["messages"][-1]["content"] == "Saved partial"
    assert snapshot["messages"][-1]["retry_root"] == f"stored:{source}"
    assert app.turns.receipt(admitted.request_id).state == "interrupted"


def test_host_keeps_older_retry_source_in_bounded_projection(tmp_path):
    app, source = fixture_app(tmp_path)
    for index in range(510):
        app.memory.log_turn(app.session_id, "user", f"Later question {index}")
        app.memory.log_turn(app.session_id, "assistant", f"Later answer {index}")
    app.agent.workspace.write_enabled = True
    host = LocalWebHost(app)
    host._edits_activated = True
    try:
        retry = app.retry_message(source, request_id="old-retry", controller_id="browser")
        assert retry.finished.wait(5)
        snapshot = host.public_snapshot()
        originals = [m for m in snapshot["messages"] if m["id"] == f"stored:{source}"]
        assert len(originals) == 1
        assert originals[0]["content"] == "Original response"
        assert originals[0]["previous_response"] is True
        assert snapshot["messages"][-1]["retry_root"] == f"stored:{source}"
        assert app.agent.workspace.write_enabled and host._edits_activated
    finally:
        host.http.server_close()


def test_session_deletion_clears_retry_metadata(tmp_path):
    app, source = fixture_app(tmp_path)
    retry = app.retry_message(source, request_id="delete-retry", controller_id="browser")
    assert retry.finished.wait(5)
    app.sessions.delete(SessionDeleteChange(app.session_id, expected_total_turns=4))
    assert (
        app.memory.db.execute("SELECT COUNT(*) FROM application_message_retries").fetchone()[0] == 0
    )
