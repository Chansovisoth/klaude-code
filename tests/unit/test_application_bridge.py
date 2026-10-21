"""Deterministic M1 bridge tests using the existing Agent execution engine."""

from __future__ import annotations

import asyncio
import io
import subprocess
import threading
import time
from pathlib import Path

import pytest
from klaude_application import HeadlessApplication, SessionTurn, compose_agent
from klaude_application.interactions import InteractionBroker
from klaude_core import AgentEvent, PermissionGate, Tool
from klaude_core.config import Config
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelInfo
from klaude_tools import Workspace


class ScriptedRuntime:
    def __init__(self, replies: list[dict] | None = None) -> None:
        self.replies = list(replies or [])
        self.calls = 0
        self.closed = False
        self.cancelled = False

    def chat(self, model, messages, tools=None, options=None, think=None):
        self.calls += 1
        return self.replies.pop(0)

    def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


def _tool_call(name: str, **arguments: object) -> dict:
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


def _application(
    tmp_path: Path, runtime: ScriptedRuntime, *,
    tools: list[Tool] | None = None, permissions: dict[str, str] | None = None,
    session_id: str | None = None,
) -> HeadlessApplication:
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    agent = compose_agent(
        runtime, "fixture", tools or [],
        PermissionGate(permissions or {}, lambda _tool, _detail: "n"),
        "Fixture instructions.", tool_selector=lambda _message, available: list(available),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    return HeadlessApplication(agent, memory, session_id)


async def _collect(handle) -> list:
    return [event async for event in handle.events()]


def test_headless_construction_has_no_terminal_or_network_startup(tmp_path, monkeypatch) -> None:
    import klaude_core.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    runtime = ScriptedRuntime()
    app = HeadlessApplication.open_local(
        tmp_path, runtime,
        config=Config(models={"coder": "fixture"}), model="fixture",
    )
    assert runtime.calls == 0
    assert app.agent.workspace.write_enabled is False
    assert app.settings is not None
    assert app.settings.read("composer_mode").value == "standard"
    assert "klaude_cli" not in app.agent.__class__.__module__
    asyncio.run(app.close())
    assert runtime.closed


def test_session_turn_releases_lease_when_admission_write_fails(tmp_path, monkeypatch) -> None:
    app = _application(tmp_path, ScriptedRuntime())
    turn = SessionTurn(app.memory, app.agent, app.session_id, app.client_id, "failure")
    assert turn.claim()
    with pytest.raises(RuntimeError, match="not started"):
        turn.save_assistant("too early")

    def fail_start(*_args, **_kwargs):
        raise OSError("storage unavailable")

    monkeypatch.setattr(app.memory, "start_session_turn", fail_start)
    with pytest.raises(OSError, match="storage unavailable"):
        turn.start("Hello")
    assert app.memory.session_live_state(app.session_id)["owner_client_id"] == ""
    assert not turn.release()
    asyncio.run(app.close())


def test_public_stream_and_session_resume_hide_private_payload(tmp_path) -> None:
    runtime = ScriptedRuntime([{"role": "assistant", "content": "Ready."}])
    app = _application(tmp_path, runtime)

    async def exercise():
        handle = app.submit("Hello", request_id="first")
        assert app.submit("Hello", request_id="first") is handle
        with pytest.raises(ValueError):
            app.submit("Different", request_id="first")
        events = await _collect(handle)
        receipt = await handle.result()
        assert receipt.state == "completed"
        assert [event.kind for event in events] == [
            "turn.accepted", "turn.started", "message.delta",
            "message.completed", "turn.completed",
        ]
        assert events[2].text == "Ready."
        assert all(not hasattr(event, "model_message") for event in events)
        assert app.public_history() == (
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Ready."},
        )
        session_id = app.session_id
        await app.close()
        return session_id

    session_id = asyncio.run(exercise())
    resumed = _application(tmp_path, ScriptedRuntime(), session_id=session_id)
    resumed.resume(session_id)
    assert resumed.agent.model_info.ref == "ollama/fixture"
    assert resumed.public_history()[-1]["content"] == "Ready."
    asyncio.run(resumed.close())
    wrong_model = _application(tmp_path, ScriptedRuntime(), session_id=session_id)
    wrong_model.agent.model_info = ModelInfo("ollama", "different", "different")
    with pytest.raises(ValueError, match="explicit model/runtime selection required"):
        wrong_model.resume(session_id)
    asyncio.run(wrong_model.close())


def test_detaching_event_consumer_does_not_cancel_accepted_turn(tmp_path) -> None:
    entered = threading.Event()
    release = threading.Event()

    class WaitingRuntime(ScriptedRuntime):
        def chat(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            return {"role": "assistant", "content": "Still running."}

    app = _application(tmp_path, WaitingRuntime())

    async def exercise() -> None:
        handle = app.submit("Continue", request_id="detached")
        stream = handle.events()
        assert (await anext(stream)).kind == "turn.accepted"
        assert (await anext(stream)).kind == "turn.started"
        assert entered.wait(2)
        await stream.aclose()
        assert not handle.cancelled.is_set()
        assert app.receipt("detached").state == "running"
        release.set()
        assert (await handle.result()).state == "completed"
        assert [event["kind"] for event in app.replay(
            app.snapshot()["cursor"].split(":")[0] + ":0"
        )][-1] == "turn.completed"
        await app.close()

    asyncio.run(exercise())


def test_large_unicode_stream_keeps_offsets_and_requires_snapshot_for_final(tmp_path) -> None:
    app = _application(tmp_path, ScriptedRuntime())
    answer = "🙂" * 65_537

    def public_events(_message, scope=None):
        yield AgentEvent("text_delta", {"content": answer})
        yield AgentEvent("text", {"content": answer, "metadata": {"streamed": True}})

    app.agent.run = public_events

    async def exercise() -> None:
        handle = app.submit("Describe")
        events = await _collect(handle)
        assert (await handle.result()).state == "completed"
        live = [event for event in events if event.kind == "message.delta"]
        assert [event.offset for event in live] == [0, 65_536]
        assert "".join(event.text for event in live) == answer
        final = next(event for event in events if event.kind == "message.completed")
        assert final.status == "truncated"
        assert app.snapshot()["messages"][-1]["content"] == answer
        replay = app.replay(app.snapshot()["cursor"].split(":")[0] + ":0")
        replay_deltas = [event for event in replay if event["kind"] == "message.delta"]
        assert [event["offset"] for event in replay_deltas] == [0, 65_536]
        assert [event.cursor for event in live] == [
            event["cursor"] for event in replay_deltas
        ]
        await app.close()

    asyncio.run(exercise())


def test_public_projection_excludes_tool_arguments_results_and_private_continuation(tmp_path):
    app = _application(tmp_path, ScriptedRuntime())

    def private_events(_message, scope=None):
        yield AgentEvent("tool_start", {
            "tool": "read_file", "execution_id": "exact", "args": {"key": "private-canary"},
        })
        yield AgentEvent("tool_result", {
            "tool": "read_file", "result": "private-canary",
            "metadata": {"execution_id": "exact", "executed": False,
                         "provider_debug": "private-canary"},
        })
        yield AgentEvent("text", {
            "content": "Safe answer", "model_message": {"reasoning": "private-canary"},
        })

    app.agent.run = private_events

    async def exercise():
        handle = app.submit("Inspect")
        events = await _collect(handle)
        assert (await handle.result()).state == "completed"
        assert "private-canary" not in repr(events)
        assert "private-canary" not in repr(app.public_history())
        assert next(event for event in events if event.kind == "tool.finished").executed is False
        await app.close()

    asyncio.run(exercise())


def test_headless_and_line_renderer_share_agent_answer(tmp_path, monkeypatch) -> None:
    from klaude_cli.main import _render
    from rich.console import Console

    headless = _application(
        tmp_path / "headless", ScriptedRuntime([{"role": "assistant", "content": "Ready."}]),
    )

    async def run_headless():
        handle = headless.submit("Hello")
        events = await _collect(handle)
        assert (await handle.result()).state == "completed"
        await headless.close()
        return next(event.text for event in events if event.kind == "message.completed")

    expected = asyncio.run(run_headless())
    line_agent = compose_agent(
        ScriptedRuntime([{"role": "assistant", "content": "Ready."}]),
        "fixture", [], PermissionGate({}, lambda _tool, _detail: "n"),
        "Fixture instructions.", tool_selector=lambda _message, available: list(available),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )

    class LineMemory:
        def __init__(self) -> None:
            self.turns: list[tuple[str, object]] = []

        def log_turn(self, _session_id, role, content, **_kwargs):
            self.turns.append((role, content))

    output = io.StringIO()
    monkeypatch.setattr(
        "klaude_cli.main.console", Console(file=output, force_terminal=False, width=80),
    )
    memory = LineMemory()
    assert _render(line_agent, memory, "line", "Hello") == expected
    assert memory.turns == [("user", "Hello"), ("assistant", expected)]


@pytest.mark.parametrize("decision,executed", [("allow_once", True), ("deny", False)])
def test_exact_approval_precedes_execution(tmp_path, decision, executed) -> None:
    invoked: list[str] = []
    tool = Tool(
        "fixture_action", "Fixture action",
        {"type": "object", "properties": {"value": {"type": "string"}},
         "required": ["value"]},
        lambda value: invoked.append(value) or "done",
    )
    runtime = ScriptedRuntime([
        _tool_call("fixture_action", value="one"),
        {"role": "assistant", "content": "Finished."},
    ])
    app = _application(tmp_path, runtime, tools=[tool], permissions={"fixture_action": "ask"})

    async def exercise():
        handle = app.submit("Use the action")
        consumer = asyncio.create_task(_collect(handle))
        for _ in range(200):
            pending = app.pending_interactions()
            if pending:
                break
            await asyncio.sleep(0.01)
        assert len(pending) == 1
        assert pending[0].tool == "fixture_action"
        assert pending[0].execution_id
        assert app.decide(pending[0].id, decision)
        assert not app.decide(pending[0].id, decision)
        events = await consumer
        assert ("tool.started" in [event.kind for event in events]) is executed
        result = next(event for event in events if event.kind == "tool.finished")
        assert result.executed is executed
        assert result.execution_id == pending[0].execution_id
        assert [event.kind for event in events].index("tool.requested") < [
            event.kind for event in events
        ].index("approval.required")
        await handle.result()
        await app.close()

    asyncio.run(exercise())
    assert invoked == (["one"] if executed else [])


def test_reviewed_tool_rechecks_policy_and_preflight_after_approval(tmp_path) -> None:
    invoked: list[str] = []
    safe = {"value": True}

    def preflight(_args) -> None:
        if not safe["value"]:
            raise PermissionError("workspace changed after review")

    tool = Tool(
        "fixture_action", "Action", {"type": "object", "properties": {}},
        lambda: invoked.append("called") or "done", preflight=preflight,
    )
    app = _application(
        tmp_path, ScriptedRuntime([_tool_call("fixture_action"),
                                   {"role": "assistant", "content": "Stopped."}]),
        tools=[tool], permissions={"fixture_action": "ask"},
    )

    async def exercise() -> None:
        handle = app.submit("Use the action")
        consumer = asyncio.create_task(_collect(handle))
        for _ in range(200):
            if app.pending_interactions():
                break
            await asyncio.sleep(0.01)
        pending = app.pending_interactions()
        assert pending
        safe["value"] = False
        assert app.decide(pending[0].id, "allow_once")
        events = await consumer
        assert next(event for event in events if event.kind == "tool.finished").executed is False
        assert invoked == []
        await app.close()

    asyncio.run(exercise())


def test_local_workspace_tool_requires_explicit_session_binding(tmp_path) -> None:
    invoked: list[str] = []
    app = _application(
        tmp_path,
        ScriptedRuntime([
            _tool_call("fixture_action"), {"role": "assistant", "content": "Blocked."},
            _tool_call("fixture_action"), {"role": "assistant", "content": "Allowed."},
        ]),
        tools=[Tool("fixture_action", "Action", {"type": "object", "properties": {}},
                    lambda: invoked.append("called") or "done")],
        permissions={"fixture_action": "allow"},
    )
    app.agent.workdir = tmp_path
    app.agent.workspace = Workspace(tmp_path)

    async def exercise() -> None:
        first = app.submit("Try before binding")
        events = await _collect(first)
        assert next(event for event in events if event.kind == "tool.finished").executed is False
        assert invoked == []
        assert (await first.result()).state == "completed"
        app.turns.bind_workspace(app.session_id, str(tmp_path.resolve()), expected_revision=0)
        second = app.submit("Try after binding")
        events = await _collect(second)
        assert next(event for event in events if event.kind == "tool.finished").executed is True
        assert (await second.result()).state == "completed"
        assert invoked == ["called"]
        await app.close()

    asyncio.run(exercise())


def test_cancel_pending_approval_cannot_run_tool(tmp_path) -> None:
    invoked: list[str] = []
    tool = Tool("fixture_action", "Action", {"type": "object", "properties": {}},
                lambda: invoked.append("called") or "done")
    runtime = ScriptedRuntime([_tool_call("fixture_action")])
    app = _application(tmp_path, runtime, tools=[tool], permissions={"fixture_action": "ask"})

    async def exercise():
        handle = app.submit("Use the action")
        consumer = asyncio.create_task(_collect(handle))
        for _ in range(200):
            if app.pending_interactions():
                break
            await asyncio.sleep(0.01)
        pending = app.pending_interactions()
        assert len(pending) == 1
        handle.cancel()
        assert not app.decide(pending[0].id, "allow_once")
        events = await consumer
        assert (await handle.result()).state == "cancelled"
        assert app.snapshot()["activity"]["lifecycle"] == "cancelled"
        assert app.snapshot()["activity"]["label"] != "Done"
        assert all(event.kind != "tool.started" for event in events)
        assert await handle.join()
        await app.close()

    asyncio.run(exercise())
    assert invoked == []


def test_drain_closes_reviews_without_cancelling_accepted_turn(tmp_path) -> None:
    invoked: list[str] = []
    tool = Tool("fixture_action", "Action", {"type": "object", "properties": {}},
                lambda: invoked.append("called") or "done")
    runtime = ScriptedRuntime([
        _tool_call("fixture_action"),
        {"role": "assistant", "content": "Completed without action."},
    ])
    app = _application(tmp_path, runtime, tools=[tool], permissions={"fixture_action": "ask"})

    async def exercise() -> None:
        handle = app.submit("Use the action")
        for _ in range(200):
            if app.pending_interactions():
                break
            await asyncio.sleep(0.01)
        assert app.pending_interactions()
        await asyncio.wait_for(app.close(drain=True), timeout=3)
        assert (await handle.result()).state == "completed"

    asyncio.run(exercise())
    assert invoked == []
    assert not runtime.cancelled
    assert runtime.closed


def test_worker_does_not_block_async_loop_or_leak_provider_failure(tmp_path) -> None:
    entered = threading.Event()
    release = threading.Event()

    class BlockingRuntime(ScriptedRuntime):
        def chat(self, model, messages, tools=None, options=None, think=None):
            entered.set()
            release.wait(2)
            raise RuntimeError("provider failed with secret=private")

    app = _application(tmp_path, BlockingRuntime())

    async def exercise():
        handle = app.submit("Hello")
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set()
        await asyncio.wait_for(asyncio.sleep(0.01), 0.5)
        release.set()
        events = await _collect(handle)
        assert events[-1].kind == "turn.failed"
        assert all("secret" not in event.text for event in events)
        assert (await handle.result()).state == "failed"
        assert app.snapshot()["activity"]["label"] == "Error"
        assert await handle.join()
        await app.close()

    asyncio.run(exercise())


def test_recovered_tool_failure_and_direct_failure_have_distinct_task_outcomes(tmp_path):
    def fail():
        raise RuntimeError("Fixture operation failed")

    async def exercise(root, *, direct):
        root.mkdir()
        tool = Tool("fixture_action", "Fixture action", {"type": "object", "properties": {}},
                    fail, return_direct=direct)
        app = _application(root, ScriptedRuntime([
            _tool_call("fixture_action"), {"role": "assistant", "content": "Recovered response."},
        ]), tools=[tool], permissions={"fixture_action": "allow"})
        handle = app.submit("Use the fixture action")
        events = await _collect(handle)
        snapshot = app.snapshot()
        finished = next(e for e in events if e.kind == "tool.finished")
        assert finished.executed and finished.status == "failed"
        assert any(row["kind"] == "tool.finished" and row["label"] == "Error"
                   for row in snapshot["activity"]["timeline"])
        assert snapshot["activity"]["label"] == ("Error" if direct else "Done")
        assert (await handle.result()).state == ("partial" if direct else "completed")
        assert snapshot["messages"][-1]["content"]
        await app.close()

    asyncio.run(exercise(tmp_path / "recovered", direct=False))
    asyncio.run(exercise(tmp_path / "direct", direct=True))


def test_stream_cancellation_closes_generator_and_worker(tmp_path) -> None:
    app = _application(tmp_path, ScriptedRuntime())
    closed = threading.Event()

    def stream(_message, scope=None):
        try:
            while True:
                yield AgentEvent("text_delta", {"content": "piece"})
                if app.agent.cancellation_check():
                    return
                threading.Event().wait(0.01)
        finally:
            closed.set()

    app.agent.run = stream

    async def exercise():
        handle = app.submit("Stream")
        events = []
        async for event in handle.events():
            events.append(event)
            if event.kind == "message.delta":
                handle.cancel()
        assert (await handle.result()).state == "cancelled"
        assert closed.is_set()
        assert await handle.join()
        await app.close()

    asyncio.run(exercise())


def test_unexpected_generator_exception_propagates_from_receipt(tmp_path) -> None:
    app = _application(tmp_path, ScriptedRuntime())

    def broken(_message, scope=None):
        yield AgentEvent("text_delta", {"content": "partial"})
        raise RuntimeError("worker broke with secret=private")

    app.agent.run = broken

    async def exercise():
        handle = app.submit("Break")
        events = await _collect(handle)
        assert events[-1].kind == "turn.failed"
        assert all("secret" not in event.text for event in events)
        with pytest.raises(RuntimeError, match="worker broke"):
            await handle.result()
        assert await handle.join()
        await app.close()

    asyncio.run(exercise())


def test_full_public_event_channel_requests_replay_without_blocking_worker(tmp_path) -> None:
    app = _application(tmp_path, ScriptedRuntime())

    def flood(_message, scope=None):
        for index in range(140):
            yield AgentEvent("tool_start", {
                "tool": "fixture_action", "execution_id": f"req-{index}",
            })
            if app.agent.cancellation_check():
                return

    app.agent.run = flood

    async def exercise():
        handle = app.submit("Flood")
        for _ in range(1_500):
            if handle.reset_required:
                break
            await asyncio.sleep(0.01)
        assert handle.reset_required
        events = await _collect(handle)
        assert events[-1].kind == "stream.reset_required"
        assert events[-1].cursor
        assert await handle.join(timeout=10)
        assert (await handle.result()).state == "failed"
        assert app.replay(events[-1].cursor)
        await app.close()

    asyncio.run(exercise())


def test_expired_approval_denies_and_user_input_is_structured() -> None:
    cancelled = threading.Event()
    broker = InteractionBroker("session", "turn", cancelled, lambda *_args: None, timeout=0.02)
    assert broker.ask_permission(
        "fixture_action", "private detail",
        {"execution_id": "exact", "arguments": {"secret": "private"}},
    ) == "n"
    assert broker.pending() == ()
    results: list[str] = []
    responsive = InteractionBroker(
        "session", "turn", cancelled, lambda *_args: None, timeout=1,
    )
    worker = threading.Thread(
        target=lambda: results.append(responsive.request_input("Pick one", ["A", "B"])),
    )
    worker.start()
    deadline = time.monotonic() + 1
    while not responsive.pending() and time.monotonic() < deadline:
        threading.Event().wait(0.001)
    pending = responsive.pending()
    assert len(pending) == 1
    assert pending[0].options == ("A", "B")
    assert responsive.decide(pending[0].id, "B")
    worker.join(1)
    assert not worker.is_alive()
    assert '"source": "option"' in results[0]


def test_dirty_workspace_keeps_writes_disabled(tmp_path, monkeypatch) -> None:
    import klaude_core.config as config_module

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "existing.txt").write_text("user work\n")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    runtime = ScriptedRuntime([
        _tool_call("write_file", path="new.txt", content="unsafe"),
        {"role": "assistant", "content": "Could not write."},
    ])
    app = HeadlessApplication.open_local(
        tmp_path, runtime, config=Config(models={"coder": "fixture"}),
        model="fixture", tool_selector=lambda _message, available: list(available),
    )
    assert "dirty" in app.activate_workspace().lower()

    async def exercise():
        handle = app.submit("Write new.txt")
        consumer = asyncio.create_task(_collect(handle))
        for _ in range(200):
            pending = app.pending_interactions()
            if pending:
                app.decide(pending[0].id, "allow_once")
                break
            if handle.finished.is_set():
                break
            await asyncio.sleep(0.01)
        events = await consumer
        assert all(event.kind != "tool.started" for event in events)
        await handle.result()
        await app.close()

    asyncio.run(exercise())
    assert not (tmp_path / "new.txt").exists()


def test_approval_execution_and_reconnect_restore_exact_activity(tmp_path):
    from klaude_application.coordination import DurableTurns

    entered, release = threading.Event(), threading.Event()

    def run_tests():
        entered.set()
        assert release.wait(5)
        return "fixture operation finished"

    tool = Tool("run_tests", "Fixture test operation", {"type": "object", "properties": {}},
                run_tests)
    app = _application(tmp_path, ScriptedRuntime([
        _tool_call("run_tests"), {"role": "assistant", "content": "Finished the request."},
    ]), tools=[tool], permissions={"run_tests": "ask"})

    async def exercise():
        handle = app.submit("Run the tests", request_id="activity")
        try:
            for _ in range(100):
                pending = app.pending_interactions()
                if pending and app.snapshot()["activity"]["label"] == "Needs input":
                    break
                await asyncio.sleep(.01)
            assert app.snapshot()["activity"]["label"] == "Needs input"
            assert not entered.is_set()
            assert app.decide(pending[0].id, "allow_once")
            assert entered.wait(2)
            reader = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
            try:
                reconnected = DurableTurns(reader).snapshot(app.session_id)
                assert reconnected["activity"]["label"] == "Running tests"
                assert reconnected["activity"]["active_count"] == 1
                assert reader.session_live_state(app.session_id)["activity"] == "Running tests"
                events = app.replay(reconnected["cursor"])
                assert not events
            finally:
                reader.db.close()
            release.set()
            events = await _collect(handle)
            assert (await handle.result()).state == "completed"
            assert app.snapshot()["activity"]["label"] == "Done"
            history = app.snapshot()["activity"]["timeline"]
            assert any(row["kind"] == "tool.finished" for row in history)
            assert next(e for e in events if e.kind == "tool.started").activity == "Running tests"
        finally:
            release.set()
            await app.close()

    asyncio.run(exercise())
