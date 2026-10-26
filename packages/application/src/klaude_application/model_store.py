"""Bounded Model Store projection over the native manager and operation journal.

Discovery is a shipped, dated editorial snapshot, not an undocumented catalog API.
Private recovery targets accompany existing journal receipts; no download engine
or independent job database lives here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from klaude_core.config import Config
from klaude_core.library_artifacts import regular_path
from klaude_core.model_connections import connection_key
from klaude_core.ollama_activity import local_request_ended, local_server_generation
from klaude_core.ollama_manager import ManagerTransport, endpoint, execute_manager, model_name
from klaude_core.settings_store import atomic_write_private, settings_lock

from .operation_journal import OperationConflict, OperationJournal

OPERATIONS = frozenset({"model-pull", "model-delete"})
RESOURCE = "browser-model-work"
OWNER = "web-admin"
VERIFIED = "2026-10-25"
PUBLIC_MODEL = frozenset({"name", "digest", "size", "modified", "parameters",
                          "quantization", "family", "vram", "context"})
# These are original editorial summaries; numeric facts link to exact official tags.
CATALOG: list[dict[str, Any]] = [
    {
        "id": "qwen3",
        "name": "Qwen 3",
        "publisher": "Qwen",
        "summary": "Explore reasoning and tool use with a choice of compact variants.",
        "categories": ["Reasoning", "General-purpose", "Lightweight"],
        "capabilities": ["tools", "thinking"],
        "license": "Apache 2.0",
        "variants": [
            {"tag": "qwen3:0.6b", "parameters": "752M", "size_label": "523 MB"},
            {"tag": "qwen3:4b", "parameters": "4.02B", "size_label": "2.5 GB"},
        ],
    },
    {
        "id": "qwen2.5-coder",
        "name": "Qwen 2.5 Coder",
        "publisher": "Qwen",
        "summary": "A code-focused model for writing, understanding and fixing code.",
        "categories": ["Coding"],
        "capabilities": ["tools"],
        "license": "Apache 2.0",
        "variants": [{"tag": "qwen2.5-coder:7b", "parameters": "7.62B", "size_label": "4.7 GB"}],
    },
    {
        "id": "gemma3",
        "name": "Gemma 3",
        "publisher": "Google",
        "summary": "Explore image understanding and text tasks with the 4B variant.",
        "categories": ["Vision", "General-purpose"],
        "capabilities": ["vision"],
        "license": "Gemma Terms of Use",
        "variants": [
            {"tag": "gemma3:4b", "parameters": "3.88B + 420M projector", "size_label": "3.4 GB"}
        ],
    },
]


def read_record(path, *, limit: int = 2_000_000) -> dict[str, Any]:
    regular_path(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Model Store record exceeds its read bound")
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Model Store record exceeds its read bound")
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("Invalid Model Store record")
    return result


def discovery() -> dict[str, Any]:
    return {
        "verified": VERIFIED,
        "source": "bundled",
        "rankings": False,
        "models": [
            {
                **item,
                "source_url": f"https://ollama.com/library/{item['id']}",
                "variants": [
                    {
                        **variant,
                        "quantization": "Q4_K_M",
                        "source_url": "https://ollama.com/library/" + variant["tag"],
                    }
                    for variant in item["variants"]
                ],
            }
            for item in CATALOG
        ],
    }


def inventory(cfg: Config, identity: str) -> dict[str, Any]:
    connection, credential = endpoint(cfg, identity)
    cache_key = hashlib.sha256(
        f"{identity}:{connection.revision}:{credential}".encode()
    ).hexdigest()
    cache = cfg.data_dir / "model-manager" / "inventory" / f"{cache_key}.json"
    regular_path(cache)
    result = execute_manager(cfg, {"operation": "inventory", "endpoint": identity})
    if "endpoint" not in result:
        raise ValueError("Native Ollama inventory unavailable; check the configured connection")
    if result["models"] is None:
        cached = read_record(cache)
        if (cached.get("connection") == identity and isinstance(cached.get("models"), list)
                and len(cached["models"]) <= 1000
                and all(isinstance(row, dict) for row in cached["models"])
                and set(cached) <= {"connection", "checked_at", "models", "error",
                                    "running_known", "running", "version", "stale"}):
            return {**cached, "models": [{key: value for key, value in row.items()
                                           if key in PUBLIC_MODEL}
                                          for row in cached["models"]],
                    "stale": True, "error": "Server unavailable; cached inventory"}
    # Explicit allowlist: endpoints, credentials, role bindings and paths stay private.
    public = {
        "connection": identity,
        "checked_at": result["checked_at"],
        "models": result["models"],
        "error": result.get("models_error", ""),
        "running_known": result["running"] is not None,
        "running": [row["name"] for row in result["running"] or []],
        "version": result["version"],
        "stale": False,
    }
    if result["models"] is not None:
        cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private(cache, json.dumps(public))
    return public


def prepare(cfg: Config, draft: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    from .model_manager import ModelManagerCommand

    if set(draft) != {"operation", "connection", "model"}:
        raise ValueError("Choose an exact model variant and configured endpoint")
    operation = draft["operation"]
    if operation not in OPERATIONS:
        raise ValueError("Unknown model operation")
    name = model_name(draft["model"])
    if name != draft["model"]:
        raise ValueError("Choose an explicit model:tag variant")
    connection, credential = endpoint(cfg, draft["connection"])
    result = execute_manager(cfg, {"operation": "inventory", "endpoint": connection.id})
    if result.get("models") is None or result.get("running") is None:
        raise ValueError("Fresh installed and loaded model inventory is required")
    existing = next((row for row in result["models"] if row["name"] == name), None)
    if operation == "model-pull" and existing:
        raise ValueError("This exact variant is already installed; refresh Installed")
    if operation == "model-delete":
        if not existing:
            raise ValueError("This model is no longer installed")
        if result["bindings"].get(name) or any(
            row["name"] == name or row["digest"] == existing["digest"] for row in result["running"]
        ):
            raise ValueError("This model is loaded or selected by a conversation or default role")
    fields = {
        "endpoint": connection.id,
        "model": name,
        "revision": connection.revision,
        "credential_revision": credential,
        "digest": existing["digest"] if existing else "",
        "environment_keys": ModelManagerCommand.for_client(
            cfg, "pull", key_env=connection.key_env,
        ).environment_keys,
    }
    verb = "Download" if operation == "model-pull" else "Delete"
    return (
        fields,
        RESOURCE,
        (
            f"{verb} {name} on {connection.name}. "
            + (
                "Downloads weights to this Ollama server. "
                "Size and license depend on the exact tag. "
                "Chat and default models remain unchanged. Cancelling stops the owned request; "
                "remote transfer and partial layer cleanup may remain unconfirmed."
                if operation == "model-pull"
                else "Permanently removes this model from the selected server. "
                "Loaded models and selected roles are checked again before deletion."
            )
        ),
    )


def target_path(cfg: Config, identity: str):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid model operation identity")
    path = cfg.data_dir / "model-manager" / "browser" / f"{identity}.json"
    regular_path(path)
    return path


def save_target(cfg: Config, identity: str, fields: dict[str, Any]) -> None:
    path = target_path(cfg, identity)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Inherited credentials travel only through the existing private worker pipe.
    atomic_write_private(path, json.dumps(private_target(fields)))


def private_target(fields: dict[str, Any]) -> dict[str, Any]:
    keys = ("endpoint", "model", "revision", "credential_revision", "digest")
    return {k: fields[k] for k in keys}


def witness(fields: dict[str, Any], installed: bool) -> dict[str, Any]:
    return {"target": private_target(fields), "installed": installed}


def save_message(cfg: Config, identity: str, message: str) -> None:
    path = target_path(cfg, identity)
    with settings_lock(path):
        target = read_record(path, limit=16_384)
        atomic_write_private(path, json.dumps({**target, "message": message}))


def dismiss(cfg: Config, journal: OperationJournal, identity: str) -> dict[str, Any]:
    """Dismiss history only. Unknown receipts and their admission fences survive."""
    path = target_path(cfg, identity)
    with settings_lock(path):
        receipt = journal.status(identity, OWNER)
        if receipt is None or receipt.kind not in OPERATIONS:
            raise ValueError("Choose an exact model operation")
        if receipt.state not in {"completed", "failed", "cancelled", "unknown"}:
            raise OperationConflict("Stop the active download before removing its history")
        target = read_record(path, limit=16_384)
        if not target:
            raise ValueError("Model operation target unavailable")
        atomic_write_private(path, json.dumps({**target, "dismissed": True}))
        return {"request_id": identity, "dismissed": True, "state": receipt.state}


def jobs(cfg: Config, journal: OperationJournal) -> dict[str, Any]:
    items = []
    receipts = journal.recent(OWNER, limit=100)
    pending = journal.fenced_operation(RESOURCE)
    if pending and not any(r.request_id == pending.receipt.request_id for r in receipts):
        receipts = (pending.receipt, *receipts)
    for receipt in receipts:
        if receipt.kind not in OPERATIONS:
            continue
        target = read_record(target_path(cfg, receipt.request_id), limit=16_384)
        dismissed = target.get("dismissed") is True
        if dismissed and receipt.state in {"completed", "failed", "cancelled"}:
            continue
        items.append(
            {
                **asdict(receipt),
                "model": target.get("model", "Unknown model"),
                "connection": target.get("endpoint", ""),
                "message": target.get("message", ""),
                "dismissed": dismissed,
            }
        )
        if len(items) == 30:
            break
    return {"items": items}


def run(cfg: Config, request: dict[str, Any], progress: Callable | None = None) -> dict:
    from .model_manager import ModelManagerCommand

    command = ModelManagerCommand.from_worker({
        "kind": "model_manager", "operation": request["operation"].removeprefix("model-"),
        "config_dir": str(cfg.config_dir), "data_dir": str(cfg.data_dir),
        "environment_keys": request.get("environment_keys", {}),
        **{key: request[key] for key in ("endpoint", "model", "revision",
                                       "credential_revision", "digest")},
    })
    os.environ.update(command.environment_keys)
    journal = OperationJournal(cfg.data_dir / "operations.db")
    # The native manager checks the lease at its actual effect boundary, after
    # acquiring its endpoint lock and rechecking loaded/selected models.
    result = execute_manager(
        cfg,
        command.worker_request(),
        progress or (lambda _: None),
        before_effect=lambda: journal.check_effect(request["request_id"], OWNER, request["fence"]),
        native_request_id=request["request_id"],
    )
    return {
        "ok": result.get("status") == "ok",
        "rejected": (result.get("effect_started") is False
                     or result.get("outcome_confirmed") is True),
        "message": result.get("message", "Model operation unconfirmed"),
    }


def reconcile(
    cfg: Config, journal: OperationJournal, identity: str, *, require_end_proof: bool = False,
) -> dict[str, Any]:
    receipt = journal.status(identity, OWNER)
    if receipt is None or receipt.kind not in OPERATIONS or receipt.state != "unknown":
        raise OperationConflict("Only an unconfirmed model operation can be checked")
    target = read_record(target_path(cfg, identity), limit=16_384)
    connection, _ = endpoint(cfg, target.get("endpoint", ""), target)
    lock = cfg.data_dir / "model-manager" / hashlib.sha256(connection.base_url.encode()).hexdigest()
    with settings_lock(lock):
        generation = local_server_generation(connection.base_url)
        ended = local_request_ended(connection.base_url, identity, generation=generation)
        newer = bool(generation
                     and time.time() - time.monotonic() + generation[1] / 1e6
                     > receipt.updated_at + 5)
        if require_end_proof and not (newer or ended):
            raise OperationConflict("The native request end is not confirmed")
        client = ManagerTransport(connection, connection_key(cfg, connection))
        try:
            current_model = next((row for row in client.models()
                                  if row["name"] == target["model"]), None)
            installed = current_model is not None
        finally:
            client.close()
        endpoint(cfg, connection.id, target)
        current = witness(target, installed)
        desired = installed == (receipt.kind == "model-pull")
        # A missing model alone cannot prove a remote pull stopped. A newer
        # verified local daemon cannot still own the old request, however, so
        # its fresh exact prior inventory can safely reconcile as Failed.
        stable = bool(generation and local_server_generation(connection.base_url) == generation)
        stopped = newer and stable
        ended = ended and stable
        if (not desired and not (stopped or ended)
                or receipt.kind == "model-delete" and current_model is not None
                and current_model["digest"] != target["digest"]):
            raise OperationConflict(
                ("The model is not currently installed. " if receipt.kind == "model-pull"
                 and not installed else "The reviewed final inventory is not confirmed. ")
                + "An earlier request may still be active. The operation remains fenced; "
                "check the Ollama server before trying again."
            )
        result = journal.reconcile_witness(identity, OWNER, current=current)
        if result.state == "failed":
            try:
                save_message(cfg, identity,
                             "The Ollama request ended; the reviewed change did not complete.")
            except (OSError, ValueError):
                pass
        return asdict(result)
