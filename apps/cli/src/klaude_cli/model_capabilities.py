"""Scoped, metadata-only capability checks shared by model settings pickers."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from klaude_core.config import provider_credential_current
from klaude_core.image_content import image_capability_label
from klaude_core.model_connections import (
    ModelConnection,
    connection_registry,
    legacy_connections,
    validate_model_id,
)
from klaude_core.model_runtime import ModelInfo

BATCH_SIZE = 8
MAX_MODELS = 1000
CACHE_SECONDS = 60
JOB_TIMEOUT = 20  # Two waves of four bounded six-second metadata requests plus startup.


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

    from .model_settings import request_key

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


class ModelCapabilityInventory:
    """One owned scan per picker, with bounded batches and short-lived scoped results."""

    def __init__(self, owner: Any, prefix: str):
        self.owner = owner
        self.key = prefix + ":capabilities"
        self.scope: tuple[str, str, str] | None = None
        self.pending: tuple[str, tuple[str, ...], ModelConnection] | None = None
        self.cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.active = False

    def cancel(self) -> None:
        self.active = False
        if self.pending:
            self.owner.host._background_jobs.cancel(self.key)
            self.pending = None

    def invalidate(self) -> None:
        self.cancel()
        self.cache.clear()

    def model_ids(self, connection: ModelConnection) -> list[str]:
        return list(
            dict.fromkeys(
                model.model_id
                for model in self.owner.models
                if model.connection_id == connection.id
            )
        )[:MAX_MODELS]

    def sync(self, connection: ModelConnection | None) -> None:
        if connection is None or connection.backend != "ollama" or not connection.enabled:
            self.cancel()
            return
        owner, host = self.owner, self.owner.host
        credential = owner.credential_revisions.get(connection.id, "")
        scope = (host.session_id, connection.revision, credential)
        if self.scope != scope:
            self.invalidate()
            self.scope = scope
        if not self.active:
            self.cache = {
                model: cached
                for model, cached in self.cache.items()
                if cached[0] > time.monotonic()
            }
            self.active = True
        if self.pending:
            return
        candidates = self.model_ids(connection)
        self.cache = {model: cached for model, cached in self.cache.items() if model in candidates}
        missing = [model for model in candidates if model not in self.cache][:BATCH_SIZE]
        if not missing:
            return
        cfg = host.cfg
        environment = (
            owner.environment_keys()
            if hasattr(owner, "environment_keys")
            else host._model_settings.environment_keys()
        )
        identity = host._background_jobs.submit(
            self.key,
            {
                "kind": "model_capabilities",
                "connection": asdict(connection),
                "models": missing,
                "credential_revision": credential,
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "ollama_url": cfg.ollama_url,
                "roles": dict(cfg.models),
                "environment_keys": environment,
            },
            timeout=JOB_TIMEOUT,
        )
        self.pending = (identity, tuple(missing), connection)

    def entry(self, model: ModelInfo) -> dict[str, Any] | None:
        scope = self.scope
        connection = (self.owner.connections or {}).get(model.connection_id)
        if (
            scope is None
            or connection is None
            or scope
            != (
                self.owner.host.session_id,
                connection.revision,
                self.owner.credential_revisions.get(model.connection_id, ""),
            )
        ):
            return None
        cached = self.cache.get(model.model_id)
        return cached[1] if cached and (self.active or cached[0] > time.monotonic()) else None

    def image_support(self, model: ModelInfo) -> bool | None:
        entry = self.entry(model)
        if entry is not None:
            declared = entry.get("declared")
            return "vision" in declared if isinstance(declared, list) else None
        return model.capabilities.supports_images

    def chat_support(self, model: ModelInfo) -> bool | None:
        entry = self.entry(model)
        declared = entry.get("declared") if entry else None
        return "completion" in declared if isinstance(declared, list) else None

    def description(self, model: ModelInfo) -> str:
        entry = self.entry(model)
        if entry is not None:
            declared = entry.get("declared")
            if not isinstance(declared, list):
                return "Unverified · " + entry["reason"]
            labels = [
                label
                for capability, label in (
                    ("vision", "Vision"),
                    ("image", "Image generation (server)"),
                    ("tools", "Tools"),
                    ("thinking", "Thinking"),
                    ("embedding", "Embeddings"),
                    ("audio", "Audio (server)"),
                    ("decision", "Decision"),
                    ("insert", "Fill in middle"),
                )
                if capability in declared
            ]
            if "completion" in declared and "vision" not in declared:
                labels.insert(
                    0, "Text only" if not {"image", "audio"}.intersection(declared) else "Text"
                )
            return " · ".join(labels) if labels else "No declared capabilities"
        if model.backend == "ollama" and self.pending:
            return "Checking capabilities…"
        vision = image_capability_label(
            model.capabilities.supports_images, model.capabilities.images_evidence
        )
        return (
            vision.replace("Images:", "Vision:") + " · Tools: " + model.capabilities.tools_evidence
        )

    def accept(self, identity: str, result: Any, error: str) -> None:
        pending = self.pending
        if pending is None or pending[0] != identity:
            return
        self.pending = None
        owner = self.owner
        connection = (owner.connections or {}).get(owner.target)
        if (
            not owner.visible
            or connection is None
            or connection != pending[2]
            or self.scope
            != (
                owner.host.session_id,
                connection.revision,
                owner.credential_revisions.get(connection.id, ""),
            )
        ):
            return
        rows = result.get("models", []) if isinstance(result, dict) else []
        valid = (
            not error
            and isinstance(result, dict)
            and result.get("status") == "ok"
            and result.get("connection") == asdict(connection)
            and result.get("credential_revision") == self.scope[2]
        )
        records = (
            {
                item.get("model"): item
                for item in rows
                if isinstance(item, dict) and isinstance(item.get("model"), str)
            }
            if valid and isinstance(rows, list)
            else {}
        )
        targets = (
            pending[1]
            if valid
            else tuple(model for model in self.model_ids(connection) if model not in self.cache)
        )
        for model in targets:
            record = records.get(model, {})
            entry: dict[str, Any] = {
                "model": model, "reason": "Capability check unavailable; refresh to retry"
            }
            if "declared" in record:
                try:
                    entry = {"model": model, "declared": _declared(record["declared"])}
                except ValueError:
                    pass
            elif (
                isinstance(record.get("reason"), str)
                and len(record["reason"]) <= 120
                and record["reason"].isprintable()
            ):
                entry["reason"] = record["reason"]
            self.cache[model] = (time.monotonic() + CACHE_SECONDS, entry)
        owner.show()
