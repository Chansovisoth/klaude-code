"""Fenced, exact-state writes for the shared Model Defaults preference fields."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from klaude_core.ai_defaults import DefaultsChange, save_defaults
from klaude_core.settings_store import read_settings, settings_lock

from .operation_journal import (
    OperationConflict,
    OperationFenceLost,
    OperationJournal,
    OperationReceipt,
)

FIELDS = ("ai_defaults", "model_default_selections", "require_model_selection")


class ModelDefaultsUnconfirmed(RuntimeError):
    """A Model Defaults write or its acknowledgement may have been lost."""


def model_defaults_resource(data_dir: Path) -> str:
    path = Path(data_dir).resolve() / "chat-preferences.json"
    return "model-defaults:" + hashlib.sha256(str(path).encode()).hexdigest()


def _projection(saved: dict[str, Any]) -> dict[str, Any]:
    return {key: saved.get(key) for key in FIELDS}


def recover_model_defaults(
    cfg: Any, journal: OperationJournal, request_id: str, owner_id: str,
) -> OperationReceipt:
    """Check only the fields this service owns; unrelated preferences may change."""
    fenced = journal.fenced_operation(model_defaults_resource(cfg.data_dir))
    if (
        fenced is None or fenced.owner_id != owner_id
        or fenced.receipt.request_id != request_id
        or fenced.receipt.state != "unknown"
    ):
        raise OperationConflict("Matching uncertain Model Defaults change unavailable")
    path = Path(cfg.data_dir) / "chat-preferences.json"
    with settings_lock(path, timeout=2):
        return journal.reconcile_witness(
            request_id, owner_id, current=_projection(read_settings(path)),
        )


def save_model_defaults(
    cfg: Any, change: DefaultsChange, journal: OperationJournal,
    request_id: str, owner_id: str, *, admitted: bool = False,
) -> dict[str, Any]:
    """Fence one reviewed role change under the existing preference file lock."""
    intent = json.dumps(
        asdict(change), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    if len(intent) > 128_000:
        raise ValueError("Model Defaults intent exceeds safety limit")
    resource = model_defaults_resource(cfg.data_dir)
    if admitted:
        existing = journal.status(request_id, owner_id)
        if existing is None or existing.resource != resource or existing.state != "accepted":
            raise OperationConflict("Reviewed Model Defaults admission unavailable")
        receipt = existing
    else:
        receipt = journal.admit(
            request_id=request_id, owner_id=owner_id, kind="ModelDefaultsChange",
            resource=resource, payload={"sha256": hashlib.sha256(intent).hexdigest()},
            lease_seconds=60,
        )
        if not receipt.created:
            raise OperationConflict("Model Defaults request was already submitted")
    started = False

    def before_publish(before: dict[str, Any], after: dict[str, Any]) -> None:
        nonlocal started
        journal.record_witness(
            request_id, owner_id, receipt.fence, before=before, after=after,
        )
        # A committed start can lose its acknowledgement before returning.
        started = True
        journal.start(request_id, owner_id, receipt.fence)
        journal.check_effect(request_id, owner_id, receipt.fence)

    try:
        result = save_defaults(cfg, change, before_publish=before_publish)
    except Exception as exc:
        if started:
            try:
                journal.mark_unknown(request_id, owner_id, receipt.fence)
            except (OSError, sqlite3.Error, OperationFenceLost):
                pass
            raise ModelDefaultsUnconfirmed(
                "Model Defaults outcome uncertain; run "
                "`klaude model-manager defaults-recover`"
            ) from exc
        try:
            current = journal.status(request_id, owner_id)
            if current is not None and current.state == "accepted":
                journal.finish(request_id, owner_id, receipt.fence, state="failed",
                               outcome="failed")
        except (OSError, sqlite3.Error, OperationFenceLost):
            raise ModelDefaultsUnconfirmed(
                "Model Defaults admission uncertain; inspect journal before retrying"
            ) from exc
        raise
    try:
        journal.finish(request_id, owner_id, receipt.fence, state="completed",
                       outcome="ok")
    except (OSError, sqlite3.Error, OperationFenceLost) as exc:
        if not started:
            # An automatic no-op did not publish a changed preference.
            return result
        try:
            journal.mark_unknown(request_id, owner_id, receipt.fence)
        except (OSError, sqlite3.Error, OperationFenceLost):
            pass
        raise ModelDefaultsUnconfirmed(
            "Model Defaults saved but acknowledgement uncertain; "
            "run `klaude model-manager defaults-recover`"
        ) from exc
    return result
