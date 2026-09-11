import pytest
from klaude_core import (
    Agent,
    PermissionGate,
    SubagentBudget,
    SubagentRole,
    SubagentStatus,
    SubagentSupervisor,
    SubagentTask,
    SubagentWorkerOutput,
    supervise_agent_tasks,
)
from klaude_core.execution import TurnGovernor
from klaude_core.subagents import SubagentExecutionError, run_agent_assignment


def test_task_normalizes_objective_and_rejects_unbounded_input():
    task = SubagentTask("  inspect   routing  ", requested_tools=("read_file", "read_file"))

    assert task.objective == "inspect routing"
    assert task.requested_tools == ("read_file",)
    with pytest.raises(ValueError, match="objective"):
        SubagentTask(" ")
    with pytest.raises(ValueError, match="context"):
        SubagentTask("inspect", context="x" * 8_001)
    with pytest.raises(ValueError, match="requested_tools"):
        SubagentTask("inspect", requested_tools=("x" * 129,))


def test_budget_is_bounded_and_total_caps_each_child():
    budget = SubagentBudget(
        max_children=99,
        max_steps_per_child=99,
        max_total_steps=3,
        max_result_characters=1,
    ).bounded()

    assert budget == SubagentBudget(
        max_children=8,
        max_steps_per_child=3,
        max_total_steps=3,
        max_result_characters=512,
    )


def test_prepare_intersects_role_parent_scope_and_effective_permissions():
    supervisor = SubagentSupervisor(
        parent_callable_tools={
            "read_file",
            "web_search",
            "storage_usage",
            "write_file",
            "run_shell",
        },
        effective_permissions={
            "read_file": "allow",
            "web_search": "ask",
            "storage_usage": "deny",
            "write_file": "allow",
            "run_shell": "allow",
        },
        process_grants={"web_search", "storage_usage"},
        worker=lambda _assignment: SubagentWorkerOutput("", 0),
    )
    assignment = supervisor.prepare(
        SubagentTask(
            "inspect safely",
            requested_tools=(
                "read_file",
                "web_search",
                "storage_usage",
                "write_file",
                "run_shell",
                "git_diff",
            ),
        )
    )

    assert assignment.callable_tools == ("read_file", "web_search")
    assert dict(assignment.unavailable_tools) == {
        "git_diff": "not callable by parent turn",
        "run_shell": "not allowed for child role",
        "storage_usage": "denied by parent policy",
        "write_file": "not allowed for child role",
    }


def test_supervisor_returns_bounded_structured_result_and_public_events():
    events = []

    def worker(assignment):
        assert assignment.max_steps == 4
        assert assignment.callable_tools == ("read_file",)
        return SubagentWorkerOutput(
            summary="evidence" * 200,
            model_steps=2,
            tool_calls=1,
            tools_used=("read_file",),
        )

    supervisor = SubagentSupervisor(
        parent_callable_tools={"read_file"},
        effective_permissions={"read_file": "allow"},
        worker=worker,
        budget=SubagentBudget(max_steps_per_child=4, max_result_characters=512),
        event_sink=events.append,
    )
    task = SubagentTask("inspect", task_id="child-1", requested_tools=("read_file",))

    result = supervisor.run([task])[0]

    assert result.status is SubagentStatus.COMPLETED
    assert len(result.summary) == 512
    assert result.tools_used == ("read_file",)
    assert result.to_dict()["role"] == "read_research"
    assert [event.to_dict() for event in events] == [
        {"kind": "subagent_started", "task_id": "child-1", "role": "read_research"},
        {
            "kind": "subagent_finished",
            "task_id": "child-1",
            "role": "read_research",
            "status": "completed",
        },
    ]


def test_supervisor_stops_children_at_shared_budget_and_honors_cancellation():
    calls = []

    def worker(assignment):
        calls.append(assignment.task.task_id)
        return SubagentWorkerOutput("done", model_steps=3)

    supervisor = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=worker,
        budget=SubagentBudget(max_children=2, max_steps_per_child=3, max_total_steps=3),
    )
    results = supervisor.run(
        [
            SubagentTask("first", task_id="one"),
            SubagentTask("second", task_id="two"),
        ]
    )

    assert calls == ["one"]
    assert [result.status for result in results] == [
        SubagentStatus.COMPLETED,
        SubagentStatus.FAILED,
    ]
    assert results[1].error_category == "budget_exhausted"

    cancelled = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=lambda _assignment: pytest.fail("cancelled child must not start"),
        cancelled=lambda: True,
    ).run([SubagentTask("cancel me")])[0]
    assert cancelled.status is SubagentStatus.CANCELLED
    assert cancelled.error_category == "cancelled"


