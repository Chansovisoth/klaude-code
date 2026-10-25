"""Shared model-connection definitions and reviewed revisioned changes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
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


@dataclass(frozen=True)
class ModelDefinitionChange:
    expected: ModelConnection | None
    value: ModelConnection | None


class ModelConnectionService:
    """Reuse the existing registry, migration and revision checks without UI state."""

    def __init__(self, cfg: Any) -> None:
        self.cfg = cfg

    def list(self) -> dict[str, ModelConnection]:
        registry = connection_registry(self.cfg)
        return (
            registry.load()
            if registry.path.exists()
            else {item.id: item for item in legacy_connections(self.cfg)}
        )

    def add(self, action: ModelConnectionAdd) -> None:
        registry = connection_registry(self.cfg)
        registry.migrate(self.cfg, self.cfg.data_dir / "chat-preferences.json")
        registry.add(action.connection, secret=action.secret)

    def change(self, action: ModelConnectionChange) -> Any:
        return apply_model_change(self.cfg, action.change)

    def save_definition(
        self,
        action: ModelDefinitionChange,
        *,
        before_publish: Callable[[dict[str, Any], dict[str, Any]], None],
    ) -> None:
        """One reviewed definition, using the existing registry writer and locks.

        This narrow operation never rewrites role preferences or removes secrets.
        Browser and embedded callers get the same exact-state publication seam.
        """
        from klaude_core.ai_defaults import read_defaults
        from klaude_core.model_connections import CONNECTION_VERSION, MAX_CONNECTIONS
        from klaude_core.model_management import reference_parts, write_registry
        from klaude_core.model_runtime import save_model_cache
        from klaude_core.settings_store import SettingsConflictError, read_settings, settings_lock

        old, value = action.expected, action.value
        if old is None and value is None or old and value and old.id != value.id:
            raise ValueError("Choose one exact model connection")
        identity = old.id if old else value.id  # type: ignore[union-attr]
        registry = connection_registry(self.cfg)
        preferences = self.cfg.data_dir / "chat-preferences.json"
        with (
            settings_lock(registry.path),
            settings_lock(preferences),
            settings_lock(self.cfg.config_dir / ".env"),
        ):
            before = registry._read()
            current = (
                registry._records(before)
                if before
                else {item.id: item for item in legacy_connections(self.cfg)}
            )
            if current.get(identity) != old:
                raise SettingsConflictError("Connection changed; refresh and review again")
            if old == value:
                return
            defaults = read_defaults(self.cfg)
            references = (
                defaults.chat,
                defaults.utility,
                defaults.research,
                defaults.vision,
                *defaults.fallbacks,
                *defaults.vision_fallbacks,
            )
            if old and (
                value is None
                or not value.enabled
                or (old.base_url, old.backend, old.key_env)
                != (value.base_url, value.backend, value.key_env)
            ):
                if any(ref and reference_parts(ref)[1] == identity for ref in references):
                    raise ValueError(
                        "Change this connection's Model Defaults before editing, "
                        "disabling or removing it"
                    )
            records = {key: asdict(item) for key, item in current.items()}
            if value is None:
                records.pop(identity)
            else:
                records[identity] = asdict(value)
            if len(records) > MAX_CONNECTIONS:
                raise ValueError("Model connection limit reached")
            after = {**before, "version": CONNECTION_VERSION, "connections": records}
            if not before:
                saved = read_settings(preferences)
                after["legacy"] = {
                    "startup_model": saved.get("last_model", ""),
                    "roles": dict(self.cfg.models),
                }
            after["checks"] = {k: v for k, v in before.get("checks", {}).items() if k != identity}
            if value is None:
                after["model_choices"] = {
                    k: v for k, v in before.get("model_choices", {}).items() if k != identity
                }
            before_publish(before, after)
            write_registry(registry, after)
            if old is not None:
                save_model_cache(
                    self.cfg.data_dir / "model-cache.json",
                    [],
                    backend=old.backend,
                    connection_id=identity,
                    invalidate=True,
                )
