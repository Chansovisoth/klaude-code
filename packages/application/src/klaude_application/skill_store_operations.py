"""Skill install checkpoints and conservative, local-only reconciliation.

The Skill lock spans publication, indexing and finalization. Recovery takes that
same lock after the journal revokes the worker's effect gate. Thus a suspended
worker either finishes before inspection or fails its gate after inspection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from urllib.parse import quote

from klaude_core.skill_catalog import (
    MAX_SKILL_FILE_BYTES,
    MAX_SKILL_FILES,
    MAX_SKILL_PACKAGE_BYTES,
    CatalogFailure,
    SkillRecord,
    SkillSourceError,
)
from klaude_core.skill_drop import file_signature

from .operation_journal import OperationConflict, OperationFenceLost

OWNER = "web-admin"
STAGES = frozenset({"download", "install_package", "knowledge_index", "finalize_package",
                    "verify_postcondition"})
MESSAGES = {
    "SOURCE_UNAVAILABLE": "The pinned source could not be downloaded. Check connectivity.",
    "SOURCE_RATE_LIMIT": "GitHub's request limit was reached. Wait before trying again.",
    "SOURCE_REJECTED": "The pinned source failed package or integrity validation.",
    "PACKAGE_FILE_LIMIT": "The package exceeds the limit of 100 files or directories.",
    "PACKAGE_SIZE_LIMIT": "The source exceeds a 2 MB file or 16 MB package download limit.",
    "PACKAGE_UNSUPPORTED_ENTRY": "The package contains a symlink, submodule or unsupported entry.",
    "DESTINATION_EXISTS": "The local Skill destination already exists. Inspect it before retrying.",
    "INDEX_WRITE_FAILED": "Knowledge indexing could not be confirmed. Inspect recovery.",
    "PACKAGE_FINALIZE_FAILED": "Package publication could not be confirmed. Inspect recovery.",
    "UNEXPECTED_FAILURE": "The Skill installation stopped unexpectedly. Inspect recovery.",
}


def initial(record):
    return {"schema_version": 1, "record": record, "stage": "download",
            "effect_started": False}


def failure(exc, stage):
    code = "UNEXPECTED_FAILURE"
    if isinstance(exc, CatalogFailure):
        code = "SOURCE_RATE_LIMIT" if exc.status == "rate_limit" else "SOURCE_UNAVAILABLE"
    elif stage == "download" and isinstance(exc, SkillSourceError):
        # Exact fixed messages from the trusted validator; never publish arbitrary exceptions.
        code = {
            "Skill package has too many directories": "PACKAGE_FILE_LIMIT",
            "Skill package has too many files": "PACKAGE_FILE_LIMIT",
            "Skill package exceeds download limits": "PACKAGE_SIZE_LIMIT",
            "Skill file is too large or has unknown size": "PACKAGE_SIZE_LIMIT",
            "Skill contains a symlink, submodule, or unsupported file": "PACKAGE_UNSUPPORTED_ENTRY",
        }.get(str(exc), "SOURCE_REJECTED")
    elif isinstance(exc, FileExistsError):
        code = "DESTINATION_EXISTS"
    elif stage == "knowledge_index":
        code = "INDEX_WRITE_FAILED"
    elif stage in {"finalize_package", "verify_postcondition"}:
        code = "PACKAGE_FINALIZE_FAILED"
    return {"stage": stage, "code": code}


def public(evidence, state=None):
    evidence = evidence if isinstance(evidence, dict) else {}
    error = evidence.get("failure", {})
    error = error if isinstance(error, dict) else {}
    code = error.get("code")
    code = code if isinstance(code, str) else ""
    stage = evidence.get("stage")
    stage = stage if isinstance(stage, str) and stage in STAGES else "unavailable"
    failure_stage = error.get("stage")
    return {
        "stage": stage,
        "failure_stage": (failure_stage if isinstance(failure_stage, str)
                          and failure_stage in STAGES else ""),
        "code": code if code in MESSAGES else "",
        "message": MESSAGES.get(code, ""),
        "evidence_version": 1 if evidence.get("schema_version") == 1 else 0,
        "effect_status": ("verified" if state == "completed" else
                          "possibly_started" if evidence.get("effect_started") else
                          "not_started" if evidence else "unproven"),
        "retry_policy": ("not_applicable" if state in {"completed", "cancelled"} else
                         "retry_allowed" if state == "failed" and evidence
                         and not evidence.get("effect_started") else
                         "reconcile_first" if evidence else "manual_review"),
    }


def read_evidence(journal, rid):
    """Corrupt or unsupported evidence grants no recovery authority."""
    try:
        value = journal.evidence(rid, OWNER)
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or type(value.get("effect_started")) is not bool
                or value.get("stage") not in STAGES):
            return {}
        if ((value["stage"] == "download") == value["effect_started"]
                or "expected" in value and not value["effect_started"]):
            return {}
        record = SkillRecord.from_payload(value["record"])
        if (not record.canonical_identity
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", record.name)
                or len(record.name) > 80):
            return {}
        return value
    except (ValueError, TypeError, KeyError):
        return {}


def owner_state(cfg, name):
    """Read all libraries for this owner without initializing Knowledge or LanceDB."""
    path = cfg.data_dir / "knowledge.lance" / "fts.db"
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Unsafe Knowledge database")
    if not path.exists():
        return []
    if not path.is_file():
        raise ValueError("Unsafe Knowledge database")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT ac.library,ac.source,sv.checksum,sv.library,sv.owner,sv.source,sv.status "
            "FROM active_sources ac LEFT JOIN source_versions sv ON sv.version_id=ac.version_id "
            "WHERE ac.owner=? ORDER BY ac.library,ac.source LIMIT ?",
            (f"skill:{name}", MAX_SKILL_FILES + 1),
        ).fetchall()
        if len(rows) > MAX_SKILL_FILES:
            raise ValueError("Knowledge owner exceeds Skill limits")
        if any((row[3], row[4], row[5], row[6]) !=
               (row[0], f"skill:{name}", row[1], "active") for row in rows):
            raise ValueError("Knowledge owner metadata is inconsistent")
        return [list(row[:3]) for row in rows]


def _read_regular(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("Unsafe or oversized Skill file")
        content = stream.read(limit + 1)
        if (len(content) != before.st_size or len(content) > limit
                or file_signature(before) != file_signature(os.fstat(stream.fileno()))):
            raise ValueError("Skill file changed during inspection")
        return content


def _package_checksum(root):
    """Same content identity as the installer, with bounded reads of changed state."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Unsafe Skill version directory")
    queued = [(root, 0)]
    files, directories, total = {}, 0, 0
    while queued:
        directory, depth = queued.pop()
        directories += 1
        if directories > MAX_SKILL_FILES or depth > 12:
            raise ValueError("Skill directory limits exceeded")
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = entry.path[len(str(root)) + 1:]
                info = entry.stat(follow_symlinks=False)
                if len(relative) > 512:
                    raise ValueError("Skill path limit exceeded")
                if stat.S_ISDIR(info.st_mode):
                    queued.append((directory / entry.name, depth + 1))
                    if len(queued) + directories > MAX_SKILL_FILES:
                        raise ValueError("Skill directory limits exceeded")
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                    if len(files) >= MAX_SKILL_FILES or total > MAX_SKILL_PACKAGE_BYTES:
                        raise ValueError("Skill package limits exceeded")
                    files[relative] = hashlib.sha256(
                        _read_regular(directory / entry.name, MAX_SKILL_FILE_BYTES),
                    ).hexdigest()
                else:
                    raise ValueError("Unsupported Skill file")
    digest = hashlib.sha256()
    # The installer's Path ordering compares path components, not slash strings.
    for relative, checksum in sorted(files.items(), key=lambda item: tuple(item[0].split("/"))):
        digest.update(relative.encode() + b"\0" + checksum.encode() + b"\0")
    return digest.hexdigest()


