"""Exact configured model choices; endpoints and credentials remain host-owned."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from klaude_core.config import Config, provider_secret_revision
from klaude_core.model_connections import (
    DEFAULT_IDS,
    ModelConnection,
    connection_key,
    connection_registry,
    legacy_connections,
    split_model_ref,
)
from klaude_core.model_discovery import discover_connection
from klaude_core.model_management import model_choice, public_snapshot, validate_model_reference
from klaude_core.model_runtime import CodexRuntime, ModelCapabilities, ModelInfo, load_model_cache
from klaude_core.session_runtime import decode
from klaude_core.utility import runtime_for_utility

from .model_capabilities import read_capabilities


class BrowserModels:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def connections(self) -> dict[str, ModelConnection]:
        registry = connection_registry(self.cfg)
        return (registry.load() if registry.path.exists()
                else {item.id: item for item in legacy_connections(self.cfg)})

    def connection(self, identity: str) -> ModelConnection:
        connection = self.connections().get(identity)
        if connection is None or not connection.enabled:
            raise ValueError("Model connection unavailable; refresh the model picker")
        return connection

    def inventory(self) -> list[dict[str, Any]]:
        return [{"id": item.id, "name": item.name, "backend": item.backend,
                 "source": item.source, "enabled": item.enabled}
                for item in list(self.connections().values())[:64]]

    def catalog(self, identity: str) -> list[ModelInfo]:
        connection = self.connection(identity)
        revision = (provider_secret_revision(self.cfg.config_dir, connection.key_env)
                    if connection.key_env else "")
        models = discover_connection(connection, connection_key(self.cfg, connection))
        if self.connection(identity) != connection or (
            connection.key_env
            and provider_secret_revision(self.cfg.config_dir, connection.key_env) != revision
        ):
            raise ValueError("Model connection changed during discovery; refresh")
        registry = connection_registry(self.cfg)
        choices = public_snapshot(registry)["choices"] if registry.path.exists() else {}
        return [replace(item, credential_revision=revision) for item in models[:1000]
                if model_choice(choices, identity, item.model_id)["enabled"]]

    def verify(self, identity: str, model_id: str, *, require_tools: bool = True) -> ModelInfo:
        connection = self.connection(identity)
        found = next((item for item in self.catalog(identity) if item.model_id == model_id), None)
        if found is None:
            raise ValueError("Model is not in the current configured catalog")
        if connection.backend == "ollama":
            check = read_capabilities({
                "connection": asdict(connection), "models": [model_id],
                "credential_revision": found.credential_revision,
                "config_dir": str(self.cfg.config_dir), "data_dir": str(self.cfg.data_dir),
                "ollama_url": self.cfg.ollama_url, "roles": dict(self.cfg.models),
            })
            records = check.get("models", [])
            declared = (records[0].get("declared")
                        if check.get("status") == "ok" and records else None)
            required = {"completion", "tools"} if require_tools else {"completion"}
            if not isinstance(declared, list) or not required <= set(declared):
                raise ValueError("Exact model completion and tool capability is unavailable")
            thinking = "thinking" in declared
            found = replace(found, capabilities=replace(
                found.capabilities,
                thinking_types=("disabled", "enabled") if thinking else ("disabled",),
                effort_levels=("off", "medium") if thinking else ("off",),
                supports_tools="tools" in declared, tools_evidence="api/show",
                supports_images="vision" in declared, images_evidence="api/show",
            ))
        if require_tools and not found.capabilities.supports_tools:
            raise ValueError("This model does not support Klaude tool use")
        self.current(found)
        return found

    def current(self, info: ModelInfo) -> ModelConnection:
        validate_model_reference(self.cfg, info.ref)
        if (info.backend == "ollama" and not info.connection_id
                and not info.connection_revision and not info.credential_revision):
            connection = self.connection(DEFAULT_IDS["ollama"])
            if connection.base_url != self.cfg.ollama_url or connection.key_env:
                raise ValueError("Legacy local model connection changed")
            return connection
        connection = self.connection(info.connection_id)
        if (connection.backend != info.backend or connection.revision != info.connection_revision
                or (provider_secret_revision(self.cfg.config_dir, connection.key_env)
                    if connection.key_env else "") != info.credential_revision):
            raise ValueError("Selected model connection or credentials changed; refresh")
        return connection

    def runtime(self, info: ModelInfo) -> Any:
        connection = self.current(info)
        if info.backend == "openai_codex":
            return CodexRuntime()
        return runtime_for_utility(connection, connection_key(self.cfg, connection), 120, info)

    def verify_ref(self, reference: str, *, require_tools: bool = True) -> ModelInfo:
        parts = split_model_ref(reference)
        if parts is None:
            backend, separator, model_id = reference.partition("/")
            if backend != "ollama" or not separator or not model_id:
                raise ValueError("Choose a model from a configured connection")
            self.current(ModelInfo("ollama", model_id, model_id))
            return replace(
                self.verify(DEFAULT_IDS["ollama"], model_id, require_tools=require_tools),
                connection_id="", connection_revision="", connection_source="",
                credential_revision="",
            )
        backend, connection_id, model_id = parts
        if self.connection(connection_id).backend != backend:
            raise ValueError("Model adapter changed; refresh")
        return self.verify(connection_id, model_id, require_tools=require_tools)

    def saved(self, memory: Any, session_id: str) -> tuple[str, str, str | None]:
        choice = decode(memory.session_runtime(session_id))
        parts = split_model_ref(choice["model"]) if choice else None
        if choice is None:
            raise ValueError("Conversation requires an exact configured model choice")
        if parts is None:
            backend, separator, model_id = choice["model"].partition("/")
            if backend != "ollama" or not separator or not model_id:
                raise ValueError("Conversation requires an exact configured model choice")
            identity = ""
        else:
            backend, identity, model_id = parts
        self.current(ModelInfo(
            backend, model_id, model_id, connection_id=identity,
            connection_revision=choice["definition"], credential_revision=choice["credentials"],
        ))
        return choice["model"], choice["mode"], choice["effort"]

    def saved_info(self, memory: Any, session_id: str) -> tuple[ModelInfo, str, str | None]:
        reference, mode, effort = self.saved(memory, session_id)
        choice = memory.session_runtime(session_id)
        parts = split_model_ref(reference)
        backend, identity, model_id = parts or ("ollama", "", reference.partition("/")[2])
        found = next((item for item in load_model_cache(self.cfg.data_dir / "model-cache.json")
                      if item.ref == reference and item.connection_revision == choice["definition"]
                      and item.credential_revision == choice["credentials"]), None)
        if found is None:
            # A trusted saved choice restores only its previous effort. Changing
            # mode or enabling new capabilities still requires fresh metadata.
            found = ModelInfo(backend, model_id, model_id, ModelCapabilities(
                effort_levels=("off", effort) if effort else ("off",),
                tools_evidence="saved-session-choice",
            ), connection_id=identity, connection_revision=choice["definition"],
                credential_revision=choice["credentials"])
        return found, mode, effort
