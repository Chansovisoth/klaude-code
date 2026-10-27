"""Reviewed model roles and image-service setup with shared witnessed effects."""

from __future__ import annotations

from dataclasses import asdict
from time import monotonic
from typing import Any

from klaude_core.ai_defaults import DefaultsChange, defaults_from_preferences, read_defaults
from klaude_core.config import Config
from klaude_core.image_content import IMAGE_BACKENDS
from klaude_core.image_generation import endpoint, inspect, inspect_settings, read
from klaude_core.model_management import reference_parts
from klaude_core.vision import inspect_model

from .browser_models import BrowserModels
from .image_settings import image_settings_resource, recover_image_settings, save_image_settings
from .model_capabilities import BATCH_SIZE, read_capabilities
from .model_default_settings import (
    model_defaults_resource,
    recover_model_defaults,
    save_model_defaults,
)
from .operation_journal import OperationConflict, OperationJournal

OPERATIONS = frozenset({"defaults-save", "image-settings-save",
                        "defaults-recover", "image-settings-recover"})
WITNESSED = frozenset({"defaults-save", "image-settings-save"})
FIELDS = frozenset({"chat", "utility", "research", "vision", "fallbacks", "vision_fallbacks",
                    "vision_enabled", "output_tokens"})


def media_settings(cfg: Config) -> dict[str, Any]:
    pending = {}
    if (cfg.data_dir / "operations.db").exists():
        journal = OperationJournal(cfg.data_dir / "operations.db")
        for kind, resource in (("defaults", model_defaults_resource(cfg.data_dir)),
                               ("image_service", image_settings_resource(cfg.config_dir))):
            fenced = journal.fenced_operation(resource)
            if fenced is not None:
                pending[kind] = {"request_id": fenced.receipt.request_id,
                                 "state": fenced.receipt.state}
    return {"defaults": read_defaults(cfg).public(), "image_service": read(cfg),
            "connections": BrowserModels(cfg).inventory(), "pending": pending}


def default_model_catalog(cfg: Config, identity: str) -> list[dict[str, Any]]:
    """Role hints from metadata, with exact checks still required at review time.

    Unknown capabilities remain explicit rather than guessing from model names.
    Native Ollama needs /api/show: /api/tags alone also lists embedding models.
    """
    service = BrowserModels(cfg)
    connection = service.connection(identity)
    models = service.catalog(identity)
    declarations = {}
    deadline = monotonic() + 20
    if connection.backend == "ollama":
        for offset in range(0, len(models), BATCH_SIZE):
            if monotonic() >= deadline:
                break  # Remaining choices are explicitly unverified, never guessed.
            batch = models[offset:offset + BATCH_SIZE]
            checked = read_capabilities({
                "connection": asdict(connection), "models": [item.model_id for item in batch],
                "credential_revision": batch[0].credential_revision,
                "config_dir": str(cfg.config_dir), "data_dir": str(cfg.data_dir),
                "ollama_url": cfg.ollama_url, "roles": dict(cfg.models),
            })
            if checked.get("status") != "ok":
                raise ValueError("Model connection changed; refresh models")
            declarations.update({item["model"]: item.get("declared")
                                 for item in checked["models"]})
    result = []
    for item in models:
        caps = item.capabilities
        completion: bool | None = True
        tools: bool | None = (caps.supports_tools
                              if caps.supports_tools is False or caps.tools_evidence != "unknown"
                              else None)
        images = caps.supports_images
        if connection.backend == "ollama":
            declared = declarations.get(item.model_id)
            completion = "completion" in declared if declared is not None else None
            tools = "tools" in declared if declared is not None else None
            images = "vision" in declared if declared is not None else None
        standard = not caps.requires_thinking
        bounded = item.backend != "openai_codex"
        roles = {
            "chat": False if completion is False or tools is False else
                None if completion is None or tools is None else True,
            "utility": completion if bounded and standard else False,
            "research": False if not bounded or not standard or completion is False
                or tools is False else None if completion is None or tools is None else True,
            "vision": False if item.backend not in IMAGE_BACKENDS or not standard
                or completion is False else images,
        }
        result.append({"id": item.ref, "name": item.display_name, "roles": roles})
    # Reject definitions/credentials changed while the metadata batches ran.
    if models:
        service.current(models[0])
    elif service.connection(identity) != connection:
        raise ValueError("Model connection changed; refresh models")
    return result


def _binding(cfg: Config, reference: str, role: str) -> tuple[str, str, str]:
    models = BrowserModels(cfg)
    backend, identity, model_id = reference_parts(reference)
    info = models.verify(identity, model_id, require_tools=role in {"chat", "research"})
    if info.backend != backend:
        raise ValueError("Model adapter changed; refresh before reviewing")
    if role != "chat" and info.backend == "openai_codex":
        raise ValueError("This role requires an endpoint with bounded generation support")
    if role in {"utility", "research", "vision"} and info.capabilities.requires_thinking:
        raise ValueError("Choose a model that supports Standard mode for this role")
    if role == "vision":
        inspect_model(cfg, reference, {"connection_revision": info.connection_revision,
                                       "credential_revision": info.credential_revision},
                      analysis=True)
    return reference, info.connection_revision, info.credential_revision


