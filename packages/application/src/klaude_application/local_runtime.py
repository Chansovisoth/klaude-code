"""Prepare an exact saved local session runtime without model generation."""

from __future__ import annotations

from klaude_core import Agent
from klaude_core.config import Config
from klaude_core.memory import Memory
from klaude_core.model_connections import (
    DEFAULT_IDS,
    connection_registry,
    legacy_connections,
    split_model_ref,
)
from klaude_core.model_runtime import ModelInfo
from klaude_core.session_runtime import decode


def saved_local_choice(
    agent: Agent, memory: Memory, session_id: str,
) -> tuple[ModelInfo, str, str | None]:
    """Validate the saved Ollama identity against the current configured endpoint."""
    cfg = agent.tool_config
    if not isinstance(cfg, Config):
        raise ValueError("local model configuration unavailable")
    local_runtime_matches(agent, cfg)
    saved = decode(memory.session_runtime(session_id))
    if saved is None:
        raise ValueError("saved session has no explicit model choice")
    reference = saved["model"]
    qualified = split_model_ref(reference)
    if qualified is not None:
        backend, connection_id, model_id = qualified
        registry = connection_registry(cfg)
        choices = (
            registry.load() if registry.path.exists()
            else {item.id: item for item in legacy_connections(cfg)}
        )
        connection = choices.get(connection_id)
        if (backend != "ollama" or connection_id != DEFAULT_IDS["ollama"]
                or connection is None or not connection.enabled
                or connection.base_url != cfg.ollama_url
                or saved["definition"] != connection.revision
                or saved["credentials"]):
            raise ValueError("saved local model connection changed")
        info = ModelInfo(
            "ollama", model_id, model_id, connection_id=connection.id,
            connection_revision=connection.revision,
            connection_source=connection.source,
        )
    else:
        backend, separator, model_id = reference.partition("/")
        if (backend != "ollama" or not separator or not model_id
                or saved["definition"] or saved["credentials"]):
            raise ValueError("saved session requires another model runtime")
        info = ModelInfo("ollama", model_id, model_id)
    return info, saved["mode"], saved["effort"]


def local_runtime_matches(agent: Agent, cfg: Config) -> None:
    """Reject a provider or endpoint mismatch before binding an Ollama choice."""
    runtime = agent.runtime
    if getattr(runtime, "backend", "ollama") != "ollama":
        raise ValueError("current runtime is not Ollama")
    endpoint = getattr(getattr(runtime, "ollama", None), "base_url", None)
    if isinstance(endpoint, str) and endpoint.rstrip("/") != cfg.ollama_url.rstrip("/"):
        raise ValueError("configured local Ollama endpoint changed")
