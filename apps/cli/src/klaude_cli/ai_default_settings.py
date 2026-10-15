"""AI Defaults pages and explicit, owned session utility actions."""

from __future__ import annotations

import os
import uuid
from dataclasses import replace
from typing import Any

from klaude_core.ai_defaults import (
    AIDefaults,
    DefaultsChange,
    defaults_from_preferences,
    read_defaults,
)
from klaude_core.image_content import IMAGE_BACKENDS, image_capability_label
from klaude_core.model_connections import ModelConnection, validate_model_id
from klaude_core.model_management import model_choice, reference_parts
from klaude_core.model_runtime import ModelInfo, models_from_records
from klaude_core.vision import INSPECT_TIMEOUT

from .model_settings import row as model_row
from .session_actions import AIDefaultUpdate, SessionSettingUpdate, SessionTitleUpdate
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind


def row(identity: str, label: str, value: str = "", **kwargs: Any) -> PanelRow:
    result = model_row(identity, label, value, **kwargs)
    return replace(result, action=PanelAction("ai-defaults-" + identity, kwargs.get("target", "")))


def back(target: str) -> PanelRow:
    return row("back", "Back", target=target, kind=RowKind.NAVIGATION, control=RowControl.BACK)


def utility_request(
    cfg: Any,
    session_id: str,
    chat_ref: str,
    connections: Any = None,
    defaults: AIDefaults | None = None,
    native_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from klaude_core.model_connections import connection_registry, legacy_connections

    if connections is None:
        registry = connection_registry(cfg)
        connections = (
            registry.load().values() if registry.path.exists() else legacy_connections(cfg)
        )
    if defaults is None:
        defaults = read_defaults(cfg)
    references = (defaults.utility or chat_ref, *defaults.fallbacks)
    identities = {reference_parts(ref)[1] for ref in references}
    names = {item.key_env for item in connections if item.id in identities and item.key_env}
    return {
        "kind": "utility",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "roles": dict(cfg.models),
        "ollama_url": cfg.ollama_url,
        "session_id": session_id,
        "chat_ref": chat_ref,
        "defaults": defaults.public(),
        "native_options": {
            name: value
            for name, value in (native_options or {}).items()
            if name in {"num_gpu", "num_thread"} and type(value) is int
        },
        "environment_keys": {
            name: value for name in names if (value := os.environ.get(name)) and len(value) <= 8192
        },
    }


class AIDefaultSettings:
    def __init__(self, host: Any):
        self.host = host
        self.defaults: AIDefaults | None = None
        self.connections: dict[str, ModelConnection] = {}
        self.registered = False
        self.models: list[ModelInfo] = []
        self.choices: dict[str, Any] = {}
        self.authenticated: dict[str, bool] = {}
        self.credential_revisions: dict[str, str] = {}
        self.view, self.role, self.target, self.fallback = "home", "chat", "", ""
        self.inventory: tuple[str, str] | None = None
        self.pending: tuple[str, DefaultsChange] | None = None
        self.unconfirmed = False
        self.feedback: tuple[str, str] | None = None
        self.utility: tuple[str, str, str] | None = None
        self.title_pending: tuple[str, str] | None = None
        self.new_session_pending = ""
        self.fallback_field = "fallbacks"
        self.vision_check: tuple[str, str, str, str] | None = None
        self.vision_return: Any = None
        self.preparing_utility = ""
        self.utility_started_at = 0.0

    @property
    def visible(self) -> bool:
        return str(self.host._choice_kind).startswith("ai defaults ")

    def show(self, view: str | None = None, focus: str = "") -> None:
        if view is not None:
            self.view = view
        self.host._open_panel(self.page(), "ai defaults " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def open(self) -> None:
        self.vision_return = None
        self.show("home")
        self.refresh()

    def refresh(self, *, show: bool = True) -> None:
        cfg = self.host.cfg
        environment = self.host._model_settings.environment_keys()
        environment.update(
            {
                item.key_env: os.environ[item.key_env]
                for item in self.connections.values()
                if item.key_env in os.environ and len(os.environ[item.key_env]) <= 8192
            }
        )
        identity = self.host._background_jobs.submit(
            "ai-defaults:inventory",
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
        self.inventory = (identity, self.host.session_id)
        if show:
            self.show()

    def label(self, reference: str | None) -> str:
        if reference is None:
            return "Not selected"
        _backend, identity, model = reference_parts(reference)
        connection = self.connections.get(identity)
        return f"{connection.name if connection else identity} / {model}"

    def page(self) -> PanelPage:
        crumbs: tuple[str, ...] = ("Settings", "AI Defaults")
        defaults = self.defaults
        rows: list[PanelRow]
        if self.view == "utility":
            task = self.utility[2] if self.utility else "recap"
            rows = [
                PanelRow(
                    "work",
                    RowKind.INFO,
                    "Generating AI " + ("title" if task == "name" else "recap"),
                    description="Recent public turns only · no tools · 45s deadline",
                ),
                row("utility-cancel", "Cancel", control=RowControl.CANCEL),
            ]
            return PanelPage("ai-defaults:utility", ("Session", "AI Utility"), tuple(rows))
        if self.view == "home":
            rows = [
                row("reload", "Reload defaults", "Loading…" if self.inventory else ""),
                row(
                    "chat",
                    "Default Chat",
                    self.label(defaults.chat) if defaults else "Loading…",
                    description="Used for new sessions; the open session keeps its model",
                    enabled=defaults is not None,
                ),
                row(
                    "utility",
                    "Utility",
                    self.label(defaults.utility)
                    if defaults and defaults.utility
                    else "Same as chat → " + self.label(self.chat_ref()),
                    enabled=defaults is not None,
                    description="Explicit /recap --ai and /rename --ai only",
                ),
                row(
                    "research",
                    "Research",
                    self.label(defaults.research)
                    if defaults and defaults.research
                    else "Same as chat",
                    enabled=defaults is not None,
                    description="Bounded Deep Research jobs · no automatic fallback",
                ),
                row(
                    "vision-page",
                    "Vision",
                    "ON" if defaults and defaults.vision_enabled else "OFF",
                    enabled=defaults is not None,
                    description="Explicit Media image analysis · declared image support",
                ),
                row("image-generation", "Image generation",
                    description="Explicit local image service · saved Media output"),
                row(
                    "fallbacks",
                    "Utility fallbacks",
                    str(len(defaults.fallbacks)) if defaults else "Loading…",
                    enabled=defaults is not None,
                    description="Ordered explicit choices; no automatic cloud fallback",
                ),
                row(
                    "output",
                    "Utility output",
                    f"{defaults.output_tokens} tokens" if defaults else "Loading…",
                    enabled=defaults is not None,
                    description="Per attempt; includes provider reasoning · 128–2048 tokens",
                ),
                PanelRow("current", RowKind.INFO, "Session model", self.label(self.chat_ref())),
                PanelRow(
                    "compaction", RowKind.INFO, "Compaction", "Deterministic · no utility calls"
                ),
                back("settings"),
            ]
        elif self.view == "output":
            crumbs += ("Utility output",)
            rows = [
                row(
                    "output:" + str(value),
                    str(value) + " tokens",
                    target=str(value),
                    description="Saved" if defaults and defaults.output_tokens == value else "",
                )
                for value in (128, 256, 512, 1024, 2048)
            ]
            rows.append(back("home"))
        elif self.view == "vision":
            crumbs += ("Vision",)
            rows = [
                row(
                    "vision-toggle",
                    "Enable Vision",
                    "ON" if defaults and defaults.vision_enabled else "OFF",
                ),
                row(
                    "vision",
                    "Model",
                    self.label(defaults.vision) if defaults else "Loading…",
                    description="Media analysis model; chat images use the active Chat model",
                ),
                row(
                    "vision-fallbacks",
                    "Fallbacks",
                    str(len(defaults.vision_fallbacks)) if defaults else "0",
                ),
                PanelRow(
                    "budget", RowKind.INFO, "Analysis budget", "4096 context · 512 output tokens"
                ),
                PanelRow(
                    "input",
                    RowKind.INFO,
                    "Image input",
                    "PNG/JPEG · 8 MiB · 4 megapixels",
                    description="Library → Media → Analyze image, or chat /attach and @PATH. "
                    "Chat requires an image-capable active model; provider limits apply",
                ),
                back("home"),
            ]
        elif self.view == "endpoints":
            crumbs += (
                "Default Chat"
                if self.role == "chat"
                else "Research"
                if self.role.startswith("research")
                else "Vision"
                if self.role.startswith("vision")
                else "Utility",
                "Endpoint",
            )
            rows = (
                []
                if self.role in {"fallbacks", "vision_fallbacks"}
                else [
                    row(
                        "inherit",
                        "Unset · require selection"
                        if self.role == "chat"
                        else "Research default"
                        if self.role == "research-job"
                        else "Clear Vision model"
                        if self.role == "vision"
                        else "Same as chat",
                    )
                ]
            )
            for item in self.connections.values():
                usable = item.enabled and (
                    item.backend == "openai_codex"
                    or self.authenticated.get(item.id, not item.key_env)
                )
                if self.role != "chat" and item.backend == "openai_codex":
                    usable = False
                if self.role.startswith("vision") and item.backend not in IMAGE_BACKENDS:
                    usable = False
                rows.append(
                    row(
                        "endpoint:" + item.id,
                        item.name,
                        item.source,
                        target=item.id,
                        enabled=usable,
                        description="Disabled"
                        if not item.enabled
                        else "Select a supported image endpoint with documented capabilities"
                        if self.role.startswith("vision") and item.backend not in IMAGE_BACKENDS
                        else "Utility unavailable"
                        if self.role != "chat" and item.backend == "openai_codex"
                        else "Authentication required"
                        if not usable
                        else "",
                    )
                )
            rows.append(
                back(
                    "fallbacks"
                    if self.role in {"fallbacks", "vision_fallbacks"}
                    else "vision"
                    if self.role == "vision"
                    else "home"
                )
            )
        elif self.view == "models":
            item = self.connections[self.target]
            crumbs += (
                "Default Chat"
                if self.role == "chat"
                else "Research"
                if self.role.startswith("research")
                else "Vision"
                if self.role.startswith("vision")
                else "Utility",
                item.name,
                "Model",
            )
            rows = [row("manual", "Enter model ID")]
            rows.extend(
                [
                    PanelRow("models-heading", RowKind.SECTION, "MODELS"),
                    PanelRow("models-columns", RowKind.TABLE_HEADER, ""),
                ]
            )
            for model in self.models:
                if (
                    model.connection_id == item.id
                    and model_choice(self.choices, item.id, model.model_id)["enabled"]
                ):
                    rows.append(
                        row(
                            "model:" + model.model_id,
                            model.model_id,
                            "Available" if self.role == "chat"
                            or not model.capabilities.requires_thinking else "Unavailable",
                            description=(image_capability_label(model.capabilities.supports_images,
                                                               model.capabilities.images_evidence)
                                         + " · checked before saving"
                                         + (" · Thinking required; Vision unavailable"
                                            if model.capabilities.requires_thinking else ""))
                            if self.role.startswith("vision")
                            else "Tools: "
                            + model.capabilities.tools_evidence
                            + " · " + image_capability_label(model.capabilities.supports_images,
                                                            model.capabilities.images_evidence)
                            + (
                                " · Thinking required"
                                + ("; "
                                   + ("Research" if self.role.startswith("research") else "Utility")
                                   + " unavailable" if self.role != "chat" else "")
                                if model.capabilities.requires_thinking
                                else ""
                            ),
                            enabled=self.role == "chat" or not model.capabilities.requires_thinking,
                            kind=RowKind.NAVIGATION,
                            section="models-heading",
                            target=model.model_id,
                        )
                    )
            rows.append(back("endpoints"))
        elif self.view == "fallback-detail":
            crumbs += (
                "Vision fallbacks"
                if self.fallback_field == "vision_fallbacks"
                else "Utility fallbacks",
                self.label(self.fallback),
            )
            rows = [
                row("up", "Move up"),
                row("down", "Move down"),
                row("remove", "Remove fallback"),
                back("fallbacks"),
            ]
        else:
            crumbs += (
                "Vision fallbacks"
                if self.fallback_field == "vision_fallbacks"
                else "Utility fallbacks",
            )
            rows = [
                row(
                    "add-fallback",
                    "Add fallback",
                    enabled=bool(defaults and len(getattr(defaults, self.fallback_field)) < 3),
                )
            ]
            for i, reference in enumerate(
                getattr(defaults, self.fallback_field) if defaults else ()
            ):
                rows.append(
                    row("fallback:" + str(i), f"{i + 1}. {self.label(reference)}", target=reference)
                )
            rows.extend(
                [
                    PanelRow(
                        "policy",
                        RowKind.INFO,
                        "Fallback policy",
                        description="Network, timeout, rate limit or temporary service errors only;"
                        " "
                        "90s per model; at most 4 explicit attempts"
                        if self.fallback_field == "vision_fallbacks"
                        else "at most 4 attempts / 45s",
                    ),
                    back("vision" if self.fallback_field == "vision_fallbacks" else "home"),
                ]
            )
        if self.pending or self.vision_check:
            rows = [
                replace(item, enabled=False) if item.selectable and not item.footer else item
                for item in rows
            ]
        return PanelPage(
            "ai-defaults:" + self.view + ":" + self.role + ":" + self.target,
            crumbs,
            tuple(rows),
            scroll_wrapped_rows=True,
            column_headers=("MODEL", "STATUS", "CAPABILITIES") if self.view == "models" else None,
            table_section_id="models-heading" if self.view == "models" else "",
        )

    def chat_ref(self) -> str | None:
        if getattr(self.host, "_startup_unselected", False):
            return None
        info = getattr(self.host.agent, "model_info", None)
        return info.ref if isinstance(info, ModelInfo) else "ollama/" + self.host.agent.model

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("ai-defaults-")
        if kind == "utility-cancel":
            self.cancel_utility()
            self.host._panel = None
            self.host._cancel_choice()
            return
        if kind == "back":
            if self.vision_check:
                self.host._background_jobs.cancel("ai-defaults:vision")
                self.vision_check = None
            if self.view == "vision" and self.vision_return:
                panel, self.vision_return = self.vision_return, None
                panel.library.show("vision-form")
                return
            if self.role == "research-job" and action.target == "home":
                self.host._library.research.set_model(self.host._library.research.draft["model"])
                return
            if action.target == "settings":
                self.host._begin_choice(
                    "settings", self.host._settings_categories(), "ai defaults", refresh=True
                )
            else:
                self.show(action.target)
        elif kind == "reload":
            self.unconfirmed = False
            self.refresh()
        elif kind in {"chat", "utility", "research", "vision", "add-fallback"}:
            self.role = self.fallback_field if kind == "add-fallback" else kind
            self.show("endpoints")
        elif kind == "image-generation":
            self.host._library.generation.open(settings=True)
        elif kind == "vision-page":
            self.show("vision")
        elif kind == "vision-toggle" and self.defaults:
            self.role = "vision_enabled"
            self.submit(not self.defaults.vision_enabled)
        elif kind in {"fallbacks", "vision-fallbacks"}:
            self.fallback_field = "vision_fallbacks" if kind == "vision-fallbacks" else "fallbacks"
            self.show("fallbacks")
        elif kind == "output":
            self.role = "output_tokens"
            self.show("output")
        elif kind.startswith("output:"):
            self.submit(int(action.target))
        elif kind == "inherit":
            if self.role in {"fallbacks", "vision_fallbacks"}:
                raise ValueError("Choose an explicit fallback endpoint/model")
            self.submit(None)
        elif kind.startswith("endpoint:"):
            self.target = action.target
            self.show("models")
        elif kind.startswith("model:"):
            self.select(action.target)
        elif kind == "manual":
            self.host._begin_settings_input(
                "Model ID", "Exact provider model ID", ("ai-defaults", self.target)
            )
        elif kind.startswith("fallback:"):
            self.fallback = action.target
            self.show("fallback-detail")
        elif kind in {"up", "down", "remove"} and self.defaults:
            values = list(getattr(self.defaults, self.fallback_field))
            index = values.index(self.fallback)
            if kind == "remove":
                values.pop(index)
            else:
                target = index + (-1 if kind == "up" else 1)
                if not 0 <= target < len(values):
                    return
                values[index], values[target] = values[target], values[index]
            self.role = self.fallback_field
            self.submit(tuple(values))

    def answer(self, value: str | None) -> None:
        if value is not None:
            self.select(validate_model_id(value))
        else:
            self.show("models")

    def select(self, model: str) -> None:
        connection = self.connections[self.target]
        reference = connection.model_ref(model)
        if self.role != "chat" and connection.backend == "gemini_api":
            from klaude_core.model_runtime import gemini_capabilities

            if gemini_capabilities(model).requires_thinking:
                raise ValueError(
                    "This model requires Thinking; choose a Standard-mode model for this role"
                )
        if self.role.startswith("vision"):
            connection = self.connections[self.target]
            identity = self.host._background_jobs.submit(
                "ai-defaults:vision",
                {
                    "kind": "vision",
                    "operation": "inspect",
                    "reference": reference,
                    "config_dir": str(self.host.cfg.config_dir),
                    "data_dir": str(self.host.cfg.data_dir),
                    "roles": dict(self.host.cfg.models),
                    "ollama_url": self.host.cfg.ollama_url,
                    "expected": {
                        "connection_revision": connection.revision,
                        "credential_revision": self.credential_revisions.get(connection.id, ""),
                    },
                    "environment_keys": self.host._model_settings.environment_keys(),
                },
                timeout=INSPECT_TIMEOUT,
            )
            self.vision_check = (identity, self.host.session_id, self.role, reference)
            self.feedback = ("Checking declared image support…", "neutral")
            self.show()
            return
        if self.role == "fallbacks":
            assert self.defaults is not None
            self.submit((*self.defaults.fallbacks, reference))
        else:
            self.submit(reference)

    def choose_for_research(self) -> None:
        self.role = "research-job"
        self.show("endpoints")
        self.refresh()

    def submit(self, value: str | None | tuple[str, ...] | int) -> None:
        if self.role == "research-job":
            if value is not None and not isinstance(value, str):
                raise ValueError("Choose one research model")
            self.host._library.research.set_model(value)
            return
        if self.pending or self.defaults is None:
            return
        old = self.defaults
        updated = defaults_from_preferences(
            self.host.cfg, {"ai_defaults": {**old.public(), self.role: value}}
        )
        refs = (
            getattr(updated, self.role)
            if self.role in {"fallbacks", "vision_fallbacks"}
            else ((value,) if isinstance(value, str) else ())
        )
        bindings = []
        for reference in refs:
            _backend, identity, _model = reference_parts(reference)
            item = self.connections[identity]
            bindings.append((reference, item.revision, self.credential_revisions.get(identity, "")))
        change = DefaultsChange(self.role, value, getattr(old, self.role), tuple(bindings))
        identity = uuid.uuid4().hex
        self.pending = (identity, change)
        self.defaults = updated
        accepted = self.host._session_actions.submit(
            AIDefaultUpdate(self.host.session_id, identity, self.host.cfg, change)
        )
        self.feedback = (
            ("Saving AI Defaults…", "neutral")
            if accepted
            else ("Save unconfirmed; reload defaults", "warning")
        )
        if not accepted:
            self.pending = None
            self.unconfirmed = True
        self.show(
            "fallbacks"
            if self.role in {"fallbacks", "vision_fallbacks"}
            else "vision"
            if self.role.startswith("vision")
            else "home",
            "output" if self.role == "output_tokens" else self.role,
        )

    def saved(self, payload: Any) -> None:
        session, identity, result, error = payload
        if not self.pending or identity != self.pending[0]:
            return
        self.pending = None
        self.unconfirmed = bool(error)
        if not error:
            self.defaults = defaults_from_preferences(self.host.cfg, {"ai_defaults": result})
        self.feedback = (error, "warning") if error else ("AI Defaults saved", "success")
        if self.visible and session == self.host.session_id:
            self.show()
        self.host._start_next()

    def accept(self, key: str, identity: str, result: Any, error: str) -> None:
        if key == "ai-defaults:vision":
            pending = self.vision_check
            if pending is None or pending[0] != identity:
                return
            self.vision_check = None
            if pending[1] != self.host.session_id or not self.visible:
                return
            if error or not isinstance(result, dict) or result.get("status") == "error":
                self.feedback = (
                    result.get("message", "Vision capability check failed")
                    if isinstance(result, dict)
                    else "Vision capability check failed",
                    "error",
                )
                if self.visible:
                    self.show()
                return
            _, _, self.role, reference = pending
            self.submit(
                (*self.defaults.vision_fallbacks, reference)
                if self.role == "vision_fallbacks" and self.defaults
                else reference
            )
            return
        if key == "ai-defaults:utility":
            self.utility_result(identity, result, error)
            return
        if self.inventory != (identity, self.host.session_id):
            return
        self.inventory = None
        if error or not isinstance(result, dict):
            self.feedback = ("AI Defaults unavailable; reload to retry", "warning")
        else:
            self.connections = {
                item.id: item
                for value in result["connections"]
                if (item := ModelConnection.from_record(value))
            }
            self.registered = result["registered"]
            self.models = models_from_records(result["models"])
            self.choices = result["choices"]
            self.authenticated = result["authenticated"]
            self.credential_revisions = result["credential_revisions"]
            if not self.pending and not self.unconfirmed:
                self.defaults = defaults_from_preferences(
                    self.host.cfg, {"ai_defaults": result["defaults"]}
                )
        if self.new_session_pending == self.host.session_id:
            self.new_session_pending = ""
            self.host._activate_new_session_default(
                self.defaults.chat if self.defaults and not error else None, self
            )
        elif self.preparing_utility:
            task = self.preparing_utility
            self.preparing_utility = ""
            if error:
                self.host._panel = None
                self.host._cancel_choice()
                self.host._append("\n[warning] Utility configuration unavailable.\n")
            else:
                self.start_utility(task)
        elif self.visible and self.host._settings_input_request is None:
            self.show()
        else:
            library = getattr(self.host, "_library", None)
            if (library is not None and library.visible and library.vision.active
                    and not library.vision.busy and self.host._settings_input_request is None):
                library.show()

    def new_session(self) -> None:
        self.new_session_pending = self.host.session_id
        self.refresh(show=False)

    def leave(self) -> None:
        if not self.new_session_pending and not self.preparing_utility:
            self.host._background_jobs.cancel("ai-defaults:inventory")
            self.inventory = None

    def cancel_utility(self) -> None:
        active = bool(self.preparing_utility or self.utility)
        self.preparing_utility = ""
        self.leave()
        self.host._background_jobs.cancel("ai-defaults:utility")
        if active:
            self.utility = None
            self.host._append("\n[cancelled] AI Utility cancelled.\n")

    def start_utility(self, task: str) -> None:
        library = getattr(self.host, "_library", None)
        if getattr(getattr(library, "generation", None), "busy", False):
            self.host._append("\n[warning] Finish image generation before using Utility.\n")
            return
        if getattr(getattr(self.host, "_model_manager", None), "busy", False):
            self.host._append(
                "\n[warning] Finish the Model Manager operation before using Utility.\n"
            )
            return
        if not self.chat_ref() or self.pending or self.unconfirmed:
            self.host._append(
                "\n[warning] Choose a model and confirm AI Defaults before using Utility.\n"
            )
            return
        if self.defaults is None:
            self.preparing_utility = task
            self.refresh(show=False)
            self.feedback = None
            self.show("utility")
            return
        request = utility_request(
            self.host.cfg,
            self.host.session_id,
            str(self.chat_ref()),
            self.connections.values(),
            self.defaults,
            getattr(self.host.agent, "ollama_options", {}),
        )
        request.update(task=task, defaults=self.defaults.public() if self.defaults else None)
        identity = self.host._background_jobs.submit("ai-defaults:utility", request, timeout=45)
        import time

        self.utility_started_at = time.monotonic()
        self.utility = (identity, self.host.session_id, task)
        self.feedback = None
        self.show("utility")

    def utility_result(self, identity: str, result: Any, error: str) -> None:
        if not self.utility or self.utility[:2] != (identity, self.host.session_id):
            return
        task = self.utility[2]
        self.utility = None
        if self.visible and self.view == "utility":
            self.host._panel = None
            self.host._cancel_choice(resume_queue=False)
        if error or not isinstance(result, dict) or result.get("error"):
            self.host._append(
                "\n[warning] "
                + (error or (result or {}).get("error", "Utility unavailable"))
                + "\n"
            )
        else:
            model = result["model"]
            fallback = len(result["attempts"]) - 1
            usage = result["usage"]
            label = (
                f"AI {'title' if task == 'name' else 'recap'} via {model} · fallback {fallback} · "
            )
            label += (
                f"↑{usage[0]} ↓{usage[1]}" if usage else "usage unknown"
            ) + f" · {result['elapsed']}s"
            if task == "name":
                accepted = self.host._session_actions.submit(
                    SessionTitleUpdate(
                        self.host.session_id, identity, result["text"], result["prior_name"], label
                    )
                )
                self.title_pending = (identity, self.host.session_id) if accepted else None
                if not accepted:
                    self.host._append("\n[warning] Generated title could not be saved.\n")
            else:
                self.host._append("\n[recap] " + label + "\n" + result["text"] + "\n")
                self.host._session_actions.submit(
                    SessionSettingUpdate(
                        self.host.session_id, self.host.client_id, label + "\n" + result["text"]
                    )
                )
        self.host._start_next()

    def title_saved(self, payload: Any) -> None:
        update, saved = payload
        if self.title_pending != (update.identity, update.session_id):
            return
        self.title_pending = None
        if update.session_id == self.host.session_id:
            if saved:
                self.host._session_title_hint = update.name
                self.host._append(
                    "\n[session] " + update.detail + "\nRenamed to " + update.name + "\n"
                )
            else:
                self.host._append(
                    "\n[warning] Title changed or save unconfirmed; "
                    "reload the session before retrying.\n"
                )
        self.host._start_next()
