"""Durable application admission and stale-worker safety across SQLite owners."""

from __future__ import annotations

import asyncio
import multiprocessing
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import pytest
from klaude_application import HeadlessApplication, SessionTurn, compose_agent
from klaude_application.coordination import CursorExpired, DurableTurns, LeaseLost
from klaude_application.lease import SessionLeaseKeeper
from klaude_core import PermissionGate, Tool
from klaude_core.memory import Memory, SessionLeaseLost
from klaude_core.model_runtime import ModelInfo

RUNTIME = {
    "version": 1, "model": "ollama/fixture", "mode": "standard",
    "effort": None, "definition": "", "credentials": "", "at": 1.0,
}


def _open(path: Path) -> tuple[Memory, DurableTurns]:
    memory = Memory(path / "memory.md", path / "sessions.db")
    return memory, DurableTurns(memory)


def _admit(store: DurableTurns, *, request: str = "request", worker: str = "worker"):
    return store.admit(
        request_id=request, session_id="session", turn_id=uuid.uuid4().hex,
        worker_id=worker, text="one instruction", scope="standard", runtime=RUNTIME,
    )


def _process_admit(path: str, request: str, worker: str, output) -> None:
    memory, store = _open(Path(path))
    try:
        result = _admit(store, request=request, worker=worker)
        output.put(("ok", result.created, result.turn_id, result.fence))
    except Exception as exc:
        output.put(("error", type(exc).__name__, str(exc)))
    finally:
        memory.db.close()


def _process_plan_mutation(path: str, request: str, output) -> None:
    memory, store = _open(Path(path))
    try:
        revision = store.set_plan_mode(
            "session", True, expected_revision=0, request_id=request,
        )
        output.put(("ok", revision))
    except Exception as exc:
        output.put(("error", type(exc).__name__, str(exc)))
    finally:
        memory.db.close()


