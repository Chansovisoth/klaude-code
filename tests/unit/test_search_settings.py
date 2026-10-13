import json
import queue
from types import SimpleNamespace

import pytest
from klaude_cli.search_settings import run_search_test
from klaude_cli.session_actions import SearchProviderSecret, SessionActionWriter
from klaude_cli.settings_panel import PanelAction
from klaude_cli.settings_writer import public_tool_settings
from klaude_core.config import Config
from klaude_core.search_settings import apply_search_settings, public_search_settings, service_url
from klaude_core.settings_store import update_settings
from klaude_web.providers import (
    ProviderRegistry,
    ProviderSearchError,
    ProviderState,
    ProviderStateStore,
    build_search_query,
    quality_search,
    search_cache_key,
)

from .test_cli_commands import _fake_persistent_tui
from .test_search import FakeProvider


def action(controller, kind, target=""):
    controller.action(PanelAction("search-settings-" + kind, target))


def controller(tmp_path):
    host = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
    host.agent.tools = {name: object() for name in ("web_search", "fetch_url")}
    host._open_settings_category("search")
    return host._search_settings


def test_public_search_metadata_excludes_secrets_and_invalid_values():
    assert (
        public_search_settings(
            {
                "provider": "unknown",
                "results": True,
                "fallbacks": ["ddgs", {}],
                "searxng_url": "https://secret:pass@example.com",
                "key": "private-canary",
            }
        )
        == {}
    )
    assert public_tool_settings({"search_settings": {"results": 5, "key": "private-canary"}}) == {
        "search_settings": {"results": 5}
    }
    assert public_search_settings({"fallbacks": ["ddgs", "ddgs", "exa"]}) == {
        "fallbacks": ["ddgs", "exa"]
    }


@pytest.mark.parametrize(
    "url",
    [
        "ftp://host",
        "http://host:0",
        "http://host?key=x",
        "http://host/#secret",
        "http://host/\npath",
        "http://host:99999",
    ],
)
def test_service_url_rejects_unsafe_configuration(url):
    with pytest.raises(ValueError):
        service_url(url)


def test_explicit_local_service_url_is_allowed_without_relaxing_fetch():
    assert service_url(" http://127.0.0.1:8888/ ") == "http://127.0.0.1:8888"


def test_search_navigation_uses_live_state_and_preserves_filter(tmp_path, monkeypatch):
    item = controller(tmp_path)
    host = item.host
    monkeypatch.setattr(
        "klaude_cli.main._load_chat_preferences",
        lambda _path: pytest.fail("Navigation must not read preferences"),
    )
    host._panel.picker.query = "Tool availability"
    host._panel.search_active = True
    action(item, "enabled")
    item.host._agent_settings.action(PanelAction("agent-settings-tool-toggle"))
    item.host._agent_settings.action(PanelAction("agent-settings-back", "tool-parent"))
    assert "web_search" in host.agent.disabled_tool_names
    assert host._panel.picker.query == "Tool availability"
    assert host._panel.picker.selected_id == "enabled"
    action(item, "enabled")
    item.host._agent_settings.action(PanelAction("agent-settings-tool-toggle"))
    item.host._agent_settings.action(PanelAction("agent-settings-back", "tool-parent"))
    assert "web_search" not in host.agent.disabled_tool_names
    assert host._panel.picker.query == "Tool availability"


def test_search_fields_save_independently_and_reset_keeps_keys_and_availability(tmp_path):
    item = controller(tmp_path)
    host = item.host
    host.cfg.tavily_api_key = "private-canary"
    item.set_value("provider", "searxng")
    item.set_value("results", 5)
    item.set_value("fallbacks", [])
    item.provider = "exa"
    action(item, "provider-enabled")
    action(item, "validation")
    assert host.agent.tool_config.web_search.default_results == 5
    assert host.cfg.web_search.settings_provider == "searxng"
    action(item, "reset")
    host._before_render(None)
    saved = json.loads(host.chat_preferences_path.read_text())
    assert saved["search_settings"] == {}
    assert saved["web_provider_availability"]["exa"] is False
    assert saved["tool_validation"]["web_search"] is False
    assert host.cfg.web_search.settings_provider is None
    assert host.cfg.web_search.settings_fallbacks is None
    assert host.cfg.web_search.default_results == 12
    assert host.cfg.tavily_api_key == "private-canary"


