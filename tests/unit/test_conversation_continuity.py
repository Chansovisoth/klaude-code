"""Regressions from recent chat failures; fixtures contain no private dialogue."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from klaude_application.browser_tool_routing import configure_browser_routing, select_browser_tools
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.context_compaction import build_recap
from klaude_core.intent import requests_skill_guidance
from klaude_core.model_runtime import GeminiRuntime
from klaude_core.source_use import asks_what_was_used


class Runtime:
    def __init__(self, replies=None):
        self.requests = []
        self.replies = iter(replies or [{"role": "assistant", "content": "Acknowledged."}])

    def chat(self, model, messages, tools=None, **kwargs):
        self.requests.append((deepcopy(messages), deepcopy(tools)))
        return next(self.replies)


def agent_with_tools(runtime):
    tools = [Tool("read_file", "Read a file", {"type": "object"}, lambda: "text")]
    # Mirrors a large configured MCP inventory that must not dominate every turn.
    tools += [Tool(f"mcp__crawler__monitor_{i}", "External monitoring", {
        "type": "object", "description": "parameters " * 400,
    }, lambda: pytest.fail("Unrequested MCP operation")) for i in range(25)]
    agent = Agent(runtime, "fixture", tools, PermissionGate({}, lambda *_: "n"),
                  "Continue this conversation.", ollama_options={"num_ctx": 8192})
    configure_browser_routing(agent)
    return agent


@pytest.mark.parametrize("history,followup", [
    (["Test", "Choose: 1. A tool test 2. A connection test 3. Conversation"], "3"),
    (["Generate an SVG heart", "Here is the SVG heart source."], "That is an oval!"),
    (["Generate an image of a fox", "Generated fox. Library assets: media:" + "a" * 32],
     "What did you generate?"),
    (["Generate an image of a fox", "Generated fox."], "now of a rabbit"),
])
def test_browser_short_followups_keep_recent_exchange_with_large_mcp_catalog(history, followup):
    runtime = Runtime()
    agent = agent_with_tools(runtime)
    agent.messages.extend([
        {"role": "user", "content": history[0]},
        {"role": "assistant", "content": history[1]},
    ])
    list(agent.run(followup))
    messages, schemas = runtime.requests[0]
    assert history[0] in str(messages) and history[1] in str(messages)
    assert messages[-1]["content"] == followup
    assert all(not s["function"]["name"].startswith("mcp__") for s in schemas)
    assert "discover_tools" in {s["function"]["name"] for s in schemas}
    assert "mcp__crawler__monitor_0" not in messages[0]["content"]


def test_external_tools_can_be_discovered_without_executing_or_granting_them():
    name = "mcp__crawler__monitor_3"
    runtime = Runtime([
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "discover_tools", "arguments": {"query": name},
        }}]},
        {"role": "assistant", "content": "The tool is discoverable; it has not executed."},
    ])
    agent = agent_with_tools(runtime)
    # The provider discovers a schema by its exact registered name.
    agent.tools[name].parameters = {"type": "object"}
    list(agent.run("Find an external monitoring capability"))
    assert name not in {s["function"]["name"] for s in runtime.requests[0][1]}
    assert name in {s["function"]["name"] for s in runtime.requests[1][1]}
    assert name not in agent.gate.process_grants


def test_browser_explicit_tool_limit_and_prohibition_survive_lazy_routing():
    name = "mcp__crawler__inspect"
    tools = {name: Tool(name, "Inspect", {}, lambda: "")}
    assert select_browser_tools(f"Use only {name}", tools) == [name]
    assert select_browser_tools("Do not use tools", tools) == []


def test_restored_chat_retains_prior_turns_with_lazy_external_tools():
    runtime = Runtime()
    agent = agent_with_tools(runtime)
    agent.restore_session([
        {"role": "user", "content": "Create an orange dashboard called AmberLake."},
        {"role": "assistant", "content": "The project is AmberLake with an orange theme."},
    ])
    list(agent.run("What was the project name?"))
    assert "AmberLake" in str(runtime.requests[0][0])
    assert runtime.requests[0][0][-1]["content"] == "What was the project name?"


def test_gemini_text_request_keeps_compaction_recap_and_recent_dialogue(monkeypatch):
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return object()

    runtime = GeminiRuntime("fixture-key")
    monkeypatch.setattr(runtime, "_sdk", lambda: (SimpleNamespace(
        Client=lambda **kwargs: SimpleNamespace(models=Models()),
    ), object()))
    recap = build_recap([
        {"role": "user", "content": "Build the orange offline dashboard."},
        {"role": "assistant", "content": "I will retain the orange theme."},
    ], 1200)
    runtime._request("gemini-fixture", [
        {"role": "system", "content": "Host rules"}, recap,
        {"role": "user", "content": "Keep the same theme"},
    ], None, False, False)
    assert "Host rules" in captured["config"]["system_instruction"]
    assert "orange offline dashboard" in captured["config"]["system_instruction"]
    assert captured["contents"][-1]["parts"][0]["text"] == "Keep the same theme"


def test_small_recap_keeps_answer_that_a_numbered_choice_refers_to():
    messages = [{"role": "user", "content": "Explore the workspace"}]
    for i in range(10):
        messages.extend([
            {"role": "user", "content": f"Earlier request {i}: " + "details " * 50},
            {"role": "assistant", "content": "Old discussion " * 60},
        ])
    messages.extend([
        {"role": "assistant", "content": "Choose: 1. Read 2. Compare 3. Explain"},
        {"role": "user", "content": "3"},
    ])
    recap = build_recap(messages, 1000)
    assert "Explore the workspace" in recap["content"]
    assert "3. Explain" in recap["content"]
    assert "User: 3" in recap["content"]


@pytest.mark.parametrize("text,expected", [
    ("Use the meme maker", True),
    ("Using our existing meme skills, generate a meme image", True),
    ("Don't use any skills, generate an image", False),
    ("What skills did you use?", False),
    ("Generate an image of a fox", False),
])
def test_requested_skill_guidance_handles_names_and_prohibitions(text, expected):
    assert requests_skill_guidance(text, ("meme-maker",)) is expected


def test_why_tool_was_used_is_not_hijacked_by_source_receipt_shortcut():
    assert not asks_what_was_used("Why did you use it?")
    assert not asks_what_was_used("How did you use that tool?")
    assert asks_what_was_used("Which tools did you use?")


def test_browser_application_preserves_history_across_real_turn_boundaries(tmp_path, monkeypatch):
    from klaude_core import config
    from klaude_core.config import Config
    from klaude_webhost import main

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config(models={"coder": "fixture"})
    runtime = Runtime([
        {"role": "assistant", "content": "Choose: 1. Orange 2. Blue 3. Green"},
        {"role": "assistant", "content": "You selected Green."},
    ])
    external = [Tool(f"mcp__fixture__monitor_{i}", "Monitor", {
        "type": "object", "description": "large schema " * 350,
    }, lambda: pytest.fail("No external call requested")) for i in range(25)]
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "OllamaRuntime", lambda _: runtime)
    monkeypatch.setattr("klaude_application.browser_tools.configured_mcp_tools",
                        lambda *args, **kwargs: external)
    app = main.create_application(tmp_path)

    async def exercise():
        try:
            first = app.submit("Give me three theme choices.")
            assert await first.join(timeout=5)
            assert first.failure is None
            second = app.submit("3")
            assert await second.join(timeout=5)
            assert second.failure is None
            assert app.snapshot()["messages"][-1]["content"] == "You selected Green."
            messages, schemas = runtime.requests[-1]
            assert "Choose: 1. Orange 2. Blue 3. Green" in str(messages)
            assert messages[-1]["content"] == "3"
            assert not any(s["function"]["name"].startswith("mcp__") for s in schemas)
        finally:
            await app.close()

    asyncio.run(exercise())