def test_durable_mutation_receipts_deduplicate_across_processes(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    output = ctx.Queue()
    workers = [ctx.Process(target=_process_plan_mutation,
                           args=(str(tmp_path), "plan-request", output)) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    assert sorted(output.get(timeout=2) for _ in workers) == [("ok", 1), ("ok", 1)]
    memory, store = _open(tmp_path)
    assert store.session_options("session") == (1, True)
    with pytest.raises(ValueError, match="different input"):
        store.set_plan_mode("session", False, expected_revision=0,
                            request_id="plan-request")
    with pytest.raises(ValueError, match="different input"):
        store.bind_workspace("session", str(tmp_path.resolve()), expected_revision=0,
                             request_id="plan-request")
    assert memory.db.execute(
        "SELECT COUNT(*) FROM application_mutations WHERE request_id='plan-request'"
    ).fetchone()[0] == 1
    memory.db.close()


def test_durable_mutation_receipts_do_not_repeat_revisions_or_events(tmp_path):
    memory, store = _open(tmp_path)
    path = str(tmp_path.resolve())
    assert store.bind_workspace("session", path, expected_revision=0,
                                request_id="bind") == 1
    assert store.bind_workspace("session", path, expected_revision=0,
                                request_id="bind") == 1
    assert store.workspace("session") == (path, 1)
    memory.db.execute(
        "INSERT INTO application_control(session_id,controller_id,epoch,updated_at) "
        "VALUES ('session','first',1,0)"
    )
    memory.db.commit()
    assert store.claim_control("session", "second", expected_epoch=1,
                               request_id="control") == 2
    assert store.claim_control("session", "second", expected_epoch=1,
                               request_id="control") == 2
    assert store.control("session") == ("second", 2)
    with pytest.raises(ValueError, match="different input"):
        store.claim_control("session", "third", expected_epoch=1,
                            request_id="control")
    item = store.enqueue(
        session_id="session", creator_id="second", request_id="queue-item",
        text="later", scope="standard", runtime=RUNTIME,
    )
    assert store.remove_queue_item("session", item.id, "second", expected_revision=1,
                                   request_id="remove")
    assert store.remove_queue_item("session", item.id, "second", expected_revision=1,
                                   request_id="remove")
    assert memory.db.execute(
        "SELECT revision FROM application_queue WHERE id=?", (item.id,)
    ).fetchone()[0] == 2
    assert memory.db.execute(
        "SELECT COUNT(*) FROM session_events WHERE session_id='session' "
        "AND kind='application.public.v1' AND payload LIKE '%queue.changed%'"
    ).fetchone()[0] == 2
    memory.db.close()


def test_two_processes_deduplicate_exact_submission_and_reject_competing_turn(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    output = ctx.Queue()
    workers = [
        ctx.Process(target=_process_admit, args=(str(tmp_path), "same", f"worker-{n}", output))
        for n in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    results = [output.get(timeout=2) for _ in workers]
    assert sorted(item[1] for item in results) == [False, True]
    assert results[0][2] == results[1][2]

    memory, store = _open(tmp_path)
    assert memory.db.execute(
        "SELECT COUNT(*) FROM turns WHERE session_id='session' AND role='user'"
    ).fetchone()[0] == 1
    with pytest.raises(RuntimeError, match="active worker"):
        _admit(store, request="different", worker="another")
    memory.db.close()


def test_shared_keeper_renews_fenced_application_turn_and_stops_on_loss(tmp_path):
    from klaude_cli.session_io import SessionLeaseKeeper as TerminalLeaseKeeper

    assert TerminalLeaseKeeper is SessionLeaseKeeper
    memory, store = _open(tmp_path)
    admitted = _admit(store)
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=? WHERE session_id='session'",
        (time.time() + 0.2,),
    )
    memory.db.commit()
    keeper = SessionLeaseKeeper(
        memory, "session", "worker", admitted.turn_id,
        interval=0.01, ttl=0.1, fence=admitted.fence,
    )
    keeper.start()
    try:
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            live = memory.session_live_state("session")
            if live["owner_lease_until"] > time.time() + 4:
                break
            time.sleep(0.01)
        assert live["owner_lease_until"] > time.time() + 4
    finally:
        keeper.close()
    assert not keeper.thread.is_alive()

    lost = threading.Event()
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'"
    )
    memory.db.commit()
    stale = SessionLeaseKeeper(
        memory, "session", "worker", admitted.turn_id,
        interval=0.01, fence=admitted.fence, on_lost=lost.set,
    )
    stale.start()
    assert lost.wait(1)
    stale.close()
    assert stale.lost.is_set() and not stale.thread.is_alive()
    memory.db.close()


def test_shared_keeper_fails_closed_after_storage_outage():
    class UnavailableMemory:
        def renew_session_lease(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("storage unavailable")

    lost = threading.Event()
    keeper = SessionLeaseKeeper(
        UnavailableMemory(), "session", "worker", "turn",
        interval=0.01, outage_grace=0.04, on_lost=lost.set,
    )
    keeper.start()
    assert lost.wait(1)
    keeper.close()
    assert keeper.lost.is_set() and not keeper.thread.is_alive()


def test_schema_upgrade_waits_for_active_legacy_writer_and_blocks_old_binary(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    assert memory.acquire_session_lease("session", "old", "turn")
    with pytest.raises(RuntimeError, match="active terminal worker"):
        DurableTurns(memory)
    assert memory.release_session_lease("session", "old", "turn")
    DurableTurns(memory)
    old_connection = sqlite3.connect(tmp_path / "sessions.db")
    with pytest.raises(sqlite3.OperationalError, match="klaude_writer_v3"):
        old_connection.execute(
            "UPDATE session_live SET state='running' WHERE session_id='session'"
        )
    old_connection.close()
    memory.db.close()


def test_newer_application_schema_refuses_binary_downgrade(tmp_path):
    memory, _store = _open(tmp_path)
    memory.db.execute("UPDATE application_schema SET version=99 WHERE id=1")
    memory.db.commit()
    with pytest.raises(RuntimeError, match="newer"):
        DurableTurns(memory)
    assert memory.db.execute(
        "SELECT version FROM application_schema WHERE id=1"
    ).fetchone()[0] == 99
    memory.db.close()


def test_expired_owner_is_interrupted_and_cannot_append_or_finish(tmp_path):
    memory, store = _open(tmp_path)
    first = _admit(store)
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0, partial='Saved public fragment' "
        "WHERE session_id='session'"
    )
    memory.db.commit()
    with pytest.raises(RuntimeError, match="outcome unknown"):
        _admit(store, request="second", worker="new-worker")
    assert store.reconcile_interrupted("session", first.fence)
    second = _admit(store, request="second", worker="new-worker")
    assert second.fence == first.fence + 1
    assert store.receipt(first.request_id).state == "interrupted"
    with pytest.raises(LeaseLost):
        store.assert_fence("session", first.turn_id, "worker", first.fence)
    with pytest.raises(LeaseLost):
        store.finish(
            request_id=first.request_id, session_id="session", turn_id=first.turn_id,
            worker_id="worker", fence=first.fence, state="completed", assistant="stale",
        )
    assert [{"role": item["role"], "content": item["content"]}
            for item in store.snapshot("session")["messages"]] == [
        {"role": "user", "content": "one instruction"},
        {"role": "assistant", "content": "Saved public fragment"},
        {"role": "user", "content": "one instruction"},
    ]
    store.finish(
        request_id=second.request_id, session_id="session", turn_id=second.turn_id,
        worker_id="new-worker", fence=second.fence, state="completed", assistant="done",
        model_content={"reasoning": "private-canary"},
    )
    memory.db.close()

    reopened, resumed = _open(tmp_path)
    assert resumed.receipt("second").state == "completed"
    retry = _admit(resumed, request="second", worker="third")
    assert retry.created is False and retry.turn_id == second.turn_id
    assert "private-canary" not in str(resumed.snapshot("session"))
    assert "private-canary" not in str(resumed.replay(
        "session", resumed.snapshot("session")["cursor"], limit=10
    ))
    reopened.db.close()


def test_same_request_after_restart_reports_interrupted_without_reexecution(tmp_path):
    memory, store = _open(tmp_path)
    first = _admit(store)
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'"
    )
    memory.db.commit()
    memory.db.close()

    reopened, recovered = _open(tmp_path)
    retry = _admit(recovered)
    assert retry.created is False
    assert retry.turn_id == first.turn_id
    assert retry.state == "interrupted"
    assert reopened.db.execute(
        "SELECT COUNT(*) FROM turns WHERE session_id='session' AND role='user'"
    ).fetchone()[0] == 1
    with pytest.raises(RuntimeError, match="outcome unknown"):
        _admit(recovered, request="new")
    reopened.db.close()


def test_explicit_restart_recovery_freezes_queue_and_requires_effect_review(tmp_path):
    memory, store = _open(tmp_path)
    first = _admit(store)
    queued = store.enqueue(
        session_id="session", creator_id="owner", request_id="next",
        text="later", scope="standard", runtime=RUNTIME,
    )
    assert not store.recover_session("session")  # A live peer still owns execution.
    assert store.queue("session", "owner")[0]["state"] == "queued"
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0,partial='Visible fragment' "
        "WHERE session_id='session'"
    )
    memory.db.commit()
    memory.db.close()

    reopened, recovered = _open(tmp_path)
    assert recovered.recover_session("session")
    assert not recovered.recover_session("session")
    assert recovered.receipt(first.request_id).state == "interrupted"
    snapshot = recovered.snapshot("session", "owner")
    assert snapshot["state"] == "interrupted"
    assert snapshot["fence_generation"] == first.fence
    assert snapshot["queue"][0]["id"] == queued.id
    assert snapshot["queue"][0]["state"] == "paused"
    assert [message["content"] for message in snapshot["messages"]].count(
        "Visible fragment"
    ) == 1
    with pytest.raises(RuntimeError, match="outcome unknown"):
        _admit(recovered, request="new")
    assert recovered.reconcile_interrupted("session", first.fence)
    assert not recovered.reconcile_interrupted("session", first.fence)
    reopened.db.close()


def test_terminal_watcher_uses_application_recovery_without_losing_partial(tmp_path):
    from klaude_cli.session_io import SessionIORequest, collect_session_io

    memory, store = _open(tmp_path)
    first = _admit(store)
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0,partial='Public partial' "
        "WHERE session_id='session'"
    )
    memory.db.commit()
    legacy_snapshot = memory.session_snapshot("session")
    assert legacy_snapshot["live"]["state"] == "running"
    assert store.receipt(first.request_id).state == "running"
    result = collect_session_io(
        memory, SessionIORequest("session", "watcher", "", 0, was_watching=True),
    )
    assert result.live["state"] == "interrupted"
    assert store.receipt(first.request_id).state == "interrupted"
    assert [item["content"] for item in store.snapshot("session")["messages"]].count(
        "Public partial"
    ) == 1
    memory.db.close()


