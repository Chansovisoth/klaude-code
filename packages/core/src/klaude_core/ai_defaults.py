"""Independent startup/utility roles, migrated without changing session choices."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from .image_content import IMAGE_BACKENDS
from .model_connections import connection_registry, split_model_ref, validate_model_id
from .model_management import reference_parts, validate_model_reference
from .settings_store import (
    SettingsConflictError,
    atomic_write_private,
    read_settings,
    settings_lock,
)


def model_reference(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 400:
        raise ValueError("Choose a valid endpoint and model")
    backend, _identity, model = reference_parts(value)
    validate_model_id(model)
    return value if split_model_ref(value) else f"{backend}/{model}"


@dataclass(frozen=True)
class AIDefaults:
    chat: str | None
    utility: str | None = None
    fallbacks: tuple[str, ...] = ()
    output_tokens: int = 512
    research: str | None = None
    vision: str | None = None
    vision_enabled: bool = False
    vision_fallbacks: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "fallbacks": list(self.fallbacks),
            "vision_fallbacks": list(self.vision_fallbacks),
        }


def defaults_from_preferences(cfg: Any, saved: dict[str, Any]) -> AIDefaults:
    raw = saved.get("ai_defaults")
    if raw is None:
        chat = (
            None
            if saved.get("require_model_selection") is True
            else (saved.get("last_model") or cfg.models.get("coder"))
        )
        return AIDefaults(model_reference(chat) if chat else None)
    if not isinstance(raw, dict) or "chat" not in raw:
        raise ValueError("Model Defaults are invalid; review the saved configuration")
    chat, utility, fallbacks = raw.get("chat"), raw.get("utility"), raw.get("fallbacks", [])
    if not isinstance(fallbacks, (list, tuple)) or len(fallbacks) > 3:
        raise ValueError("Utility supports at most three explicit fallbacks")
    refs = tuple(model_reference(value) for value in fallbacks)
    primary = model_reference(utility) if utility is not None else None
    output = raw.get("output_tokens", 512)
    if type(output) is not int or not 128 <= output <= 2048:
        raise ValueError("Utility output must be 128–2048 tokens")
    identities = [reference_parts(ref) for ref in refs]
    if len(set(identities)) != len(refs) or (primary and reference_parts(primary) in identities):
        raise ValueError("Utility models must be distinct")
    vision = model_reference(raw["vision"]) if raw.get("vision") is not None else None
    enabled = raw.get("vision_enabled", False)
    alternatives = raw.get("vision_fallbacks", [])
    if (
        type(enabled) is not bool
        or not isinstance(alternatives, (tuple, list))
        or len(alternatives) > 3
    ):
        raise ValueError("Vision requires an enable switch and at most three explicit fallbacks")
    vision_refs = tuple(model_reference(value) for value in alternatives)
    identities = [reference_parts(ref) for ref in ((vision,) if vision else ()) + vision_refs]
    if len(set(identities)) != len(identities) \
            or any(part[0] not in IMAGE_BACKENDS for part in identities):
        raise ValueError("Vision requires distinct supported image models")
    return AIDefaults(
        model_reference(chat) if chat is not None else None,
        primary,
        refs,
        output,
        model_reference(raw["research"]) if raw.get("research") is not None else None,
        vision,
        enabled,
        vision_refs,
    )


def read_defaults(cfg: Any) -> AIDefaults:
    return defaults_from_preferences(cfg, read_settings(cfg.data_dir / "chat-preferences.json"))


def migrate_defaults(cfg: Any) -> AIDefaults:
    """Freeze the effective legacy startup choice before session-only edits."""
    path = cfg.data_dir / "chat-preferences.json"
    with settings_lock(path):
        saved = read_settings(path)
        defaults = defaults_from_preferences(cfg, saved)
        if "ai_defaults" not in saved:
            saved["ai_defaults"] = defaults.public()
            atomic_write_private(path, json.dumps(saved, indent=2) + "\n")
        return defaults


@dataclass(frozen=True)
class DefaultsChange:
    field: str
    value: str | None | tuple[str, ...] | int
    expected: str | None | tuple[str, ...] | int
    # Public definition/credential revisions captured by the selector.
    bindings: tuple[tuple[str, str, str], ...] = ()
    automatic: bool = False


def save_defaults(
    cfg: Any, change: DefaultsChange, *,
    before_publish: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from .config import provider_secret_revision

    if change.field not in {
        "chat",
        "utility",
        "fallbacks",
        "output_tokens",
        "research",
        "vision",
        "vision_enabled",
        "vision_fallbacks",
    }:
        raise ValueError("Invalid Model Defaults field")
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    path = cfg.data_dir / "chat-preferences.json"
    with settings_lock(registry.path), settings_lock(path), settings_lock(cfg.config_dir / ".env"):
        saved = read_settings(path)
        keys = ("ai_defaults", "model_default_selections", "require_model_selection")
        before = {key: deepcopy(saved.get(key)) for key in keys}
        defaults = defaults_from_preferences(cfg, saved)
        selections = saved.get("model_default_selections", {})
        selections = selections if isinstance(selections, dict) else {}
        if change.automatic and (
            change.field not in {"chat", "utility", "research", "vision"}
            or change.value is None
            or getattr(defaults, change.field) is not None
            or selections.get(change.field) == "manual"
        ):
            return defaults.public()
        if getattr(defaults, change.field) != change.expected:
            raise SettingsConflictError("AI default changed; reload and select again")
        candidate = {**defaults.public(), change.field: change.value}
        updated = defaults_from_preferences(cfg, {"ai_defaults": candidate})
        refs = (
            getattr(updated, change.field)
            if change.field in {"fallbacks", "vision_fallbacks"}
            else (
                (getattr(updated, change.field),)
                if change.field not in {"output_tokens", "vision_enabled"}
                and getattr(updated, change.field)
                else ()
            )
        )
        if change.field == "vision_enabled" and change.value and change.bindings:
            if updated.vision is None:
                raise SettingsConflictError("Vision model changed; review again")
            refs = (updated.vision, *updated.vision_fallbacks)
        bindings = {
            reference: (revision, credentials)
            for reference, revision, credentials in change.bindings
        }
        for reference in refs:
            validate_model_reference(cfg, reference)
            backend, identity, _model = reference_parts(reference)
            connection = registry.load().get(identity)
            if connection is None or connection.backend != backend:
                raise ValueError("Endpoint unavailable; reload models")
            expected = bindings.get(reference)
            current_credentials = (
                provider_secret_revision(cfg.config_dir, connection.key_env)
                if connection.key_env
                else ""
            )
            if expected is None or expected != (connection.revision, current_credentials):
                raise SettingsConflictError("Endpoint or credentials changed; reload models")
        saved["ai_defaults"] = updated.public()
        if change.field in {"chat", "utility", "research", "vision"}:
            saved["model_default_selections"] = {
                **{key: value for key, value in selections.items()
                   if key in {"chat", "utility", "research", "vision"}
                   and value in {"manual", "automatic"}},
                change.field: "automatic" if change.automatic else "manual",
            }
        # Keep the old unset marker meaningful for older clients without changing
        # last_model, which is session history rather than a default now.
        saved["require_model_selection"] = updated.chat is None
        after = {key: deepcopy(saved.get(key)) for key in keys}
        if before_publish is not None and before != after:
            before_publish(before, after)
        atomic_write_private(path, json.dumps(saved, indent=2) + "\n")
        return updated.public()
