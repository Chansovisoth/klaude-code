"""Model connection pages, unsaved drafts and owned catalog checks.

Only the ordered session action lane saves connections. Navigation and rendering
consume public snapshots; neither performs filesystem or network I/O.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlsplit

from klaude_core.ai_defaults import AIDefaults, defaults_from_preferences, read_defaults
from klaude_core.config import provider_secret_revision
from klaude_core.model_connections import (
    DEFAULT_IDS,
    DEFAULT_URLS,
    ModelConnection,
    connection_key,
    connection_registry,
    legacy_connections,
    validate_model_id,
)
from klaude_core.model_discovery import ModelDiscoveryError, discover_connection, probe_connection
from klaude_core.model_management import (
    OFFLINE_STATUSES,
    ModelChange,
    affected_startup,
    choices_from_payload,
    model_choice,
    public_snapshot,
    startup_snapshot,
)
from klaude_core.model_runtime import (
    ModelInfo,
    load_model_cache,
    model_cache_generation,
    model_records,
    models_from_records,
)

from .session_actions import ModelConnectionAdd, ModelConnectionUpdate
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

PREFIX = "model-settings-"
PROVIDERS = {
    "openai_api": "OpenAI API",
    "gemini_api": "Gemini API",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek",
    "anthropic": "Anthropic",
    "openai_compatible": "Custom compatible endpoint",
}
ADAPTERS = {"ollama": "Ollama native", "openai_compatible": "OpenAI-compatible"}


def row(
    identity: str,
    label: str,
    value: str = "",
    *,
    target: str = "",
    kind: RowKind = RowKind.ACTION,
    description: str = "",
    enabled: bool = True,
    control: RowControl | None = None,
    section: str = "",
    checked: bool | None = None,
) -> PanelRow:
    return PanelRow(
        identity,
        kind,
        label,
        value,
        description,
        enabled=enabled,
        action=PanelAction(PREFIX + identity, target),
        control=control,
        footer=control is not None,
        section_id=section,
        checked=checked,
    )


def back(target: str, *, cancel: bool = False) -> PanelRow:
    return row(
        "back",
        "Cancel" if cancel else "Back",
        target=target,
        kind=RowKind.NAVIGATION,
        control=RowControl.CANCEL if cancel else RowControl.BACK,
    )


@dataclass
class ConnectionDraft:
    source: str
    backend: str
    url: str
    identity: str = field(default_factory=lambda: "endpoint-" + uuid.uuid4().hex[:12])
    name: str = ""
    key: str = field(default="", repr=False)
    revision: int = 0

    def connection(self) -> ModelConnection:
        host = urlsplit(self.url).hostname or "Model server"
        required_key = self.backend in {
            "openai_api",
            "gemini_api",
            "openrouter",
            "deepseek",
            "anthropic",
        }
        reference = (
            "KLAUDE_MODEL_" + self.identity.upper().replace("-", "_")
            if self.key or required_key
            else ""
        )
        return ModelConnection(
            self.identity, self.name or host, self.backend, self.url, self.source, reference
        )


def read_inventory(request: dict[str, Any]) -> dict[str, Any]:
    """Private worker: bounded public definitions/catalogs, never key values."""
    cfg = SimpleNamespace(
        config_dir=Path(request["config_dir"]),
        data_dir=Path(request["data_dir"]),
        ollama_url=request["ollama_url"],
        models=request.get("roles", {}),
    )
    registry = connection_registry(cfg)
    defaults = {item.id: item for item in legacy_connections(cfg)}
    metadata = (
        public_snapshot(registry) if registry.path.exists() else {"choices": {}, "checks": {}}
    )
    connections = registry.load() if registry.path.exists() else defaults
    credentials = {
        item.id: (
            bool(request_key(request, cfg, item)) if item.key_env else True,
            provider_secret_revision(cfg.config_dir, item.key_env) if item.key_env else "",
        )
        for item in connections.values()
    }
    models = []
    for model in load_model_cache(cfg.data_dir / "model-cache.json"):
        connection = connections.get(model.connection_id or DEFAULT_IDS.get(model.backend, ""))
        if connection is None or connection.backend != model.backend:
            continue
        if model.connection_id:
            if (
                model.connection_revision
                not in {
                    connection.revision,
                    replace(connection, enabled=not connection.enabled).revision,
                }
                or model.credential_revision != credentials[connection.id][1]
            ):
                continue
            model = replace(model, connection_revision=connection.revision)
        else:
            original = defaults.get(connection.id)
            if original is None or (original.base_url, original.key_env, original.source) != (
                connection.base_url,
                connection.key_env,
                connection.source,
            ):
                continue
            model = replace(
                model,
                connection_id=connection.id,
                connection_revision=connection.revision,
                connection_source=connection.source,
                credential_revision=credentials[connection.id][1],
            )
        models.append(model)
    discovered = [model.ref for model in models]
    for identity, choices in metadata["choices"].items():
        connection = connections.get(identity)
        if connection is None:
            continue
        for model_id in choices:
            if connection.model_ref(model_id) not in discovered:
                models.append(
                    ModelInfo(
                        connection.backend,
                        model_id,
                        model_id,
                        connection_id=identity,
                        connection_revision=connection.revision,
                        connection_source=connection.source,
                        credential_revision=credentials[identity][1],
                    )
                )
    return {
        **metadata,
        "defaults": read_defaults(cfg).public(),
        "connections": [asdict(item) for item in connections.values()],
        "models": model_records(list({model.ref: model for model in models}.values())),
        "authenticated": {identity: value[0] for identity, value in credentials.items()},
        "credential_revisions": {identity: value[1] for identity, value in credentials.items()},
        "registered": registry.path.exists(),
        "discovered": discovered,
        "startup": startup_snapshot(cfg.data_dir / "chat-preferences.json"),
        "checks": {
            identity: check
            for identity, check in metadata["checks"].items()
            if check.get("credential_revision", "") == credentials.get(identity, (False, ""))[1]
        },
    }


def test_catalog(request: dict[str, Any]) -> dict[str, Any]:
    """Test an unsaved draft without publishing, or refresh a registered catalog."""
    start = time.monotonic()
    connection = ModelConnection.from_record(request["connection"])
    if request.get("draft"):
        try:
            models = discover_connection(connection, str(request.get("key", "")))
            result = {
                "status": "ok" if models else "empty",
                "message": "Connection reached",
                "models": model_records(models),
            }
        except ModelDiscoveryError as exc:
            result = {"status": exc.status, "message": str(exc), "models": []}
        except Exception:
            result = {"status": "service", "message": "Connection check failed", "models": []}
    else:
        cfg = SimpleNamespace(
            config_dir=Path(request["config_dir"]),
            data_dir=Path(request["data_dir"]),
            ollama_url=request["ollama_url"],
            models=request.get("roles", {}),
        )
        connection_registry(cfg).migrate(cfg, cfg.data_dir / "chat-preferences.json")
        cache = Path(request["cache_file"])
        result = probe_connection(
            {
                **request,
                "key": request_key(request, cfg, connection),
                "credential_revision": provider_secret_revision(cfg.config_dir, connection.key_env)
                if connection.key_env
                else "",
                "generation": model_cache_generation(
                    cache, f"{connection.backend}@{connection.id}"
                ),
            }
        )
    return {
        **result,
        "connection": asdict(connection),
        "credential_revision": provider_secret_revision(
            Path(request["config_dir"]), connection.key_env
        )
        if not request.get("draft") and connection.key_env
        else "",
        "elapsed": round(time.monotonic() - start, 1),
    }


def request_key(request: dict[str, Any], cfg: Any, connection: ModelConnection) -> str:
    key = connection_key(cfg, connection)
    if (
        key
        or not connection.key_env
        or provider_secret_revision(cfg.config_dir, connection.key_env)
    ):
        return key
    # Environment-only credentials cross the same private pipe as draft keys.
    # A stored removal/replacement always wins over the launch environment.
    value = request.get("environment_keys", {}).get(connection.key_env, "")
    return value if isinstance(value, str) and len(value) <= 8192 else ""


class ModelSettings:
    """One controller per TUI; the host supplies shared panel/editor/action services."""

    def begin_api_provider(self, backend: str) -> None:
        """Use the ordinary unsaved form with an explicitly selected preset."""
        if backend not in PROVIDERS:
            return
        if self.pending:
            self.notify("Finish the accepted save before adding another endpoint", "warning")
            return
        self.action(PanelAction(PREFIX + "api"))
        self.action(PanelAction(PREFIX + "choose:" + backend, backend))

    def __init__(self, host: Any):
        self.host = host
        self.view = "home"
        self.target = ""
        self.connections: dict[str, ModelConnection] | None = None
        self.models: list[ModelInfo] = []
        self.authenticated: dict[str, bool] = {}
        self.credential_revisions: dict[str, str] = {}
        self.registered = False
        self.inventory_session = ""
        self.inventory_environment_names: set[str] = set()
        self.draft: ConnectionDraft | None = None
        self.test_result: dict[str, Any] | None = None
        self.checks: dict[str, dict[str, Any]] = {}
        self.request: tuple[str, str, str, int] | None = None
        self.loading = False
        self.pending: tuple[str, str] | None = None
        self.feedback: tuple[str, str] | None = None
        self.choices: dict[str, Any] = {}
        self.discovered: set[str] = set()
        self.startup: dict[str, Any] = {"last_model": None, "require_model_selection": False}
        self.defaults: AIDefaults | None = None
        self.model_id = ""
        self.catalog_filters: dict[str, str] = {}
        self.review: ModelChange | None = None
        self.review_return = "detail"
        self.offline_selected: set[str] = set()
        self.batch_queue: list[ModelConnection] = []
        self.batch_counts = [0, 0]
        self.batch_active = False
        self.change_pending: tuple[str, str, ModelChange] | None = None
        self.unconfirmed = False

    @property
    def jobs(self) -> Any:
        return self.host._background_jobs

    @property
    def catalog_filter(self) -> str:
        return self.catalog_filters.get(self.target, "all")

    @catalog_filter.setter
    def catalog_filter(self, value: str) -> None:
        self.catalog_filters[self.target] = value

    def show(self, view: str | None = None, target: str | None = None, focus: str = "") -> None:
        if view is not None:
            if view != self.view or target is not None and target != self.target:
                self.cancel_test()
                self.feedback = None
            self.view = view
        if target is not None:
            self.target = target
        self.host._open_panel(self.page(), "model settings " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def open(self) -> None:
        self.show("home")
        self.refresh()

    def refresh(self) -> None:
        cfg = self.host.cfg
        self.loading = True
        self.inventory_session = self.host.session_id
        environment = self.environment_keys()
        self.inventory_environment_names = set(environment)
        self.jobs.submit(
            "model-settings:inventory",
            {
                "kind": "model_settings_inventory",
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "ollama_url": cfg.ollama_url,
                "roles": dict(cfg.models),
                "environment_keys": environment,
            },
            timeout=8,
        )
        self.show()

    def environment_keys(self) -> dict[str, str]:
        names = {
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "ANTHROPIC_API_KEY",
        }
        names.update(
            connection.key_env
            for connection in (self.connections or {}).values()
            if connection.key_env
        )
        return {
            name: value for name in names if (value := os.environ.get(name)) and len(value) <= 8192
        }

    def cancel_test(self) -> None:
        self.jobs.cancel("model-settings:test")
        self.jobs.cancel("model-settings:probe")
        self.request = None
        self.batch_queue = []
        self.batch_active = False

    def leave(self) -> None:
        self.cancel_test()
        self.jobs.cancel("model-settings:inventory")
        self.loading = False
        self.inventory_session = ""
        self.draft = None
        self.test_result = None

    def notify(self, message: str, tone: str = "neutral") -> None:
        self.feedback = (message, tone)
        if self.visible:
            self.show()

    @property
    def visible(self) -> bool:
        return str(self.host._choice_kind).startswith("model settings ")

    def page(self) -> PanelPage:
        if self.view in {"confirm", "replacement", "offline", "catalog-filter", "model-detail"}:
            return self.maintenance_page()
        crumbs: tuple[str, ...] = ("Settings", "Models")
        connection: ModelConnection | None
        result: dict[str, Any] | None
        rows: list[PanelRow]
        if self.view == "home":
            count = (
                f"{len(self.connections)} endpoints"
                if self.connections is not None
                else "Loading…"
                if self.loading
                else "Unavailable"
            )
            info = getattr(self.host.agent, "model_info", None)
            current = info.ref if isinstance(info, ModelInfo) else self.host.agent.model
            if getattr(self.host, "_startup_unselected", False):
                current = "Not selected"
            rows = [
                row("added", "Added Models", count, kind=RowKind.NAVIGATION),
                row("add", "Add Models", kind=RowKind.NAVIGATION),
                row(
                    "session",
                    "Session model",
                    current,
                    kind=RowKind.NAVIGATION,
                    description="Choose a model or sign in to a native provider",
                ),
                back("settings"),
            ]
        elif self.view == "add":
            crumbs += ("Add Models",)
            rows = [
                row("local", "Add Local Models", description="Ollama, llama.cpp, vLLM"),
                row("api", "Add API Models", description="Cloud provider or compatible API"),
                back("home"),
            ]
        elif self.view in {"providers", "adapters"}:
            draft = self.draft
            assert draft is not None
            crumbs += ("Add Models", "Provider" if self.view == "providers" else "Server type")
            labels = PROVIDERS if self.view == "providers" else ADAPTERS
            rows = [
                row(
                    "choose:" + identity,
                    label,
                    "Current" if draft.backend == identity else "",
                    target=identity,
                )
                for identity, label in labels.items()
            ]
            if self.view == "providers":
                rows.append(
                    row(
                        "codex",
                        "OpenAI Codex account",
                        description="Uses the existing account login and model page",
                    )
                )
            rows.append(back("form"))
        elif self.view in {"form", "untested"}:
            draft = self.draft
            assert draft is not None
            crumbs += ("Add Models", "Local" if draft.source == "Local" else "API")
            if self.view == "untested":
                rows = [
                    PanelRow(
                        "warning",
                        RowKind.INFO,
                        "Add this endpoint without a successful test?",
                        description="Availability and model capabilities remain unverified.",
                    ),
                    row("save", "Add untested"),
                    back("form", cancel=True),
                ]
            else:
                labels = ADAPTERS if draft.source == "Local" else PROVIDERS
                rows = [
                    row("name", "Name", draft.name or "Use endpoint host"),
                    row(
                        "adapter",
                        "Server type" if draft.source == "Local" else "Provider",
                        labels[draft.backend],
                    ),
                    row("url", "Endpoint URL", draft.url),
                    row(
                        "key",
                        "Authentication",
                        "API key entered"
                        if draft.key
                        else "API key required"
                        if draft.backend in DEFAULT_URLS
                        else "None",
                        description="Masked input; saved only when you Add",
                    ),
                    row(
                        "test",
                        "Test connection",
                        "Checking…" if self.request else "",
                        enabled=self.pending is None,
                        description="Catalog only; does not invoke or load a model",
                    ),
                ]
                if draft.key:
                    rows.insert(4, row("clear-key", "Clear entered key"))
                if self.test_result:
                    result = self.test_result
                    rows.append(
                        PanelRow(
                            "test-result",
                            RowKind.INFO,
                            f"{result.get('message')} · {result.get('elapsed', 0)}s",
                            description=f"{len(result.get('models', []))} listed models · "
                            "tool capabilities unknown"
                            if result.get("status") in {"ok", "empty"}
                            else "",
                        )
                    )
                rows.extend(
                    [
                        row(
                            "save",
                            "Add",
                            "Saving…" if self.pending else "",
                            enabled=self.pending is None,
                        ),
                        back("discard", cancel=True),
                    ]
                )
        elif self.view == "added":
            crumbs += ("Added Models",)
            rows = [
                row("reload", "Reload endpoints", "Loading…" if self.loading else ""),
                row("probe", "Probe enabled endpoints", "Checking…" if self.batch_active else ""),
                row("offline", "Clear offline", description="Review unreachable endpoints"),
            ]
            if self.batch_active:
                rows.append(row("stop-probe", "Cancel probe"))
            rows.append(
                PanelRow(
                    "heading",
                    RowKind.SECTION,
                    "ENDPOINTS",
                    description=f"{len(self.connections or {})} added",
                )
            )
            rows.append(PanelRow("columns", RowKind.TABLE_HEADER, ""))
            if self.connections is None:
                rows.append(
                    PanelRow(
                        "loading",
                        RowKind.INFO,
                        "Loading…" if self.loading else "Inventory unavailable",
                    )
                )
            for connection in (self.connections or {}).values():
                models = [model for model in self.models if model.connection_id == connection.id]
                check = self.checks.get(connection.id, {})
                state = "Enabled" if connection.enabled else "Disabled"
                status = self.check_label(check)
                enabled_count = sum(
                    model_choice(self.choices, connection.id, model.model_id)["enabled"]
                    for model in models
                )
                rows.append(
                    row(
                        "endpoint:" + connection.id,
                        connection.name,
                        f"{connection.source} · {state}",
                        target=connection.id,
                        kind=RowKind.NAVIGATION,
                        description=f"{enabled_count}/{len(models)} models enabled · {status}",
                        section="heading",
                    )
                )
            rows.append(back("home"))
        else:
            connection = (self.connections or {}).get(self.target)
            if connection is None:
                return PanelPage(
                    "model-settings:missing",
                    crumbs,
                    (PanelRow("missing", RowKind.INFO, "Endpoint unavailable"), back("added")),
                )
            crumbs += ("Added Models", connection.name)
            models = [model for model in self.models if model.connection_id == connection.id]
            if self.view == "catalog":
                crumbs += ("Manage models",)
                enabled_count = sum(
                    model_choice(self.choices, connection.id, m.model_id)["enabled"] for m in models
                )
                rows = [
                    row("filter", "Filter", self.catalog_filter.capitalize()),
                    row("test", "Reload models", "Checking…" if self.request else ""),
                    row("manual", "Enter model ID", description="For services without a catalog"),
                    PanelRow(
                        "heading",
                        RowKind.SECTION,
                        "MODELS",
                        description=f"{enabled_count}/{len(models)} enabled",
                    ),
                    PanelRow("columns", RowKind.TABLE_HEADER, ""),
                ]
                for model in sorted(
                    models,
                    key=lambda item: (
                        not model_choice(self.choices, connection.id, item.model_id)["pinned"],
                        item.model_id,
                    ),
                ):
                    choice = model_choice(self.choices, connection.id, model.model_id)
                    if self.catalog_filter != "all" and not (
                        self.catalog_filter == "enabled"
                        and choice["enabled"]
                        or self.catalog_filter == "disabled"
                        and not choice["enabled"]
                        or self.catalog_filter in {"hidden", "pinned"}
                        and choice[self.catalog_filter]
                    ):
                        continue
                    current = getattr(self.host.agent, "model_info", None)
                    rows.append(
                        row(
                            "model:" + model.model_id,
                            model.model_id,
                            "Current"
                            if isinstance(current, ModelInfo) and current.ref == model.ref
                            else "Enabled"
                            if choice["enabled"]
                            else "Disabled",
                            description=" · ".join(
                                [
                                    "Tools: " + model.capabilities.tools_evidence,
                                    *(
                                        name.capitalize()
                                        for name in ("pinned", "hidden")
                                        if choice[name]
                                    ),
                                    *(
                                        ["Missing from catalog"]
                                        if model.ref not in self.discovered
                                        else []
                                    ),
                                ]
                            ),
                            target=model.model_id,
                            kind=RowKind.NAVIGATION,
                            enabled=True,
                            section="heading",
                        )
                    )
                if not models:
                    rows.append(
                        PanelRow(
                            "empty",
                            RowKind.INFO,
                            "No cached models",
                            description="Reload the catalog or enter a model ID.",
                        )
                    )
                rows.append(back("detail"))
            else:
                rows = [
                    row(
                        "catalog", "Manage models", f"{len(models)} listed", kind=RowKind.NAVIGATION
                    ),
                    row(
                        "test",
                        "Test connection",
                        "Checking…" if self.request else "",
                        description="Explicitly checks this disabled endpoint"
                        if not connection.enabled
                        else "Catalog only; no generation",
                    ),
                    row(
                        "endpoint-enabled",
                        "Enabled",
                        kind=RowKind.TOGGLE,
                        checked=connection.enabled,
                    ),
                    PanelRow(
                        "authentication",
                        RowKind.INFO,
                        "Authentication",
                        "Codex account"
                        if connection.backend == "openai_codex"
                        else "Configured"
                        if connection.key_env and self.authenticated.get(connection.id)
                        else "Not configured"
                        if connection.key_env
                        else "None",
                    ),
                    row("remove", "Remove endpoint"),
                    PanelRow(
                        "url",
                        RowKind.INFO,
                        "Endpoint URL",
                        connection.base_url or "Managed by Codex",
                    ),
                    PanelRow("adapter", RowKind.INFO, "Adapter", connection.backend),
                    PanelRow("identity", RowKind.INFO, "Endpoint ID", connection.id),
                ]
                result = self.checks.get(connection.id)
                if result:
                    rows.append(
                        PanelRow(
                            "check",
                            RowKind.INFO,
                            "Last check",
                            self.check_label(result),
                        )
                    )
                rows.append(back("added"))
        columns = (
            ("ENDPOINT", "SOURCE / STATUS", "CATALOG")
            if self.view == "added"
            else ("MODEL", "STATUS", "CAPABILITIES")
            if self.view == "catalog"
            else None
        )
        if self.pending and self.view in {"form", "untested"}:
            rows = [
                replace(item, enabled=False)
                if item.selectable and item.effective_control is None
                else item
                for item in rows
            ]
        if self.change_pending:
            rows = [
                replace(item, enabled=False)
                if item.selectable and item.effective_control is None
                else item
                for item in rows
            ]
        return PanelPage(
            "model-settings:"
            + self.view
            + (":" + self.target if self.view in {"detail", "catalog"} else ""),
            crumbs,
            tuple(rows),
            column_headers=columns,
            table_section_id="heading" if columns else "",
            scroll_wrapped_rows=True,
        )

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix(PREFIX)
        if kind == "back":
            if action.target == "settings":
                self.leave()
                self.host._begin_choice("settings", self.host._settings_categories(), "models")
            elif action.target == "discard":
                self.draft = None
                self.test_result = None
                self.show("add")
            else:
                self.show(action.target)
        elif kind in {"added", "add", "catalog"}:
            self.show(kind)
        elif kind == "session":
            self.host._open_model_source("settings")
        elif kind == "codex":
            self.draft = None
            self.test_result = None
            self.host._model_flow_parent = "settings"
            self.host._open_model_backend("openai_codex", "cloud")
        elif kind in {"local", "api"}:
            if self.pending:
                self.notify("Finish the accepted save before adding another endpoint", "warning")
                return
            # A new draft starts unfiltered, even if the last form was searched.
            for view in ("form", "providers", "adapters", "untested"):
                getattr(self.host, "_panel_states", {}).pop("model-settings:" + view, None)
            self.draft = (
                ConnectionDraft("Local", "ollama", "http://localhost:11434")
                if kind == "local"
                else ConnectionDraft("Cloud", "openai_api", DEFAULT_URLS["openai_api"])
            )
            self.test_result = None
            self.show("form", focus="url")
        elif kind.startswith("endpoint:"):
            self.show("detail", action.target)
        elif kind == "adapter" and self.draft:
            self.show("adapters" if self.draft.source == "Local" else "providers")
        elif kind.startswith("choose:") and self.draft:
            backend = action.target
            if backend not in (ADAPTERS if self.draft.source == "Local" else PROVIDERS):
                return
            if backend != self.draft.backend:
                self.draft.backend = backend
                self.draft.url = DEFAULT_URLS.get(
                    backend,
                    "http://localhost:8080/v1"
                    if self.draft.source == "Local"
                    else "https://example.com/v1",
                )
                self.changed(clear_key=True)
            self.show("form", focus="adapter")
        elif kind in {"name", "url", "manual"}:
            self.cancel_test()
            label = {"name": "Endpoint name", "url": "Endpoint URL", "manual": "Model ID"}[kind]
            self.host._begin_settings_input(
                label, "Enter " + label.lower(), ("model-settings", kind)
            )
            if self.draft and kind in {"name", "url"}:
                self.host._set_input(self.draft.name if kind == "name" else self.draft.url)
        elif kind == "key" and self.draft:
            self.cancel_test()
            self.host._begin_model_connection_secret()
        elif kind == "clear-key" and self.draft:
            self.changed(clear_key=True)
            self.notify("Entered key cleared")
        elif kind == "reload":
            self.refresh()
        elif kind == "test":
            self.test()
        elif kind == "filter":
            self.show("catalog-filter")
        elif kind.startswith("model:"):
            self.model_id = action.target
            self.show("model-detail")
        elif kind == "save":
            self.save()
        else:
            self.maintenance_action(kind, action.target)

    def changed(self, *, clear_key: bool = False) -> None:
        self.cancel_test()
        if self.draft:
            self.draft.revision += 1
            if clear_key:
                self.draft.key = ""
        self.test_result = None
        self.feedback = None

    @staticmethod
    def check_label(check: dict[str, Any]) -> str:
        if not check:
            return "Not checked"
        checked = check.get("checked_at")
        age = max(0, int(time.time() - checked)) if isinstance(checked, (int, float)) else None
        suffix = (
            f" · {age}s ago"
            if age is not None and age < 60
            else f" · {age // 60}m ago"
            if age is not None
            else ""
        )
        return str(check.get("message", "Unavailable")) + suffix

    def maintenance_page(self) -> PanelPage:
        crumbs: tuple[str, ...] = ("Settings", "Models", "Added Models")
        connection: ModelConnection | None
        rows: list[PanelRow] = []
        if self.view == "catalog-filter":
            crumbs += ("Manage models", "Filter")
            rows = [
                row(
                    "filter-choice:" + value,
                    value.capitalize(),
                    "Current" if value == self.catalog_filter else "",
                    target=value,
                )
                for value in ("all", "enabled", "disabled", "hidden", "pinned")
            ]
            rows.append(back("catalog"))
        elif self.view == "offline":
            crumbs += ("Clear offline",)
            rows.append(
                PanelRow(
                    "scope",
                    RowKind.INFO,
                    "Select unreachable endpoints to remove",
                    description="Authentication, rate limits and service errors are kept.",
                )
            )
            for connection in (self.connections or {}).values():
                check = self.checks.get(connection.id, {})
                if check.get("status") in OFFLINE_STATUSES:
                    rows.append(
                        row(
                            "offline-choice:" + connection.id,
                            connection.name,
                            target=connection.id,
                            kind=RowKind.TOGGLE,
                            checked=connection.id in self.offline_selected,
                            description=self.check_label(check),
                        )
                    )
            if len(rows) == 1:
                rows.append(PanelRow("empty", RowKind.INFO, "No unreachable endpoints to review"))
            rows.extend(
                [
                    row(
                        "remove-selected",
                        "Review selected removals",
                        str(len(self.offline_selected)),
                        enabled=bool(self.offline_selected),
                    ),
                    back("added"),
                ]
            )
        elif self.view in {"confirm", "replacement"}:
            change = self.review
            assert change is not None
            affected = affected_startup(
                self.host.cfg,
                self.startup,
                change.connections,
                change.model_id if change.kind == "choice" else "",
            )
            crumbs += ("Review change",)
            if self.view == "replacement":
                rows = [
                    row(
                        "replacement-choice",
                        "Unset startup model",
                        target="",
                        description="Require selection when starting the next chat",
                    )
                ]
                for model in self.models:
                    connection = (self.connections or {}).get(model.connection_id)
                    if (
                        not connection
                        or not connection.enabled
                        or not model_choice(self.choices, connection.id, model.model_id)["enabled"]
                        or any(item.id == connection.id for item in change.connections)
                        and (change.kind != "choice" or model.model_id == change.model_id)
                    ):
                        continue
                    rows.append(
                        row(
                            "replacement:" + model.ref,
                            f"{connection.name} / {model.model_id}",
                            connection.source,
                            target=model.ref,
                        )
                    )
                rows.append(back("confirm", cancel=True))
            else:
                title = (
                    "Remove endpoints?"
                    if change.kind == "remove"
                    else "Disable model?"
                    if change.kind == "choice"
                    else "Disable endpoint?"
                )
                rows.append(
                    PanelRow(
                        "scope",
                        RowKind.INFO,
                        title,
                        description="Running work keeps its accepted model. New prompts "
                        "must use an enabled endpoint and model.",
                    )
                )
                for connection in change.connections:
                    rows.append(
                        PanelRow(
                            "review:" + connection.id,
                            RowKind.INFO,
                            connection.name,
                            connection.base_url or "Codex account",
                        )
                    )
                if change.kind == "choice":
                    rows.append(PanelRow("model", RowKind.INFO, "Model", change.model_id))
                if change.kind == "remove":
                    rows.append(
                        PanelRow(
                            "retained",
                            RowKind.INFO,
                            "Saved credentials and conversation history are retained.",
                        )
                    )
                if affected:
                    rows.extend(
                        [
                            PanelRow("affected", RowKind.INFO, "Affected startup model", affected),
                            row(
                                "replacement-open",
                                "Startup choice",
                                change.replacement or "Unset · require selection",
                                kind=RowKind.NAVIGATION,
                            ),
                        ]
                    )
                research = self.research_affected(change)
                if research:
                    rows.extend(
                        [
                            PanelRow(
                                "affected-research", RowKind.INFO, "Affected Research", research
                            ),
                            row(
                                "unset-research",
                                "Unset Research override",
                                kind=RowKind.TOGGLE,
                                checked=change.unset_research,
                            ),
                        ]
                    )
                utility, fallbacks = self.utility_affected(change)
                if utility:
                    rows.extend(
                        [
                            PanelRow("affected-utility", RowKind.INFO, "Affected Utility", utility),
                            row(
                                "unset-utility",
                                "Unset Utility override",
                                kind=RowKind.TOGGLE,
                                checked=change.unset_utility,
                                description="Return to Same as chat; explicit selection required",
                            ),
                        ]
                    )
                for ref in fallbacks:
                    rows.append(
                        PanelRow(
                            "affected-fallback:" + ref, RowKind.INFO, "Remove Utility fallback", ref
                        )
                    )
                rows.extend(
                    [
                        row(
                            "confirm-change",
                            "Remove selected endpoints" if change.kind == "remove" else "Disable",
                            enabled=(not utility or change.unset_utility)
                            and (not research or change.unset_research),
                        ),
                        back(self.review_return, cancel=True),
                    ]
                )
        else:
            connection = (self.connections or {}).get(self.target)
            if connection is None:
                return PanelPage(
                    "model-settings:missing",
                    crumbs,
                    (PanelRow("missing", RowKind.INFO, "Endpoint unavailable"), back("added")),
                )
            crumbs += (connection.name, "Manage models", self.model_id)
            choice = model_choice(self.choices, connection.id, self.model_id)
            rows = [
                row(
                    "use-model",
                    "Use for this session",
                    enabled=connection.enabled and choice["enabled"],
                    description="Retains conversation; running work is unchanged",
                ),
                *(
                    row(
                        "model-choice:" + name,
                        label,
                        kind=RowKind.TOGGLE,
                        checked=choice[name],
                        target=name,
                    )
                    for name, label in (
                        ("enabled", "Enabled"),
                        ("pinned", "Pinned"),
                        ("hidden", "Hide from session picker"),
                    )
                ),
                PanelRow(
                    "capabilities",
                    RowKind.INFO,
                    "Tool capability",
                    next(
                        (
                            model.capabilities.tools_evidence
                            for model in self.models
                            if model.connection_id == connection.id
                            and model.model_id == self.model_id
                        ),
                        "unknown",
                    ),
                ),
                back("catalog"),
            ]
        if self.change_pending:
            rows = [
                replace(item, enabled=False)
                if item.selectable and item.effective_control is None
                else item
                for item in rows
            ]
        return PanelPage(
            "model-settings:"
            + self.view
            + ":"
            + self.target
            + ":"
            + (self.model_id if self.view == "model-detail" else ""),
            crumbs,
            tuple(rows),
            scroll_wrapped_rows=True,
        )

    def research_affected(self, change: ModelChange) -> str:
        if not self.defaults or not self.defaults.research:
            return ""
        from klaude_core.model_management import reference_parts

        _backend, identity, model = reference_parts(self.defaults.research)
        return (
            self.defaults.research
            if any(item.id == identity for item in change.connections)
            and (change.kind != "choice" or model == change.model_id)
            else ""
        )

    def utility_affected(self, change: ModelChange) -> tuple[str, tuple[str, ...]]:
        if self.defaults is None:
            return "", ()
        from klaude_core.model_management import reference_parts

        def affected(ref: str | None) -> bool:
            if ref is None:
                return False
            _backend, identity, model = reference_parts(ref)
            return any(item.id == identity for item in change.connections) and (
                change.kind != "choice" or model == change.model_id
            )

        return (self.defaults.utility if affected(self.defaults.utility) else "") or "", tuple(
            ref for ref in self.defaults.fallbacks if affected(ref)
        )

    def maintenance_action(self, kind: str, target: str) -> None:
        if self.change_pending:
            self.notify("Finish the accepted change before editing models", "warning")
            return
        connection = (self.connections or {}).get(self.target)
        if kind in {"remove", "endpoint-enabled"} and connection:
            change = ModelChange(
                "remove" if kind == "remove" else "enabled",
                (connection,),
                value=not connection.enabled,
            )
            if (
                kind == "remove"
                or connection.enabled
                and (
                    self.utility_affected(change)[0]
                    or self.utility_affected(change)[1]
                    or affected_startup(
                        self.host.cfg,
                        self.startup,
                        change.connections,
                    )
                )
            ):
                self.begin_review(change, "detail")
            else:
                self.submit_change(change)
        elif kind.startswith("model-choice:") and connection:
            choice = model_choice(self.choices, connection.id, self.model_id)
            change = ModelChange(
                "choice", (connection,), self.model_id, target, not choice[target], choice[target]
            )
            if (
                target == "enabled"
                and choice[target]
                and (
                    self.utility_affected(change)[0]
                    or self.utility_affected(change)[1]
                    or affected_startup(
                        self.host.cfg,
                        self.startup,
                        change.connections,
                        self.model_id,
                    )
                )
            ):
                self.begin_review(change, "model-detail")
            else:
                self.submit_change(change)
        elif kind == "use-model":
            self.select(self.model_id)
        elif kind.startswith("filter-choice:"):
            self.catalog_filter = target
            self.show("catalog", focus="filter")
            # A search used to reach the Filter control must not hide the
            # inventory after applying a new inventory filter.
            self.host._panel.search_active = False
            self.host._panel.filter("")
            if hasattr(self.host, "_apply_picker_state"):
                self.host._apply_picker_state()
                self.host._set_input("")
        elif kind == "replacement-open":
            self.show("replacement")
        elif kind == "replacement-choice" or kind.startswith("replacement:"):
            if self.review:
                self.review = replace(self.review, replacement=target)
                self.show("confirm", focus="replacement-open")
        elif kind == "confirm-change" and self.review:
            self.submit_change(self.review)
        elif kind == "unset-utility" and self.review:
            self.review = replace(self.review, unset_utility=not self.review.unset_utility)
            self.show()
        elif kind == "offline":
            self.offline_selected.clear()
            self.show("offline")
        elif kind.startswith("offline-choice:"):
            self.offline_selected.symmetric_difference_update({target})
            self.show()
        elif kind == "remove-selected":
            items = tuple(
                item
                for identity, item in (self.connections or {}).items()
                if identity in self.offline_selected
                and self.checks.get(identity, {}).get("status") in OFFLINE_STATUSES
            )
            if items:
                checks = tuple(
                    (
                        item.id,
                        float(self.checks[item.id]["checked_at"]),
                        self.checks[item.id]["status"],
                        str(self.checks[item.id].get("credential_revision", "")),
                    )
                    for item in items
                )
                self.begin_review(ModelChange("remove", items, offline_checks=checks), "offline")
        elif kind == "probe":
            self.cancel_test()
            self.batch_queue = [item for item in (self.connections or {}).values() if item.enabled]
            self.batch_counts = [0, 0]
            self.batch_active = True
            self.next_probe()
        elif kind == "stop-probe":
            completed = sum(self.batch_counts)
            self.cancel_test()
            self.notify(f"Probe cancelled · {completed} checked", "warning")

    def begin_review(self, change: ModelChange, parent: str) -> None:
        affected = affected_startup(
            self.host.cfg,
            self.startup,
            change.connections,
            change.model_id if change.kind == "choice" else "",
        )
        self.review = replace(
            change,
            research_expected=self.defaults.research if self.defaults else None,
            startup_last=self.startup.get("last_model"),
            startup_required=self.startup.get("require_model_selection") is True,
            replacement="" if affected else None,
            defaults_expected=(self.defaults.chat, self.defaults.utility, self.defaults.fallbacks)
            if self.defaults
            else None,
        )
        self.review_return = parent
        self.show("confirm", focus="back")
        # A previous destructive review must never restore its confirm focus.
        self.host._panel.search_active = False
        self.host._panel.filter("")
        self.host._panel.picker.focus("back")
        if hasattr(self.host, "_apply_picker_state"):
            self.host._apply_picker_state()
            self.host._set_input("")

    def submit_change(self, change: ModelChange) -> None:
        if self.change_pending:
            return
        cfg = self.host.cfg
        snapshot = SimpleNamespace(
            config_dir=cfg.config_dir,
            data_dir=cfg.data_dir,
            ollama_url=cfg.ollama_url,
            models=dict(cfg.models),
        )
        identity = uuid.uuid4().hex
        self.change_pending = (identity, self.host.session_id, change)
        if not self.host._session_actions.submit(
            ModelConnectionUpdate(
                self.host.session_id,
                identity,
                snapshot,
                change,
            )
        ):
            self.change_pending = None
            self.notify("Change queue unavailable; endpoint was not changed", "error")
            return
        self.jobs.cancel("model-settings:inventory")
        self.cancel_test()
        self.loading = False
        self.notify("Saving model settings…")

    def updated(self, payload: object) -> None:
        session, identity, result, error = cast(tuple[str, str, Any, str], payload)
        pending = self.change_pending
        if not pending or pending[:2] != (identity, session):
            return
        self.change_pending = None
        visible = self.visible and session == self.host.session_id
        if error or not isinstance(result, dict):
            self.unconfirmed = True
            if visible:
                self.show("added")
                self.notify(error or "Change unconfirmed; reload to verify", "error")
            return
        self.apply_snapshot(result)
        self.registered = True
        change = pending[2]
        if visible:
            if change.kind == "remove":
                self.show("added")
            elif change.kind == "choice":
                self.model_id = change.model_id
                self.show("model-detail", change.connections[0].id)
            else:
                self.show("detail", change.connections[0].id)
            self.notify(str(result["message"]), "success")
            self.refresh()
        if hasattr(self.host, "_start_next"):
            self.host._start_next()

    def next_probe(self) -> None:
        if not self.batch_queue:
            self.batch_active = False
            self.notify(
                f"Probe complete · {self.batch_counts[0]} reached · {self.batch_counts[1]} failed",
                "warning" if self.batch_counts[1] else "success",
            )
            return
        connection = self.batch_queue.pop(0)
        self.start_check(connection, None, "model-settings:probe")
        self.notify(f"Probing {connection.name} · {sum(self.batch_counts)} checked")

    def answer(self, kind: str, value: str | None) -> None:
        if value is None:
            self.show("catalog" if kind == "manual" else "form", focus=kind)
            return
        if kind == "manual":
            self.model_id = validate_model_id(value)
            self.show("model-detail")
            return
        draft = self.draft
        if draft is None:
            return
        if kind == "url":
            normalized = replace(draft, url=value, key="").connection().base_url
            changed = normalized != draft.url
            draft.url = normalized
            self.changed(clear_key=changed)
        elif kind == "name":
            replace(draft, name=value).connection()
            draft.name = value
            self.changed()
        elif kind == "key":
            if (
                not value
                or len(value) > 8192
                or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)
            ):
                raise ValueError("Use a nonempty, single-line API key of at most 8192 characters")
            self.changed()
            draft.key = value
        self.show("form", focus=kind)
        if kind == "url" and changed:
            self.notify("Endpoint changed; re-enter authentication and test again", "warning")

    def test(self) -> None:
        if self.pending:
            return
        draft = self.draft if self.view == "form" else None
        connection = draft.connection() if draft else (self.connections or {}).get(self.target)
        if connection is None:
            return
        if connection.backend == "openai_codex":
            self.host._model_flow_parent = "settings"
            self.host._open_model_backend("openai_codex", "cloud")
            return
        self.start_check(connection, draft, "model-settings:test")
        self.notify("Checking model catalog…")

    def start_check(
        self, connection: ModelConnection, draft: ConnectionDraft | None, job_key: str
    ) -> None:
        cfg = self.host.cfg
        identity = self.jobs.submit(
            job_key,
            {
                "kind": "model_settings_test",
                "connection": asdict(connection),
                "draft": draft is not None,
                "key": draft.key if draft else "",
                "config_dir": str(cfg.config_dir),
                "cache_file": str(cfg.data_dir / "model-cache.json"),
                "data_dir": str(cfg.data_dir),
                "ollama_url": cfg.ollama_url,
                "roles": dict(cfg.models),
                "include_disabled": draft is None and not connection.enabled,
                "environment_keys": self.environment_keys(),
            },
            timeout=15,
        )
        self.request = (
            identity,
            self.host.session_id,
            connection.id,
            draft.revision if draft else -1,
        )

    def save(self) -> None:
        if self.pending or self.draft is None:
            return
        connection = self.draft.connection()
        if connection.key_env and not self.draft.key:
            self.notify("Enter the required API key before adding this provider", "error")
            return
        if self.view != "untested" and (
            not self.test_result or self.test_result.get("status") not in {"ok", "empty"}
        ):
            self.show("untested", focus="back")
            return
        cfg = self.host.cfg
        snapshot = SimpleNamespace(
            config_dir=cfg.config_dir,
            data_dir=cfg.data_dir,
            ollama_url=cfg.ollama_url,
            models=dict(cfg.models),
        )
        accepted = self.host._session_actions.submit(
            ModelConnectionAdd(
                self.host.session_id, self.host.client_id, snapshot, connection, self.draft.key
            )
        )
        if not accepted:
            self.notify("Save queue unavailable; endpoint was not added", "error")
            return
        self.pending = (self.host.session_id, connection.id)
        self.jobs.cancel("model-settings:inventory")
        self.loading = False
        self.cancel_test()
        self.notify("Saving endpoint…")

    def saved(self, payload: object) -> None:
        session, connection, saved = cast(tuple[str, ModelConnection, bool], payload)
        if self.pending != (session, connection.id):
            return
        self.pending = None
        visible = session == self.host.session_id and str(self.host._choice_kind).startswith(
            "model settings "
        )
        if saved:
            if self.connections is None:
                self.connections = {}
            self.connections[connection.id] = connection
            self.authenticated[connection.id] = bool(connection.key_env)
            if self.draft and self.draft.identity == connection.id:
                self.draft = None
                self.test_result = None
            if visible:
                self.show("detail", connection.id)
                self.notify("Endpoint saved; current chat model retained", "success")
                self.refresh()
        elif visible:
            self.show("form" if self.draft else "added")
            self.notify("Endpoint save unconfirmed; reload before retrying", "error")

    def accept(self, key: str, identity: str, result: Any, error: str) -> None:
        if key == "model-settings:inventory":
            if self.inventory_session != self.host.session_id:
                return
            self.loading = False
            if error or not isinstance(result, dict):
                self.notify("Endpoint inventory unavailable; reload to retry", "error")
                return
            try:
                self.apply_snapshot(result)
                self.unconfirmed = False
            except (KeyError, ValueError, TypeError, AttributeError):
                self.notify("Endpoint inventory unavailable; reload to retry", "error")
                return
            if any(
                connection.key_env not in self.inventory_environment_names
                and os.environ.get(connection.key_env)
                for connection in (self.connections or {}).values()
                if connection.key_env
            ):
                self.refresh()
                return
            if self.visible:
                self.show()
            return
        request = self.request
        if not request or request[:2] != (identity, self.host.session_id):
            return
        self.request = None
        draft = self.draft if self.view == "form" else None
        if draft and (draft.identity, draft.revision) != request[2:]:
            return
        if not isinstance(result, dict) or error:
            if self.batch_active:
                self.batch_counts[1] += 1
                self.next_probe()
            else:
                self.notify(error or "Connection check unavailable", "error")
            return
        connection = draft.connection() if draft else (self.connections or {}).get(request[2])
        if connection is None or result.get("connection") != asdict(connection):
            return
        succeeded = result.get("status") in {"ok", "empty"}
        if draft:
            self.test_result = result
        else:
            self.checks[connection.id] = {
                name: result.get(name)
                for name in (
                    "status",
                    "message",
                    "elapsed",
                    "checked_at",
                    "revision",
                    "credential_revision",
                )
            }
            self.registered = True
            self.credential_revisions[connection.id] = str(result.get("credential_revision", ""))
            if succeeded:
                self.models = [
                    model for model in self.models if model.connection_id != connection.id
                ]
                self.models.extend(models_from_records(result.get("models")))
                self.discovered = {
                    ref
                    for ref in self.discovered
                    if ref.partition("/")[0] != f"{connection.backend}@{connection.id}"
                }
                self.discovered.update(
                    model.ref for model in self.models if model.connection_id == connection.id
                )
        if self.batch_active:
            self.batch_counts[0 if succeeded else 1] += 1
            self.next_probe()
            return
        message = f"{result.get('message', 'Check unavailable')} · {result.get('elapsed', 0)}s"
        self.notify(message, "success" if succeeded else "error")

    def apply_snapshot(self, result: dict[str, Any]) -> None:
        connections = [ModelConnection.from_record(item) for item in result["connections"]]
        if len(connections) > 64 or len({item.id for item in connections}) != len(connections):
            raise ValueError("Invalid endpoint inventory")
        self.connections = {item.id: item for item in connections}
        self.choices = choices_from_payload({"model_choices": result.get("choices", {})})
        self.checks = result.get("checks", {})
        self.startup = result.get("startup", self.startup)
        if "defaults" in result:
            self.defaults = defaults_from_preferences(
                self.host.cfg, {"ai_defaults": result["defaults"]}
            )
        if "models" in result:
            self.models = models_from_records(result["models"])
        else:
            self.models = [
                replace(model, connection_revision=self.connections[model.connection_id].revision)
                for model in self.models
                if model.connection_id in self.connections
            ]
        if "discovered" in result:
            self.discovered = set(result["discovered"])
        if "authenticated" in result:
            self.authenticated = {
                key: value
                for key, value in result["authenticated"].items()
                if key in self.connections and type(value) is bool
            }
        if "credential_revisions" in result:
            self.credential_revisions = {
                key: value
                for key, value in result["credential_revisions"].items()
                if key in self.connections and isinstance(value, str) and len(value) <= 64
            }
        if "registered" in result:
            self.registered = result["registered"] is True

    def select(self, model_id: str) -> None:
        connection = (self.connections or {}).get(self.target)
        if connection is None or not connection.enabled:
            raise ValueError("Endpoint unavailable or disabled")
        if not model_choice(self.choices, connection.id, model_id)["enabled"]:
            raise ValueError("Model is disabled; enable it before selecting")
        info = next(
            (
                item
                for item in self.models
                if item.connection_id == connection.id and item.model_id == model_id
            ),
            None,
        ) or ModelInfo(
            connection.backend,
            model_id,
            model_id,
            connection_id=connection.id,
            connection_revision=connection.revision,
            connection_source=connection.source,
            credential_revision=self.credential_revisions.get(connection.id, ""),
        )
        if not self.registered:
            info = replace(info, connection_id="", connection_revision="", credential_revision="")
        self.cancel_test()
        self.host._model_flow_parent = "settings"
        self.host._activate_selected_model(info)
        if self.host._choice_kind is None:
            # A running turn accepted a next-prompt selection. Close the panel
            # through the same draft-preserving boundary as ordinary navigation.
            self.leave()
            self.host._panel = None
            self.host._restore_panel_composer_draft()
            self.host.application.layout.focus(self.host.input)
            self.host.application.invalidate()
