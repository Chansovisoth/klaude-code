"""Metadata-only proposals for empty model roles; never perform inference or save."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from klaude_core.ai_defaults import read_defaults
from klaude_core.model_connections import connection_registry, legacy_connections
from klaude_core.model_discovery import discover_connection
from klaude_core.model_management import model_choice, public_snapshot, reference_parts
from klaude_core.settings_store import read_settings
from klaude_core.vision import inspect_model

from .model_capabilities import BATCH_SIZE, read_capabilities
from .model_settings import request_key

ROLES = ("chat", "utility", "research", "vision")
MAX_ENDPOINTS = 8
MAX_NATIVE_MODELS = 32


def read_default_candidates(request: dict[str, Any]) -> dict[str, Any]:
    cfg = SimpleNamespace(
        config_dir=Path(request["config_dir"]),
        data_dir=Path(request["data_dir"]),
        ollama_url=request["ollama_url"],
        models=request.get("roles", {}),
    )
    registry = connection_registry(cfg)
    connections = (
        registry.load()
        if registry.path.exists()
        else {item.id: item for item in legacy_connections(cfg)}
    )
    snapshot = public_snapshot(registry) if registry.path.exists() else {"choices": {}}
    preferences = read_settings(cfg.data_dir / "chat-preferences.json")
    defaults = read_defaults(cfg)
    sources = preferences.get("model_default_selections", {})
    sources = sources if isinstance(sources, dict) else {}
    needed = [
        role
        for role in ROLES
        if role in request.get("requested_roles", ROLES)
        and getattr(defaults, role) is None
        and sources.get(role) != "manual"
    ]
    if not needed:
        return {"proposals": []}
    # Local metadata is preferred. Work is bounded; unverified entries stay unset.
    endpoints = sorted(
        (c for c in connections.values() if c.enabled), key=lambda c: (c.source != "Local", c.id)
    )[:MAX_ENDPOINTS]
    deadline = time.monotonic() + 40

    def catalog(connection):
        try:
            key = request_key(request, cfg, connection)
            return connection, discover_connection(connection, key)
        except Exception:
            return connection, []  # No provider bodies or credentials cross the worker.

    with ThreadPoolExecutor(max_workers=4) as pool:
        catalogs = list(pool.map(catalog, endpoints))
    candidates = []
    counts: dict[str, int] = {}
    for connection, models in catalogs:
        enabled = [
            m
            for m in models
            if model_choice(snapshot["choices"], connection.id, m.model_id)["enabled"]
        ]
        if connection.backend == "ollama":
            records: dict[str, dict] = {}
            from dataclasses import asdict

            for start in range(0, min(len(enabled), MAX_NATIVE_MODELS), BATCH_SIZE):
                if time.monotonic() >= deadline:
                    break
                try:
                    result = read_capabilities(
                        {
                            **request,
                            "connection": asdict(connection),
                            "models": [m.model_id for m in enabled[start : start + BATCH_SIZE]],
                            "credential_revision": request.get("credential_revisions", {}).get(
                                connection.id, ""
                            ),
                        }
                    )
                    if result.get("status") == "ok":
                        records.update({item["model"]: item for item in result["models"]})
                except Exception:
                    break
            for model in enabled:
                record = records.get(model.model_id, {})
                declared = record.get("declared", [])
                if "completion" not in declared:
                    continue
                candidates.append(
                    replace(
                        model,
                        capabilities=replace(
                            model.capabilities,
                            supports_images="vision" in declared,
                            images_evidence="api/show",
                            supports_tools="tools" in declared,
                            tools_evidence="api/show",
                        ),
                    )
                )
                counts[model.ref] = record.get("parameter_count", 10**13)
        else:
            candidates.extend(enabled)
    active = request.get("chat_ref")
    try:
        active_identity = reference_parts(active) if isinstance(active, str) else None
    except ValueError:
        active_identity = None

    def rank(model, role="chat"):
        return (
            model.source != "Local",
            reference_parts(model.ref) != active_identity,
            not model.capabilities.supports_tools if role in {"chat", "research"} else False,
            counts.get(model.ref, 10**13),
            model.ref,
        )

    candidates.sort(key=rank)
    proposals = []
    for role in needed:
        options = [m for m in candidates if role == "chat" or not m.capabilities.requires_thinking]
        if role == "vision":
            options = [m for m in options if m.capabilities.supports_images is True]
        options.sort(key=lambda model: rank(model, role))
        for model in options:
            connection = connections[model.connection_id]
            # Metadata and the setting write both check exact endpoint/key revisions.
            credential = request.get("credential_revisions", {}).get(connection.id, "")
            expected = {
                "connection_revision": connection.revision,
                "credential_revision": credential,
            }
            if role == "vision":
                if time.monotonic() >= deadline:
                    break
                try:
                    inspect_model(cfg, model.ref, expected, analysis=True)
                except Exception:
                    continue
            proposals.append(
                {
                    "role": role,
                    "reference": model.ref,
                    "binding": [model.ref, connection.revision, credential],
                }
            )
            break
    # Save rechecks the registry; do not return raw catalog payloads.
    return {"proposals": proposals}
