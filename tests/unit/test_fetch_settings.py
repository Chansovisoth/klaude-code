import json
import queue
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.fetch_settings import FetchSettings, run_fetch_test
from klaude_cli.session_actions import SessionActionWriter
from klaude_cli.settings_panel import PanelAction
from klaude_cli.settings_writer import public_tool_settings
from klaude_core.config import Config, save_provider_secret
from klaude_core.fetch_settings import (
    apply_fetch_settings,
    exa_fallback,
    fetch_provider,
    public_fetch_settings,
)
from klaude_core.settings_store import update_settings
from klaude_web.facade import Web
from klaude_web.fetch import FetchPageError, fetch_page_detailed
from klaude_web.provider_http import post_json

from .test_cli_commands import _fake_persistent_tui
from .test_web_fetch import public_resolver, response_transport


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr("klaude_core.config.CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr("klaude_core.config.DATA_DIR", tmp_path / "data")


def controller(tmp_path):
    host = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
    host.agent.tools = {name: object() for name in ("web_search", "fetch_url")}
    host._fetch_settings = FetchSettings(host)
    host._fetch_settings.open(parent="search")
    return host._fetch_settings


def action(item, kind, target=""):
    item.action(PanelAction("fetch-settings-" + kind, target))


@pytest.mark.parametrize(
    "legacy,route,fallback",
    [
        ("quality", "local", False),
        ("local", "local", False),
        ("auto", "local", True),
        ("exa", "exa", False),
    ],
)
def test_migration_retains_existing_fetch_route_without_search_coupling(legacy, route, fallback):
    cfg = Config(web_provider=legacy)
    assert (fetch_provider(cfg), exa_fallback(cfg)) == (route, fallback)
    cfg.web_search.settings_provider = "exa" if route == "local" else "searxng"
    assert fetch_provider(cfg) == route
    apply_fetch_settings(cfg, {"provider": "local", "exa_fallback": False})
    assert (fetch_provider(cfg), exa_fallback(cfg)) == ("local", False)
    assert cfg.web_provider == legacy


def test_public_fetch_metadata_filters_secrets_and_invalid_fields():
    assert (
        public_fetch_settings(
            {
                "provider": [],
                "crawl4ai_enabled": 1,
                "crawl4ai_url": "https://user:key@host",
                "api_key": "private-canary",
            }
        )
        == {}
    )
    assert public_tool_settings({"fetch_settings": {"provider": "exa", "secret": "canary"}}) == {
        "fetch_settings": {"provider": "exa"}
    }
    assert public_fetch_settings({"crawl4ai_url": "http://127.0.0.1:11235/"}) == {
        "crawl4ai_url": "http://127.0.0.1:11235"
    }


def test_fetch_navigation_filters_and_saves_without_reading_disk(tmp_path, monkeypatch):
    item = controller(tmp_path)
    monkeypatch.setattr(
        "klaude_cli.main._load_chat_preferences",
        lambda _p: pytest.fail("Navigation must use live state"),
    )
    item.host._panel.picker.query = "Tool availability"
    item.host._panel.search_active = True
    action(item, "enabled")
    item.host._agent_settings.action(PanelAction("agent-settings-tool-toggle"))
    item.host._agent_settings.action(PanelAction("agent-settings-back", "tool-parent"))
    assert "fetch_url" in item.host.agent.disabled_tool_names
    assert item.host._panel.picker.query == "Tool availability"
    assert item.host._panel.picker.selected_id == "enabled"
    item.host._before_render(None)
    assert (
        json.loads(item.host.chat_preferences_path.read_text())["tool_availability"]["fetch_url"]
        is False
    )


def test_fetch_reset_and_tools_reset_preserve_migrated_settings(tmp_path):
    item = controller(tmp_path)
    item.set_value("provider", "exa")
    item.set_value("exa_fallback", True)
    item.set_value("crawl4ai_url", "http://127.0.0.1:11235")
    item.set_value("crawl4ai_enabled", False)
    action(item, "enabled")
    item.host._agent_settings.action(PanelAction("agent-settings-tool-toggle"))
    item.host._agent_settings.action(PanelAction("agent-settings-back", "tool-parent"))
    action(item, "reset")
    item.host._before_render(None)
    cfg = item.host.cfg
    assert cfg.web_fetch.settings_provider is None and cfg.web_fetch.exa_fallback is None
    assert not cfg.web_fetch.crawl4ai_enabled
    assert cfg.crawl4ai_url == "http://127.0.0.1:11235"
    item.host._open_settings_category("tools")
    assert item.host._agent_settings.view == "home"
    item.host._agent_settings.show("tools")
    item.host._agent_settings.action(PanelAction("agent-settings-reset-tools"))
    assert item.host._tool_availability["fetch_url"] is True
    assert not cfg.web_fetch.crawl4ai_enabled
    assert cfg.crawl4ai_url == "http://127.0.0.1:11235"
    item.host._open_provider_key_settings("Crawl4AI Cloud")
    assert item.host._fetch_settings.provider == "crawl4ai"
    action(item, "back", "providers")
    assert item.host._choice_kind == "providers settings"


def test_fetch_latest_ack_merges_cross_client_values_and_failed_saves_retain_intent(tmp_path):
    item = controller(tmp_path)
    update_settings(item.host.chat_preferences_path, {("fetch_settings", "provider"): "exa"})
    item.set_value("crawl4ai_enabled", False)
    item.host._before_render(None)
    assert fetch_provider(item.host.cfg) == "exa"
    assert item.host.cfg.web_fetch.crawl4ai_enabled is False
    item.host.chat_preferences_path.write_text("broken")
    item.set_value("provider", "local", "provider")
    item.host._before_render(None)
    assert fetch_provider(item.host.cfg) == "local"
    assert item.host._runtime_save_state == "failed"
    assert item.host._panel.picker.selected_id == "provider"


@pytest.mark.parametrize("kind", ["endpoint", "test", "test-provider"])
def test_fetch_uses_single_line_private_editor_and_cancel_returns_to_parent(tmp_path, kind):
    item = controller(tmp_path)
    item.provider = "crawl4ai"
    item.show("detail" if kind != "test" else "home")
    parent = item.view
    action(item, kind)
    assert item.host._settings_input_request["single_line"] is True
    item.host._answer_settings_input(None)
    assert item.host._settings_input_request is None
    assert item.host._choice_kind == "fetch settings " + parent


def test_fetch_test_cancel_and_changed_shared_key_reject_late_success(tmp_path):
    item = controller(tmp_path)
    cancelled = []
    item.host._background_jobs = SimpleNamespace(
        submit=lambda *_a, **_k: "job", cancel=cancelled.append
    )
    item.start_test("https://example.com")
    item.host.cfg.exa_api_key = "changed-shared-key"
    item.accept("job", {"status": "ok", "message": "stale"}, "")
    assert item.feedback == ("Settings changed; rerun test", "warning")
    item.start_test("https://example.com")
    action(item, "cancel-test")
    item.accept("job", {"status": "ok", "message": "stale"}, "")
    assert item.feedback == ("Test cancelled", "neutral")
    assert "fetch-settings:test" in cancelled


def test_private_key_write_drains_after_navigation_without_session_io(tmp_path):
    item = controller(tmp_path)
    events = queue.Queue()
    writer = SessionActionWriter(
        SimpleNamespace(db_path=tmp_path / "missing.sqlite"), lambda *event: events.put(event)
    )
    item.host._session_actions = writer
    item.open(provider="crawl4ai")
    item.save_key("fetch-private-canary")
    item.leave()
    assert writer.close(wait=True)
    kind, payload = events.get(timeout=2)
    assert kind == "fetch_provider_saved" and payload[2]
    item.saved_key(payload)
    assert item.host.cfg.crawl4ai_api_key == "fetch-private-canary"
    assert (tmp_path / "config/.env").stat().st_mode & 0o777 == 0o600
    assert "fetch-private-canary" not in item.host.output.text
    assert not (tmp_path / "missing.sqlite").exists()


def test_fetch_key_cancel_and_remove_confirmation_focus(tmp_path):
    item = controller(tmp_path)
    item.open(provider="exa")
    item.host._begin_fetch_secret()
    assert item.host._choice_kind is None
    assert item.host._choice_values == []
    item.host._answer_secret("cancelled-canary", cancelled=True)
    assert item.key_pending is None
    action(item, "remove-key")
    assert item.host._panel.picker.selected_id == "back"
    assert "cancelled-canary" not in item.host.output.text


def make_web(tmp_path):
    return Web(Config())


def test_changed_configuration_retries_failures_without_forgetting_verified_sources(
    tmp_path, monkeypatch
):
    web = make_web(tmp_path)
    attempts = []

    def fetch(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise FetchPageError("Missing service", failure_class="configuration")
        return {
            "requested_url": url,
            "final_url": url,
            "content": "verified content",
            "provider": "direct",
        }

    monkeypatch.setattr(web, "_fetch_uncached_detailed", fetch)
    assert web.fetch_detailed("https://example.com")["status"] == "failed"
    assert web.fetch_detailed("https://example.com")["attempt_reused"]
    web.cfg.crawl4ai_url = "http://127.0.0.1:11235"
    result = web.fetch_detailed("https://example.com")
    assert result["status"] == "succeeded" and len(attempts) == 2
    web.cfg.web_fetch.max_content_characters = 5
    reused = web.fetch_detailed("https://example.com")
    assert reused["source_id"] == result["source_id"] and reused["content"] == "verif"
    assert reused["content_truncated"] and len(attempts) == 2


def test_disk_cache_scoped_to_route_and_limits_and_can_be_disabled(tmp_path, monkeypatch):
    attempts = []

    def fetch(self, url):
        attempts.append(url)
        return {"requested_url": url, "content": "page", "provider": "direct"}

    monkeypatch.setattr(Web, "_fetch_uncached_detailed", fetch)
    make_web(tmp_path).fetch_detailed("https://example.com")
    assert make_web(tmp_path).fetch_detailed("https://example.com")["cache_hit"]
    web = make_web(tmp_path)
    web.cfg.web_fetch.settings_provider = "exa"
    assert not web.fetch_detailed("https://example.com")["cache_hit"]
    web = make_web(tmp_path)
    web.cfg.web_fetch.cache_ttl_seconds = 0
    assert not web.fetch_detailed("https://example.com")["cache_hit"]
    assert len(attempts) == 3


def test_exa_disabled_or_missing_key_does_not_contact_any_network(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    web.cfg.web_fetch.settings_provider = "exa"
    monkeypatch.setattr(
        "klaude_web.facade.resolve_public_url", lambda *_a, **_k: pytest.fail("No network")
    )
    assert web.fetch_detailed("https://example.com")["failure"]["class"] == "configuration"
    web.cfg.web_fetch.exa_enabled = False
    assert web.fetch_detailed("https://example.com")["failure"]["class"] == "disabled"


def test_local_cascade_excludes_disabled_crawl4ai_and_cloud_fallback(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    web.cfg.crawl4ai_url = "http://127.0.0.1:11235"
    web.cfg.exa_api_key = "cloud-key"
    web.cfg.web_fetch.crawl4ai_enabled = False
    seen = []

    def fail(url, endpoint, key, **_kw):
        seen.append(endpoint)
        raise FetchPageError("no extraction", failure_class="empty_extraction", final_url=url)

    monkeypatch.setattr("klaude_web.facade.fetch_page_detailed", fail)
    monkeypatch.setattr(
        "klaude_web.facade.exa_fetch", lambda *_a, **_k: pytest.fail("No implicit cloud")
    )
    assert web.fetch_detailed("https://example.com")["status"] == "failed"
    assert seen == [""]


def test_explicit_exa_fallback_revalidates_url_and_reports_provider(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    web.cfg.exa_api_key = "key"
    web.cfg.web_fetch.exa_fallback = True

    def fail(url, *_a, **_k):
        raise FetchPageError("no extraction", failure_class="empty_extraction", final_url=url)

    monkeypatch.setattr("klaude_web.facade.fetch_page_detailed", fail)
    urls = []
    monkeypatch.setattr(
        "klaude_web.facade.validate_public_url", lambda url: urls.append(url) or url
    )
    monkeypatch.setattr("klaude_web.facade.exa_fetch", lambda *_a, **_k: "cloud content")
    result = web.fetch_detailed("https://example.com")
    assert urls == ["https://example.com/"]
    assert result["provider"] == "exa" and result["fallback_used"]


def test_crawl4ai_detail_does_not_hide_error_with_trafilatura(monkeypatch):
    monkeypatch.setattr(
        "klaude_web.provider_http.post_json",
        lambda *_a, **_k: (_ for _ in ()).throw(
            FetchPageError("private-canary", failure_class="authentication")
        ),
    )
    monkeypatch.setattr(
        "klaude_web.fetch._trafilatura_html", lambda *_a: pytest.fail("No fallback")
    )
    with pytest.raises(FetchPageError, match="private-canary") as raised:
        fetch_page_detailed(
            "https://example.com",
            "http://crawl.test",
            extraction="crawl4ai",
            resolver=public_resolver,
            transport=response_transport("text", "text/plain"),
        )
    assert raised.value.attempted_providers == ("direct", "crawl4ai")


@pytest.mark.parametrize(
    "status,body,reason",
    [
        (401, {}, "authentication"),
        (429, {}, "rate_limit"),
        (302, {}, "provider_failure"),
        (200, [], "provider_failure"),
        (200, {"markdown": "x" * 100}, "response_too_large"),
    ],
)
def test_provider_http_bounds_sanitizes_and_does_not_follow_redirects(
    monkeypatch, status, body, reason
):
    original = httpx.Client
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return original(
            **kwargs,
            transport=httpx.MockTransport(
                lambda req: httpx.Response(status, json=body, request=req)
            ),
        )

    monkeypatch.setattr("klaude_web.provider_http.httpx.Client", factory)
    with pytest.raises(FetchPageError) as error:
        post_json(
            "http://service.test/md",
            headers={"Authorization": "Bearer private-canary"},
            payload={"url": "https://example.com"},
            timeout=1,
            max_bytes=50,
        )
    assert error.value.failure_class == reason
    assert "private-canary" not in str(error.value)
    assert calls[0]["trust_env"] is False and calls[0]["follow_redirects"] is False


def test_worker_uses_actual_provider_metadata_and_saved_key_over_old_environment(
    tmp_path, monkeypatch
):
    cfg = Config()
    save_provider_secret(cfg.config_dir, "CRAWL4AI_API_KEY", "new-key")
    monkeypatch.setattr("klaude_core.config.load_config", lambda: cfg)
    seen = []

    def fetch(self, url, **_kw):
        seen.append(self.cfg.crawl4ai_api_key)
        return {
            "provider": "crawl4ai",
            "content": "private-page-canary",
            "attempted_providers": ["direct", "crawl4ai"],
        }

    monkeypatch.setattr(Web, "_fetch_uncached_detailed", fetch)
    result = run_fetch_test(
        {
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "url": "https://example.com",
            "environment_keys": {"CRAWL4AI_API_KEY": "old-key"},
        }
    )
    assert seen == ["new-key"] and result["provider"] == "crawl4ai"
    assert "private-page-canary" not in json.dumps(result)
    assert "new-key" not in json.dumps(result)


def test_startup_loads_independent_fetch_preferences(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    update_settings(
        tmp_path / "data/chat-preferences.json",
        {
            ("fetch_settings",): {
                "provider": "exa",
                "crawl4ai_enabled": False,
                "exa_fallback": False,
                "crawl4ai_url": "http://127.0.0.1:11235",
            }
        },
    )
    cfg = config.load_config()
    assert fetch_provider(cfg) == "exa" and not exa_fallback(cfg)
    assert not cfg.web_fetch.crawl4ai_enabled and cfg.crawl4ai_url == "http://127.0.0.1:11235"


def test_explicit_url_read_survives_search_prohibition_and_availability_still_wins():
    from klaude_cli.main import _select_tool_names
    from klaude_core.agent import Tool
    from klaude_core.intent import explicit_public_page_read_request

    prompt = (
        "Fetch https://example.com and summarize this page. "
        "Do not search, learn, write files or run shell."
    )
    tools = {
        name: Tool(name, name, {"type": "object", "properties": {}}, lambda: "")
        for name in ("fetch_url", "web_search", "learn_source", "run_shell", "write_file")
    }
    assert _select_tool_names(prompt, tools) == ["fetch_url"]
    assert _select_tool_names(prompt, {"web_search": tools["web_search"]}) == []
    assert not explicit_public_page_read_request("Do not fetch https://example.com")
    assert not explicit_public_page_read_request("Read file.py; do not fetch https://example.com")
    assert _select_tool_names("Fetch https://example.com but do not use any tools", tools) == []


def test_transient_editor_prioritizes_error_over_long_navigation_hints(tmp_path):
    item = controller(tmp_path)
    item.provider = "crawl4ai"
    item.show("detail")
    action(item, "endpoint")
    item.host._answer_settings_input("http://user:secret@localhost")
    fragments = item.host._status_fragments()
    text = "".join(value for _, value in fragments)
    assert "without credentials" in text
    assert "Enter submit" not in text
    assert all(style == "class:runtime_error" for style, _value in fragments)


def test_custom_exa_reference_is_shared_on_startup_and_saved_removal_wins(tmp_path, monkeypatch):
    from klaude_core.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[web.providers.exa]\napi_key_env="TEAM_EXA_KEY"\n')
    monkeypatch.setenv("TEAM_EXA_KEY", "inherited-key")
    assert load_config().exa_api_key == "inherited-key"
    save_provider_secret(config_dir, "TEAM_EXA_KEY", "new-key")
    assert load_config().exa_api_key == "new-key"
    save_provider_secret(config_dir, "TEAM_EXA_KEY", "")
    monkeypatch.setenv("TEAM_EXA_KEY", "stale-key")
    assert load_config().exa_api_key == ""


def test_crawl4ai_saved_removal_overrides_toml_and_old_environment_on_restart(
    tmp_path, monkeypatch
):
    from klaude_core.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[services]\ncrawl4ai_api_key="toml-key"\n')
    save_provider_secret(config_dir, "CRAWL4AI_API_KEY", "")
    monkeypatch.setenv("CRAWL4AI_API_KEY", "stale-key")
    assert load_config().crawl4ai_api_key == ""


def test_worker_can_use_custom_inherited_exa_reference_without_publishing_it(tmp_path, monkeypatch):
    cfg = Config()
    cfg.web_providers["exa"].api_key_env = "TEAM_EXA_KEY"
    monkeypatch.setattr("klaude_core.config.load_config", lambda: cfg)
    seen = []

    def fetch(self, url, **_kw):
        seen.append(self.cfg.exa_api_key)
        return {"provider": "exa", "content": "content", "attempted_providers": ["exa"]}

    monkeypatch.setattr(Web, "_fetch_uncached_detailed", fetch)
    result = run_fetch_test(
        {
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "url": "https://example.com",
            "environment_keys": {"TEAM_EXA_KEY": "custom-canary"},
        }
    )
    assert seen == ["custom-canary"] and "custom-canary" not in json.dumps(result)


def test_search_diagnostic_uses_the_same_custom_exa_reference(tmp_path, monkeypatch):
    from klaude_cli.search_settings import run_search_test
    from klaude_web.search import SearchResponse

    cfg = Config()
    cfg.web_providers["exa"].api_key_env = "TEAM_EXA_KEY"
    monkeypatch.setattr("klaude_core.config.load_config", lambda: cfg)
    seen = []

    def search(config, *_a, **_kw):
        seen.append(config.exa_api_key)
        return SearchResponse(results=[], warnings=[])

    monkeypatch.setattr("klaude_web.providers.quality_search", search)
    result = run_search_test(
        {
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "query": "Example",
            "environment_keys": {"TEAM_EXA_KEY": "custom-canary"},
        }
    )
    assert seen == ["custom-canary"] and "custom-canary" not in json.dumps(result)


def test_blank_endpoint_is_authoritative_in_worker_snapshot_and_can_be_removed(tmp_path):
    cfg = Config(crawl4ai_url="http://old-service.test")
    assert public_fetch_settings({"crawl4ai_url": ""}) == {"crawl4ai_url": ""}
    apply_fetch_settings(cfg, {"crawl4ai_url": ""})
    assert cfg.crawl4ai_url == ""
    item = controller(tmp_path)
    item.provider = "crawl4ai"
    item.show("detail")
    item.answer("endpoint", "")
    item.host._before_render(None)
    assert (
        json.loads(item.host.chat_preferences_path.read_text())["fetch_settings"]["crawl4ai_url"]
        == ""
    )


def test_changed_exa_endpoint_invalidates_failed_attempt_identity(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    attempts = []

    def fetch(url):
        attempts.append(url)
        raise FetchPageError("endpoint unavailable", failure_class="provider_failure")

    monkeypatch.setattr(web, "_fetch_uncached_detailed", fetch)
    web.fetch_detailed("https://example.com")
    assert web.fetch_detailed("https://example.com")["attempt_reused"]
    web.cfg.exa_base_url = "https://another-extraction.test"
    assert not web.fetch_detailed("https://example.com").get("attempt_reused")
    assert len(attempts) == 2


def test_cloud_fallback_reports_only_providers_actually_attempted(tmp_path, monkeypatch):
    web = make_web(tmp_path)
    web.cfg.web_fetch.exa_fallback = True
    web.cfg.exa_api_key = "key"

    def fetch(url, *_a, **_k):
        raise FetchPageError(
            "unsupported",
            failure_class="unsupported_content_type",
            final_url=url,
            attempted_providers=("direct",),
        )

    monkeypatch.setattr("klaude_web.facade.fetch_page_detailed", fetch)
    monkeypatch.setattr("klaude_web.facade.validate_public_url", lambda url: url)
    monkeypatch.setattr("klaude_web.facade.exa_fetch", lambda *_a, **_k: "content")
    result = web.fetch_detailed("https://example.com")
    assert result["attempted_providers"] == ["direct", "exa"]