def prepare_media_setting(
    cfg: Config, draft: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    operation = draft["operation"]
    if operation in {"defaults-recover", "image-settings-recover"}:
        if set(draft) != {"operation", "target"}:
            raise ValueError("Choose an exact unconfirmed save")
        resource = (model_defaults_resource(cfg.data_dir) if operation == "defaults-recover"
                    else image_settings_resource(cfg.config_dir))
        fenced = OperationJournal(cfg.data_dir / "operations.db").fenced_operation(resource)
        if (fenced is None or fenced.receipt.request_id != draft["target"]
                or fenced.receipt.state != "unknown"):
            raise ValueError("Unconfirmed save changed; refresh before reviewing")
        return {"target": fenced.receipt.request_id, "target_owner": fenced.owner_id}, (
            "recover:" + resource
        ), ("Check the exact prior or saved settings. "
            "This does not replay a save or contact a model.")
    if operation == "image-settings-save":
        if (set(draft) - {"operation", "endpoint", "enabled", "revision", "provider", "model"}
                or not {"operation", "endpoint", "enabled", "revision"} <= set(draft)
                or type(draft["enabled"]) is not bool or not isinstance(draft["revision"], str)
                or not isinstance(draft["endpoint"], str)):
            raise ValueError("Invalid image-service settings")
        image_current = read(cfg)
        if image_current["revision"] != draft["revision"]:
            raise ValueError("Image-service settings changed; refresh before reviewing")
        url = endpoint(draft["endpoint"]) if draft["endpoint"] else ""
        provider = draft.get("provider", "sdcpp")
        if provider not in {"sdcpp", "ollama"}:
            raise ValueError("Choose stable-diffusion.cpp or Ollama")
        evidence = inspect(url, provider, draft.get("model", "")) if draft["enabled"] else None
        image_candidate = {"enabled": draft["enabled"], "endpoint": url,
                           "model": (evidence["model"] if evidence else
                                     draft.get("model", image_current["model"])),
                           **({"provider": provider} if provider != "sdcpp" else {})}
        return {"candidate": image_candidate, "revision": image_current["revision"],
                "evidence": evidence}, image_settings_resource(cfg.config_dir), (
            f"{'Enable' if image_candidate['enabled'] else 'Disable'} image generation.\n"
            f"Server: {url or '(none)'}\nModel: {image_candidate['model'] or '(none)'}\n"
            "Enabling checks the server's loaded model and generation capabilities."
        )
    if (operation != "defaults-save" or set(draft) != {"operation", "field", "value", "expected"}
            or not isinstance(draft["field"], str) or draft["field"] not in FIELDS):
        raise ValueError("Invalid Model Defaults request")
    field = draft["field"]
    current = read_defaults(cfg)
    if (type(current.public()[field]) is not type(draft["expected"])
            or current.public()[field] != draft["expected"]):
        raise ValueError("Model default changed; refresh before reviewing")
    candidate = defaults_from_preferences(cfg, {"ai_defaults": {
        **current.public(), field: draft["value"],
    }})
    if candidate.vision_enabled and candidate.vision is None:
        raise ValueError("Disable Vision before clearing its primary model")
    value = getattr(candidate, field)
    role = "utility" if field == "fallbacks" else "vision" if field.startswith("vision") else field
    references = (value if field in {"fallbacks", "vision_fallbacks"} else
                  (value,) if field in {"chat", "utility", "research", "vision"} and value else ())
    # Enabling pixels revalidates the saved primary and every explicit fallback.
    if field == "vision_enabled" and value:
        if not candidate.vision:
            raise ValueError("Choose a Vision model before enabling image input")
        references = (candidate.vision, *candidate.vision_fallbacks)
    bindings = tuple(_binding(cfg, reference, role) for reference in references)
    change = DefaultsChange(field, value, getattr(current, field), bindings)
    return {"change": asdict(change)}, model_defaults_resource(cfg.data_dir), (
        f"Set {field.replace('_', ' ')} to {value if value is not None else 'unset'}.\n"
        "Shares this default with Klaude's terminal workflows. The current chat keeps its model."
    )


def run_media_setting(cfg: Config, request: dict[str, Any]) -> dict[str, bool]:
    journal = OperationJournal(cfg.data_dir / "operations.db")
    if request["operation"] in {"defaults-recover", "image-settings-recover"}:
        recover = (recover_model_defaults if request["operation"] == "defaults-recover"
                   else recover_image_settings)
        try:
            recover(cfg, journal, request["target"], request["target_owner"])
        except OperationConflict:
            return {"rejected": True}
        return {"ok": True}
    if request["operation"] == "image-settings-save":
        candidate = request["candidate"]
        if candidate["enabled"] and inspect_settings(candidate) != request["evidence"]:
            return {"rejected": True}
        save_image_settings(cfg, candidate, request["revision"], journal,
                            request["request_id"], "web-admin", admitted=True)
    else:
        raw = request["change"]
        value, expected = raw["value"], raw["expected"]
        if raw["field"] in {"fallbacks", "vision_fallbacks"}:
            value, expected = tuple(value), tuple(expected)
        bindings = tuple(tuple(item) for item in raw["bindings"])
        change = DefaultsChange(raw["field"], value, expected, bindings)
        # The shared writer validates current definition/credential bindings.
        if change.field == "vision_enabled" and change.value:
            current = read_defaults(cfg)
            if tuple(item[0] for item in bindings) != (current.vision, *current.vision_fallbacks):
                return {"rejected": True}
            for reference, definition, credential in bindings:
                inspect_model(cfg, reference, {"connection_revision": definition,
                                               "credential_revision": credential}, analysis=True)
        save_model_defaults(cfg, change, journal, request["request_id"], "web-admin", admitted=True)
    return {"ok": True}