def test_failed_save_retains_requested_live_value_and_exact_focus(tmp_path):
    item = controller(tmp_path)
    item.host.chat_preferences_path.write_text("broken")
    item.set_value("results", 20, "results")
    item.host._before_render(None)
    assert item.host.cfg.web_search.default_results == 20
    assert item.host._runtime_save_state == "failed"
    assert item.host._panel.picker.selected_id == "results"
    assert item.host.chat_preferences_path.read_text() == "broken"


def test_latest_save_merges_other_clients_search_values(tmp_path):
    item = controller(tmp_path)
    update_settings(item.host.chat_preferences_path, {("search_settings", "provider"): "exa"})
    item.set_value("results", 5)
    item.host._before_render(None)
    assert item.host.cfg.web_search.settings_provider == "exa"
    assert item.host.cfg.web_search.default_results == 5
    item.host._emit("settings_tools", (0, {"search_settings": {"results": 50}}))
    item.host._before_render(None)
    assert item.host.cfg.web_search.default_results == 5


def test_test_cancellation_and_changed_settings_reject_late_results(tmp_path):
    item = controller(tmp_path)
    requests = []
    jobs = SimpleNamespace(
        submit=lambda *_args, **_kwargs: "job", cancel=lambda key: requests.append(key)
    )
    item.host._background_jobs = jobs
    item.start_test("Python documentation")
    assert item.test == ("job", item.host.session_id, 0)
    item.set_value("results", 5)
    item.accept("job", {"status": "ok", "message": "Stale success"}, "")
    assert item.result is None and item.test is None
    item.start_test("Python documentation")
    item.host._web_provider_availability["exa"] = False
    item.accept("job", {"status": "ok", "message": "Stale success"}, "")
    assert item.feedback == ("Settings changed; rerun test", "warning")
    assert "search-settings:test" in requests


def test_provider_tests_name_the_actual_used_provider_and_keep_only_metadata(tmp_path):
    item = controller(tmp_path)
    item.host._background_jobs = SimpleNamespace(
        submit=lambda *_a, **_k: "job", cancel=lambda _k: None
    )
    item.start_test("Python documentation")
    item.accept("job", {"status": "ok", "message": "SearXNG · 3 results", "used": ["searxng"]}, "")
    assert item.feedback == ("SearXNG · 3 results", "success")


def test_fallback_move_remove_add_is_bounded_and_preserves_primary(tmp_path):
    item = controller(tmp_path)
    item.set_value("provider", "exa")
    item.set_value("fallbacks", ["ddgs", "searxng"])
    item.provider = "searxng"
    item.show("fallback-detail")
    action(item, "move-up")
    assert item.order() == ["searxng", "ddgs"]
    action(item, "remove-fallback")
    assert item.order() == ["ddgs"]
    item.show("add-fallback")
    labels = [entry.label for entry in item.page().rows]
    assert "Exa" not in labels and "DDGS (keyless)" not in labels
    action(item, "select:searxng", "searxng")
    assert item.order() == ["ddgs", "searxng"]
    assert item.host.cfg.web_search.settings_provider == "exa"


def test_tools_and_providers_compatibility_links_use_search_owner(tmp_path):
    item = controller(tmp_path)
    host = item.host
    host._open_settings_category("tools")
    assert host._agent_settings.view == "home"
    host._agent_settings.open_tool("web_search")
    host._agent_settings.action(PanelAction("agent-settings-configure"))
    assert item.parent == "agent-tool"
    action(item, "back", "agent-tool")
    assert host._agent_settings.view == "tool"
    assert host._agent_settings.tool == "web_search"
    host._open_provider_key_settings("Tavily")
    assert item.view == "detail" and item.provider == "tavily" and item.parent == "providers"
    action(item, "back", "legacy-providers")
    assert host._choice_kind == "providers settings"


def test_key_composer_cancel_never_saves_or_echoes_secret(tmp_path):
    item = controller(tmp_path)
    item.open(provider="tavily")
    item.host._begin_search_secret()
    item.host._answer_secret("cancelled-private-canary", cancelled=True)
    assert item.key_pending is None
    assert "cancelled-private-canary" not in item.host.output.text
    assert item.host._choice_kind == "search settings detail"