def test_terminal_journal_crash_recovers_partial_once_across_both_replay_paths(tmp_path):
    from klaude_cli.session_io import SessionIORequest, collect_session_io

    class NoopRuntime:
        def close(self):
            pass

    memory, _store = _open(tmp_path)
    agent = compose_agent(
        NoopRuntime(), "fixture", [], PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.", model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    turn = SessionTurn(memory, agent, "session", "terminal", "turn", journal=True)
    assert turn.claim()
    turn.start("User prompt")
    memory.publish_session_event(
        "session", "terminal", "assistant_delta", {"text": "Partial"},
        turn_id="turn", fence=turn.fence,
    )
    memory.db.execute("UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'")
    memory.db.commit()
    assert [entry["role"] for entry in memory.session_snapshot("session")["turns"]] == [
        "user"
    ]
    collect_session_io(
        memory, SessionIORequest("session", "watcher", "", 0, was_watching=True),
    )
    memory.session_snapshot("session")
    assert [entry["content"] for entry in memory.load_session("session")
            if entry["role"] == "assistant"] == ["Partial"]
    assert DurableTurns(memory).receipt(turn.request_id).state == "interrupted"
    memory.db.close()


def test_prejournal_expired_terminal_partial_is_preserved_on_upgrade(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.acquire_session_lease("session", "old", "old-turn")
    memory.start_session_turn("session", "old", "old-turn", "User prompt")
    memory.publish_session_event(
        "session", "old", "assistant_delta", {"text": "Legacy partial"},
        turn_id="old-turn",
    )
    memory.db.execute("UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'")
    memory.db.commit()
    journal = DurableTurns(memory)
    assert journal.recover_session("session")
    assert [turn["content"] for turn in memory.load_session("session")
            if turn["role"] == "assistant"] == ["Legacy partial"]
    assert journal.snapshot("session")["state"] == "interrupted"
    memory.db.close()


def test_terminal_reconcile_command_unfreezes_exact_interrupted_fence(tmp_path, monkeypatch):
    from klaude_cli import main as cli_main

    memory, store = _open(tmp_path)
    first = _admit(store)
    memory.db.execute("UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'")
    memory.db.commit()
    memory.db.close()

    def open_memory():
        return Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    monkeypatch.setattr(cli_main, "_memory_store", open_memory)
    cli_main.sessions_reconcile("session", yes=True)
    reopened, journal = _open(tmp_path)
    assert journal.receipt(first.request_id).state == "interrupted"
    assert journal.snapshot("session")["state"] == "idle"
    assert reopened.acquire_session_lease("session", "terminal", "new-turn")
    reopened.db.close()


def test_replay_cursor_survives_restart_and_pruning_requires_snapshot(tmp_path):
    memory, store = _open(tmp_path)
    admitted = _admit(store)
    initial = store.snapshot("session")["cursor"]
    store.finish(
        request_id="request", session_id="session", turn_id=admitted.turn_id,
        worker_id="worker", fence=admitted.fence, state="completed", assistant="safe",
        model_content={"provider_signature": "private-canary"},
    )
    memory.db.close()
    reopened, resumed = _open(tmp_path)
    events = resumed.replay("session", f"{initial.split(':')[0]}:0")
    assert [item["kind"] for item in events] == [
        "turn.accepted", "message.completed", "turn.completed"
    ]
    assert "private-canary" not in str(events)
    assert resumed.replay("session", initial)[-1]["kind"] == "turn.completed"
    with pytest.raises(CursorExpired):
        resumed.replay("session", "wrong:0")
    reopened.db.execute(
        "UPDATE session_events SET ts=? WHERE session_id='session'",
        (time.time() - 120,),
    )
    reopened.db.commit()
    assert reopened.prune_session_events("session", retention_seconds=60) == 3
    with pytest.raises(CursorExpired):
        resumed.replay("session", f"{initial.split(':')[0]}:0")
    assert {key: resumed.snapshot("session")["messages"][-1][key]
            for key in ("role", "content")} == {
        "role": "assistant", "content": "safe",
    }
    reopened.db.close()


def test_replay_projects_known_fields_only(tmp_path):
    memory, store = _open(tmp_path)
    admitted = _admit(store)
    epoch = store.snapshot("session")["cursor"].split(":")[0]
    cursor = memory.db.execute(
        "INSERT INTO session_events(session_id,turn_id,client_id,ts,kind,payload) "
        "VALUES ('session','injected','x',?,'application.public.v1',?)",
        (time.time(), '{"kind":"tool.finished","tool":"safe",'
         '"provider_secret":"private-canary","executed":true}'),
    )
    memory.db.execute(
        "UPDATE application_streams SET high_water=? WHERE session_id='session'",
        (cursor.lastrowid,),
    )
    memory.db.commit()
    events = store.replay("session", f"{epoch}:0")
    assert events[-1]["kind"] == "tool.finished"
    assert events[-1]["executed"] is True
    assert "private-canary" not in str(events)
    assert store.receipt(admitted.request_id).state == "running"
    memory.db.close()


def test_terminal_transaction_failure_does_not_publish_completion(tmp_path):
    memory, store = _open(tmp_path)
    admitted = _admit(store)
    memory.db.execute(
        "CREATE TRIGGER reject_terminal BEFORE UPDATE OF state ON application_turns "
        "WHEN NEW.state='completed' BEGIN SELECT RAISE(ABORT,'disk failure'); END"
    )
    memory.db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="disk failure"):
        store.finish(
            request_id=admitted.request_id, session_id="session", turn_id=admitted.turn_id,
            worker_id="worker", fence=admitted.fence, state="completed",
            assistant="answer", model_content={"private": "canary"},
        )
    assert store.receipt(admitted.request_id).state == "running"
    assert [event["kind"] for event in store.replay(
        "session", store.snapshot("session")["cursor"].split(":")[0] + ":0"
    )] == ["turn.accepted"]
    assert [message["role"] for message in store.snapshot("session")["messages"]] == [
        "user"
    ]
    memory.db.close()


def test_lost_fence_blocks_tool_execution_even_after_provider_response(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    invoked: list[str] = []

    class DelayedRuntime:
        def chat(self, *_args, **_kwargs):
            entered.set()
            release.wait(5)
            return {
                "role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "fixture_action", "arguments": {}}}],
            }

        def close(self):
            pass

    memory, store = _open(tmp_path)
    agent = compose_agent(
        DelayedRuntime(), "fixture",
        [Tool("fixture_action", "Action", {"type": "object", "properties": {}},
              lambda: invoked.append("called") or "done")],
        PermissionGate({"fixture_action": "allow"}, lambda *_args: "y"),
        "Fixture instructions.", tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    app = HeadlessApplication(agent, memory, "session")

    async def exercise():
        handle = app.submit("one instruction", request_id="first")
        assert entered.wait(2)
        memory.db.execute(
            "UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'"
        )
        memory.db.commit()
        competitor_memory, competitor = _open(tmp_path)
        with pytest.raises(RuntimeError, match="outcome unknown"):
            _admit(competitor, request="second", worker="new-worker")
        assert competitor.reconcile_interrupted("session", 1)
        _admit(competitor, request="second", worker="new-worker")
        release.set()
        events = [event async for event in handle.events()]
        receipt = await handle.result()
        assert receipt.state == "interrupted"
        assert events[-1].kind == "turn.interrupted"
        competitor_memory.db.close()
        await app.close()

    asyncio.run(exercise())
    assert invoked == []


def test_approval_cannot_be_accepted_after_lease_loss(tmp_path):
    class ApprovalRuntime:
        def chat(self, *_args, **_kwargs):
            return {
                "role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "fixture_action", "arguments": {}}}],
            }

        def close(self):
            pass

    invoked: list[str] = []
    memory, _store = _open(tmp_path)
    agent = compose_agent(
        ApprovalRuntime(), "fixture",
        [Tool("fixture_action", "Action", {"type": "object", "properties": {}},
              lambda: invoked.append("called") or "done")],
        PermissionGate({"fixture_action": "ask"}, lambda *_args: "n"),
        "Fixture instructions.", tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    app = HeadlessApplication(agent, memory, "session")

    async def exercise():
        handle = app.submit("one instruction")
        for _ in range(200):
            if app.pending_interactions():
                break
            await asyncio.sleep(0.01)
        pending = app.pending_interactions()
        assert pending
        memory.db.execute(
            "UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'"
        )
        memory.db.commit()
        assert not app.decide(pending[0].id, "allow_once")
        handle.cancel()
        assert (await handle.result()).state == "interrupted"
        await app.close()

    asyncio.run(exercise())
    assert invoked == []


def test_terminal_session_turn_fences_stale_transcript_writes(tmp_path):
    class NoopRuntime:
        def close(self):
            pass

    agent = compose_agent(
        NoopRuntime(), "fixture", [], PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.", tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    old = SessionTurn(memory, agent, "session", "first-worker", "first-turn")
    assert old.claim()
    old.start("first user turn")
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'"
    )
    memory.db.commit()
    new = SessionTurn(memory, agent, "session", "second-worker", "second-turn")
    assert new.claim()
    assert new.fence == old.fence + 1
    with pytest.raises(SessionLeaseLost):
        old.guard()
    with pytest.raises(SessionLeaseLost):
        old.save_assistant("stale answer")
    with pytest.raises(SessionLeaseLost):
        memory.publish_session_event(
            "session", "first-worker", "assistant_delta", {"text": "stale"},
            turn_id="first-turn", fence=old.fence,
        )
    assert old.release() is False
    new.start("second user turn")
    new.save_assistant("fresh answer")
    assert new.release()
    assert [item["content"] for item in memory.load_session("session")
            if item["role"] == "assistant"] == ["fresh answer"]
    memory.db.close()


def test_terminal_turn_uses_same_atomic_journal_and_public_replay(tmp_path):
    class NoopRuntime:
        def close(self):
            pass

    agent = compose_agent(
        NoopRuntime(), "fixture", [], PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.", tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    turn = SessionTurn(memory, agent, "session", "terminal", "terminal-turn", journal=True)
    assert turn.claim()
    turn.start("Hello")
    assert DurableTurns(memory).receipt(turn.request_id).state == "running"
    turn.save_assistant("Visible", model_content={"secret": "private-canary"})
    assert [entry["role"] for entry in DurableTurns(memory).snapshot("session")["messages"]] == [
        "user"
    ]
    assert turn.release(completion_payload={"cancelled": False, "failed": False})
    journal = DurableTurns(memory)
    assert journal.receipt(turn.request_id).state == "completed"
    assert [entry["content"] for entry in journal.snapshot("session")["messages"]] == [
        "Hello", "Visible"
    ]
    assert [event["kind"] for event in journal.replay(
        "session", journal.snapshot("session")["cursor"].split(":")[0] + ":0"
    )] == ["turn.accepted", "turn.started", "message.completed", "turn.completed"]
    assert [event["kind"] for event in memory.session_events_since("session", 0)
            if event["kind"] in {"user_started", "turn_done"}] == [
        "user_started", "turn_done"
    ]
    assert "private-canary" not in str(journal.snapshot("session"))
    memory.db.close()


def test_terminal_cannot_bypass_interrupted_application_owner(tmp_path):
    class NoopRuntime:
        def close(self):
            pass

    memory, store = _open(tmp_path)
    first = _admit(store)
    memory.db.execute(
        "UPDATE session_live SET owner_lease_until=0 WHERE session_id='session'"
    )
    memory.db.commit()
    agent = compose_agent(
        NoopRuntime(), "fixture", [], PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.", model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    terminal = SessionTurn(memory, agent, "session", "terminal", "next", journal=True)
    assert not terminal.claim()
    assert store.receipt(first.request_id).state == "interrupted"
    assert store.reconcile_interrupted("session", first.fence)
    assert terminal.claim()
    terminal.release()
    memory.db.close()


def test_session_deletion_rejects_live_work_and_keeps_private_free_tombstone(tmp_path):
    memory, store = _open(tmp_path)
    first = _admit(store)
    with pytest.raises(ValueError, match="unresolved work"):
        memory.delete_session("session")
    store.finish(
        request_id=first.request_id, session_id="session", turn_id=first.turn_id,
        worker_id="worker", fence=first.fence, state="completed", assistant="answer",
    )
    store.enqueue(
        session_id="session", creator_id="owner", request_id="queued",
        text="private queued prompt", scope="standard", runtime=RUNTIME,
    )
    assert memory.delete_session("session") == 2
    assert store.receipt(first.request_id).state == "gone"
    assert memory.db.execute(
        "SELECT fingerprint FROM application_turns WHERE request_id=?",
        (first.request_id,),
    ).fetchone()[0] == ""
    assert memory.db.execute(
        "SELECT COUNT(*) FROM application_queue WHERE session_id='session'"
    ).fetchone()[0] == 0
    with pytest.raises(ValueError, match="deleted"):
        store.snapshot("session")
    with pytest.raises(ValueError, match="gone"):
        _admit(store, request="new")
    assert not memory.acquire_session_lease("session", "terminal", "new-turn")
    memory.db.close()


def test_fork_requires_committed_boundary_and_copies_session_binding(tmp_path):
    memory, store = _open(tmp_path)
    first = _admit(store)
    with pytest.raises(ValueError, match="unresolved work"):
        memory.fork_session("session", "fork")
    store.finish(
        request_id=first.request_id, session_id="session", turn_id=first.turn_id,
        worker_id="worker", fence=first.fence, state="completed", assistant="answer",
    )
    store.bind_workspace("session", str(tmp_path.resolve()), expected_revision=0)
    store.set_plan_mode("session", True, expected_revision=0)
    memory.fork_session("session", "fork")
    assert store.workspace("fork") == (str(tmp_path.resolve()), 1)
    assert store.session_options("fork") == (1, True)
    assert memory.session_runtime("fork") is not None
    assert [turn["content"] for turn in memory.load_session("fork")
            if turn["role"] in {"user", "assistant"}] == ["one instruction", "answer"]
    memory.db.close()


def test_control_takeover_invalidates_old_approval_epoch(tmp_path):
    invoked: list[str] = []

    class OneActionRuntime:
        def __init__(self):
            self.calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "fixture_action", "arguments": {}}}],
                }
            return {"role": "assistant", "content": "complete"}

        def close(self):
            pass

    memory, _store = _open(tmp_path)
    agent = compose_agent(
        OneActionRuntime(), "fixture",
        [Tool("fixture_action", "Action", {"type": "object", "properties": {}},
              lambda: invoked.append("called") or "done")],
        PermissionGate({"fixture_action": "ask"}, lambda *_args: "n"),
        "Fixture instructions.", tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    app = HeadlessApplication(agent, memory, "session")

    async def exercise():
        handle = app.submit("one instruction")
        for _ in range(200):
            if app.pending_interactions():
                break
            await asyncio.sleep(0.01)
        pending = app.pending_interactions()
        assert len(pending) == 1
        old_epoch = app.control()[1]
        new_epoch = app.take_control(
            "second-client", expected_epoch=old_epoch, request_id="take-control"
        )
        assert app.take_control(
            "second-client", expected_epoch=old_epoch, request_id="take-control"
        ) == new_epoch
        assert new_epoch == old_epoch + 1
        assert app.pending_interactions() == ()
        assert not app.decide(pending[0].id, "allow_once", control_epoch=old_epoch)
        assert not app.decide(
            pending[0].id, "allow_once", controller_id="second-client",
            control_epoch=old_epoch,
        )
        assert app.pending_interactions(
            controller_id="second-client", control_epoch=new_epoch
        ) == pending
        assert app.decide(
            pending[0].id, "allow_once", controller_id="second-client",
            control_epoch=new_epoch,
        )
        assert (await handle.result()).state == "completed"
        assert memory.db.execute(
            "SELECT COUNT(*) FROM application_decisions WHERE session_id='session'"
        ).fetchone()[0] == 1
        await app.close()

    asyncio.run(exercise())
    assert invoked == ["called"]


def test_queue_privacy_pause_and_runtime_workspace_conflicts(tmp_path):
    memory, store = _open(tmp_path)
    first = _admit(store)
    store.finish(
        request_id=first.request_id, session_id="session", turn_id=first.turn_id,
        worker_id="worker", fence=first.fence, state="completed", assistant="ready",
    )
    assert store.bind_workspace("session", str(tmp_path.resolve()), expected_revision=0) == 1
    assert store.set_plan_mode("session", True, expected_revision=0) == 1
    assert store.snapshot("session")["plan_mode"] is True
    with pytest.raises(ValueError, match="stale settings revision"):
        store.set_plan_mode("session", False, expected_revision=0)
    item = store.enqueue(
        session_id="session", creator_id="owner", request_id="queued-one",
        text="private queued prompt", scope="standard", runtime=RUNTIME,
    )
    assert store.enqueue(
        session_id="session", creator_id="owner", request_id="queued-one",
        text="private queued prompt", scope="standard", runtime=RUNTIME,
    ).id == item.id
    with pytest.raises(ValueError, match="different input"):
        store.enqueue(
            session_id="session", creator_id="owner", request_id="queued-one",
            text="changed prompt", scope="standard", runtime=RUNTIME,
        )
    assert store.queue("session", "watcher")[0]["text"] == ""
    assert store.queue("session", "owner")[0]["text"] == "private queued prompt"
    assert store.recover_queue("session") == 1
    assert store.claim_next_queued("session", RUNTIME) is None
    assert store.resume_queue_item(
        "session", item.id, "owner", expected_revision=2
    )
    assert store.claim_next_queued("session", RUNTIME).id == item.id
    assert store.recover_queue("session") == 1
    assert store.bind_workspace("session", str((tmp_path / "new").resolve()),
                                expected_revision=1) == 2
    assert not store.resume_queue_item(
        "session", item.id, "owner", expected_revision=5
    )
    assert store.queue("session", "owner")[0]["state"] == "needs_review"
    assert not store.remove_queue_item(
        "session", item.id, "watcher", expected_revision=6
    )
    assert store.remove_queue_item(
        "session", item.id, "owner", expected_revision=6
    )
    memory.db.close()


def test_accepted_queue_runs_after_active_turn_and_keeps_one_user_turn(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class OrderedRuntime:
        def __init__(self):
            self.calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                release.wait(5)
            return {"role": "assistant", "content": f"answer {self.calls}"}

        def close(self):
            pass

    memory, _store = _open(tmp_path)
    runtime = OrderedRuntime()
    agent = compose_agent(
        runtime, "fixture", [], PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.", tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    app = HeadlessApplication(agent, memory, "session")

    async def exercise():
        first = app.submit("first prompt", request_id="first")
        assert entered.wait(2)
        item = app.enqueue("second prompt", request_id="second")
        assert item.state == "queued"
        release.set()
        assert (await first.result()).state == "completed"
        for _ in range(500):
            receipt = app.receipt("second")
            if (receipt is not None and receipt.state == "completed"
                    and not app.active_turn_count()):
                break
            await asyncio.sleep(0.01)
        assert receipt is not None and receipt.state == "completed"
        assert runtime.calls == 2
        assert app.queued()[0]["state"] == "submitted"
        assert app.snapshot()["queue"] == []
        assert [part["content"] for part in app.public_history()
                if part["role"] == "user"] == ["first prompt", "second prompt"]
        app.agent.workdir = tmp_path
        assert app.start_session() != "session"
        await app.close()

    asyncio.run(exercise())


def test_steering_requires_control_and_runs_one_priority_followup(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class WaitingRuntime:
        def __init__(self):
            self.calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                release.wait(5)
            return {"role": "assistant", "content": f"answer {self.calls}"}

        def close(self):
            pass

    memory, _store = _open(tmp_path)
    runtime = WaitingRuntime()
    agent = compose_agent(
        runtime, "fixture", [], PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.", model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    app = HeadlessApplication(agent, memory, "session")

    async def exercise():
        first = app.submit("first", request_id="first")
        assert entered.wait(2)
        controller, epoch = app.control()
        assert not app.cancel_active(
            first.turn_id, controller_id="observer", control_epoch=epoch
        )
        with pytest.raises(ValueError, match="stale session control"):
            app.steer(
                "priority", request_id="priority", turn_id=first.turn_id,
                controller_id="observer", control_epoch=epoch,
            )
        queued = app.steer(
            "priority", request_id="priority", turn_id=first.turn_id,
            controller_id=controller, control_epoch=epoch,
        )
        assert queued.state == "queued"
        release.set()
        assert (await first.result()).state == "cancelled"
        for _ in range(500):
            receipt = app.receipt("priority")
            if receipt is not None and receipt.state == "completed":
                break
            await asyncio.sleep(0.01)
        assert receipt is not None and receipt.state == "completed"
        assert runtime.calls == 2
        assert app.queued(controller)[0]["state"] == "submitted"
        await app.close()

    asyncio.run(exercise())
