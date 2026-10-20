"""Bounded metadata-only model capability checks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from klaude_core.config import provider_credential_current
from klaude_core.model_connections import (
    ModelConnection,
    connection_registry,
    legacy_connections,
    validate_model_id,
)

BATCH_SIZE = 8
MAX_MODELS = 1000
CACHE_SECONDS = 60
JOB_TIMEOUT = 20

def _declared(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > 32
        or any(
            not isinstance(item, str)
            or not item.isascii()
            or not item.replace("-", "").replace("_", "").isalnum()
            or len(item) > 64
            for item in value
        )
    ):
        raise ValueError("Invalid capability metadata")
    return sorted(set(value))


def read_capabilities(request: dict[str, Any]) -> dict[str, Any]:
    """Read only /api/show; never load, generate, publish config, or return raw metadata."""
    from klaude_core.vision import VisionHTTP

    from .model_catalog import request_key

    connection = ModelConnection.from_record(request["connection"])
    models = request.get("models")
    if (
        connection.backend != "ollama"
        or not connection.enabled
        or not isinstance(models, list)
        or not 1 <= len(models) <= BATCH_SIZE
    ):
        raise ValueError("Invalid capability request")
    models = [validate_model_id(model) for model in models]
    if len(set(models)) != len(models):
        raise ValueError("Duplicate capability request")
    cfg = SimpleNamespace(
        config_dir=Path(request["config_dir"]),
        data_dir=Path(request["data_dir"]),
        ollama_url=request["ollama_url"],
        models=request.get("roles", {}),
    )
    key = request_key(request, cfg, connection)
    revision = str(request.get("credential_revision", ""))

    def current() -> bool:
        registry = connection_registry(cfg)
        connections = (
            registry.load()
            if registry.path.exists()
            else {item.id: item for item in legacy_connections(cfg)}
        )
        return connections.get(connection.id) == connection and (
            not connection.key_env
            or provider_credential_current(cfg.config_dir, connection.key_env, key, revision)
        )

    if not current() or (connection.key_env and not key):
        return {"status": "stale"}

    def inspect(model: str) -> dict[str, Any]:
        client = VisionHTTP(
            connection.base_url,
            timeout=httpx.Timeout(5, connect=3),
            trust_env=False,
            headers={"Authorization": "Bearer " + key} if key else {},
        )
        try:
            data = client.request("/api/show", {"model": model, "verbose": False})
            declared = data.get("capabilities") if isinstance(data, dict) else None
            if declared is None:
                return {"model": model, "reason": "Server did not declare capabilities"}
            try:
                declared = _declared(declared)
            except ValueError:
                return {"model": model, "reason": "Invalid capability metadata"}
            info = data.get("model_info", {})
            count = info.get("general.parameter_count") if isinstance(info, dict) else None
            return {"model": model, "declared": declared, **(
                {"parameter_count": count} if type(count) is int and 0 < count < 10**13 else {}
            )}
        except httpx.HTTPStatusError as exc:
            return {
                "model": model,
                "reason": f"Metadata unavailable (HTTP {exc.response.status_code})",
            }
        except (httpx.TimeoutException, TimeoutError):
            return {"model": model, "reason": "Metadata check timed out"}
        except Exception:
            # API responses and exceptions may include local paths or credentials.
            return {"model": model, "reason": "Capability metadata unavailable"}
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(inspect, models))
    if not current():
        return {"status": "stale"}
    return {
        "status": "ok",
        "connection": asdict(connection),
        "credential_revision": revision,
        "models": results,
    }