@pytest.mark.parametrize("kind", ["custom-results", "endpoint", "test", "test-provider"])
def test_search_actions_use_the_real_single_line_editor_and_cancel_to_parent(tmp_path, kind):
    item = controller(tmp_path)
    item.provider = "searxng"
    item.show("detail" if kind in {"endpoint", "test-provider"} else "home")
    parent = item.view
    action(item, kind)
    assert item.host._settings_input_request["single_line"] is True
    assert item.host._settings_input_request["on_submit"] == ("search-settings", kind)
    item.host._answer_settings_input(None)
    assert item.host._choice_kind == "search settings " + parent
    assert item.host._settings_input_request is None


def test_key_replacement_and_removal_win_over_old_worker_environment(tmp_path, monkeypatch):
    from klaude_core.config import provider_secret_value, save_provider_secret

    cfg_dir = tmp_path / "config"
    save_provider_secret(cfg_dir, "TAVILY_API_KEY", "new-key")
    monkeypatch.setenv("TAVILY_API_KEY", "old-key")
    assert provider_secret_value(cfg_dir, "TAVILY_API_KEY") == "new-key"
    save_provider_secret(cfg_dir, "TAVILY_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "old-key")
    assert provider_secret_value(cfg_dir, "TAVILY_API_KEY", "old-config-key") == ""


@pytest.mark.parametrize(
    "prompt",
    [
        "Search for Python asyncio documentation. Return source leads only; "
        "do not fetch pages, write files or run shell.",
        "Find Rust references; do not build programs or modify files.",
        "Read Java code, but do not fix it.",
    ],
)
def test_search_and_read_prohibitions_do_not_trigger_code_generation(prompt):
    from klaude_core.agent import _code_work_request, _expects_standalone_code_answer

    assert not _code_work_request(prompt)
    assert not _expects_standalone_code_answer(prompt)


def test_positive_code_work_after_a_prohibition_still_routes_to_implementation():
    from klaude_core.agent import _code_work_request, _expects_standalone_code_answer

    assert _code_work_request("Do not edit tests, but fix the Python parser")
    assert _expects_standalone_code_answer("Return a complete Python function")


def test_common_agent_factory_honors_disabled_tools_before_first_model_request(
    tmp_path, monkeypatch
):
    from klaude_cli import main
    from klaude_core import config

    from .test_agentic_search import ScriptedOllama

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "_runtime_context_result", lambda *_a: None)
    monkeypatch.setattr(main, "_configured_mcp_tools", lambda *_a: [])
    update_settings(
        config.DATA_DIR / "chat-preferences.json",
        {
            ("tool_availability",): {
                "web_search": False,
                "fetch_url": False,
                "query_knowledge": False,
            },
            ("tool_validation", "web_search"): False,
        },
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agent, memory = main._build_agent(workspace)
    runtime = ScriptedOllama([{"role": "assistant", "content": "Web Search is disabled."}])
    agent.ollama = runtime
    events = list(agent.run("Search the web for documentation; do not write code."))
    assert not any(event.kind == "error" for event in events)
    names = {tool["function"]["name"] for tool in runtime.calls[0]["tools"] or []}
    assert not {"web_search", "fetch_url", "query_knowledge"} & names
    assert agent.tool_config.web_search.result_validation_enabled is False
    assert len(runtime.calls) == 1
    main._close_agent_mcp(agent)


def test_private_key_mutation_has_no_session_io_and_drains_after_navigation(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    cfg = SimpleNamespace(config_dir=tmp_path / "config")
    events = queue.Queue()
    memory = SimpleNamespace(open_session_io=lambda: pytest.fail("Secrets are not session updates"))
    writer = SessionActionWriter(memory, lambda *value: events.put(value))
    update = SearchProviderSecret("session", "key", cfg, "TAVILY_API_KEY", "private-canary")
    assert "private-canary" not in repr(update)
    assert writer.submit(update)
    assert writer.close(wait=True)
    assert events.get_nowait() == ("search_provider_saved", ("session", "key", True, True))
    assert "private-canary" in (cfg.config_dir / ".env").read_text()
    assert (cfg.config_dir / ".env").stat().st_mode & 0o777 == 0o600
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


def registry(tmp_path, cfg, *providers):
    return ProviderRegistry(
        cfg, providers=list(providers), state_store=ProviderStateStore(tmp_path / "health.json")
    )


def test_pinned_routing_has_exact_fallbacks_and_disabled_entries_are_skipped(tmp_path):
    cfg = Config()
    apply_search_settings(cfg, {"provider": "exa", "fallbacks": ["ddgs", "searxng"]})
    cfg.web_providers["exa"].enabled = False
    store = registry(
        tmp_path, cfg, FakeProvider("exa"), FakeProvider("ddgs"), FakeProvider("searxng")
    )
    query = build_search_query("Python docs", cfg, 5)
    selected, _ = store.eligible_providers(query)
    assert [provider.name for provider in selected] == ["ddgs", "searxng"]
    cfg.web_search.settings_fallbacks = []
    assert store.eligible_providers(query)[0] == []


def test_explicit_provider_strictness_wins_over_saved_pin_and_fallbacks(tmp_path):
    cfg = Config()
    apply_search_settings(cfg, {"provider": "exa", "fallbacks": ["ddgs"]})
    store = registry(
        tmp_path, cfg, FakeProvider("exa"), FakeProvider("ddgs"), FakeProvider("searxng")
    )
    query = build_search_query("Python docs", cfg, 5)
    selected, _ = store.eligible_providers(query, provider_override="searxng", provider_strict=True)
    assert [provider.name for provider in selected] == ["searxng"]


def test_operational_failure_uses_next_configured_fallback(tmp_path):
    cfg = Config()
    apply_search_settings(cfg, {"provider": "exa", "fallbacks": ["ddgs"]})
    calls = []
    store = registry(
        tmp_path,
        cfg,
        FakeProvider(
            "exa",
            calls=calls,
            error=ProviderSearchError(ProviderState.UNHEALTHY, "unavailable"),
        ),
        FakeProvider(
            "ddgs",
            calls=calls,
            results=[
                {
                    "title": "Python asyncio documentation",
                    "url": "https://docs.python.org/3/library/asyncio.html",
                    "snippet": "Python asyncio documentation and examples",
                }
            ],
        ),
    )
    response = quality_search(cfg, "Python asyncio documentation", 5, registry=store)
    assert calls == ["exa", "ddgs"]
    assert response.providers_succeeded == ["ddgs"]


def test_search_cache_changes_with_route_endpoint_and_depth():
    cfg = Config()
    query = build_search_query("Python docs", cfg, 5)
    keys = [search_cache_key(cfg, query)]
    for change in (
        {"provider": "exa"},
        {"fallbacks": []},
        {"searxng_url": "http://127.0.0.1:9999"},
        {"tavily_depth": "advanced"},
    ):
        apply_search_settings(cfg, change)
        keys.append(search_cache_key(cfg, query))
    assert len(set(keys)) == len(keys)
    assert cfg.web_provider == "quality"  # Fetch policy is independent.


def test_searxng_planned_queries_are_not_expanded_again(monkeypatch):
    import httpx
    from klaude_web.providers import SearXNGProvider

    cfg = Config()
    cfg.web_search.behavior.max_query_rewrites = 2
    seen = []

    def get(url, *, params, **_kwargs):
        seen.append(params["q"])
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "results": [
                    {
                        "title": "Python asyncio documentation",
                        "url": "https://docs.python.org/3/library/asyncio.html",
                        "content": "Python asyncio documentation, coroutines and tasks",
                    }
                ]
            },
        )

    monkeypatch.setattr("klaude_web.search.httpx.get", get)
    response = SearXNGProvider(cfg).search(
        build_search_query("Python asyncio documentation", cfg, 5)
    )
    assert len(seen) == 2
    assert response.queries_attempted == seen
    assert all(query.startswith("site:") for query in seen)
    assert not any("YouTube" in query or "Twitch" in query for query in seen)


def test_test_worker_does_not_publish_snippets_keys_or_upstream_errors(tmp_path, monkeypatch):
    from klaude_core import config
    from klaude_web.search import SearchResponse

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "_load_env_files", lambda: None)
    monkeypatch.setattr(
        "klaude_web.providers.quality_search",
        lambda *_a, **_k: SearchResponse(
            results=[{"snippet": "private-canary"}],
            providers_attempted=["searxng"],
            providers_succeeded=["searxng"],
        ),
    )
    result = run_search_test(
        {
            "config_dir": str(config.CONFIG_DIR),
            "data_dir": str(config.DATA_DIR),
            "query": "Python docs",
            "provider": "searxng",
            "settings": {},
        }
    )
    assert result["status"] == "ok" and result["used"] == ["searxng"]
    assert "private-canary" not in str(result)
