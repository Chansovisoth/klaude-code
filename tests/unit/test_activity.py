"""Activity labels follow execution facts without changing turn ownership."""

from __future__ import annotations

import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from klaude_application.activity import Activity, ActivityState, classify_activity, tool_outcome
from klaude_application.runner import iter_agent_events
from klaude_core import AgentEvent


@pytest.mark.parametrize(("tool", "arguments", "expected"), [
    ("write_file", {"path": "src/a.py"}, "Writing code"),
    ("write_file", {"path": "report.md"}, "Creating files"),
    ("edit_file", {"path": "src/a.py"}, "Editing"),
    ("apply_patch", {}, "Applying changes"),
    ("generate_image", {}, "Generating images"),
    ("edit_image", {}, "Generating images"),
    ("analyze_data", {}, "Analyzing data"),
    ("run_tests", {}, "Running tests"),
    ("http_probe", {}, "Validating"),
    ("read_file", {}, "Waiting"),
    ("run_shell", {"command": "uv run --frozen --offline pytest tests/unit -q"}, "Running tests"),
    ("run_shell", {"command": "/repo/.venv/bin/python -m unittest discover"}, "Running tests"),
    ("run_shell", {"command": "npm test -- --runInBand"}, "Running tests"),
    ("run_shell", {"command": "cargo test"}, "Running tests"),
    ("run_shell", {"command": "go test ./..."}, "Running tests"),
    ("run_shell", {"command": "make check"}, "Validating"),
    ("run_shell", {"command": "ruff check ."}, "Validating"),
    ("run_shell", {"command": "ruff check --fix ."}, "Editing"),
    ("run_shell", {"command": "ruff format ."}, "Editing"),
    ("run_shell", {"command": "ruff format --check ."}, "Validating"),
    ("run_shell", {"command": "python3 -m py_compile a.py"}, "Validating"),
    ("run_shell", {"command": "git diff --check"}, "Validating"),
    ("run_shell", {"command": "git apply patch.diff"}, "Applying changes"),
    ("run_shell", {"command": "git apply --check patch.diff"}, "Validating"),
    ("run_shell", {"command": "git apply --stat patch.diff"}, "Validating"),
])
def test_known_activity(tool, arguments, expected):
    assert classify_activity(tool, arguments).value == expected


@pytest.mark.parametrize("command", [
    "echo pytest", "python dataset.py", "pytest --help", "npm run custom-tests",
    "echo test; pytest", "pytest && rm file", "pytest | cat", "pytest > report",
    "$(pytest)", "python -c 'print(\"pytest\")'", "'unterminated", "", "make test clean",
])
def test_shell_words_and_uncertain_operations_do_not_claim_work(command):
    assert classify_activity("run_shell", {"command": command}) == Activity.WAITING
    assert classify_activity("mcp__untrusted__generate_image", {}) == Activity.WAITING


def test_activity_projection_separates_lifecycle_and_preserves_parent_execution():
    state = ActivityState()
    state.observe("parent", "turn.started")
    assert state.label == "Generating response"
    state.observe("parent", "tool.requested", execution_id="a", activity="Editing")
    assert state.label == "Waiting"  # Requested is not executed.
    state.observe("parent", "approval.required", interaction_id="review")
    state.observe("parent", "user_input.required", interaction_id="question")
    assert state.label == "Needs input"
    state.observe("parent", "approval.resolved", interaction_id="review")
    assert state.label == "Needs input"
    state.observe("parent", "user_input.resolved", interaction_id="question")
    assert state.label == "Waiting"
    state.observe("parent", "tool.started", execution_id="a", tool="edit_file", activity="Editing")
    state.observe("parent", "tool.started", execution_id="b", tool="run_shell",
                  activity="Running tests")
    state.observe("child", "tool.started", execution_id="c", activity="Generating images")
    assert state.label == "Editing"
    assert state.public()["active_count"] == 2
    state.observe("parent", "message.delta")
    assert state.label == "Editing"  # Overlapping response cannot hide a tool.
    state.observe("parent", "tool.finished", execution_id="a", status="succeeded")
    assert state.label == "Running tests"
    state.observe("parent", "tool.finished", execution_id="b", status="succeeded")
    assert state.label == "Waiting"
    assert state.lifecycle == "running"
    state.observe("parent", "turn.completed")
    assert state.label == "Done"
    state.observe("parent", "tool.started", execution_id="late", activity="Editing")
    assert state.label == "Done"


def test_recoverable_error_does_not_finish_task_and_cancellation_never_means_done():
    state = ActivityState()
    state.observe("turn", "turn.started")
    state.observe("turn", "tool.finished", execution_id="failed", status="failed")
    assert state.label == "Error" and state.recoverable
    assert state.lifecycle == "running"
    state.observe("turn", "message.delta")
    assert state.label == "Generating response" and not state.recoverable
    state.observe("turn", "turn.cancelled")
    assert state.label == "" and state.lifecycle == "cancelled"
    assert not state.active
    state.observe("next", "turn.started")
    state.observe("next", "turn.failed")
    assert state.label == "Error" and not state.recoverable


@pytest.mark.parametrize(("result", "metadata", "expected"), [
    ("ok", {"executed": True}, "succeeded"),
    ("exit=1", {"executed": True, "exit_code": 1}, "failed"),
    ("tool error: failure", {"executed": True}, "failed"),
    ("error: unavailable", {"executed": False}, "failed"),
    ("permission denied: no", {"executed": False}, "rejected"),
])
def test_tool_outcomes_do_not_confuse_execution_with_success(result, metadata, expected):
    assert tool_outcome(result, metadata) == expected


@pytest.mark.parametrize("terminal", ["completed", "failed", "partial", "cancelled", "interrupted"])
def test_projection_roundtrip_retains_terminal_semantics_and_bounded_timeline(terminal):
    state = ActivityState()
    state.observe("turn", "turn.started")
    for index in range(90):
        state.observe("turn", "tool.requested", tool="read_file", execution_id=str(index))
    state.observe("turn", f"turn.{terminal}")
    restored = ActivityState(**json.loads(json.dumps(asdict(state))))
    assert restored.public(timeline=True) == state.public(timeline=True)
    assert len(restored.timeline) == 80
    assert (restored.label == "Done") is (terminal == "completed")


def test_activity_adapter_preserves_tool_output_and_restores_observer_on_close():
    seen, observed = [], []

    def original_observer(tool, identity):
        seen.append((tool, identity))

    agent = SimpleNamespace(execution_observer=original_observer)
    result = AgentEvent("tool_result", {
        "tool": "run_shell", "result": "Full output\n" * 2000,
        "metadata": {"executed": True, "execution_id": "call", "exit_code": 0},
    })

    def run(_message, **_kwargs):
        yield AgentEvent("tool_start", {"tool": "run_shell", "execution_id": "call",
                                        "args": {"command": "pytest"}})
        agent.execution_observer("run_shell", "call")
        yield result

    agent.run = run
    events = iter_agent_events(agent, "Test", on_activity=observed.append)
    next(events)
    assert next(events) is result
    assert result.payload["result"] == "Full output\n" * 2000
    assert seen == [("run_shell", "call")]
    assert next(e for e in observed if e.kind == "tool.started").activity == "Running tests"
    events.close()
    assert agent.execution_observer is original_observer
