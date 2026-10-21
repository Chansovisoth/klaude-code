"""Browser retrieval is lazy, permission-gated and uses real installed Skills."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from klaude_application.browser_tools import ASSISTANT_READ_TOOLS, BrowserTools
from klaude_core.config import Config
from klaude_core.memory import Memory

from .test_application_bridge import ScriptedRuntime, _collect, _tool_call


def test_browser_has_fresh_clock_tool_and_refreshes_timezone_each_turn(tmp_path, monkeypatch):
    from klaude_core import config, time_settings
    from klaude_core.settings_store import update_settings
    from klaude_webhost import main

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config(models={"coder": "fixture"})
    cfg.permissions["current_time"] = "allow"
    instant = [datetime(2040, 5, 6, 12, 30, tzinfo=UTC)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant[0].astimezone(tz)

    monkeypatch.setattr(time_settings, "datetime", Clock)
    runtime = ScriptedRuntime([
        _tool_call("current_time"), {"role": "assistant", "content": "Clock read."},
        _tool_call("current_time", timezone="UTC"),
        {"role": "assistant", "content": "Clock read again."},
    ])
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "OllamaRuntime", lambda _: runtime)
    update_settings(cfg.data_dir / "chat-preferences.json", {
        ("time_settings", "timezone"): "Asia/Tokyo",
    })
    app = main.create_application(tmp_path)

    async def exercise():
        try:
            assert "current_time" in app.agent.tools
            first = app.submit("What date and time is it right now?")
            events = await asyncio.wait_for(_collect(first), timeout=10)
            await first.result()
            assert first.state == "completed"
            assert any(event.kind == "tool.finished" and event.executed for event in events)
            assert not app.pending_interactions()
            assert app.agent.gate.policies["current_time"] == "allow"
            prompt = app.agent.messages[0]["content"]
            assert "2040-05-06T21:30:00+09:00" in prompt and "Timezone: Asia/Tokyo" in prompt
            assert any(message["role"] == "tool" and "Asia/Tokyo" in message["content"]
                       for message in app.agent.messages)
            update_settings(cfg.data_dir / "chat-preferences.json", {
                ("time_settings", "timezone"): "America/New_York",
            })
            instant[0] += timedelta(days=1)
            second = app.submit("What is the current time in UTC?")
            await asyncio.wait_for(second.result(), timeout=10)
            assert second.state == "completed"
            prompt = app.agent.messages[0]["content"]
            assert "2040-05-07T08:30:00-04:00" in prompt
            assert "Timezone: America/New_York" in prompt
            assert "2040-05-06T21:30:00+09:00" not in prompt
            assert any(message["role"] == "tool" and "2040-05-07T12:30:00+00:00" in
                       message["content"] for message in app.agent.messages)
        finally:
            await app.close()

    asyncio.run(exercise())


def _skill(cfg):
    directory = cfg.data_dir / "skills" / "fixture"
    content = directory / "current"
    content.mkdir(parents=True)
    (content / "SKILL.md").write_text("---\ndescription: Testing guidance\n---\nUse amber widgets.")
    (directory / "manifest.json").write_text(json.dumps({
        "name": "fixture", "current_dir": str(content), "enabled": True,
    }))


@pytest.mark.parametrize("decision,executed", [("allow_once", True), ("deny", False)])
def test_browser_agent_reads_installed_skill_only_after_exact_approval(
    tmp_path, monkeypatch, decision, executed,
):
    from klaude_core import config
    from klaude_webhost import main

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config(models={"coder": "fixture"})
    cfg.permissions["read_skill"] = "ask"
    _skill(cfg)
    skill_call = _tool_call("read_skill")
    skill_call["tool_calls"][0]["function"]["arguments"] = {"name": "fixture"}
    runtime = ScriptedRuntime([
        skill_call,
        {"role": "assistant", "content": "The Skill was handled."},
    ])
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "OllamaRuntime", lambda _: runtime)
    app = main.create_application(tmp_path)
    app.agent.gate.policies["read_skill"] = "ask"
    assert ASSISTANT_READ_TOOLS <= app.agent.tools.keys()
    assert not (cfg.data_dir / "webcache.db").exists()

    async def exercise():
        try:
            app.memory.remember("Prefer compact output")
            handle = app.submit("Read the installed fixture Skill", request_id="skill-read")
            consumer = asyncio.create_task(_collect(handle))
            pending = ()
            for _ in range(200):
                pending = app.pending_interactions()
                if pending:
                    break
                await asyncio.sleep(0.01)
            assert len(pending) == 1 and pending[0].tool == "read_skill"
            assert app.decide(pending[0].id, decision)
            events = await consumer
            await handle.result()
            finished = next(event for event in events if event.kind == "tool.finished")
            assert finished.executed is executed
            assert "Prefer compact output" in app.agent.messages[0]["content"]
            assert "fixture: Testing guidance" in app.agent.messages[0]["content"]
            assert not app.agent.workspace.write_enabled
        finally:
            await app.close()

    asyncio.run(exercise())


def test_browser_fetch_returns_source_identity_and_research_evidence(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    cfg = Config()
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    tools = BrowserTools(cfg, memory)
    tools._web = SimpleNamespace(fetch_detailed=lambda url: {
        "content": "Amber widgets support exact revision checks.", "status": "succeeded",
        "source_id": "src_001", "final_url": url, "title": "Widgets",
        "provider": "direct",
    })
    try:
        result = tools.fetch("https://example.test/widgets")
        assert "src_001" in result["content"]
        assert "https://example.test/widgets" in result["content"]
        assert result["metadata"]["research_evidence"][0]["source_id"] == "src_001"
        assert result["metadata"]["untrusted_external_evidence"]
    finally:
        memory.db.close()


def test_browser_applies_shared_settings_and_automatic_memory(tmp_path, monkeypatch):
    from klaude_core import config
    from klaude_core.settings_store import update_settings
    from klaude_webhost import main

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config(models={"coder": "fixture"})
    runtime = ScriptedRuntime([{"role": "assistant", "content": "Understood."}])
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "OllamaRuntime", lambda _: runtime)
    app = main.create_application(tmp_path)
    update_settings(cfg.data_dir / "chat-preferences.json", {
        ("runtime_options", "max_steps"): 5,
        ("tool_availability", "web_search"): False,
        ("permissions", "fetch_url"): "deny",
        ("search_settings", "provider"): "brave",
        ("search_settings", "results"): 25,
        ("fetch_settings", "provider"): "exa",
        ("fetch_settings", "exa_fallback"): False,
    })

    async def exercise():
        try:
            handle = app.submit("Remember that I prefer short responses.")
            await handle.result()
            assert handle.state == "completed"
            assert app.agent.max_steps == 5
            assert "web_search" in app.agent.disabled_tool_names
            assert app.agent.gate.policies["fetch_url"] == "deny"
            assert cfg.web_search.settings_provider == "brave"
            assert cfg.web_search.default_results == 25
            assert cfg.web_fetch.settings_provider == "exa"
            assert cfg.web_fetch.exa_fallback is False
            assert app.memory.search_facts("short responses")
            assert "short responses" not in app.agent.code_context
            app.agent.browser_tools.prompt("Browser prompt", app.agent)
            assert "short responses" in app.agent.code_context
            identity = app.memory.search_facts("short responses")[0].id
            app.memory.update_fact(identity, None)
            update_settings(cfg.data_dir / "chat-preferences.json", {
                ("search_settings", "provider"): "ddgs",
                ("fetch_settings", "provider"): "local",
            })
            app.agent.browser_tools.prompt("Browser prompt", app.agent)
            assert cfg.web_search.settings_provider == "ddgs"
            assert cfg.web_fetch.settings_provider == "local"
            assert "short responses" not in app.agent.code_context
        finally:
            await app.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("change_after_review", [False, True])
def test_browser_mcp_tools_require_review_and_recheck_definition(
    tmp_path, monkeypatch, change_after_review,
):
    from klaude_core import config
    from klaude_core.mcp_client import MCPRegistry, MCPServerConfig, namespaced_tool_name
    from klaude_webhost import main

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config(models={"coder": "fixture"})
    server = MCPServerConfig("fixture", "http", True, url="https://example.test/mcp", tools=[{
        "name": "lookup", "description": "Look up a fixture", "inputSchema": {
            "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
        },
    }])
    MCPRegistry(cfg.mcp_servers_file).save({server.name: server})
    name = namespaced_tool_name("fixture", "lookup")
    calls = []
    cfg._mcp_client_manager = SimpleNamespace(
        call=lambda selected, tool, arguments: calls.append((selected.name, tool, arguments)) or {
            "content": [{"type": "text", "text": "Fixture result"}], "is_error": False,
        }, close=lambda: None,
    )
    runtime = ScriptedRuntime([
        _tool_call(name, query="widgets"), {"role": "assistant", "content": "Finished."},
    ])
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "OllamaRuntime", lambda _: runtime)
    app = main.create_application(tmp_path)

    async def exercise():
        try:
            handle = app.submit("Use the fixture MCP lookup")
            consumer = asyncio.create_task(_collect(handle))
            pending = ()
            for _ in range(200):
                pending = app.pending_interactions()
                if pending:
                    break
                await asyncio.sleep(0.01)
            assert pending and pending[0].tool == name
            assert not calls
            if change_after_review:
                registry = MCPRegistry(cfg.mcp_servers_file)
                values = registry.load()
                values["fixture"].enabled = False
                registry.save(values)
            assert app.decide(pending[0].id, "allow_once")
            await consumer
            await handle.result()
            assert bool(calls) is not change_after_review
        finally:
            await app.close()

    asyncio.run(exercise())
