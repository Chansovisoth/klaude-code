"""Shared model-connection definitions and reviewed revisioned changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from klaude_core.model_connections import (
    ModelConnection,
    connection_registry,
    legacy_connections,
)
from klaude_core.model_management import ModelChange, apply_model_change


@dataclass(frozen=True)
class ModelConnectionAdd:
    connection: ModelConnection
    secret: str = field(default="", repr=False)


@dataclass(frozen=True)
class ModelConnectionChange:
    change: ModelChange = field(repr=False)


class ModelConnectionService:
    """Reuse the existing registry, migration and revision checks without UI state."""

    def __init__(self, cfg: Any) -> None:
        self.cfg = cfg

    def list(self) -> dict[str, ModelConnection]:
        registry = connection_registry(self.cfg)
        return registry.load() if registry.path.exists() else {
            item.id: item for item in legacy_connections(self.cfg)
        }

    def add(self, action: ModelConnectionAdd) -> None:
        registry = connection_registry(self.cfg)
        registry.migrate(self.cfg, self.cfg.data_dir / "chat-preferences.json")
        registry.add(action.connection, secret=action.secret)

    def change(self, action: ModelConnectionChange) -> Any:
        return apply_model_change(self.cfg, action.change)
