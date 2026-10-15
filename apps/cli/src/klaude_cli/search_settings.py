"""Web Search settings: in-memory pages, ordered saves and owned diagnostics."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import replace
from typing import Any

from klaude_core.search_settings import (
    KEYS,
    PROVIDERS,
    apply_search_settings,
    primary_provider,
    public_search_settings,
    service_url,
)
from klaude_core.settings_store import DELETE

from .model_settings import row as model_row
from .session_actions import SearchProviderSecret
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

KEY_LABELS = {
    "Brave Search": "brave_api",
    "Parallel": "parallel",
    "Tavily": "tavily",
    "Exa": "exa",
    "Firecrawl": "firecrawl",
}
PURPOSES = {
    "brave": "Keyless Brave website search through DDGS.",
    "brave_api": "Official Brave Search API; separate from keyless Brave.",
    "google": "Google Search Grounding; shares the Gemini API key with chat.",
    "parallel": "Parallel hosted web search.",
    "exa": "Exa semantic web search; its key is also used by URL Fetch.",
    "ddgs": "Keyless metasearch through the optional DDGS package.",
    "tavily": "Tavily search; Advanced depth may consume more credits.",
    "firecrawl": "Firecrawl search; scrape/crawl products are not enabled here.",
    "searxng": "Your configured SearXNG service; deployment secrets stay in searxng.env.",
}


def row(identity: str, label: str, value: str = "", **kwargs: Any) -> PanelRow:
    item = model_row(identity, label, value, **kwargs)
    return replace(
        item, action=PanelAction("search-settings-" + identity, kwargs.get("target", ""))
    )


def back(target: str) -> PanelRow:
    return row("back", "Back", target=target, kind=RowKind.NAVIGATION, control=RowControl.BACK)


def run_search_test(request: dict[str, Any]) -> dict[str, Any]:
    """Private worker; no snippets, credentials or upstream errors in the result."""
    from klaude_core.config import load_config, provider_secret_value
    from klaude_web.providers import quality_search

    os.environ["KLAUDE_CONFIG_DIR"] = request["config_dir"]
    os.environ["KLAUDE_DATA_DIR"] = request["data_dir"]
    cfg = load_config()
    for name, (default_env, attr) in KEYS.items():
        reference = cfg.web_providers[name].api_key_env or default_env
        value = request.get("environment_keys", {}).get(reference)
        if isinstance(value, str) and len(value) <= 8192:
            os.environ[reference] = value
        fallback = getattr(cfg, attr, "") if reference == default_env else ""
        setattr(cfg, attr, provider_secret_value(cfg.config_dir, reference, fallback))
    apply_search_settings(cfg, request.get("settings"))
    for name, enabled in request.get("availability", {}).items():
        if name in cfg.web_providers and isinstance(enabled, bool):
            cfg.web_providers[name].enabled = enabled
    cfg.web_search.result_validation_enabled = request.get("validation") is not False
    if request.get("enabled") is False:
        return {"status": "disabled", "message": "Web Search is disabled", "attempted": []}
    query = str(request.get("query", "")).strip()
    provider = str(request.get("provider", ""))
    if not query or len(query) > 500 or provider not in {"", *PROVIDERS}:
        raise ValueError("Invalid search test")
    if provider:
        # Detail tests identify this provider, never silently test a fallback.
        cfg.web_search.allow_explicit_provider_fallback = False
    start = time.monotonic()
    try:
        response = quality_search(
            cfg,
            query,
            cfg.web_search.default_results,
            provider=provider or None,
            provider_strict=bool(provider),
        )
    except Exception:
        return {
            "status": "failed",
            "message": "Search test failed; check provider settings",
            "attempted": [],
            "count": 0,
        }
    attempted = [name for name in response.providers_attempted if name in PROVIDERS][:9]
    used = [name for name in response.providers_succeeded if name in PROVIDERS][:9]
    count = len(response.results)
    metadata = response.provider_metadata or {}
    states = [
        item.get("status")
        for item in metadata.get("provider_attempts", [])
        if isinstance(item, dict)
    ]
    status = "ok" if count else "empty" if used else "failed"
    if not count and "authentication_failed" in states:
        status = "authentication"
    elif not count and "quota_exhausted" in states:
        status = "quota"
    elif not count and "rate_limited" in states:
        status = "rate_limit"
    names = ", ".join(PROVIDERS[name] for name in used or attempted) or "No provider"
    issue = {
        "authentication": "Authentication failed",
        "quota": "Quota exhausted",
        "rate_limit": "Rate limited",
        "failed": "Search unavailable",
        "empty": "No results",
    }.get(status)
    return {
        "status": status,
        "message": f"{issue} · {names}" if issue else f"{names} · {count} results",
        "attempted": attempted,
        "used": used,
        "count": min(count, 50),
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    }


class SearchSettings:
    def __init__(self, host: Any):
        self.host = host
        self.view, self.provider, self.parent = "home", "", "settings"
        self.feedback: tuple[str, str] | None = None
        self.test: tuple[str, str, int] | None = None
        self.epoch = 0
        self.key_pending: tuple[str, str, str] | None = None
        self.result: dict[str, Any] | None = None
        self.defaults = {"results": 12}
        self.test_profile: tuple[Any, ...] | None = None

    @property
    def visible(self) -> bool:
        return str(self.host._choice_kind).startswith("search settings ")

    def show(self, view: str | None = None, focus: str = "") -> None:
        if view is not None:
            self.view = view
        self.host._open_panel(self.page(), "search settings " + self.view, focus)
        if focus:
            self.host._panel.picker.focus(focus)
            self.host._apply_picker_state()
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def open(self, *, provider: str = "", parent: str = "settings") -> None:
        self.parent = parent
        self.provider = provider
        self.feedback = None
        self.show("detail" if provider else "home")

    def order(self) -> list[str]:
        cfg = self.host.cfg
        names = cfg.web_search.settings_fallbacks
        return list(dict.fromkeys(names if names is not None else cfg.web_search.provider_order))

    def configured(self, name: str) -> str:
        cfg = self.host.cfg
        if name in KEYS:
            env, attr = KEYS[name]
            env = cfg.web_providers[name].api_key_env or env
            return (
                "Configured · untested"
                if getattr(cfg, attr, "") or os.getenv(env)
                else "API key missing"
            )
        if name == "searxng":
            return "Endpoint set · untested" if cfg.searxng_url else "Endpoint missing"
        return "Keyless · untested"

    def page(self) -> PanelPage:
        cfg = self.host.cfg
        primary = primary_provider(cfg)
        enabled = self.host._tool_availability["web_search"]
        crumbs: tuple[str, ...] = ("Settings", "Search", "Web Search")
        rows: list[PanelRow] = []
        if self.view == "home":
            rows = [
                row(
                    "enabled",
                    "Tool availability",
                    "ON" if enabled else "OFF",
                    kind=RowKind.NAVIGATION,
                    description="Manage in Tools",
                ),
                row(
                    "provider",
                    "Provider",
                    "Auto" if primary == "auto" else PROVIDERS[primary],
                    description="Current routing"
                    if cfg.web_search.settings_provider is None
                    else "Explicit selection",
                ),
                row("results", "Results per query", str(cfg.web_search.default_results)),
                row(
                    "providers",
                    "Manage providers",
                    description="Enabled state, credentials and provider options",
                ),
                row(
                    "test",
                    "Test search",
                    description="Sends a query; provider charges and billing policy apply",
                    enabled=enabled,
                ),
                row(
                    "fallbacks",
                    "Fallback order",
                    str(sum(name != primary for name in self.order())) + " listed",
                    description="Eligible providers only; existing attempt limits apply",
                ),
                row(
                    "validation",
                    "Validate search results",
                    "ON" if self.host._tool_validation["web_search"] else "OFF",
                    kind=RowKind.TOGGLE,
                    checked=self.host._tool_validation["web_search"],
                ),
                replace(
                    row(
                        "research",
                        "Deep Research",
                        description="Research defaults and bounded budgets",
                    ),
                    action=PanelAction("library-research-settings", "search"),
                ),
                row(
                    "url-fetch",
                    "URL Fetch settings",
                    description="Page reading, extraction providers and transport limits",
                ),
                row(
                    "reset",
                    "Reset to default",
                    control=RowControl.RESET,
                    description="Routing and result count only; keep keys and availability",
                ),
                back(self.parent),
            ]
        elif self.view in {"providers", "provider", "add-fallback"}:
            crumbs += (
                "Providers"
                if self.view == "providers"
                else "Provider"
                if self.view == "provider"
                else "Add fallback",
            )
            if self.view == "provider":
                rows.append(
                    row(
                        "select",
                        "Auto",
                        target="auto",
                        description="Use configured routing and eligible fallbacks",
                    )
                )
            for name in PROVIDERS:
                available = self.host._web_provider_availability[name]
                if self.view == "add-fallback" and (name in self.order() or name == primary):
                    continue
                rows.append(
                    row(
                        "select:" + name,
                        PROVIDERS[name],
                        "ON" if available else "OFF",
                        target=name,
                        description=self.configured(name),
                    )
                )
            rows.append(back("fallbacks" if self.view == "add-fallback" else "home"))
        elif self.view == "results":
            crumbs += ("Results per query",)
            rows = [
                row(
                    "count:" + str(n),
                    str(n),
                    "Current" if n == cfg.web_search.default_results else "",
                    target=str(n),
                )
                for n in (3, 5, 10, 12, 20)
            ]
            rows.extend(
                [
                    row(
                        "custom-results",
                        "Custom",
                        str(cfg.web_search.default_results),
                        description="1–50 results",
                    ),
                    back("home"),
                ]
            )
        elif self.view == "detail":
            name = self.provider
            available = self.host._web_provider_availability[name]
            crumbs += ("Providers", PROVIDERS[name])
            rows = [
                PanelRow("purpose", RowKind.INFO, PURPOSES[name]),
                row(
                    "provider-enabled",
                    "Enabled",
                    "ON" if available else "OFF",
                    kind=RowKind.TOGGLE,
                    checked=available,
                ),
            ]
            if name in KEYS:
                env, _attr = KEYS[name]
                env = cfg.web_providers[name].api_key_env or env
                rows.append(
                    row(
                        "key",
                        "API key",
                        self.configured(name),
                        description=env,
                        enabled=self.key_pending is None,
                    )
                )
                rows.append(row("remove-key", "Remove API key", enabled=self.key_pending is None))
            if name == "searxng":
                rows.append(row("endpoint", "Endpoint URL", cfg.searxng_url))
            if name == "tavily":
                rows.append(row("depth", "Search depth", cfg.web_providers[name].default_depth))
            rows.extend(
                [
                    row(
                        "test-provider",
                        "Test provider",
                        description="This provider only; no fallback",
                        enabled=enabled and available,
                    ),
                    back("providers" if self.parent != "providers" else "legacy-providers"),
                ]
            )
        elif self.view == "remove-key":
            crumbs += (PROVIDERS[self.provider], "Remove API key")
            rows = [
                PanelRow(
                    "warning",
                    RowKind.INFO,
                    "Remove this provider's shared API key?",
                    description=PURPOSES[self.provider],
                ),
                row("confirm-remove-key", "Remove API key"),
                row(
                    "back",
                    "Cancel",
                    target="detail",
                    control=RowControl.CANCEL,
                    kind=RowKind.NAVIGATION,
                ),
            ]
        elif self.view == "fallbacks":
            crumbs += ("Fallback order",)
            rows = [row("add-fallback", "Add fallback")]
            for i, name in enumerate(self.order()):
                if name == primary:
                    continue
                rows.append(
                    row(
                        "fallback:" + name,
                        f"{i + 1}. {PROVIDERS[name]}",
                        "ON" if self.host._web_provider_availability[name] else "OFF",
                        target=name,
                    )
                )
            rows.append(
                PanelRow(
                    "policy",
                    RowKind.INFO,
                    "Unavailable entries are skipped",
                    description="Existing relevance, quota, billing and attempt limits apply.",
                )
            )
            rows.append(back("home"))
        elif self.view == "fallback-detail":
            crumbs += ("Fallback order", PROVIDERS[self.provider])
            position = self.order().index(self.provider)
            rows = [
                row("move-up", "Move up", enabled=position > 0),
                row("move-down", "Move down", enabled=position < len(self.order()) - 1),
                row("remove-fallback", "Remove from fallback order"),
                back("fallbacks"),
            ]
        if self.test:
            rows.insert(
                0,
                row(
                    "cancel-test",
                    "Cancel test",
                    description="Test running; leaving this page also cancels",
                ),
            )
        scope = self.provider if self.view in {"detail", "remove-key", "fallback-detail"} else ""
        return PanelPage(
            "search:" + self.view + ":" + scope, crumbs, tuple(rows), scroll_wrapped_rows=True
        )

    def notify(self, message: str, tone: str = "neutral") -> None:
        self.feedback = (message, tone)
        if self.visible:
            self.host._set_panel_feedback(message, tone)

    def changed(self) -> None:
        self.epoch += 1
        self.leave()
        self.result = None
        self.feedback = None

    def save(self, changes: dict[tuple[str, ...], object], focus: str = "") -> None:
        self.changed()
        self.host._apply_live_tool_preferences()
        self.host._submit_preference_changes(changes)
        self.show(focus=focus)

    def set_value(self, key: str, value: Any, focus: str = "") -> None:
        apply_search_settings(self.host.cfg, {key: value})
        if self.host.agent.tool_config is not self.host.cfg:
            apply_search_settings(self.host.agent.tool_config, {key: value})
        self.save({("search_settings", key): value}, focus)

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("search-settings-")
        if kind == "back":
            if action.target == "agent-tool":
                self.leave()
                self.host._agent_settings.show("tool", "configure")
                return
            if action.target in {"settings", "tools", "legacy-providers"}:
                self.leave()
                category = "providers" if action.target == "legacy-providers" else action.target
                if category == "settings":
                    self.host._begin_choice(
                        "settings", self.host._settings_categories(), "search", refresh=True
                    )
                else:
                    self.host._open_settings_category(category, restore=True)
            else:
                self.show(action.target)
        elif kind == "url-fetch":
            if not hasattr(self.host, "_fetch_settings"):
                from .fetch_settings import FetchSettings

                self.host._fetch_settings = FetchSettings(self.host)
            self.host._fetch_settings.open(parent="search")
        elif kind in {"provider", "providers", "results", "fallbacks", "add-fallback"}:
            self.show(kind)
        elif kind == "enabled":
            self.host._agent_settings.open_tool("web_search", parent="search")
        elif kind == "validation":
            values = self.host._tool_validation
            values["web_search"] = not values["web_search"]
            self.save({("tool_validation", "web_search"): values["web_search"]}, "validation")
        elif kind == "provider-enabled":
            values = self.host._web_provider_availability
            values[self.provider] = not values[self.provider]
            self.save(
                {("web_provider_availability", self.provider): values[self.provider]},
                "provider-enabled",
            )
        elif kind.startswith("select"):
            if self.view == "providers":
                self.provider = action.target
                self.show("detail")
            elif self.view == "add-fallback":
                self.view = "fallbacks"
                self.set_value("fallbacks", [*self.order(), action.target])
            else:
                self.view = "home"
                self.set_value("provider", action.target, "provider")
        elif kind.startswith("count:"):
            self.view = "home"
            self.set_value("results", int(action.target), "results")
        elif kind.startswith("fallback:"):
            self.provider = action.target
            self.show("fallback-detail")
        elif kind in {"move-up", "move-down", "remove-fallback"}:
            order = self.order()
            i = order.index(self.provider)
            if kind == "remove-fallback":
                order.remove(self.provider)
                self.view = "fallbacks"
            else:
                j = i + (-1 if kind == "move-up" else 1)
                if not 0 <= j < len(order):
                    return
                order[i], order[j] = order[j], order[i]
            self.set_value("fallbacks", order, kind)
        elif kind == "depth":
            depth = self.host.cfg.web_providers["tavily"].default_depth
            self.set_value("tavily_depth", "advanced" if depth == "basic" else "basic", "depth")
        elif kind in {"custom-results", "endpoint", "test", "test-provider"}:
            self.host._begin_settings_input(
                "Results per query"
                if kind == "custom-results"
                else "SearXNG endpoint"
                if kind == "endpoint"
                else "Test search",
                "1–50 results"
                if kind == "custom-results"
                else "HTTP(S) service URL"
                if kind == "endpoint"
                else "Query sent to provider(s); charges may apply",
                ("search-settings", kind),
            )
            self.host._set_input(
                str(self.host.cfg.web_search.default_results)
                if kind == "custom-results"
                else self.host.cfg.searxng_url
                if kind == "endpoint"
                else "Python asyncio documentation"
            )
        elif kind == "key":
            self.host._begin_search_secret()
        elif kind == "remove-key":
            self.show("remove-key", "back")
        elif kind == "confirm-remove-key":
            self.save_key("")
        elif kind == "cancel-test":
            self.leave()
            self.show()
            self.notify("Test cancelled")
        elif kind == "reset":
            for target in (self.host.cfg, self.host.agent.tool_config):
                target.web_search.settings_provider = None
                target.web_search.settings_fallbacks = None
                target.web_search.default_results = self.defaults["results"]
            self.save(
                {
                    ("search_settings", name): DELETE
                    for name in ("provider", "fallbacks", "results")
                },
                "reset",
            )

    def answer(self, kind: str, value: str | None) -> None:
        if value is None:
            self.show()
        elif kind == "custom-results":
            try:
                count = int(value)
            except ValueError:
                raise ValueError("Enter a result count from 1 to 50") from None
            if not 1 <= count <= 50:
                raise ValueError("Enter a result count from 1 to 50")
            self.view = "home"
            self.set_value("results", count, "results")
        elif kind == "endpoint":
            self.set_value("searxng_url", service_url(value), "endpoint")
        else:
            if not value.strip() or len(value) > 500:
                raise ValueError("Enter a test query of 1–500 characters")
            self.start_test(value, self.provider if kind == "test-provider" else "")

    def start_test(self, query: str, provider: str = "") -> None:
        self.leave()
        cfg = self.host.cfg
        settings = {
            "provider": primary_provider(cfg),
            "results": cfg.web_search.default_results,
            "fallbacks": self.order(),
            "searxng_url": cfg.searxng_url,
            "tavily_depth": cfg.web_providers["tavily"].default_depth,
        }
        identity = self.host._background_jobs.submit(
            "search-settings:test",
            {
                "kind": "search_settings_test",
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "query": query,
                "provider": provider,
                "settings": public_search_settings(settings),
                "availability": dict(self.host._web_provider_availability),
                "enabled": self.host._tool_availability["web_search"],
                "validation": self.host._tool_validation["web_search"],
                "environment_keys": {
                    (cfg.web_providers[name].api_key_env or env): str(
                        getattr(cfg, attr, "")
                        or os.getenv(cfg.web_providers[name].api_key_env or env, "")
                    )
                    for name, (env, attr) in KEYS.items()
                },
            },
            timeout=25,
        )
        self.test = identity, self.host.session_id, self.epoch
        self.test_profile = self.signature()
        self.show()
        self.notify("Testing search…")

    def leave(self) -> None:
        self.host._background_jobs.cancel("search-settings:test")
        self.test = None

    def accept(self, identity: str, result: Any, error: str) -> None:
        if self.test != (identity, self.host.session_id, self.epoch) or not self.visible:
            return
        if self.test_profile != self.signature():
            self.leave()
            self.show()
            self.notify("Settings changed; rerun test", "warning")
            return
        self.test = None
        self.result = result if isinstance(result, dict) else None
        self.show()
        if error or self.result is None:
            self.notify("Search test unavailable or timed out; retry", "error")
        else:
            status = self.result.get("status")
            self.notify(
                str(self.result.get("message", "Test finished")),
                "success"
                if status == "ok"
                else "warning"
                if status in {"empty", "disabled"}
                else "error",
            )

    def save_key(self, value: str | None) -> None:
        self.show("detail", "key")
        if value is None:
            return
        if self.key_pending:
            raise ValueError("Wait for the accepted key save")
        if len(value) > 8192 or any(c in value for c in "\r\n\x00"):
            raise ValueError("API keys must be a single line, at most 8,192 characters")
        identity = uuid.uuid4().hex
        env, _attr = KEYS[self.provider]
        env = self.host.cfg.web_providers[self.provider].api_key_env or env
        accepted = self.host._session_actions.submit(
            SearchProviderSecret(
                self.host.session_id,
                identity,
                self.host.cfg,
                env,
                value,
                "gemini_api" if self.provider == "google" else "",
            )
        )
        if not accepted:
            self.notify("Key save not accepted; retry", "error")
            return
        self.changed()
        self.key_pending = identity, self.provider, value
        self.show("detail", "key")
        self.notify("Saving API key…")

    def saved_key(self, payload: Any) -> None:
        session, identity, saved, catalog_ok = payload
        if not self.key_pending or self.key_pending[0] != identity:
            return
        _, name, value = self.key_pending
        self.key_pending = None
        if saved:
            _env, attr = KEYS[name]
            setattr(self.host.cfg, attr, value)
            setattr(self.host.agent.tool_config, attr, value)
        if self.visible:
            self.show()
            self.notify(
                PROVIDERS[name] + " API key saved"
                if saved and value
                else PROVIDERS[name] + " API key removed"
                if saved
                else PROVIDERS[name] + " API key save unconfirmed; retry",
                "success" if saved and catalog_ok else "warning" if saved else "error",
            )
            if saved and not catalog_ok:
                self.notify(
                    PROVIDERS[name] + " key saved; model catalog refresh unconfirmed", "warning"
                )

    def signature(self) -> tuple[Any, ...]:
        cfg = self.host.cfg
        return (
            primary_provider(cfg),
            tuple(self.order()),
            cfg.web_search.default_results,
            cfg.searxng_url,
            cfg.web_providers["tavily"].default_depth,
            tuple(self.host._web_provider_availability.items()),
            self.host._tool_availability["web_search"],
            self.host._tool_validation["web_search"],
        )

    def merge_saved(self, values: Any) -> None:
        before = self.signature()
        for target in (self.host.cfg, self.host.agent.tool_config):
            target.web_search.settings_provider = None
            target.web_search.settings_fallbacks = None
            target.web_search.default_results = self.defaults["results"]
            apply_search_settings(target, values)
        if before != self.signature() or self.test and self.test_profile != self.signature():
            self.changed()
