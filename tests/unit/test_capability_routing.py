from types import SimpleNamespace

import pytest
from klaude_cli.main import (
    _agent_context_window,
    _configured_mcp_tools,
    _select_tool_names,
    _system_prompt,
)
from klaude_cli.skill_runtime import InstalledSkillReader
from klaude_core import Agent, Memory, PermissionGate, Tool
from klaude_core.mcp_client import MCPServerConfig, namespaced_tool_name


class ScriptedRuntime:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, _model, messages, tools=None, **_kwargs):
        self.requests.append({"messages": messages, "tools": tools})
        return self.responses.pop(0)


@pytest.mark.parametrize("fenced", [False, True])
def test_printed_json_tool_envelope_gets_one_native_retry_without_execution(fenced):
    envelope = '{"name":"read_file","arguments":{"path":"/invented/path"}}'
    if fenced:
        envelope = "```json\n" + envelope + "\n```"
    calls = []
    runtime = ScriptedRuntime([
        {"role": "assistant", "content": envelope},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "read_file", "arguments": {"path": "README.md"},
        }}]},
        {"role": "assistant", "content": "The title is Stockroom."},
    ])
    tool = Tool("read_file", "Read project files", {"type": "object", "properties": {
        "path": {"type": "string"}}, "required": ["path"]},
        lambda path: calls.append(path) or "# Stockroom")
    agent = Agent(runtime, "local-model", [tool],
        PermissionGate({"read_file": "allow"}, lambda *_: "n"), "system")

    events = list(agent.run("Read the project README"))

    assert calls == ["README.md"]
    assert [event.kind for event in events].count("retry") == 1
    assert all("/invented/path" not in str(event.payload) for event in events)
    assert "native structured call" in runtime.requests[1]["messages"][-1]["content"]


def test_repeated_printed_json_call_fails_without_executing_or_claiming_success():
    envelope = '{"name":"read_file","arguments":{"path":"README.md"}}'
    runtime = ScriptedRuntime([{"role": "assistant", "content": envelope}] * 2)
    tool = Tool("read_file", "Read", {"type": "object"},
        lambda **_: pytest.fail("printed JSON must not execute"))
    agent = Agent(runtime, "local-model", [tool],
        PermissionGate({"read_file": "allow"}, lambda *_: "n"), "system")
    events = list(agent.run("Read README.md"))
    assert [event.kind for event in events] == ["retry", "error"]
    assert not any(message.get("content") == envelope for message in agent.messages)


@pytest.mark.parametrize("content,select_tools", [
    ('Example:\n```json\n{"name":"read_file","arguments":{"path":"README.md"}}\n```', True),
    ('{"name":"record","arguments":{"description":"data"}}', True),
    ('{"name":"read_file","arguments":{"path":"README.md"}}', False),
])
def test_json_examples_and_no_tool_answers_remain_text(content, select_tools):
    runtime = ScriptedRuntime([{"role": "assistant", "content": content}])
    tool = Tool("read_file", "Read", {"type": "object"}, lambda **_: "unused")
    agent = Agent(runtime, "local-model", [tool],
        PermissionGate({"read_file": "allow"}, lambda *_: "n"), "system",
        tool_selector=lambda *_: ["read_file"] if select_tools else [])
    events = list(agent.run("Show a JSON example"))
    assert [event.kind for event in events] == ["text", "done"]
    assert events[0].payload["content"] == content


def test_long_system_prose_does_not_erase_the_plan_of_a_code_continuation():
    agent = Agent(object(), "local-model", [], PermissionGate({}, lambda *_: "n"),
                  "Use supplied tools and preserve the workspace. " * 450,
                  ollama_options={"num_ctx": 8192, "num_predict": 2048})
    objective = "Plan atomic stock persistence while retaining CLI behavior."
    plan = "Write a sibling temporary file, then replace the stock file atomically."
    agent.messages.extend([
        {"role": "user", "content": objective},
        {"role": "assistant", "content": plan},
        {"role": "user", "content": "Go ahead with that plan."},
    ])
    agent._compact_history([{"schema": "dense parameters " * 245}],
                           ollama_options={"num_ctx": 16384, "num_predict": 4096})
    dialogue = str(agent.messages[1:])
    assert objective in dialogue and plan in dialogue
    assert agent.messages[-1]["content"] == "Go ahead with that plan."