def expected_package(installed):
    indexed = []
    for path, uri in zip(installed.text_files, installed.source_uris, strict=True):
        # Match KnowledgeIndexer's universal-newline and empty-document semantics.
        text = _read_regular(path, MAX_SKILL_FILE_BYTES).decode(errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text.strip():
            indexed.append([installed.library, uri, hashlib.sha256(text.encode()).hexdigest()])
    return {
        "version": installed.version_id,
        "checksum": _package_checksum(installed.current_dir),
        "index": sorted(indexed),
    }


def verify_complete(cfg, evidence):
    try:
        return _verify_complete(cfg, evidence)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _verify_complete(cfg, evidence):
    record = SkillRecord.from_payload(evidence["record"])
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", record.name) or len(record.name) > 80:
        return False
    root = cfg.skills_dir / record.name
    expected = evidence.get("expected")
    if (not expected or not root.is_dir() or root.is_symlink()
            or cfg.skills_dir.is_symlink()):
        return False
    if (root / "versions").is_symlink():
        return False
    manifest = json.loads(_read_regular(root / "manifest.json", 256_000))
    if (not isinstance(manifest, dict) or not isinstance(expected, dict)
            or not isinstance(expected.get("version"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", expected["version"])):
        return False
    version = root / "versions" / expected["version"]
    return (
        manifest.get("name") == record.name
        and manifest.get("library") == record.name
        and manifest.get("source_revision") == record.revision
        and manifest.get("source") == (
            f"https://github.com/{record.repository}/blob/{record.revision}/"
            f"{quote(record.skill_path, safe='/')}"
        )
        and manifest.get("state") == "active"
        and manifest.get("active_version") == expected["version"]
        and manifest.get("source_checksum") == expected["checksum"]
        and manifest.get("current_dir") == str(version)
        and _read_regular(root / "CURRENT", 128).decode().strip() == expected["version"]
        and _package_checksum(version) == expected["checksum"]
        and bool(expected["index"])
        and owner_state(cfg, record.name) == expected["index"]
    )


def install(cfg, request):
    from klaude_knowledge.skill_management import import_remote_skill

    from .operation_journal import OperationJournal

    journal = OperationJournal(cfg.data_dir / "operations.db")
    rid, fence = request["request_id"], request["fence"]
    journal.check_effect(rid, OWNER, fence)
    evidence = journal.evidence(rid, OWNER)
    if not evidence:
        evidence = initial(request["record"])
        journal.save_evidence(rid, OWNER, fence, evidence, expected={})
    if evidence["record"] != request["record"] or evidence["effect_started"]:
        raise OperationFenceLost("Skill attempt already reached its effect boundary")
    persisted = copy.deepcopy(evidence)

    def persist():
        nonlocal persisted
        journal.save_evidence(rid, OWNER, fence, evidence, expected=persisted,
                              require_running=True)
        persisted = copy.deepcopy(evidence)

    def save(stage, installed=None):
        journal.check_effect(rid, OWNER, fence)
        evidence["stage"] = stage
        if installed is not None:
            candidate = expected_package(installed)
            if "expected" in evidence and evidence["expected"] != candidate:
                raise ValueError("Skill content changed during installation")
            evidence["expected"] = candidate
        persist()
        if stage == "verify_postcondition" and not verify_complete(cfg, evidence):
            raise ValueError("Skill postconditions do not match")

    def gate():
        # This runs under the Skill mutation lock, before package or index writes.
        name = evidence["record"]["name"]
        root = cfg.skills_dir / name
        if root.exists() or root.is_symlink() or owner_state(cfg, name):
            raise FileExistsError("Skill destination or Knowledge owner is occupied")
        evidence["effect_started"] = True
        save("install_package")

    try:
        import_remote_skill(
            cfg, SkillRecord.from_payload(request["record"]), overwrite=False,
            before_effect=gate, checkpoint=save,
        )
        return {"ok": True}
    except OperationFenceLost:
        raise
    except Exception as exc:
        evidence["failure"] = failure(exc, evidence["stage"])
        persist()
        return {"rejected": not evidence["effect_started"], "failure": public(evidence)}


def reconcile(cfg, journal, rid, *, apply=False, expected_fingerprint=""):
    from klaude_knowledge.skill_management import skill_mutation_lock

    receipt = journal.status(rid, OWNER)
    if receipt is None or receipt.kind != "skill-store-install":
        raise ValueError("Choose a Skill Store installation")
    name = receipt.resource.removeprefix("skill:")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("Invalid Skill resource")
    with skill_mutation_lock(cfg, blocking=False):
        receipt = journal.status(rid, OWNER)
        evidence = read_evidence(journal, rid)
        if receipt.state != "unknown":
            return {"decision": "settled" if receipt.state in {"completed", "failed", "cancelled"}
                    else "active", "state": receipt.state, "request_id": rid,
                    "message": "Only unconfirmed installations need reconciliation."}
        owned = journal.fenced_operation(receipt.resource)
        if owned is None or owned.receipt.request_id != rid:
            raise OperationConflict("Skill resource ownership changed")
        root = cfg.skills_dir / name
        owner = owner_state(cfg, name)
        decision = "manual_review"
        if evidence and evidence.get("record", {}).get("name") == name:
            if (not evidence["effect_started"] and not root.exists()
                    and not root.is_symlink() and not owner):
                decision = "proven_no_effect"
            elif verify_complete(cfg, evidence):
                decision = "verified_complete"
        publication = None
        if decision == "verified_complete":
            publication = [hashlib.sha256(_read_regular(root / filename, limit)).hexdigest()
                           for filename, limit in (("manifest.json", 256_000), ("CURRENT", 128))]
        fingerprint = hashlib.sha256(json.dumps(
            [rid, receipt.fence, evidence, owner, decision, publication], sort_keys=True,
        ).encode()).hexdigest()
        messages = {
            "manual_review": "Evidence is insufficient or local state differs. "
                             "The Skill name remains reserved.",
            "proven_no_effect": "No installation effect started. "
                                "This receipt can be closed as failed.",
            "verified_complete": "The pinned package and Knowledge snapshot match. "
                                 "Installation can be confirmed.",
        }
        result = {**public(evidence), "request_id": rid, "decision": decision,
                  "fingerprint": fingerprint, "message": messages[decision], "state": receipt.state}
        if apply:
            if fingerprint != expected_fingerprint or decision == "manual_review":
                raise OperationConflict("Inspect the current Skill evidence before recovery")
            final = journal.reconcile(
                rid, OWNER, state="completed" if decision == "verified_complete" else "failed",
                evidence=f"skill-v1:{decision}:{fingerprint}",
            )
            result.update(public(evidence, final.state))
            result["message"] = ("Installation verified and confirmed."
                                 if final.state == "completed"
                                 else "No installation effect started. Attempt closed as failed.")
            result["state"] = final.state
        return result
