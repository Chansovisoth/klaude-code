"""Reviewed managed ComfyUI installation, inspection and exact-outcome recovery."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

from klaude_core import comfyui_managed as managed
from klaude_core.comfyui_bundle import CONTROL, digest
from klaude_core.settings_store import read_settings

from . import image_model_store
from .operation_journal import OperationConflict, OperationJournal

OPERATIONS = frozenset(
    {
        "comfy-install",
        "comfy-recover",
        "comfy-import",
        "comfy-remove",
        "comfy-repair",
        "comfy-store-install",
    }
)
OWNER = "web-admin"


def resource(cfg):
    return "comfy-install:" + digest(str(managed.root(cfg)))


def inventory(cfg):
    from .comfyui_models import public_items

    record = {}
    error = ""
    try:
        record = managed.installed(cfg)
    except (ValueError, OSError) as exc:
        error = str(exc) if isinstance(exc, ValueError) else "Managed installation unavailable"
    pending = None
    if (cfg.data_dir / "operations.db").exists():
        journal = OperationJournal(cfg.data_dir / "operations.db")
        fenced = journal.fenced_operation(resource(cfg))
        if fenced:
            evidence = journal.evidence(fenced.receipt.request_id, OWNER)
            pending = {
                "request_id": fenced.receipt.request_id,
                "state": fenced.receipt.state,
                "kind": fenced.receipt.kind,
                "progress": evidence.get("progress", {}),
            }
            checking = journal.fenced_operation("recover:" + resource(cfg))
            if checking and checking.receipt.state in {"accepted", "running", "cancelling"}:
                pending["checking"] = True

    try:
        last = read_settings(managed.root(cfg) / "last-generation.json")
    except OSError:
        last = {}
    verification = (
        last.get("models", {}).get(managed.BUNDLE_ID, last)
        if isinstance(last.get("models", {}), dict)
        else last
    )
    if not isinstance(verification, dict):
        verification = {}
    return {
        "support_message": managed.support_reason(),
        "items": public_items(cfg),
        "runtime_version": managed.COMFY_VERSION,
        "bundle": {
            **CONTROL.public(),
            "id": managed.BUNDLE_ID,
            "name": "Stable Diffusion 1.5",
            "install_available": not managed.support_reason(),
            "runtime_lock_verified": bool(record),
            "generation_verified": bool(
                record and verification.get("installation") == digest(record)
            ),
        },
        "installed": bool(record),
        "installation_revision": digest(record),
        "endpoint": "managed",
        "pending": pending,
        "message": error,
        "generation_verified": bool(record and verification.get("installation") == digest(record)),
        "setup_started": (managed.root(cfg) / "install.log").exists(),
    }


def prepare(cfg, draft):
    if draft.get("operation") in {
        "comfy-import",
        "comfy-remove",
        "comfy-repair",
        "comfy-store-install",
    }:
        from .comfyui_models import prepare as prepare_model

        return prepare_model(cfg, draft)
    operation = draft["operation"]
    if operation == "comfy-recover":
        if set(draft) != {"operation", "target"}:
            raise ValueError("Choose an exact uncertain installation")
        journal = OperationJournal(cfg.data_dir / "operations.db")
        fenced = journal.fenced_operation(resource(cfg))
        if (
            not fenced
            or fenced.receipt.request_id != draft["target"]
            or fenced.owner_id != OWNER
            or fenced.receipt.state != "unknown"
        ):
            raise ValueError("Unconfirmed ComfyUI installation changed")
        previous = journal.fenced_operation("recover:" + resource(cfg))
        if previous and previous.receipt.state == "unknown":
            proof = journal.evidence(previous.receipt.request_id, OWNER)
            if proof != {"version": 1, "target": draft["target"]}:
                raise OperationConflict("Previous check lacks recovery evidence; inspect Activity")
            with managed.install_lock(cfg):
                journal.reconcile(
                    previous.receipt.request_id,
                    OWNER,
                    state="failed",
                    evidence="Interrupted checked read; exact target remains fenced",
                )
        return (
            {"target": draft["target"]},
            "recover:" + resource(cfg),
            (
                "Check this removal and finish only its exact reviewed managed-file cleanup. "
                "Keeps original Store downloads and Library images."
                if fenced.receipt.kind == "comfy-remove"
                else "Check this exact installation without replaying downloads or generation. "
                "A stopped partial installation is retained for an explicit retry."
            ),
        )
    if set(draft) != {"operation"} or operation != "comfy-install":
        raise ValueError("Choose the supported complete image bundle")
    base = managed.root(cfg)
    source = ""
    for candidate in (
        image_model_store.root() / CONTROL.filename,
        image_model_store.root() / "checkpoints" / CONTROL.repository / CONTROL.filename,
    ):
        if candidate.exists() and managed.signature(candidate)[2] == CONTROL.size:
            source = str(candidate)
            break
    before = read_settings(base / "installed.json")
    fields = {
        "definition": digest(managed.definition()),
        "reuse_path": source,
        "source_signature": managed.signature(Path(source)) if source else [],
        "before": before,
    }
    return (
        fields,
        resource(cfg),
        (
            "Install/repair ComfyUI 0.43.0 in an isolated Python 3.12 environment and the "
            "complete Stable Diffusion 1.5 image bundle. Runtime: pinned CUDA 12.6 dependencies; "
            "download size not yet known, allow at least 12 GiB disk for runtime/staging. "
            f"Model: {CONTROL.size:,} bytes; "
            + (
                "copy and verify the existing local file."
                if source
                else "download the pinned model."
            )
            + f" SHA-256: {CONTROL.sha256}. Weights license: {CONTROL.license}. "
            "Starts a private local engine with low-memory settings. Does not load weights, "
            "generate an image or change defaults. Partial downloads remain available for retry."
        ),
    )


def run(cfg, request, progress):
    if request["operation"] in {
        "comfy-import",
        "comfy-remove",
        "comfy-repair",
        "comfy-store-install",
    }:
        from .comfyui_models import run as run_model

        return run_model(cfg, request, progress)
    journal = OperationJournal(cfg.data_dir / "operations.db")
    rid, fence = request["request_id"], request["fence"]
    base = managed.root(cfg)
    if request["operation"] == "comfy-recover":
        target = request["target"]
        journal.save_evidence(rid, OWNER, fence, {"version": 1, "target": target})
        receipt = journal.status(rid, OWNER)
        if receipt and receipt.state == "accepted":
            journal.start(rid, OWNER, fence)
        with managed.install_lock(cfg):
            journal.check_effect(rid, OWNER, fence)
            pending = journal.fenced_operation(resource(cfg))
            evidence = journal.evidence(target, OWNER)
            if (
                not pending
                or pending.receipt.request_id != target
                or pending.receipt.state != "unknown"
                or (
                    evidence.get("operation")
                    not in {"comfy-import", "comfy-remove", "comfy-repair", "comfy-store-install"}
                    and evidence.get("definition") != digest(managed.definition())
                )
            ):
                raise OperationConflict("Installation recovery evidence changed")
            current = read_settings(base / "installed.json")
            state: Literal["completed", "failed"]
            if evidence.get("operation") in {
                "comfy-import",
                "comfy-remove",
                "comfy-repair",
                "comfy-store-install",
            }:
                from .comfyui_models import recover as recover_model

                state = recover_model(
                    cfg, target, evidence, lambda: journal.check_effect(rid, OWNER, fence)
                )
            elif current.get("request_id") == target:
                managed.installed(cfg, full=True)
                state = "completed"
            elif current == evidence.get("before"):
                # The inherited exclusive install lock proves no installer child
                # can still be writing. Retained partial files are explicit effects.
                state = "failed"
            else:
                raise OperationConflict("Installed bundle differs from the reviewed outcome")
            journal.check_effect(rid, OWNER, fence)
            journal.reconcile(
                target,
                OWNER,
                state=state,
                evidence="Exact owned bundle inventory checked under exclusive install lock",
            )
        return {"ok": True}

    if (
        request["definition"] != digest(managed.definition())
        or read_settings(base / "installed.json") != request["before"]
        or request["reuse_path"]
        and managed.signature(Path(request["reuse_path"])) != request["source_signature"]
    ):
        return {"rejected": True}
    receipt = journal.status(rid, OWNER)
    if not receipt or receipt.state != "accepted":
        raise OperationConflict("Exact ComfyUI installation admission unavailable")
    journal.save_evidence(
        rid, OWNER, fence, {"definition": request["definition"], "before": request["before"]}
    )
    journal.start(rid, OWNER, fence)

    checked = [0.0]

    def check():
        if time.monotonic() - checked[0] >= 0.2:
            journal.check_effect(rid, OWNER, fence)
            checked[0] = time.monotonic()

    reported_at = 0.0
    reported_stage = ""

    def notify(value):
        nonlocal reported_at, reported_stage
        if progress:
            progress(value)
        now = time.monotonic()
        if now - reported_at >= 0.5 or reported_stage != value.get("stage"):
            old = journal.evidence(rid, OWNER)
            journal.save_evidence(
                rid, OWNER, fence, {**old, "progress": value}, expected=old, require_running=True
            )
            reported_at, reported_stage = now, value.get("stage", "")

    def before_publish(value):
        journal.check_effect(rid, OWNER, fence)

    def fetch(directory, temporary, notify, verify):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                image_model_store._transfer(
                    {
                        "base_url": "https://huggingface.co",
                        "repo": CONTROL.repository,
                        "revision": CONTROL.revision,
                        "filename": CONTROL.filename,
                        "size": CONTROL.size,
                        "sha256": CONTROL.sha256,
                    },
                    descriptor,
                    temporary,
                    notify,
                    verify,
                )
            except image_model_store.InvalidPartial:
                os.unlink(temporary, dir_fd=descriptor)
                raise
        finally:
            os.close(descriptor)

    try:
        managed.install(cfg, rid, request["reuse_path"], fetch, check, notify, before_publish)
        return {"ok": True}
    except (ValueError, OSError):
        # Normal failures reap their subprocesses and release the install lock.
        # A killed worker cannot reach here and remains uncertain/fenced.
        return {
            "rejected": True,
            "message": "Installation incomplete. Inspect the managed log and retry.",
        }
