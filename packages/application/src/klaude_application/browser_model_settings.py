"""Owner-reviewed connection definitions and write-only credentials.

All publications use shared application services, fixed workers and the existing
private operation journal. Recovery compares witnessed local state without replay.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import asdict, replace
from typing import Any

from klaude_core.config import provider_secret_revision, provider_secret_value
from klaude_core.model_connections import (
    BACKENDS,
    DEFAULT_URLS,
    ModelConnection,
    connection_registry,
)
from klaude_core.model_discovery import discover_connection
from klaude_core.settings_store import settings_lock

from .model_connections import ModelConnectionService, ModelDefinitionChange
from .model_store import read_record, target_path
from .operation_journal import OperationConflict, OperationJournal
from .provider_secrets import ProviderSecretUpdate

OWNER = "web-admin"
PREFIX = "model-connection-"
WRITES = frozenset(PREFIX + name for name in ("add", "edit", "enabled", "remove", "credential"))
OPERATIONS = WRITES | {PREFIX + "recover"}
CREDENTIAL_NAMES = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_API_KEY",
    }
)


def resource(cfg) -> str:
    return (
        "model-connections:"
        + hashlib.sha256(str(connection_registry(cfg).path.resolve()).encode()).hexdigest()
    )


def recovery_path(cfg, request_id):
    # Reuse the manager's bounded private adjunct record directory, not a job DB.
    path = target_path(cfg, request_id)
    return path.with_name("settings-" + path.name)


def _write_context(cfg, identity, value):
    import json

    from klaude_core.settings_store import atomic_write_private

    path = recovery_path(cfg, identity)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private(path, json.dumps(value))


def _credential_supported(name):
    return bool(name and (name.startswith("KLAUDE_MODEL_") or name in CREDENTIAL_NAMES))


def inventory(cfg, *, management_allowed: bool) -> dict[str, Any]:
    connections = ModelConnectionService(cfg).list()
    pending = None
    if (cfg.data_dir / "operations.db").exists():
        fenced = OperationJournal(cfg.data_dir / "operations.db").fenced_operation(resource(cfg))
        if fenced:
            pending = {"request_id": fenced.receipt.request_id, "state": fenced.receipt.state}
    return {
        "management_allowed": management_allowed,
        "pending": pending,
        "adapters": [
            {"id": backend, "url": DEFAULT_URLS.get(backend, "")}
            for backend in sorted(BACKENDS - {"openai_codex"})
        ],
        "connections": [
            {
                "id": c.id,
                "name": c.name,
                "backend": c.backend,
                "source": c.source,
                "enabled": c.enabled,
                "revision": c.revision,
                "authentication": bool(c.key_env),
                "credential_set": bool(provider_secret_value(cfg.config_dir, c.key_env))
                if c.key_env
                else False,
                "credential_editable": _credential_supported(c.key_env),
                **({"url": c.base_url} if management_allowed else {}),
            }
            for c in connections.values()
        ],
    }


def exact(cfg, identity, revision) -> ModelConnection:
    connection = ModelConnectionService(cfg).list().get(identity)
    if connection is None or connection.revision != revision:
        raise ValueError("Connection changed; refresh and review again")
    return connection


def test_connection(cfg, draft) -> dict[str, Any]:
    if set(draft) != {"connection", "revision"}:
        raise ValueError("Choose an exact saved connection")
    connection = exact(cfg, draft["connection"], draft["revision"])
    from klaude_core.model_connections import connection_key

    credential = (
        provider_secret_revision(cfg.config_dir, connection.key_env) if connection.key_env else ""
    )
    try:
        models = discover_connection(
            replace(connection, enabled=True), connection_key(cfg, connection)
        )
    except Exception:
        # Provider errors can contain tokens or private paths.
        return {
            "available": False,
            "message": "Connection unavailable; check its address and credential.",
        }
    exact(cfg, connection.id, connection.revision)
    if (
        connection.key_env
        and provider_secret_revision(cfg.config_dir, connection.key_env) != credential
    ):
        raise ValueError("Credential changed during testing; test again")
    return {
        "available": True,
        "models": len(models),
        "message": f"Connection reached: {len(models)} model(s). No generation submitted.",
    }


def prepare(cfg, draft):
    operation = draft["operation"]
    if operation == PREFIX + "recover":
        if set(draft) != {"operation", "target"}:
            raise ValueError("Choose an exact unconfirmed connection change")
        fenced = OperationJournal(cfg.data_dir / "operations.db").fenced_operation(resource(cfg))
        if (
            not fenced
            or fenced.receipt.request_id != draft["target"]
            or fenced.receipt.state != "unknown"
        ):
            raise ValueError("Unconfirmed connection change unavailable")
        return (
            {"target": draft["target"]},
            "recover:" + resource(cfg),
            "Check saved connection or credential state without replay or provider requests.",
        )
    if operation == PREFIX + "add":
        if set(draft) - {"authentication"} != {
            "operation",
            "name",
            "backend",
            "url",
            "source",
        } or draft["backend"] not in BACKENDS - {"openai_codex"}:
            raise ValueError("Choose a supported model adapter and connection")
        authentication = draft.get(
            "authentication", not (draft["backend"] == "ollama" and draft["source"] == "Local")
        )
        if type(authentication) is not bool:
            raise ValueError("Choose whether the connection uses a credential")
        identity = "model-" + secrets.token_hex(8)
        connection = ModelConnection(
            identity,
            draft["name"],
            draft["backend"],
            draft["url"],
            draft["source"],
            ("KLAUDE_MODEL_" + identity.replace("-", "_").upper()) if authentication else "",
            False,
        )
        fields: dict[str, Any] = {"expected": None, "value": asdict(connection)}
        summary = (
            f"Add disabled model connection {connection.name}. "
            f"Adapter: {connection.backend}. "
            f"Address: {connection.base_url}. "
            f"Saved credential: {'required' if authentication else 'not used'}. "
            f"Enabling and credentials are separate actions."
        )
    else:
        old = exact(cfg, draft.get("connection"), draft.get("revision"))
        base = {"operation", "connection", "revision"}
        fields = {"expected": asdict(old)}
        if operation == PREFIX + "credential":
            if set(draft) != base | {"value"} or not _credential_supported(old.key_env):
                raise ValueError("This credential is managed in the terminal")
            value = draft["value"]
            if (
                not isinstance(value, str)
                or len(value) > 8192
                or any(not c.isprintable() for c in value)
            ):
                raise ValueError("Use a single-line credential of at most 8192 characters")
            fields.update(
                secret=value,
                credential_revision=provider_secret_revision(cfg.config_dir, old.key_env),
            )
            summary = (
                f"{'Replace' if value else 'Remove'} saved credential for {old.name}. "
                f"The secret is never shown or included in public activity. "
                f"Connections sharing this credential are also affected."
            )
        elif operation == PREFIX + "edit":
            if (
                set(draft) - {"authentication"} != base | {"name", "url", "source"}
                or old.backend == "openai_codex"
            ):
                raise ValueError("Choose editable connection fields")
            authentication = draft.get("authentication", bool(old.key_env))
            if type(authentication) is not bool:
                raise ValueError("Choose whether the connection uses a credential")
            key_env = (
                (old.key_env or "KLAUDE_MODEL_" + old.id.replace("-", "_").upper())
                if authentication
                else ""
            )
            value = replace(
                old,
                name=draft["name"],
                base_url=draft["url"],
                source=draft["source"],
                key_env=key_env,
            )
            fields["value"] = asdict(value)
            summary = (
                f"Update {old.name}: {value.name}, {value.base_url}, {value.source} routing. "
                f"Saved credential: {'required' if authentication else 'not used'}. "
                "Saved conversations keep their revision and may require model selection."
            )
        elif operation == PREFIX + "enabled":
            if set(draft) != base | {"enabled"} or type(draft["enabled"]) is not bool:
                raise ValueError("Choose enabled or disabled")
            if draft["enabled"]:
                revision = (
                    provider_secret_revision(cfg.config_dir, old.key_env) if old.key_env else ""
                )
                check = test_connection(cfg, {"connection": old.id, "revision": old.revision})
                if not check["available"]:
                    raise ValueError(check["message"])
                if (
                    old.key_env
                    and provider_secret_revision(cfg.config_dir, old.key_env) != revision
                ):
                    raise ValueError("Credential changed during testing; review again")
                fields["credential_revision"] = revision
            fields["value"] = asdict(replace(old, enabled=draft["enabled"]))
            summary = (
                f"{'Enable' if draft['enabled'] else 'Disable'} {old.name}. "
                f"Current conversation and role protections are rechecked before saving."
            )
        elif operation == PREFIX + "remove" and set(draft) == base:
            fields["value"] = None
            summary = (
                f"Remove model connection {old.name}. "
                f"Installed weights and stored credentials are retained. "
                f"Clear any dedicated credential first if you also want it removed."
            )
        else:
            raise ValueError("Unknown connection change")
    return fields, resource(cfg), summary


def _credential_state(cfg, name):
    from klaude_core.config import _parse_env_file

    return {
        "value": _parse_env_file(cfg.config_dir / ".env").get(name),
        "revision": provider_secret_revision(cfg.config_dir, name),
    }


def recover(cfg, journal, identity):
    receipt = journal.status(identity, OWNER)
    if not receipt or receipt.resource != resource(cfg) or receipt.state != "unknown":
        raise OperationConflict("Matching unconfirmed connection change unavailable")
    context = read_record(recovery_path(cfg, identity), limit=16384)
    registry = connection_registry(cfg)
    with settings_lock(registry.path), settings_lock(cfg.config_dir / ".env"):
        current = (
            {
                "kind": "credential",
                "name": context["name"],
                "record": _credential_state(cfg, context["name"]),
            }
            if context.get("kind") == "credential"
            else {"kind": "definition", "record": registry._read()}
        )
        return journal.reconcile_witness(identity, OWNER, current=current)


def run(cfg, request):
    journal = OperationJournal(cfg.data_dir / "operations.db")
    identity, fence = request["request_id"], request["fence"]
    if request["operation"] == PREFIX + "recover":
        recover(cfg, journal, request["target"])
        return {"ok": True}
    old = ModelConnection.from_record(request["expected"]) if request["expected"] else None
    started = False
    credential = request["operation"] == PREFIX + "credential"
    context = (
        {"kind": "credential", "name": old.key_env}
        if credential and old
        else {"kind": "definition"}
    )
    _write_context(cfg, identity, context)

    def gate(before, after):
        nonlocal started
        if credential and before["revision"] != request["credential_revision"]:
            raise ValueError("Credential changed; review again")
        if not credential and old and "credential_revision" in request:
            actual = provider_secret_revision(cfg.config_dir, old.key_env) if old.key_env else ""
            if actual != request["credential_revision"]:
                raise ValueError("Credential changed; review again")

        def wrap(record):
            return {**context, "record": record}

        journal.record_witness(identity, OWNER, fence, before=wrap(before), after=wrap(after))
        started = True
        journal.start(identity, OWNER, fence)
        journal.check_effect(identity, OWNER, fence)

    try:
        if credential and old:
            registry = connection_registry(cfg)
            with settings_lock(registry.path):
                exact(cfg, old.id, old.revision)
                if (
                    provider_secret_revision(cfg.config_dir, old.key_env)
                    != request["credential_revision"]
                ):
                    raise ValueError("Credential changed; review again")
                ProviderSecretUpdate(cfg.config_dir, old.key_env, request["secret"]).apply(
                    before_publish=gate
                )
        else:
            value = ModelConnection.from_record(request["value"]) if request["value"] else None
            ModelConnectionService(cfg).save_definition(
                ModelDefinitionChange(old, value), before_publish=gate
            )
    except Exception:
        if started:
            journal.mark_unknown(identity, OWNER, fence)
            return {"ok": False}
        return {"rejected": True}
    return {"ok": True}
