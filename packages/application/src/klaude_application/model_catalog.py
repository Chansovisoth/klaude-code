"""Model connection inventory and catalog checks without terminal controllers."""

from __future__ import annotations

import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from klaude_core.ai_defaults import read_defaults
from klaude_core.config import provider_secret_revision
from klaude_core.model_connections import (
    DEFAULT_IDS,
    ModelConnection,
    connection_key,
    connection_registry,
    legacy_connections,
)
from klaude_core.model_discovery import ModelDiscoveryError, discover_connection, probe_connection
from klaude_core.model_management import public_snapshot, startup_snapshot
from klaude_core.model_runtime import (
    ModelInfo,
    load_model_cache,
    model_cache_generation,
    model_records,
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
