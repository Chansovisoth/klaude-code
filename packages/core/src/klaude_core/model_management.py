"""Public model metadata and reviewed, field-scoped connection maintenance."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .model_connections import (
    DEFAULT_IDS,
    ModelConnection,
    connection_registry,
    split_model_ref,
    validate_model_id,
)
from .settings_store import (
    SettingsConflictError,
    atomic_write_private,
    read_settings,
    settings_lock,
)

CHOICE_FIELDS = ("enabled", "hidden", "pinned")
CHECK_STATUSES = frozenset(
    {
        "ok",
        "empty",
        "authentication",
        "missing_catalog",
        "rate_limit",
        "service",
        "timeout",
        "network",
        "malformed",
        "disabled",
    }
)
OFFLINE_STATUSES = frozenset({"network", "timeout"})


def choices_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, dict[str, bool]]]:
    raw = payload.get("model_choices", {})
    if not isinstance(raw, dict) or len(raw) > 64:
        raise ValueError("Invalid model preferences")
    result = {}
    for identity, models in raw.items():
        if not isinstance(identity, str) or not isinstance(models, dict) or len(models) > 1000:
            raise ValueError("Invalid model preferences")
        entries = {}
        for model_id, fields in models.items():
            validate_model_id(model_id)
            if not isinstance(fields, dict) or any(
                type(value) is not bool or name not in CHOICE_FIELDS
                for name, value in fields.items()
            ):
                raise ValueError("Invalid model preferences")
            entries[model_id] = {
                name: fields.get(name, name == "enabled") for name in CHOICE_FIELDS
            }
        result[identity] = entries
    return result


def model_choice(choices: dict[str, Any], identity: str, model_id: str) -> dict[str, bool]:
    return choices.get(identity, {}).get(model_id, dict(enabled=True, hidden=False, pinned=False))


def reference_parts(value: str) -> tuple[str, str, str]:
    qualified = split_model_ref(value)
    if qualified:
        return qualified
    backend, separator, model = value.partition("/")
    if separator and backend in DEFAULT_IDS:
        return backend, DEFAULT_IDS[backend], model
    return "ollama", DEFAULT_IDS["ollama"], value


def startup_snapshot(preferences: Path) -> dict[str, Any]:
    saved = read_settings(preferences)
    if "ai_defaults" in saved:
        from .ai_defaults import defaults_from_preferences

        defaults = defaults_from_preferences(None, saved)
        return {"last_model": defaults.chat, "require_model_selection": defaults.chat is None}
    last = saved.get("last_model")
    return {
        "last_model": last if isinstance(last, str) else None,
        "require_model_selection": saved.get("require_model_selection") is True,
    }


def affected_startup(
    cfg: Any, startup: dict[str, Any], connections: tuple[ModelConnection, ...], model_id: str = ""
) -> str:
    if startup.get("require_model_selection"):
        return ""
    selected = startup.get("last_model") or cfg.models.get("coder", "")
    if not selected:
        return ""
    _backend, identity, model = reference_parts(selected)
    return (
        selected
        if any(item.id == identity for item in connections) and (not model_id or model_id == model)
        else ""
    )


def public_snapshot(registry: Any) -> dict[str, Any]:
    payload = registry._read()
    connections = registry._records(payload)
    checks = {}
    raw = payload.get("checks", {})
    if isinstance(raw, dict):
        for identity, check in raw.items():
            connection = connections.get(identity)
            if (
                not connection
                or not isinstance(check, dict)
                or check.get("status") not in CHECK_STATUSES
            ):
                continue
            if check.get("revision") != connection.revision:
                continue
            checked = check.get("checked_at")
            if (
                not isinstance(checked, (int, float))
                or isinstance(checked, bool)
                or not 0 < checked <= time.time() + 60
            ):
                continue
            message = check.get("message")
            if not isinstance(message, str) or len(message) > 160 or not message.isprintable():
                continue
            checks[identity] = {
                name: check[name]
                for name in (
                    "status",
                    "message",
                    "checked_at",
                    "elapsed",
                    "revision",
                    "credential_revision",
                )
                if name in check
            }
    return {
        "connections": [asdict(item) for item in connections.values()],
        "choices": choices_from_payload(payload),
        "checks": checks,
    }


def write_registry(registry: Any, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2) + "\n"
    if len(text.encode()) > 1_000_000:
        raise ValueError("Model registry size limit reached")
    atomic_write_private(registry.path, text)


@dataclass(frozen=True)
class ModelChange:
    kind: str
    connections: tuple[ModelConnection, ...]
    model_id: str = ""
    field: str = ""
    value: bool = False
    expected: bool = False
    startup_last: str | None = None
    startup_required: bool = False
    replacement: str | None = None
    offline_checks: tuple[tuple[str, float, str, str], ...] = ()
    defaults_expected: tuple[str | None, str | None, tuple[str, ...]] | None = None
    unset_utility: bool = False
    research_expected: str | None = None
    unset_research: bool = False


def apply_model_change(cfg: Any, change: ModelChange) -> dict[str, Any]:
    """Registry -> preferences -> credentials/cache, matching catalog publication.

    Endpoints change before the startup preference. A later write failure is
    unconfirmed, never a blind rollback/retry of a possibly committed update.
    """
    from .model_runtime import save_model_cache

    if not 1 <= len(change.connections) <= 64 or change.kind not in {
        "remove",
        "enabled",
        "choice",
    }:
        raise ValueError("Invalid model maintenance request")
    if (
        len({item.id for item in change.connections}) != len(change.connections)
        or type(change.value) is not bool
        or type(change.expected) is not bool
    ):
        raise ValueError("Invalid model maintenance request")
    registry = connection_registry(cfg)
    registry.migrate(cfg, cfg.data_dir / "chat-preferences.json")
    preferences = cfg.data_dir / "chat-preferences.json"
    with (
        settings_lock(registry.path),
        settings_lock(preferences),
        settings_lock(cfg.config_dir / ".env"),
    ):
        payload = registry._read()
        current = registry._records(payload)
        choices = choices_from_payload(payload)
        if any(current.get(item.id) != item for item in change.connections):
            raise SettingsConflictError("Endpoint changed; reload and review again")
        if change.offline_checks:
            from .config import provider_secret_revision

            if {item[0] for item in change.offline_checks} != {
                item.id for item in change.connections
            }:
                raise ValueError("Invalid offline review")
            for identity, checked_at, status, revision in change.offline_checks:
                check = payload.get("checks", {}).get(identity, {})
                item = current[identity]
                current_revision = (
                    provider_secret_revision(cfg.config_dir, item.key_env) if item.key_env else ""
                )
                if (
                    status not in OFFLINE_STATUSES
                    or check.get("status") != status
                    or check.get("checked_at") != checked_at
                    or current_revision != revision
                ):
                    raise SettingsConflictError("Offline status changed; reload and review again")
        startup = startup_snapshot(preferences)
        from .ai_defaults import defaults_from_preferences

        saved_preferences = read_settings(preferences)
        defaults = defaults_from_preferences(cfg, saved_preferences)
        destructive = (
            change.kind == "remove"
            or change.kind == "enabled"
            and not change.value
            or change.kind == "choice"
            and change.field == "enabled"
            and not change.value
        )
        affected = (
            affected_startup(
                cfg, startup, change.connections, change.model_id if change.kind == "choice" else ""
            )
            if destructive
            else ""
        )
        if affected and change.replacement is None:
            raise SettingsConflictError(
                "Saved startup model is affected; review a replacement or unset"
            )
        if change.replacement is not None and (
            not affected
            or {key: startup[key] for key in ("last_model", "require_model_selection")}
            != {
                "last_model": change.startup_last,
                "require_model_selection": change.startup_required,
            }
        ):
            raise SettingsConflictError("Saved startup choice changed; review again")

        def affected_role(reference: str | None) -> bool:
            if not destructive or reference is None:
                return False
            _backend, identity, model = reference_parts(reference)
            return any(item.id == identity for item in change.connections) and (
                change.kind != "choice" or model == change.model_id
            )

        research_affected = affected_role(defaults.research)
        if any(affected_role(ref) for ref in (defaults.vision, *defaults.vision_fallbacks)):
            raise SettingsConflictError(
                "Vision model is affected; change or clear Vision choices in Model Defaults first"
            )
        if research_affected and (
            change.research_expected != defaults.research or not change.unset_research
        ):
            raise SettingsConflictError(
                "Research model is affected; explicitly unset it or change Model Defaults"
            )
        utility_affected = affected_role(defaults.utility)
        removed_fallbacks = tuple(ref for ref in defaults.fallbacks if affected_role(ref))
        if utility_affected or removed_fallbacks:
            if change.defaults_expected != (defaults.chat, defaults.utility, defaults.fallbacks):
                raise SettingsConflictError("Utility defaults changed; reload and review again")
        if utility_affected and not change.unset_utility:
            raise SettingsConflictError(
                "Utility override is affected; explicitly unset it or change Model Defaults"
            )
        updated_defaults = replace(
            defaults,
            chat=(change.replacement or None) if change.replacement is not None else defaults.chat,
            utility=None if utility_affected else defaults.utility,
            research=None if research_affected else defaults.research,
            fallbacks=tuple(ref for ref in defaults.fallbacks if ref not in removed_fallbacks),
        )
        records = dict(payload["connections"])
        checks = dict(payload.get("checks", {}))
        if change.kind == "remove":
            for item in change.connections:
                records.pop(item.id)
                choices.pop(item.id, None)
                checks.pop(item.id, None)
            message = f"Removed {len(change.connections)} endpoint(s)"
        elif change.kind == "enabled":
            if len(change.connections) != 1:
                raise ValueError("Change one endpoint at a time")
            item = change.connections[0]
            records[item.id] = asdict(replace(item, enabled=change.value))
            checks.pop(item.id, None)
            message = "Endpoint enabled" if change.value else "Endpoint disabled"
        else:
            if len(change.connections) != 1 or change.field not in CHOICE_FIELDS:
                raise ValueError("Invalid model preference change")
            item = change.connections[0]
            validate_model_id(change.model_id)
            previous = dict(model_choice(choices, item.id, change.model_id))
            if previous[change.field] != change.expected:
                raise SettingsConflictError("Model preference changed; reload and retry")
            previous[change.field] = change.value
            group = choices.setdefault(item.id, {})
            if len(group) >= 1000 and change.model_id not in group:
                raise ValueError("Model preference limit reached")
            group[change.model_id] = previous
            message = "Model preference saved"
        if change.replacement:
            backend, identity, model_id = reference_parts(change.replacement)
            replacement = ModelConnection.from_record(records.get(identity))
            if (
                "@" not in change.replacement.partition("/")[0]
                or replacement.backend != backend
                or not replacement.enabled
                or not model_choice(choices, identity, model_id)["enabled"]
            ):
                raise ValueError("Choose an enabled endpoint and model")
        payload.update(connections=records, model_choices=choices, checks=checks)
        write_registry(registry, payload)
        if (
            change.replacement is not None
            or utility_affected
            or removed_fallbacks
            or research_affected
        ):
            saved = read_settings(preferences)
            saved["ai_defaults"] = updated_defaults.public()
            if change.replacement is not None:
                saved["last_model"] = change.replacement
            saved["require_model_selection"] = updated_defaults.chat is None
            atomic_write_private(preferences, json.dumps(saved, indent=2) + "\n")
        if change.kind == "remove":
            cache = cfg.data_dir / "model-cache.json"
            for item in change.connections:
                save_model_cache(
                    cache, [], backend=item.backend, connection_id=item.id, invalidate=True
                )
                if item.id == DEFAULT_IDS[item.backend]:
                    save_model_cache(cache, [], backend=item.backend, invalidate=True)
        return {
            **public_snapshot(registry),
            "startup": startup_snapshot(preferences),
            "message": message,
            "removed": len(change.connections) if change.kind == "remove" else 0,
        }


def validate_model_reference(cfg: Any, reference: str) -> None:
    registry = connection_registry(cfg)
    if not registry.path.exists():
        return
    payload = registry._read()
    backend, identity, model_id = reference_parts(reference)
    connection = registry._records(payload).get(identity)
    if connection is None or connection.backend != backend:
        raise ValueError("Model endpoint was removed; choose a session model")
    if not connection.enabled:
        raise ValueError("Model endpoint is disabled; choose an enabled session model")
    if not model_choice(choices_from_payload(payload), identity, model_id)["enabled"]:
        raise ValueError("Model is disabled; enable it or choose another session model")
