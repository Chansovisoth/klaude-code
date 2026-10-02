"""Tool contracts and isolated naming experiments preserve execution boundaries."""

from copy import deepcopy

import pytest
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.agent import _validate_tool_arguments
from klaude_core.evaluation_interfaces import configure_knowledge_interface
from klaude_core.knowledge_tool_contract import (
    KNOWLEDGE_TOOL_DESCRIPTION,
    knowledge_tool_parameters,
    normalize_knowledge_arguments,
)


def test_local_knowledge_schema_has_one_required_query_and_optional_library():
    schema = knowledge_tool_parameters()
    assert schema["required"] == ["query"]
    assert set(schema["properties"]) == {"query", "library"}
    assert schema["additionalProperties"] is False
    assert "live web" in KNOWLEDGE_TOOL_DESCRIPTION
    for arguments in ({}, {"query": ""}, {"query": 3}, {"query": "x", "unknown": "x"}):
        with pytest.raises(ValueError):
            _validate_tool_arguments(arguments, schema)
    _validate_tool_arguments({"query": "movement examples"}, schema)
    _validate_tool_arguments({"query": "movement examples", "library": "godot-2d"}, schema)


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (
            {"question": " movement ", "collection": "godot"},
            {"query": "movement", "library": "godot"},
        ),
        (
            {"question": "old", "query": "new", "library": "a", "collection": "b"},
            {"query": "old", "library": "a"},
        ),
        (
            {"question": "", "query": "new", "library": "", "collection": "b"},
            {"query": "new", "library": "b"},
        ),
    ],
)
def test_legacy_arguments_keep_existing_precedence_and_do_not_mutate_input(arguments, expected):
    saved = deepcopy(arguments)
    assert normalize_knowledge_arguments(arguments) == expected
    assert arguments == saved


class Runtime:
    last_chat_metadata = {}

    def __init__(self, arguments, wire_name="query_knowledge", *, always_call=False):
        self.arguments = arguments
        self.wire_name = wire_name
        self.always_call = always_call
        self.requests = []

    def chat(self, model, messages, **kwargs):
        self.requests.append((deepcopy(messages), deepcopy(kwargs)))
        if len(self.requests) == 1 or self.always_call:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": self.wire_name, "arguments": self.arguments}}],
            }
        return {"role": "assistant", "content": "The local document says 17 minutes."}


def make_agent(runtime, execute, policy="allow"):
    tool = Tool("query_knowledge", KNOWLEDGE_TOOL_DESCRIPTION, knowledge_tool_parameters(), execute)
    return Agent(
        runtime,
        "fake",
        [tool],
        PermissionGate({"query_knowledge": policy}, lambda *_: "n"),
        "system",
        max_steps=3,
    )


def test_legacy_model_arguments_normalize_before_validation_permission_and_execution():
    observed = []
    agent = make_agent(
        Runtime({"question": " movement ", "collection": "godot"}),
        lambda **args: observed.append(args) or "found source",
    )
    approvals = []
    agent.gate.check = lambda name, detail: approvals.append((name, detail))
    events = list(agent.run("Search the local knowledge for movement."))
    assert observed == [{"query": "movement", "library": "godot"}]
    assert approvals[0][0] == "query_knowledge"
    assert "question" not in approvals[0][1]
    start = next(event for event in events if event.kind == "tool_start")
    assert start.payload["args"] == observed[0]


@pytest.mark.parametrize(
    "arguments", [{}, {"query": "   "}, {"question": 42}, {"query": "x", "unexpected": "x"}]
)
def test_invalid_retrieval_arguments_never_reach_permission_or_execution(arguments):
    agent = make_agent(Runtime(arguments), lambda **_: pytest.fail("Invalid call executed"))
    agent.gate.check = lambda *_: pytest.fail("Invalid call requested approval")
    events = list(agent.run("Search local documentation."))
    results = [event for event in events if event.kind == "tool_result"]
    assert results and all(not event.payload["metadata"]["executed"] for event in results)


def test_candidate_name_roundtrip_retains_canonical_permissions_audits_and_history():
    runtime = Runtime({"query": "beacon interval"}, "search_local_knowledge")
    executed = []
    agent = make_agent(runtime, lambda **args: executed.append(args) or "17 minutes")
    configure_knowledge_interface(agent, "name")
    events = list(agent.run("Use only query_knowledge to find the beacon interval."))
    assert executed == [{"query": "beacon interval"}]
    assert runtime.requests[0][1]["tools"][0]["function"]["name"] == "search_local_knowledge"
    assert any(
        message.get("content") == "Use only query_knowledge to find the beacon interval."
        for message in runtime.requests[0][0]
    )
    assert any(
        message.get("tool_name") == "search_local_knowledge" for message in runtime.requests[1][0]
    )
    assert all(
        event.payload["tool"] == "query_knowledge"
        for event in events
        if event.kind in {"tool_start", "tool_result"}
    )
    assert any(message.get("tool_name") == "query_knowledge" for message in agent.messages)
    assert set(agent.tools) == {"query_knowledge"}
    assert agent.last_turn_capabilities["callable_tools"] == ["query_knowledge"]


