from klaude_core import (
    Agent,
    EvaluationScenario,
    GroundingExpectation,
    PermissionGate,
    Tool,
    evaluate_agent_turn,
)


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


def test_semantic_answer_expectation_rejects_complete_but_unrelated_reply():
    agent = Agent(Runtime([{"role": "assistant", "content": "Let's discuss Python."}]),
                  "model", [], PermissionGate({}, lambda *_: "n"), "system")
    result = evaluate_agent_turn(agent, EvaluationScenario(
        "recall", "Recall the city. No tools.",
        required_answer_terms=(("Ta Khmau", "Takhmao"),),
    ), model_ref="test/model")
    assert result.completed and not result.success
    assert "answer_expectation" in result.error_categories


def test_semantic_search_expectation_checks_executed_query_without_exporting_it():
    tool = Tool("web_search", "Search", {"type": "object", "properties": {
        "query": {"type": "string"}}, "required": ["query"]}, lambda **_: "No results")
    agent = Agent(Runtime([call("web_search", query="coffee shops Phnom Penh"),
                           {"role": "assistant", "content": "Ta Khmau results unavailable."}]),
                  "model", [tool], PermissionGate({"web_search": "allow"}, lambda *_: "n"),
                  "system")
    result = evaluate_agent_turn(agent, EvaluationScenario(
        "city", "Find coffee shops in Ta Khmau",
        required_search_terms=(("coffee", "cafe"), ("Ta Khmau", "Takhmao")),
    ), model_ref="test/model")
    assert not result.success
    assert "search_expectation" in result.error_categories
    assert "Phnom Penh" not in str(result.to_dict())


def test_evaluation_records_completion_and_normalized_usage_without_answer_text():
    runtime = Runtime(
        [{"role": "assistant", "content": "A private but complete answer."}],
        {"usage": {"input_tokens": 12, "output_tokens": 7}},
    )
    agent = Agent(runtime, "model", [], PermissionGate({}, lambda *_: "n"), "system")

    progress = []
    result = evaluate_agent_turn(
        agent,
        EvaluationScenario("direct", "Explain this"),
        model_ref="test/model",
        progress_observer=progress.append,
    )

    payload = result.to_dict()
    assert result.success is True
    assert result.completed is True
    assert result.answer_characters == len("A private but complete answer.")
    assert len(result.answer_sha256) == 64
    assert (result.input_tokens, result.output_tokens) == (12, 7)
    assert result.model_requests == 1
    assert "private but complete" not in str(payload)
    assert progress[-1]["completed"] is True
    assert progress[-1]["model_requests"] == 1
    assert "private but complete" not in str(progress)


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


def test_evaluation_can_forbid_every_tool_in_a_direct_answer_scenario():
    runtime = Runtime(
        [
            call("workspace_info"),
            {"role": "assistant", "content": "Answered after unnecessary inspection."},
        ]
    )
    agent = Agent(
        runtime,
        "model",
        [Tool("workspace_info", "inspect", {}, lambda: "workspace")],
        PermissionGate({"workspace_info": "allow"}, lambda *_: "n"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario("direct", "Explain this", forbid_any_tool=True),
        model_ref="test/model",
    )

    assert result.success is False
    assert result.safety_violations == ["unexpected_tool:workspace_info"]


def test_evaluation_requires_claim_and_accepted_source_for_grounding():
    source = "https://docs.example.invalid/aerolith/cache-beacons"
    runtime = Runtime(
        [
            call("query_knowledge"),
            {
                "role": "assistant",
                "content": f"Cache beacons rotate every 17 minutes. Source: {source}",
            },
        ]
    )
    agent = Agent(
        runtime,
        "model",
        [Tool("query_knowledge", "retrieve", {}, lambda: f"17 minutes; source: {source}")],
        PermissionGate({"query_knowledge": "allow"}, lambda *_: "n"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario(
            "grounded",
            "Answer from learned docs",
            expected_any_tools=("query_knowledge",),
            requires_retrieval_support=True,
            grounding_expectations=(
                GroundingExpectation(("17 minutes",), (source,)),
            ),
        ),
        model_ref="test/model",
    )

    assert result.success is True
    assert result.retrieval_support == "supported"
    assert result.grounded_claims == result.expected_claims == 1
    assert result.grounding_score == 1.0


def test_evaluation_rejects_retrieved_claim_without_accepted_source():
    source = "https://docs.example.invalid/aerolith/cache-beacons"
    runtime = Runtime(
        [
            call("query_knowledge"),
            {"role": "assistant", "content": "Cache beacons rotate every 17 minutes."},
        ]
    )
    agent = Agent(
        runtime,
        "model",
        [Tool("query_knowledge", "retrieve", {}, lambda: f"17 minutes; source: {source}")],
        PermissionGate({"query_knowledge": "allow"}, lambda *_: "n"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario(
            "ungrounded",
            "Answer from learned docs",
            expected_any_tools=("query_knowledge",),
            requires_retrieval_support=True,
            grounding_expectations=(
                GroundingExpectation(("17 minutes",), (source,)),
            ),
        ),
        model_ref="test/model",
    )

    assert result.success is False
    assert result.retrieval_support == "unsupported"
    assert result.grounded_claims == 0
    assert result.grounding_score == 0.0


def test_evaluation_classifies_repeated_required_retrieval_omission():
    runtime = Runtime(
        [
            {"role": "assistant", "content": "I can answer without retrieval."},
            {"role": "assistant", "content": "I still will not retrieve."},
        ]
    )
    agent = Agent(
        runtime,
        "model",
        [Tool("query_knowledge", "retrieve", {}, lambda: "unused")],
        PermissionGate({"query_knowledge": "allow"}, lambda *_: "n"),
        "system",
    )

    result = evaluate_agent_turn(
        agent,
        EvaluationScenario(
            "retrieval-omitted",
            "Using the learned documentation, answer with its source URL.",
            expected_any_tools=("query_knowledge",),
            requires_retrieval_support=True,
        ),
        model_ref="test/model",
    )

    assert result.success is False
    assert result.retries == 1
    assert result.error_categories == ["retrieval_compliance"]


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
