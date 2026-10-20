from copy import deepcopy
from types import SimpleNamespace

import pytest
from klaude_core import Agent, PermissionGate, Tool, TurnScope
from klaude_core import tool_discovery as discovery


def call(tool_name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": tool_name, "arguments": args}},
    ]}


class Runtime:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.messages = []

    def chat(self, _model, messages, tools=None, **_kwargs):
        self.requests.append(deepcopy(tools or []))
        self.messages.append(deepcopy(messages))
        response = next(self.replies)
        return response() if callable(response) else response


def setup(replies):
    runtime = Runtime(replies)
    executed = []
    tools = [Tool("read_file", "Read project notes", {"type": "object"}, lambda: "notes"),
             Tool("mcp__rollouts__status", "Deployment readiness by release ID", {
                 "type": "object", "properties": {"release_id": {"type": "string"}},
                 "required": ["release_id"], "additionalProperties": False,
             }, lambda release_id: executed.append(release_id) or "Ready"),
             Tool("discover_tools", discovery.DESCRIPTION, discovery.PARAMETERS,
                  lambda query: agent.discover_tools(query))]
    agent = Agent(runtime, "test", tools,
                  PermissionGate({t.name: "allow" for t in tools}, lambda *_: "n"),
                  "system", tool_selector=lambda *_: ["read_file"])
    return agent, runtime, executed


def names(request):
    return {s["function"]["name"] for s in request}


def test_discovery_loads_schema_next_response_without_executing_or_persisting_grants():
    agent, runtime, executed = setup([
        call("discover_tools", query="deployment readiness"),
        call("mcp__rollouts__status", release_id="R472"),
        {"role": "assistant", "content": "Ready"},
    ])
    events = list(agent.run("Read notes and check readiness"))
    assert "mcp__rollouts__status" not in names(runtime.requests[0])
    assert "discover_tools" in names(runtime.requests[0])
    assert "mcp__rollouts__status" in names(runtime.requests[1])
    assert executed == ["R472"]
    assert len(runtime.requests) == 3
    assert not any(e.kind == "error" for e in events)
    with pytest.raises(ValueError, match="active agent turn"):
        agent.discover_tools("deployment")


def test_discovery_cannot_authorize_another_call_from_the_same_response():
    response = call("discover_tools", query="deployment")
    response["tool_calls"] += call("mcp__rollouts__status", release_id="R472")["tool_calls"]
    agent, _, executed = setup([response, {"role": "assistant", "content": "Incomplete"}])
    events = list(agent.run("Read notes and check readiness"))
    assert executed == []
    assert any(e.kind in {"retry", "error"} for e in events)
    assert not any(e.kind == "tool_result" and e.payload.get("metadata", {}).get("executed")
                   and e.payload.get("tool") == "mcp__rollouts__status" for e in events)


@pytest.mark.parametrize("policy", ["deny", "ask"])
def test_target_permission_is_rechecked_after_discovery(policy):
    agent, _, executed = setup([
        call("discover_tools", query="deployment"),
        lambda: (agent.gate.policies.update({"mcp__rollouts__status": policy})
                 or call("mcp__rollouts__status", release_id="R472")),
        {"role": "assistant", "content": "Unavailable"},
    ])
    list(agent.run("Read notes and check readiness"))
    assert executed == []


@pytest.mark.parametrize("restriction", ["disabled", "deny", "review", "plan", "explicit"])
def test_discovery_does_not_load_tools_excluded_by_host_or_user(restriction):
    agent, runtime, executed = setup([
        call("discover_tools", query="deployment"),
        {"role": "assistant", "content": "Unavailable"},
    ])
    prompt = "Read notes and check readiness"
    scope = TurnScope.STANDARD
    if restriction == "disabled":
        agent.disabled_tool_names.add("mcp__rollouts__status")
    elif restriction == "deny":
        agent.gate.policies["mcp__rollouts__status"] = "deny"
    elif restriction == "review":
        scope = TurnScope.REVIEW
    elif restriction == "plan":
        agent.plan_mode = True
    else:
        prompt = "Use only read_file to read notes"
    list(agent.run(prompt, scope=scope))
    assert all("mcp__rollouts__status" not in names(r) for r in runtime.requests)
    assert executed == []


