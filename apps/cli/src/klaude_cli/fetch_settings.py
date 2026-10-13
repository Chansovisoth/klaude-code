"""URL Fetch controls with private credentials and cancellable, bounded tests."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import replace
from typing import Any

from klaude_core.fetch_settings import (
    apply_fetch_settings,
    exa_fallback,
    fetch_provider,
    public_fetch_settings,
)
from klaude_core.search_settings import service_url
from klaude_core.settings_store import DELETE

from .model_settings import row as model_row
from .search_settings import SearchSettings
from .session_actions import SearchProviderSecret
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

KEYS = {"crawl4ai": ("CRAWL4AI_API_KEY", "crawl4ai_api_key"), "exa": ("EXA_API_KEY", "exa_api_key")}
NAMES = {"crawl4ai": "Crawl4AI", "exa": "Exa"}


def row(identity: str, label: str, value: str = "", **kwargs: Any) -> PanelRow:
    return replace(
        model_row(identity, label, value, **kwargs),
        action=PanelAction("fetch-settings-" + identity, kwargs.get("target", "")),
    )


def back(target: str) -> PanelRow:
    return row("back", "Back", target=target, kind=RowKind.NAVIGATION, control=RowControl.BACK)


def run_fetch_test(request: dict[str, Any]) -> dict[str, Any]:
    """Exercise the real uncached route, returning only sanitized outcome metadata."""
    from klaude_core.config import load_config, provider_secret_value
    from klaude_web.facade import Web
    from klaude_web.fetch import FetchPageError, UnsafeURL, canonicalize_public_url

    os.environ["KLAUDE_CONFIG_DIR"] = request["config_dir"]
    os.environ["KLAUDE_DATA_DIR"] = request["data_dir"]
    cfg = load_config()
    for provider, (env, attr) in KEYS.items():
        reference = (cfg.web_providers["exa"].api_key_env or env) if provider == "exa" else env
        value = request.get("environment_keys", {}).get(reference)
        if isinstance(value, str) and len(value) <= 8192:
            os.environ[reference] = value
        fallback = getattr(cfg, attr, "") if reference == env else ""
        setattr(cfg, attr, provider_secret_value(cfg.config_dir, reference, fallback))
    apply_fetch_settings(cfg, request.get("settings"))
    if request.get("enabled") is False:
        return {"status": "disabled", "message": "URL Fetch is disabled"}
    provider = request.get("provider", "")
    if provider not in ("", "local", "crawl4ai", "exa"):
        raise ValueError("Invalid fetch provider")
    # Detail tests exercise exactly that extraction choice, without cloud fallback.
    if provider:
        cfg.web_fetch.settings_provider = "exa" if provider == "exa" else "local"
        cfg.web_fetch.exa_fallback = False
    start = time.monotonic()
    try:
        url = canonicalize_public_url(str(request.get("url", "")))
        result = Web(cfg)._fetch_uncached_detailed(
            url, extraction=provider if provider == "crawl4ai" else ""
        )
    except UnsafeURL:
        return {"status": "unsafe_url", "message": "URL blocked by public-address safety rules"}
    except FetchPageError as exc:
        reason = exc.failure_class
        labels = {
            "timeout": "Fetch timed out",
            "authentication": "Authentication failed",
            "rate_limit": "Rate limited",
            "disabled": "Provider is disabled",
            "configuration": "Provider configuration missing",
            "response_too_large": "Provider response too large",
        }
        return {
            "status": reason,
            "message": labels.get(reason, "Fetch failed; check URL and provider settings"),
        }
    except Exception:
        return {"status": "failed", "message": "Fetch failed; check URL and provider settings"}
    used = result.get("provider", "")
    used = used if used in {"direct", "trafilatura", *NAMES} else "unknown"
    fallback = bool(result.get("fallback_used"))
    return {
        "status": "ok",
        "provider": used,
        "attempted": [
            p
            for p in result.get("attempted_providers", [])
            if p in {"direct", "trafilatura", *NAMES}
        ][:4],
        "characters": min(len(result.get("content", "")), cfg.web_fetch.max_content_characters),
        "fallback": fallback,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "message": f"{NAMES.get(used, used.title())} · "
        f"{len(result.get('content', '')):,} characters"
        + (" · cloud fallback used" if fallback else ""),
    }


class FetchSettings(SearchSettings):
    """Reuse the existing live-state/save lifecycle; fetching has its own route."""

    def __init__(self, host: Any):
        super().__init__(host)
        self.endpoint_default = host.cfg.crawl4ai_url

    @property
    def visible(self) -> bool:
        return str(self.host._choice_kind).startswith("fetch settings ")

    def open(self, *, provider: str = "", parent: str = "search") -> None:
        super().open(provider=provider, parent=parent)

    def show(self, view: str | None = None, focus: str = "") -> None:
        if view is not None:
            self.view = view
        self.host._open_panel(self.page(), "fetch settings " + self.view, focus)
        if focus:
            self.host._panel.picker.focus(focus)
            self.host._apply_picker_state()
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def key_reference(self, name: str) -> str:
        env = KEYS[name][0]
        return (self.host.cfg.web_providers["exa"].api_key_env or env) if name == "exa" else env

    def configured(self, name: str) -> str:
        return (
            "Configured · untested"
            if getattr(self.host.cfg, KEYS[name][1], "")
            else "Optional key not set"
            if name == "crawl4ai"
            else "API key missing"
        )

    def page(self) -> PanelPage:
        cfg = self.host.cfg
        enabled = self.host._tool_availability["fetch_url"]
        crumbs: tuple[str, ...] = ("Settings", "Search", "URL Fetch")
        rows: list[PanelRow] = []
        if self.view == "home":
            route = "Local cascade" if fetch_provider(cfg) == "local" else "Exa cloud"
            rows = [
                row(
                    "enabled",
                    "Tool availability",
                    "ON" if enabled else "OFF",
                    kind=RowKind.NAVIGATION,
                    description="Manage in Agent Tools",
                ),
                row(
                    "provider",
                    "Provider",
                    route,
                    description="Existing routing"
                    if cfg.web_fetch.settings_provider is None
                    else "Independent of Web Search",
                ),
                row(
                    "crawl4ai",
                    "Crawl4AI",
                    "ON" if cfg.web_fetch.crawl4ai_enabled else "OFF",
                    description="Optional extraction service · "
                    + ("endpoint set" if cfg.crawl4ai_url else "endpoint missing"),
                ),
                row(
                    "exa",
                    "Exa",
                    "ON" if cfg.web_fetch.exa_enabled else "OFF",
                    description="Cloud extraction · " + self.configured("exa"),
                ),
                row(
                    "fallback",
                    "Exa cloud fallback",
                    "ON" if exa_fallback(cfg) else "OFF",
                    kind=RowKind.TOGGLE,
                    checked=exa_fallback(cfg),
                    description="Local extraction failures only; may incur charges",
                    enabled=fetch_provider(cfg) == "local",
                ),
                row(
                    "test",
                    "Test fetch",
                    description="Reads a public URL without learning or saving page content",
                    enabled=enabled,
                ),
                row(
                    "limits",
                    "Transport limits",
                    description="Current config limits; safety rules always apply",
                ),
                row(
                    "reset",
                    "Reset to default",
                    control=RowControl.RESET,
                    description="Restore config routing; keep endpoint, keys and availability",
                ),
                back(self.parent),
            ]
        elif self.view == "provider":
            crumbs += ("Provider",)
            rows = [
                row(
                    "choose:local",
                    "Local cascade",
                    "Current" if fetch_provider(cfg) == "local" else "",
                    target="local",
                    description="Direct text → configured Crawl4AI → local HTML extraction",
                ),
                row(
                    "choose:exa",
                    "Exa cloud",
                    "Current" if fetch_provider(cfg) == "exa" else "",
                    target="exa",
                    description="Explicit cloud choice; API charges may apply",
                ),
                back("home"),
            ]
        elif self.view == "detail":
            name = self.provider
            crumbs += (NAMES[name],)
            on = getattr(cfg.web_fetch, name + "_enabled")
            rows = [
                PanelRow(
                    "purpose",
                    RowKind.INFO,
                    "Configured extraction service; local/LAN endpoints supported."
                    if name == "crawl4ai"
                    else "Cloud page extraction. API key is shared with Web Search.",
                ),
                row(
                    "provider-enabled",
                    "Enabled for URL Fetch",
                    "ON" if on else "OFF",
                    kind=RowKind.TOGGLE,
                    checked=on,
                ),
            ]
            if name == "crawl4ai":
                rows.append(
                    row(
                        "endpoint",
                        "Endpoint URL",
                        cfg.crawl4ai_url or "Not configured",
                        description="Service root; Klaude calls /md",
                    )
                )
            rows.extend(
                [
                    row(
                        "key",
                        "API key",
                        self.configured(name),
                        description=self.key_reference(name),
                        enabled=self.key_pending is None,
                    ),
                    row("remove-key", "Remove API key", enabled=self.key_pending is None),
                    row(
                        "test-provider",
                        "Test provider",
                        description="This extraction provider only; no fallback",
                        enabled=enabled and on,
                    ),
                    back("providers" if self.parent == "providers" else "home"),
                ]
            )
        elif self.view == "remove-key":
            crumbs += (NAMES[self.provider], "Remove API key")
            rows = [
                PanelRow(
                    "warning",
                    RowKind.INFO,
                    "Remove this API key?",
                    description="Also affects Web Search."
                    if self.provider == "exa"
                    else "Authenticated requests to this service will lose their key.",
                ),
                row("confirm-remove-key", "Remove API key"),
                row(
                    "back",
                    "Cancel",
                    target="detail",
                    kind=RowKind.NAVIGATION,
                    control=RowControl.CANCEL,
                ),
            ]
        elif self.view == "limits":
            crumbs += ("Transport limits",)
            limits = cfg.web_fetch
            rows = [
                PanelRow(
                    "limits-info",
                    RowKind.INFO,
                    "Configured in config.toml → [web.fetch]",
                    description="Private addresses, credentials and unsafe redirects stay blocked.",
                ),
                PanelRow(
                    "timeout", RowKind.INFO, "Request timeout", f"{limits.timeout_seconds:g}s"
                ),
                PanelRow(
                    "bytes", RowKind.INFO, "Download limit", f"{limits.max_download_bytes:,} bytes"
                ),
                PanelRow(
                    "characters",
                    RowKind.INFO,
                    "Extracted content",
                    f"{limits.max_content_characters:,} characters",
                ),
                PanelRow("redirects", RowKind.INFO, "Redirect limit", str(limits.max_redirects)),
                PanelRow("cache", RowKind.INFO, "Cache TTL", f"{limits.cache_ttl_seconds:,}s"),
                back("home"),
            ]
        if self.test:
            rows.insert(0, row("cancel-test", "Cancel test", description="Fetching…"))
        scope = self.provider if self.view in {"detail", "remove-key"} else ""
        return PanelPage(
            "fetch:" + self.view + ":" + scope, crumbs, tuple(rows), scroll_wrapped_rows=True
        )

    def set_value(self, key: str, value: Any, focus: str = "") -> None:
        for cfg in (self.host.cfg, self.host.agent.tool_config):
            apply_fetch_settings(cfg, {key: value})
        self.save({("fetch_settings", key): value}, focus)

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("fetch-settings-")
        if kind == "back":
            if action.target == "agent-tool":
                self.leave()
                self.host._agent_settings.show("tool", "configure")
                return
            if action.target in {"search", "settings", "tools", "providers"}:
                self.leave()
                if action.target == "search":
                    self.host._search_settings.open()
                elif action.target == "settings":
                    self.host._begin_choice(
                        "settings", self.host._settings_categories(), "search", refresh=True
                    )
                else:
                    self.host._open_settings_category(action.target, restore=True)
            else:
                self.show(action.target)
        elif kind in {"provider", "limits"}:
            self.show(kind)
        elif kind in NAMES:
            self.provider = kind
            self.show("detail")
        elif kind == "enabled":
            self.host._agent_settings.open_tool("fetch_url", parent="fetch")
        elif kind == "provider-enabled":
            name = self.provider + "_enabled"
            self.set_value(name, not getattr(self.host.cfg.web_fetch, name), kind)
        elif kind == "fallback":
            self.set_value("exa_fallback", not exa_fallback(self.host.cfg), "fallback")
        elif kind.startswith("choose:"):
            self.view = "home"
            self.set_value("provider", action.target, "provider")
        elif kind in {"endpoint", "test", "test-provider"}:
            self.host._begin_settings_input(
                "Crawl4AI endpoint" if kind == "endpoint" else "Test fetch",
                "HTTP(S) service root; blank removes endpoint"
                if kind == "endpoint"
                else "Public page URL; configured service charges may apply",
                ("fetch-settings", kind),
            )
            self.host._set_input(
                self.host.cfg.crawl4ai_url if kind == "endpoint" else "https://example.com"
            )
        elif kind == "key":
            self.host._begin_fetch_secret()
        elif kind == "remove-key":
            self.show("remove-key", "back")
        elif kind == "confirm-remove-key":
            self.save_key("")
        elif kind == "cancel-test":
            self.leave()
            self.show()
            self.notify("Test cancelled")
        elif kind == "reset":
            for cfg in (self.host.cfg, self.host.agent.tool_config):
                cfg.web_fetch.settings_provider = None
                cfg.web_fetch.exa_fallback = None
            self.save(
                {("fetch_settings", k): DELETE for k in ("provider", "exa_fallback")}, "reset"
            )

    def answer(self, kind: str, value: str | None) -> None:
        if value is None:
            self.show()
        elif kind == "endpoint":
            self.set_value("crawl4ai_url", service_url(value) if value.strip() else "", "endpoint")
        else:
            from klaude_web.fetch import canonicalize_public_url

            self.start_test(
                canonicalize_public_url(value), self.provider if kind == "test-provider" else ""
            )

    def signature(self) -> tuple[Any, ...]:
        cfg = self.host.cfg
        return (
            fetch_provider(cfg),
            exa_fallback(cfg),
            cfg.crawl4ai_url,
            cfg.web_fetch.crawl4ai_enabled,
            cfg.web_fetch.exa_enabled,
            self.host._tool_availability["fetch_url"],
            cfg.crawl4ai_api_key,
            cfg.exa_api_key,
        )

    def merge_saved(self, values: Any) -> None:
        before = self.signature()
        for cfg in (self.host.cfg, self.host.agent.tool_config):
            cfg.web_fetch.settings_provider = None
            cfg.web_fetch.exa_fallback = None
            cfg.web_fetch.crawl4ai_enabled = cfg.web_fetch.exa_enabled = True
            cfg.crawl4ai_url = self.endpoint_default
            apply_fetch_settings(cfg, values)
        if before != self.signature():
            self.changed()

    def start_test(self, url: str, provider: str = "") -> None:
        self.leave()
        cfg = self.host.cfg
        values = {
            "provider": fetch_provider(cfg),
            "exa_fallback": exa_fallback(cfg),
            "crawl4ai_enabled": cfg.web_fetch.crawl4ai_enabled,
            "exa_enabled": cfg.web_fetch.exa_enabled,
            "crawl4ai_url": cfg.crawl4ai_url,
        }
        # Carry an explicit empty endpoint so newer disk state cannot select a service.
        identity = self.host._background_jobs.submit(
            "fetch-settings:test",
            {
                "kind": "fetch_settings_test",
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "url": url,
                "provider": provider,
                "settings": public_fetch_settings(values),
                "enabled": self.host._tool_availability["fetch_url"],
                "environment_keys": {
                    self.key_reference(name): str(getattr(cfg, attr, ""))
                    for name, (_env, attr) in KEYS.items()
                },
            },
            timeout=40,
        )
        self.test = identity, self.host.session_id, self.epoch
        self.test_profile = self.signature()
        self.show()
        self.notify("Testing fetch…")

    def leave(self) -> None:
        self.host._background_jobs.cancel("fetch-settings:test")
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
        self.notify(
            "Fetch test unavailable or timed out; retry"
            if error or self.result is None
            else str(self.result.get("message", "Test finished")),
            "success"
            if self.result and self.result.get("status") == "ok" and not error
            else "warning"
            if self.result and self.result.get("status") == "disabled"
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
        if not self.host._session_actions.submit(
            SearchProviderSecret(
                self.host.session_id,
                identity,
                self.host.cfg,
                self.key_reference(self.provider),
                value,
                owner="fetch",
            )
        ):
            self.notify("Key save not accepted; retry", "error")
            return
        self.changed()
        self.key_pending = identity, self.provider, value
        self.show("detail", "key")
        self.notify("Saving API key…")

    def saved_key(self, payload: Any) -> None:
        _session, identity, saved, _catalog_ok = payload
        if not self.key_pending or self.key_pending[0] != identity:
            return
        _, name, value = self.key_pending
        self.key_pending = None
        if saved:
            for cfg in (self.host.cfg, self.host.agent.tool_config):
                setattr(cfg, KEYS[name][1], value)
        if self.visible:
            self.show()
            self.notify(
                NAMES[name]
                + (
                    " API key saved"
                    if saved and value
                    else " API key removed"
                    if saved
                    else " API key save unconfirmed; retry"
                ),
                "success" if saved else "error",
            )
