"""Scoped, metadata-only capability checks shared by model settings pickers."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from klaude_application.model_capabilities import (
    _declared,
)
from klaude_application.model_capabilities import (
    read_capabilities as read_capabilities,
)
from klaude_core.image_content import image_capability_label
from klaude_core.model_connections import (
    ModelConnection,
)
from klaude_core.model_runtime import ModelInfo

BATCH_SIZE = 8
MAX_MODELS = 1000
CACHE_SECONDS = 60
JOB_TIMEOUT = 20  # Two waves of four bounded six-second metadata requests plus startup.


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