@pytest.mark.parametrize("boundary", ["deny", "disabled", "no-tools"])
def test_name_experiment_cannot_bypass_canonical_tool_boundaries(boundary):
    runtime = Runtime({"query": "beacons"}, "search_local_knowledge", always_call=True)
    agent = make_agent(
        runtime,
        lambda **_: pytest.fail("Forbidden tool executed"),
        policy="deny" if boundary == "deny" else "allow",
    )
    if boundary == "disabled":
        agent.disabled_tool_names = {"query_knowledge"}
    configure_knowledge_interface(agent, "name")
    prompt = (
        "Search learned documents." if boundary != "no-tools" else "Answer without calling tools."
    )
    events = list(agent.run(prompt))
    assert all(not request[1]["tools"] for request in runtime.requests)
    assert not any(
        event.kind == "tool_result" and event.payload["metadata"].get("executed")
        for event in events
    )


def test_description_experiment_changes_only_description():
    agent = make_agent(Runtime({"query": "x"}), lambda **_: "x")
    configure_knowledge_interface(agent, "baseline")
    before = agent.tools["query_knowledge"].schema()
    configure_knowledge_interface(agent, "description")
    after = agent.tools["query_knowledge"].schema()
    assert before["function"]["parameters"] == after["function"]["parameters"]
    assert before["function"]["name"] == after["function"]["name"]
    assert before["function"]["description"] != after["function"]["description"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "valid", "question": None},
        {"query": 3, "question": "valid"},
        {"query": "valid", "library": "godot", "collection": []},
        {"query": "valid", "library": False, "collection": "godot"},
    ],
)
def test_malformed_aliases_cannot_hide_behind_valid_preferred_fields(arguments):
    agent = make_agent(Runtime(arguments), lambda **_: pytest.fail("Malformed call executed"))
    agent.gate.check = lambda *_: pytest.fail("Malformed call requested approval")
    results = [
        event for event in agent.run("Search local knowledge.") if event.kind == "tool_result"
    ]
    assert results and all(not event.payload["metadata"]["executed"] for event in results)


def test_name_experiment_preserves_user_and_evidence_content_and_streams_canonical_calls():
    runtime = Runtime({}, "search_local_knowledge")
    agent = make_agent(runtime, lambda **_: "x")
    configure_knowledge_interface(agent, "name")
    messages = [
        {"role": "user", "content": "Quote query_knowledge exactly."},
        {
            "role": "tool",
            "tool_name": "query_knowledge",
            "content": "https://example.org/query_knowledge explains query_knowledge.",
        },
    ]
    original = deepcopy(messages)
    runtime.chat_stream = lambda model, messages, **kwargs: iter(
        [runtime.chat(model, messages, **kwargs)]
    )
    fragments = list(
        agent.ollama.chat_stream("fake", messages, tools=[agent.tools["query_knowledge"].schema()])
    )
    assert messages == original
    sent = runtime.requests[0][0]
    assert [message["content"] for message in sent[1:]] == [
        message["content"] for message in original
    ]
    assert sent[2]["tool_name"] == "search_local_knowledge"
    assert fragments[0]["tool_calls"][0]["function"]["name"] == "query_knowledge"


def test_interface_switching_restores_original_contract_and_runtime():
    runtime = Runtime({"query": "x"})
    agent = make_agent(runtime, lambda **_: "x")
    original = agent.tools["query_knowledge"]
    for variant in ("name", "name", "baseline", "name", "description", "schema", "current"):
        configure_knowledge_interface(agent, variant)
        if variant == "name":
            assert agent.ollama.runtime is runtime
        else:
            assert agent.ollama is runtime
        assert agent.runtime is agent.ollama
    assert agent.tools["query_knowledge"] is original


def test_cloud_name_experiment_is_rejected_without_changing_agent():
    runtime = Runtime({"query": "x"})
    runtime.backend = "openrouter"
    agent = make_agent(runtime, lambda **_: "x")
    original = agent.tools["query_knowledge"]
    with pytest.raises(ValueError, match="only Ollama"):
        configure_knowledge_interface(agent, "name")
    assert agent.ollama is runtime and agent.runtime is runtime
    assert agent.tools["query_knowledge"] is original