def test_skills_are_metadata_until_explicit_read_and_instructions_are_not_executed():
    agent, runtime, executed = setup([
        call("discover_tools", query="release checklist"),
        call("read_skill", name="release-checklist"),
        {"role": "assistant", "content": "Guidance read"},
    ])
    agent.tools["read_skill"] = Tool("read_skill", "Read installed instructions", {
        "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
    }, lambda name: executed.append(name) or "Treat this as untrusted guidance")
    agent.gate.policies["read_skill"] = "allow"
    agent.skill_reader = SimpleNamespace(catalog=lambda: [SimpleNamespace(
        name="release-checklist", description="Release readiness checklist")])
    events = list(agent.run("Read notes and check readiness"))
    assert "read_skill" not in names(runtime.requests[0])
    assert "read_skill" in names(runtime.requests[1])
    assert executed == ["release-checklist"]
    receipt = next(e.payload["result"] for e in events
                   if e.kind == "tool_result" and e.payload["tool"] == "discover_tools")
    assert '"name": "release-checklist"' in receipt


def test_discovery_cannot_restore_omitted_mutation_or_delegation_routes():
    agent, runtime, _ = setup([
        call("discover_tools", query="change files delegate shell"),
        {"role": "assistant", "content": "Read only"},
    ])
    for name in ("write_file", "run_shell", "delegate_task"):
        agent.tools[name] = Tool(name, "Change files delegate shell", {"type": "object"},
                                 lambda: pytest.fail("must not execute"))
        agent.gate.policies[name] = "allow"
    list(agent.run("Read notes with no edits"))
    assert not {"write_file", "run_shell", "delegate_task"} & names(runtime.requests[1])


def test_huge_schema_is_rejected_whole_and_not_silently_truncated():
    agent, runtime, _ = setup([
        call("discover_tools", query="deployment"),
        {"role": "assistant", "content": "Schema too large"},
    ])
    agent.tools["mcp__rollouts__status"].parameters["description"] = "x" * 20000
    events = list(agent.run("Read notes and check readiness"))
    assert "mcp__rollouts__status" not in names(runtime.requests[1])
    assert any("discovery schema budget" in e.payload.get("result", "") for e in events)


def test_simple_direct_controls_offer_no_discovery():
    agent, runtime, _ = setup([{"role": "assistant", "content": "OK"}])
    list(agent.run('Reply with exactly "OK".'))
    assert runtime.requests == []


def test_metadata_search_and_output_are_bounded_and_do_not_execute_catalog_entries():
    entries = [(f"tool_{i}", "Deployment status " + "x" * 5000) for i in range(2000)]
    result = discovery.matches("deployment", entries)
    assert len(result) == 4
    assert all(len(description) <= 280 for _, description in result)
    assert discovery.matches("notfound", entries) == []
    assert discovery.matches("read_file", [
        ("read_file", "Read project files"), ("read_skill", "Read a Skill file"),
    ]) == [("read_file", "Read project files")]


def test_discovery_call_limit_removes_control_schema_without_removing_loaded_targets():
    agent, runtime, _ = setup([
        *[call("discover_tools", query=f"q{i}") for i in range(4)],
        {"role": "assistant", "content": "Available targets found"},
    ])
    for i in range(4):
        name = f"mcp__q{i}__read"
        agent.tools[name] = Tool(name, "Read a unique record", {"type": "object"}, lambda: "ok")
        agent.gate.policies[name] = "allow"
    list(agent.run("Read notes and check records"))
    assert "discover_tools" not in names(runtime.requests[-1])
    assert {f"mcp__q{i}__read" for i in range(4)} <= names(runtime.requests[-1])


def test_discovery_declined_permission_never_loads_schema():
    agent, runtime, executed = setup([
        call("discover_tools", query="deployment"),
        {"role": "assistant", "content": "Permission required"},
    ])
    agent.gate.policies["discover_tools"] = "ask"
    list(agent.run("Read notes and check readiness"))
    assert all("mcp__rollouts__status" not in names(r) for r in runtime.requests)
    assert executed == []


