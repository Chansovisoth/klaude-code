"""Journaled, exact-state changes to the private image-service settings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from klaude_core.settings_store import settings_lock

from .operation_journal import (
    OperationConflict,
    OperationFenceLost,
    OperationJournal,
    OperationReceipt,
)


class ImageSettingsUnconfirmed(RuntimeError):
    """The settings effect or its durable acknowledgement is uncertain."""


def image_settings_resource(config_dir: Path) -> str:
    path = Path(config_dir).resolve() / "image-generation.json"
    return "image-settings:" + hashlib.sha256(str(path).encode()).hexdigest()


def recover_image_settings(
    cfg: Any, journal: OperationJournal, request_id: str, owner_id: str,
) -> OperationReceipt:
    """Reconcile only an exact prior/final settings snapshot without replay."""
    from klaude_core.image_generation import read

    fenced = journal.fenced_operation(image_settings_resource(cfg.config_dir))
    if (
        fenced is None or fenced.owner_id != owner_id
        or fenced.receipt.request_id != request_id
        or fenced.receipt.state != "unknown"
    ):
        raise OperationConflict("Matching uncertain image-service setting unavailable")
    with settings_lock(Path(cfg.config_dir) / "image-generation.json", timeout=2):
        return journal.reconcile_witness(
            request_id, owner_id, current=read(cfg),
        )


def save_image_settings(
    cfg: Any, candidate: dict, revision: str, journal: OperationJournal,
    request_id: str, owner_id: str, *, admitted: bool = False,
) -> dict:
    """Fence one already-reviewed local settings write under its file lock."""
    from klaude_core.image_generation import save

    intent = json.dumps(
        {"candidate": candidate, "revision": revision},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    if len(intent) > 262_144:
        raise ValueError("Image-service settings intent exceeds safety limit")
    resource = image_settings_resource(cfg.config_dir)
    if admitted:
        existing = journal.status(request_id, owner_id)
        if existing is None or existing.resource != resource or existing.state != "accepted":
            raise OperationConflict("Reviewed image-service admission unavailable")
        receipt = existing
    else:
        receipt = journal.admit(
            request_id=request_id, owner_id=owner_id, kind="ImageSettingsChange",
            resource=resource, payload={"sha256": hashlib.sha256(intent).hexdigest()},
            lease_seconds=60,
        )
        if not receipt.created:
            raise OperationConflict("Image-service settings request was already submitted")
    started = False

    def before_publish(before: dict, after: dict) -> None:
        nonlocal started
        journal.record_witness(
            request_id, owner_id, receipt.fence, before=before, after=after,
        )
        # A committed start can lose its acknowledgement before returning.
        started = True
        journal.start(request_id, owner_id, receipt.fence)
        journal.check_effect(request_id, owner_id, receipt.fence)

    try:
        result = save(cfg, candidate, revision, before_publish=before_publish)
    except Exception as exc:
        if started:
            try:
                journal.mark_unknown(request_id, owner_id, receipt.fence)
            except (OSError, sqlite3.Error, OperationFenceLost):
                pass
            raise ImageSettingsUnconfirmed(
                "Image-service setting outcome uncertain; run "
                "`klaude library image-service-recover`"
            ) from exc
        try:
            current = journal.status(request_id, owner_id)
            if current is not None and current.state == "accepted":
                journal.finish(request_id, owner_id, receipt.fence, state="failed",
                               outcome="failed")
        except (OSError, sqlite3.Error, OperationFenceLost):
            raise ImageSettingsUnconfirmed(
                "Image-service setting admission uncertain; inspect journal before retrying"
            ) from exc
        raise
    try:
        journal.finish(request_id, owner_id, receipt.fence, state="completed",
                       outcome="ok")
    except (OSError, sqlite3.Error, OperationFenceLost) as exc:
        try:
            journal.mark_unknown(request_id, owner_id, receipt.fence)
        except (OSError, sqlite3.Error, OperationFenceLost):
            pass
        raise ImageSettingsUnconfirmed(
            "Image-service setting saved but acknowledgement uncertain; "
            "run `klaude library image-service-recover`"
        ) from exc
    return result