@pytest.mark.parametrize("prompt,expected", [
    ("Repair this project, inspecting state.txt and running the Python validation check.",
     {"read_file", "edit_file", "run_shell"}),
    ("Inspect src/main.py then fix the bug and run the tests.",
     {"read_file", "edit_file", "run_shell"}),
    ("Read tests/test_main.py and run the suite.", {"read_file", "run_shell"}),
])
def test_named_file_inspection_does_not_hide_other_requested_project_actions(prompt, expected):
    tools = {name: Tool(name, name, {}, lambda: "") for name in
             ("read_file", "edit_file", "write_file", "run_shell", "list_dir", "grep",
              "workspace_info", "git_commit")}
    supplied = set(_select_tool_names(prompt, tools))
    assert expected <= supplied
    assert "git_commit" not in supplied


def test_named_file_read_only_boundary_still_wins_over_implementation_words():
    tools = {name: Tool(name, name, {}, lambda: "") for name in
             ("read_file", "edit_file", "write_file", "run_shell", "list_dir")}
    selected = set(_select_tool_names(
        "Read src/main.py and explain how to fix it. Do not edit or run commands.", tools,
    ))
    assert "read_file" in selected
    assert not {"write_file", "edit_file", "run_shell"} & selected


def test_relevant_mcp_tool_schema_reaches_model_and_call_uses_its_server(tmp_path):
    calls = []
    manager = SimpleNamespace(call=lambda server, name, arguments: (
        calls.append((server.name, name, arguments)) or {"answer": "docs found"}
    ))
    cfg = SimpleNamespace(
        mcp_servers_file=tmp_path / "mcp.json", mcp_auth_dir=tmp_path,
        _mcp_client_manager=manager,
    )
    server = MCPServerConfig(
        "docs", "http", url="https://example.com/mcp",
        tools=[{"name": "search_docs", "description": "Search API documentation",
                "inputSchema": {"type": "object", "properties": {
                    "query": {"type": "string"}}, "required": ["query"]}}],
    )
    disabled = MCPServerConfig(
        "disabled", "http", enabled=False, url="https://example.com/mcp",
        tools=[{"name": "search_docs", "inputSchema": {"type": "object"}}],
    )
    available = _configured_mcp_tools(cfg, servers={"docs": server, "disabled": disabled})
    name = namespaced_tool_name("docs", "search_docs")
    assert [tool.name for tool in available] == [name]
    assert available[0].schema()["function"]["parameters"]["required"] == ["query"]

    runtime = ScriptedRuntime([
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": name, "arguments": {"query": "packaging"},
        }}]},
        {"role": "assistant", "content": "The docs cover packaging."},
    ])
    agent = Agent(
        runtime, "test-model", available,
        PermissionGate({name: "ask"}, lambda *_args: "y"), "system",
        tool_selector=_select_tool_names,
    )
    events = list(agent.run("Use the docs MCP server to search API documentation for packaging"))

    assert [item["function"]["name"] for item in runtime.requests[0]["tools"]] == [name]
    assert calls == [("docs", "search_docs", {"query": "packaging"})]
    assert any(event.kind == "tool_result" and event.payload.get("tool") == name
               for event in events)


def test_skill_instructions_load_only_after_model_calls_read_skill(tmp_path):
    skill_root = tmp_path / "skills"
    current = skill_root / "design" / "versions" / "one"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text(
        "---\ndescription: Guide for landing page design\n---\n"
        "Use a clear heading and visible primary action."
    )
    (skill_root / "design" / "manifest.json").write_text(
        '{"name":"design","current_dir":"' + str(current) + '"}'
    )
    reader = InstalledSkillReader(skill_root)
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    runtime = ScriptedRuntime([
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "read_skill", "arguments": {"name": "design"},
        }}]},
        {"role": "assistant", "content": "Use a clear heading and primary action."},
    ])
    tool = Tool(
        "read_skill", "Read a Skill", {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]}, reader.read_excerpt,
    )
    context = (
        "Installed Skills: design - Guide for landing page design. "
        "Call read_skill when relevant."
    )
    agent = Agent(
        runtime, "test-model", [tool],
        PermissionGate({"read_skill": "allow"}, lambda *_args: "n"),
        _system_prompt(memory, configuration_context=context),
        tool_selector=_select_tool_names,
    )
    events = list(agent.run("Use the design skill for a landing page"))

    first = runtime.requests[0]
    assert "Installed Skills: design" in first["messages"][0]["content"]
    assert "Use a clear heading" not in first["messages"][0]["content"]
    assert first["tools"][0]["function"]["name"] == "read_skill"
    assert any(event.kind == "tool_result" and "Use a clear heading" in event.payload["result"]
               for event in events)


