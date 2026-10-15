"""Fresh declared image evidence at the active, revision-bound chat endpoint."""

from __future__ import annotations

from typing import Any

import httpx

from .image_content import IMAGE_BACKENDS
from .model_connections import (
    connection_key,
    normalize_model_url,
)
from .research import model_binding
from .vision import inspect_model


def active_binding(cfg: Any, agent: Any) -> tuple[Any, str, str]:
    info = agent.model_info
    if info.backend not in IMAGE_BACKENDS:
        raise ValueError(
            "Choose a supported image model with verified or documented capabilities"
        )
    connection, model, credentials = model_binding(cfg, info.ref)
    if info.connection_revision and (connection.revision, credentials) != (
        info.connection_revision,
        info.credential_revision,
    ):
        raise ValueError("Image endpoint or credentials changed; explicitly reselect the model")
    runtime = getattr(agent.runtime, "ollama", None) if info.backend == "ollama" else agent.runtime
    if (
        runtime is None
        or normalize_model_url(getattr(runtime, "base_url", ""), info.backend)
        != connection.base_url
        or getattr(runtime, "api_key", "") != connection_key(cfg, connection)
    ):
        raise ValueError("Active chat endpoint changed; explicitly reselect the model")
    return connection, model, credentials


def inspect_support(cfg: Any, agent: Any, observer: Any) -> dict:
    connection, model, credentials = active_binding(cfg, agent)
    expected = {"connection_revision": connection.revision, "credential_revision": credentials}
    try:
        metadata = inspect_model(cfg, agent.model_info.ref, expected, on_transport=observer)
        if connection.backend == "openai_api" and \
                getattr(agent, "reasoning_mode", "standard") != "standard":
            raise ValueError("This reviewed OpenAI image model requires Standard mode")
        if connection.backend in {"openrouter", "gemini_api"} \
                and metadata.get("requires_thinking") and \
                getattr(agent, "reasoning_mode", "standard") != "thinking":
            raise ValueError("This image model requires Thinking; choose Thinking mode explicitly")
        current = active_binding(cfg, agent)
        if (current[0].revision, current[2]) != (connection.revision, credentials):
            raise ValueError("Image endpoint or credentials changed during inspection")
        return metadata
    except (httpx.HTTPError, TimeoutError) as exc:
        raise ValueError("Could not verify image support; check the active endpoint") from exc
