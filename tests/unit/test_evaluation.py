from klaude_core import Agent, EvaluationScenario, PermissionGate, Tool, evaluate_agent_turn


class Runtime:
    backend = "test"

    def __init__(self, responses, metadata=None):
        self.responses = iter(responses)
        self.last_chat_metadata = metadata or {}

    def chat(self, *_args, **_kwargs):
        return next(self.responses)


def call(name, **arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


def test_evaluation_records_completion_and_normalized_usage_without_answer_text():
    runtime = Runtime(
        [{"role": "assistant", "content": "A private but complete answer."}],
        {"usage": {"input_tokens": 12, "output_tokens": 7}},
    )
    agent = Agent(runtime, "model", [], PermissionGate({}, lambda *_: "n"), "system")

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario("direct", "Explain this"),
        model_ref="test/model",
    )

    payload = result.to_dict()
    assert result.success is True
    assert result.completed is True
    assert result.answer_characters == len("A private but complete answer.")
    assert len(result.answer_sha256) == 64
    assert (result.input_tokens, result.output_tokens) == (12, 7)
    assert result.model_requests == 1
    assert "private but complete" not in str(payload)


def test_evaluation_counts_permissions_and_flags_forbidden_tool_execution():
    runtime = Runtime(
        [
            call("read_file"),
            {"role": "assistant", "content": "Inspected it."},
        ]
    )
    tool = Tool("read_file", "read", {}, lambda: "contents")
    agent = Agent(
        runtime,
        "model",
        [tool],
        PermissionGate({"read_file": "ask"}, lambda *_: "y"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario(
            "safety",
            "Inspect",
            expected_any_tools=("read_file",),
            forbidden_tools=("read_file",),
        ),
        model_ref="test/model",
    )

    assert result.success is False
    assert result.permission_prompts == 1
    assert result.permission_denials == 0
    assert result.tools_started == ["read_file"]
    assert result.tools_completed == ["read_file"]
    assert result.tools_succeeded == ["read_file"]
    assert result.safety_violations == ["forbidden_tool:read_file"]


def test_permission_decision_observer_failure_never_changes_policy_result():
    gate = PermissionGate({"inspect": "ask"}, lambda *_: "y")
    gate.set_decision_observer(
        lambda *_: (_ for _ in ()).throw(RuntimeError("telemetry failed"))
    )

    gate.check("inspect", "safe detail")


def test_evaluation_distinguishes_saved_policy_denial_from_a_prompt():
    runtime = Runtime(
        [
            call("read_file"),
            {"role": "assistant", "content": "The configured policy denied inspection."},
        ]
    )
    agent = Agent(
        runtime,
        "model",
        [Tool("read_file", "read", {}, lambda: "must not run")],
        PermissionGate({"read_file": "deny"}, lambda *_: "y"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario(
            "denied",
            "Inspect",
            expected_any_tools=("read_file",),
            forbidden_tools=(),
        ),
        model_ref="test/model",
    )

    assert result.success is False
    assert result.permission_prompts == 0
    assert result.permission_denials == 0
    assert result.tools_started == []
    assert result.tools_completed == []


def test_evaluation_counts_declined_ask_policy_once():
    runtime = Runtime(
        [
            call("read_file"),
            {"role": "assistant", "content": "The user declined inspection."},
        ]
    )
    agent = Agent(
        runtime,
        "model",
        [Tool("read_file", "read", {}, lambda: "must not run")],
        PermissionGate({"read_file": "ask"}, lambda *_: "n"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario(
            "declined",
            "Inspect",
            expected_any_tools=("read_file",),
            forbidden_tools=(),
        ),
        model_ref="test/model",
    )

    assert result.success is False
    assert result.permission_prompts == 1
    assert result.permission_denials == 1
    assert result.tool_failures == 1
    assert result.tools_started == ["read_file"]
    assert result.tools_completed == ["read_file"]
    assert result.tools_succeeded == []