def test_explicit_no_skill_read_hides_schema_even_without_a_selector():
    runtime = ScriptedRuntime([{"role": "assistant", "content": "Description unavailable."}])
    tool = Tool(
        "read_skill", "Read a Skill",
        {"type": "object", "properties": {"name": {"type": "string"}},
         "required": ["name"]},
        lambda name: "private instructions",
    )
    agent = Agent(
        runtime, "test-model", [tool],
        PermissionGate({"read_skill": "allow"}, lambda *_args: "n"),
        "system",
    )

    list(agent.run("What is its description? Do not read the Skill."))

    assert runtime.requests[0]["tools"] == []


def test_explicit_installed_guidance_gets_one_tool_call_retry(tmp_path):
    root = tmp_path / "skills"
    current = root / "coding-standards" / "current"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text(
        "---\ndescription: Use for code quality review.\n---\nCheck naming and readability."
    )
    (current.parent / "manifest.json").write_text(
        '{"name":"coding-standards","current_dir":"' + str(current) + '"}'
    )
    reader = InstalledSkillReader(root)
    runtime = ScriptedRuntime([
        {"role": "assistant", "content": "I can answer without reading."},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "read_skill", "arguments": {"name": "coding-standards"},
        }}]},
        {"role": "assistant", "content": "Check the function name and readability."},
    ])
    tool = Tool(
        "read_skill", "Read installed Skill",
        {"type": "object", "properties": {"name": {"type": "string"}},
         "required": ["name"]}, reader.read_excerpt,
    )
    agent = Agent(
        runtime, "test-model", [tool],
        PermissionGate({"read_skill": "allow"}, lambda *_args: "n"),
        "system", tool_selector=_select_tool_names,
    )

    events = list(agent.run("Review this code. Use any installed guidance that fits."))

    assert any(event.kind == "retry" and "read_skill" in event.payload["reason"]
               for event in events)
    assert any(event.kind == "tool_result" and event.payload["tool"] == "read_skill"
               for event in events)
    assert any(event.kind == "text" and "function name" in event.payload["content"]
               for event in events)


def test_named_prompt_file_is_read_before_one_shot_answer():
    calls = []
    runtime = ScriptedRuntime([
        {"role": "assistant", "content": "I cannot open the file."},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "read_file", "arguments": {"path": "challenge1.md"},
        }}]},
        {"role": "assistant", "content": "I read the prompt and can proceed."},
    ])
    tools = [
        Tool("read_file", "Read file", {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]},
             lambda path: calls.append(path) or "# Site instructions"),
        Tool("write_file", "Write file", {"type": "object"}, lambda **_kw: ""),
    ]
    agent = Agent(
        runtime, "test-model", tools,
        PermissionGate({"read_file": "allow", "write_file": "ask"}, lambda *_args: "n"),
        "system", tool_selector=_select_tool_names,
    )
    events = list(agent.run("Read challenge1.md and follow the instructions inside"))

    offered = {item["function"]["name"] for item in runtime.requests[0]["tools"]}
    assert {"read_file", "write_file"} <= offered
    assert any(event.kind == "retry" and "read_file" in event.payload["reason"]
               for event in events)
    assert calls == ["challenge1.md"]
    assert any(event.kind == "text" and "can proceed" in event.payload["content"]
               for event in events)


@pytest.mark.parametrize(
    "followup", ["Go ahead with that plan.", "Proceed with the plan.", "Continue."]
)
def test_workspace_plan_continuation_keeps_implementation_tools(followup):
    calls = []
    names = ("read_file", "write_file", "edit_file", "run_shell", "list_dir", "grep",
             "workspace_info", "web_search", "query_knowledge", "fetch_url",
             "search_sessions", "read_skill", "git_commit")
    tools = [Tool(name, name, {}, lambda: calls.append("edited") or "ok") for name in names]
    runtime = ScriptedRuntime([
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "edit_file", "arguments": {},
        }}]},
        {"role": "assistant", "content": "Implemented the change."},
    ])
    agent = Agent(runtime, "test-model", tools,
                  PermissionGate({name: "allow" for name in names}, lambda *_: "n"),
                  "system", tool_selector=_select_tool_names)
    agent.messages.extend([
        {"role": "user", "content": (
            "Inspect this project before we add a CSV importer. Do not edit yet."
        )},
        {"role": "assistant", "content": (
            "Plan: add CSV validation, atomic saves and regression tests."
        )},
    ])
    agent.messages.extend([
        {"role": "user", "content": "Go ahead with that plan."},
        {"role": "assistant", "content": "I was unable to complete the task."},
    ])
    list(agent.run(followup))
    supplied = {item["function"]["name"] for item in runtime.requests[0]["tools"]}
    assert {"read_file", "edit_file", "write_file", "run_shell"} <= supplied
    assert not {"web_search", "git_commit"} & supplied
    assert calls == ["edited"]
    if followup != "Continue.":
        assert "implement the preceding plan" in runtime.requests[0]["messages"][0]["content"]