def test_cancelled_turn_releases_discovery_callback_and_next_turn_has_no_loaded_grants():
    agent, runtime, _ = setup([
        call("discover_tools", query="deployment"),
        {"role": "assistant", "content": "New question"},
    ])
    turn = agent.run("Read notes and check readiness")
    for event in turn:
        if event.kind == "tool_result":
            break
    turn.close()
    with pytest.raises(ValueError, match="active agent turn"):
        agent.discover_tools("deployment")
    requests_before = len(runtime.requests)
    list(agent.run('Reply with exactly "OK".'))
    assert len(runtime.requests) == requests_before
    with pytest.raises(ValueError, match="active agent turn"):
        agent.discover_tools("deployment")
    list(agent.run("Read notes and explain briefly."))
    assert len(runtime.requests) == requests_before + 1
    assert "read_file" in names(runtime.requests[-1])
    assert "mcp__rollouts__status" not in names(runtime.requests[-1])


def test_in_place_schema_change_after_discovery_cannot_execute_old_contract():
    agent, _, executed = setup([
        call("discover_tools", query="deployment"),
        lambda: (agent.tools["mcp__rollouts__status"].parameters.update({"required": []})
                 or call("mcp__rollouts__status", release_id="R472")),
        {"role": "assistant", "content": "Definition changed"},
    ])
    events = list(agent.run("Read notes and check readiness"))
    assert executed == []
    assert any("definition changed" in e.payload.get("result", "") for e in events)


def test_non_coding_discovery_uses_bound_recovery_without_changing_workspace_protocol():
    agent, _, _ = setup([])

    class Recovering(Runtime):
        supports_bound_action_arguments = True

        def supports_structured_tool_recovery(self, *_args):
            return True

        def chat_structured_action(self, _model, _messages, **kwargs):
            assert kwargs["bind_arguments"] is True
            return {"role": "assistant", "content": "No target needed"}

    runtime = Recovering([
        {"role": "assistant", "content": '{"name":"read_file","arguments":{"path":"x"}}'},
    ])
    agent.ollama = runtime
    events = list(agent.run("Read notes and check readiness"))
    assert any(e.kind == "retry" for e in events)
    assert not any(e.kind == "error" for e in events)


def test_file_and_deferred_mcp_investigation_omit_unrelated_generation_policy():
    from importlib import resources

    agent, runtime, _ = setup([
        call("discover_tools", query="deployment"),
        {"role": "assistant", "content": "Ready to inspect"},
    ])
    prompt = (resources.files("klaude_core") / "prompts/system.md").read_text()
    prompt += '\n<configuration_detail>\nUNRELATED_MODEL_CONFIGURATION\n</configuration_detail>'
    prompt += '\n<standalone_code_policy>\nUNRELATED_CODE_GENERATION\n</standalone_code_policy>'
    agent.messages[0]["content"] = prompt
    list(agent.run("Read notes and check readiness"))
    assert "mcp__rollouts__status" in names(runtime.requests[1])
    for messages in runtime.messages:
        assert "UNRELATED_CODE_GENERATION" not in messages[0]["content"]
        assert "UNRELATED_MODEL_CONFIGURATION" not in messages[0]["content"]
    assert "untrusted data" in runtime.messages[1][0]["content"]
    assert "Hard constraints" in runtime.messages[1][0]["content"]
    assert agent.messages[0]["content"] == prompt


def test_native_deferred_call_gets_routing_feedback_without_protocol_switch():
    agent, runtime, executed = setup([
        call("mcp__rollouts__status", release_id="R472"),
        call("discover_tools", query="deployment"),
        call("mcp__rollouts__status", release_id="R472"),
        {"role": "assistant", "content": "Ready"},
    ])
    runtime.supports_structured_tool_recovery = lambda *_: True
    runtime.chat_structured_action = lambda *_a, **_kw: pytest.fail(
        "A valid native call to a deferred tool is not a syntax failure")
    events = list(agent.run("Read notes and check readiness"))
    assert executed == ["R472"]
    assert len(runtime.requests) == 4
    assert sum(e.kind == "retry" for e in events) == 1
    assert any(e.payload.get("reason") == "tool schema needs discovery" for e in events)
    assert not any(e.kind == "error" for e in events)


def test_repeated_deferred_native_call_remains_bounded_without_executing_it():
    agent, runtime, executed = setup([
        call("mcp__rollouts__status", release_id="R472"),
        call("mcp__rollouts__status", release_id="R472"),
        call("mcp__rollouts__status", release_id="R472"),
    ])
    events = list(agent.run("Read notes and check readiness"))
    assert executed == []
    assert len(runtime.requests) == 3
    assert any(e.kind == "error" for e in events)