@pytest.mark.parametrize(
    ("output", "category"),
    [
        (SubagentWorkerOutput("", model_steps=7), "budget_violation"),
        (
            SubagentWorkerOutput("", model_steps=1, tools_used=("write_file",)),
            "capability_violation",
        ),
    ],
)
def test_worker_cannot_claim_more_budget_or_capabilities(output, category):
    supervisor = SubagentSupervisor(
        parent_callable_tools={"read_file", "write_file"},
        effective_permissions={"read_file": "allow", "write_file": "allow"},
        worker=lambda _assignment: output,
        budget=SubagentBudget(max_steps_per_child=2),
    )

    result = supervisor.run([SubagentTask("inspect")])[0]

    assert result.status is SubagentStatus.FAILED
    assert result.error_category == category
    assert result.summary == ""


def test_worker_exception_exposes_only_its_category():
    def worker(_assignment):
        raise RuntimeError("secret-token-value")

    result = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=worker,
    ).run([SubagentTask("inspect")])[0]

    assert result.status is SubagentStatus.FAILED
    assert result.error_category == "RuntimeError"
    assert result.summary == ""


def test_failed_child_usage_is_still_accounted():
    def worker(_assignment):
        raise SubagentExecutionError(model_steps=2, tool_calls=3)

    result = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=worker,
    ).run([SubagentTask("inspect")])[0]

    assert result.status is SubagentStatus.FAILED
    assert result.model_steps == 2
    assert result.tool_calls == 3


def test_supervisor_rejects_excess_and_duplicate_children_before_execution():
    supervisor = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=lambda _assignment: SubagentWorkerOutput("", 0),
    )
    with pytest.raises(ValueError, match="child limit"):
        supervisor.run([SubagentTask("one"), SubagentTask("two")])

    duplicate_budget = SubagentBudget(max_children=2)
    duplicate = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=lambda _assignment: SubagentWorkerOutput("", 0),
        budget=duplicate_budget,
    )
    with pytest.raises(ValueError, match="unique"):
        duplicate.run(
            [
                SubagentTask("one", task_id="same"),
                SubagentTask("two", task_id="same"),
            ]
        )


def test_diagnostic_role_does_not_receive_shell_execution():
    assignment = SubagentSupervisor(
        parent_callable_tools={"read_file", "run_shell"},
        effective_permissions={"read_file": "allow", "run_shell": "allow"},
        worker=lambda _assignment: SubagentWorkerOutput("", 0),
    ).prepare(
        SubagentTask(
            "diagnose tests",
            role=SubagentRole.TEST_DIAGNOSTIC,
            requested_tools=("read_file", "run_shell"),
        )
    )

    assert assignment.callable_tools == ("read_file",)
    assert dict(assignment.unavailable_tools)["run_shell"] == "not allowed for child role"


class _ChildRuntime:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, model, messages, tools=None, options=None, think=None):
        self.calls.append({"model": model, "messages": messages, "tools": tools})
        return self.responses.pop(0)


def test_agent_adapter_uses_isolated_context_and_subagent_scope():
    runtime = _ChildRuntime([{"role": "assistant", "content": "Found src/router.py."}])
    parent = Agent(
        runtime,
        "test-model",
        [],
        PermissionGate({}, lambda *_args: "n"),
        "parent system",
        max_steps=20,
    )
    parent.messages.append({"role": "user", "content": "private prior conversation"})
    assignment = SubagentSupervisor(
        parent_callable_tools=(),
        effective_permissions={},
        worker=lambda _assignment: SubagentWorkerOutput("", 0),
    ).prepare(SubagentTask("Inspect routing", context="Focus on selection."))

    output = run_agent_assignment(parent, assignment)

    assert output.summary == "Found src/router.py."
    assert output.model_steps == 1
    request = runtime.calls[0]
    rendered = "\n".join(str(message["content"]) for message in request["messages"])
    assert "Role: read_research." in rendered
    assert "Objective:\nInspect routing" in rendered
    assert "Bounded context:\nFocus on selection." in rendered
    assert "private prior conversation" not in rendered
    assert request["tools"] == []


def test_agent_supervision_charges_successful_child_usage_to_parent(monkeypatch):
    parent = Agent(
        _ChildRuntime([]),
        "test-model",
        [],
        PermissionGate({"read_file": "allow"}, lambda *_args: "n"),
        "system",
        max_steps=10,
    )
    parent.last_turn_capabilities = {"callable_tools": ["read_file", "write_file"]}
    parent.active_turn_governor = TurnGovernor(10, max_tool_calls=20)
    assert parent.active_turn_governor.begin_model_step() == ""
    seen = []

    def run_child(_parent, assignment):
        seen.append(assignment)
        return SubagentWorkerOutput(
            "finding",
            model_steps=2,
            tool_calls=1,
            tools_used=("read_file",),
        )

    monkeypatch.setattr("klaude_core.subagents.run_agent_assignment", run_child)
    result = supervise_agent_tasks(
        parent,
        [SubagentTask("inspect", requested_tools=("read_file", "write_file"))],
    )[0]

    assert result.status is SubagentStatus.COMPLETED
    assert seen[0].callable_tools == ("read_file",)
    assert parent.active_turn_governor.snapshot().model_steps_used == 3
    assert parent.active_turn_governor.snapshot().tool_calls_used == 1
    assert parent.last_turn_budget["model_steps_used"] == 3