def test_plan_continuation_cannot_widen_plan_scope_or_disabled_tools():
    names = ("read_file", "edit_file", "run_shell", "web_search", "read_skill")
    runtime = ScriptedRuntime([{"role": "assistant", "content": "Here is the plan."}])
    agent = Agent(runtime, "test-model", [Tool(n, n, {}, lambda: "") for n in names],
                  PermissionGate({}, lambda *_: "n"), "system", tool_selector=_select_tool_names)
    agent.plan_mode = True
    agent.disabled_tool_names.add("read_skill")
    agent.messages.extend([
        {"role": "user", "content": "Implement a CSV importer in this project."},
        {"role": "assistant", "content": "I will add the importer."},
    ])
    list(agent.run("Go ahead with that plan."))
    supplied = {item["function"]["name"] for item in runtime.requests[0]["tools"]}
    assert "read_file" in supplied
    assert not {"edit_file", "run_shell", "read_skill", "web_search"} & supplied
    assert "implement the preceding plan" not in runtime.requests[0]["messages"][0]["content"]


def test_workspace_continuation_uses_code_context_budget_and_retains_plan():
    runtime = ScriptedRuntime([{"role": "assistant", "content": "I will implement the plan."}])
    tools = [Tool(n, n, {}, lambda: "") for n in ("read_file", "write_file", "run_shell")]
    agent = Agent(runtime, "test-model", tools, PermissionGate({}, lambda *_: "n"),
                  "instructions " * 900, tool_selector=_select_tool_names,
                  ollama_options={"num_ctx": 8192, "num_predict": 2048},
                  ollama_code_options={"num_ctx": 16384, "num_predict": 4096})
    agent.messages.extend([
        {"role": "user", "content": "Review this project before we add Python CSV import."},
        {"role": "assistant", "content": "Plan: preserve legacy stock and use atomic saves."},
    ])
    options = []
    compact = agent._compact_history
    def observe(schemas, **kwargs):
        options.append(kwargs["ollama_options"])
        return compact(schemas, **kwargs)
    agent._compact_history = observe
    list(agent.run("Go ahead with that plan."))
    assert options[0] == {"num_ctx": 16384, "num_predict": 4096,
                          "temperature": 0.2, "top_p": 0.9, "presence_penalty": 0.0}
    assert any("preserve legacy stock" in m["content"]
               for m in runtime.requests[0]["messages"])
    assert agent.last_turn_capabilities["provider"]["context_window"] == 16384
    assert _agent_context_window(agent) == 16384
    assert _agent_context_window(agent, active_request=False) == 8192
    agent.compact_now()
    assert options[-1]["num_ctx"] == 16384
    from klaude_core.model_runtime import ModelInfo
    agent.model_info = ModelInfo("ollama", "different-model", "different-model")
    assert _agent_context_window(agent) == 8192


@pytest.mark.parametrize("web_available", [False, True])
def test_request_policy_matches_callable_tools_without_mutating_saved_prompt(web_available):
    runtime = ScriptedRuntime([{"role": "assistant", "content": "Answer."}])
    prompt = ("Universal rules\n<web_research_policy>\nDetailed search policy\n"
              "</web_research_policy>\nGlobal capabilities")
    tool = "web_search" if web_available else "read_file"
    agent = Agent(runtime, "test-model", [Tool(tool, tool, {}, lambda: "")],
                  PermissionGate({}, lambda *_: "n"), prompt)
    list(agent.run("Inspect the project"))
    sent = runtime.requests[0]["messages"][0]["content"]
    assert ("Detailed search policy" in sent) == web_available
    assert "Universal rules" in sent
    assert "Global capabilities" in sent
    assert agent.messages[0]["content"] == prompt
