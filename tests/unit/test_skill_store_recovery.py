"""Real package/SQLite evidence and crash-boundary recovery without model work."""

import json
import os
import sqlite3
import subprocess
import sys
import uuid

import pytest
from klaude_application import skill_store_operations as skills
from klaude_application.operation_journal import (
    OperationConflict,
    OperationFenceLost,
    OperationJournal,
)
from klaude_core.config import Config
from klaude_core.skill_catalog import CatalogFailure, CatalogStatus, SkillRecord, SkillSourceError
from klaude_knowledge.skill_management import skill_mutation_lock
from klaude_knowledge.skills import finalize_skill_package, install_skill_package


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config()
    journal = OperationJournal(cfg.data_dir / "operations.db")
    record = SkillRecord("skillsmp", "fixture", "testing", repository="example/repo",
                         source_url="https://github.com/example/repo/tree/main/skills/testing",
                         skill_path="skills/testing/SKILL.md", revision="a" * 40)
    rid = uuid.uuid4().hex
    receipt = journal.admit(request_id=rid, owner_id=skills.OWNER, kind="skill-store-install",
                            resource="skill:testing", payload=record.payload())
    journal.save_evidence(rid, skills.OWNER, receipt.fence, skills.initial(record.payload()))
    journal.start(rid, skills.OWNER, receipt.fence)
    return cfg, journal, {"request_id": rid, "fence": receipt.fence, "record": record.payload()}


def index(cfg, rows):
    root = cfg.data_dir / "knowledge.lance"
    root.mkdir(exist_ok=True)
    with sqlite3.connect(root / "fts.db") as db:
        db.execute("CREATE TABLE IF NOT EXISTS active_sources "
                   "(library,owner,source,version_id)")
        db.execute("CREATE TABLE IF NOT EXISTS source_versions "
                   "(version_id,checksum,library,owner,source,status)")
        db.execute("DELETE FROM active_sources")
        db.execute("DELETE FROM source_versions")
        for i, (library, source, checksum) in enumerate(rows):
            db.execute("INSERT INTO active_sources VALUES(?,?,?,?)",
                       (library, "skill:testing", source, str(i)))
            db.execute("INSERT INTO source_versions VALUES(?,?,?,?,?,?)",
                       (str(i), checksum, library, "skill:testing", source, "active"))


def publish(attempt, tmp_path, *, finalize=True):
    cfg, journal, request = attempt
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Testing\nUse focused tests.")
    record = request["record"]
    installed = install_skill_package(
        cfg, source, name="testing", overwrite=False, source_revision=record["revision"],
        source_url=f"https://github.com/example/repo/blob/{record['revision']}/skills/testing/SKILL.md",
    )
    evidence = skills.initial(record)
    evidence.update(effect_started=True, stage="verify_postcondition",
                    expected=skills.expected_package(installed))
    journal.save_evidence(request["request_id"], skills.OWNER, request["fence"], evidence)
    index(cfg, evidence["expected"]["index"])
    if finalize:
        finalize_skill_package(installed)
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    return installed, evidence


def test_lost_acknowledgement_reconciles_and_is_idempotent(attempt, tmp_path):
    cfg, journal, request = attempt
    publish(attempt, tmp_path)
    inspected = skills.reconcile(cfg, journal, request["request_id"])
    assert inspected["decision"] == "verified_complete"
    result = skills.reconcile(cfg, journal, request["request_id"], apply=True,
                              expected_fingerprint=inspected["fingerprint"])
    assert result["state"] == "completed"
    assert not journal.resource_busy("skill:testing")
    assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "settled"


@pytest.mark.parametrize("change", ["package", "index", "pending", "destination"])
def test_changed_or_partial_state_remains_fenced(attempt, tmp_path, change):
    cfg, journal, request = attempt
    installed, evidence = publish(attempt, tmp_path, finalize=change != "pending")
    inspected = skills.reconcile(cfg, journal, request["request_id"])
    if change == "package":
        (installed.current_dir / "SKILL.md").write_text("Changed")
    elif change == "index":
        index(cfg, [["testing", "skill://testing/SKILL.md", "changed"]])
    elif change == "destination":
        manifest = json.loads(installed.manifest_path.read_text())
        manifest["source_revision"] = "b" * 40
        installed.manifest_path.write_text(json.dumps(manifest))
    assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "manual_review"
    with pytest.raises(OperationConflict):
        skills.reconcile(cfg, journal, request["request_id"], apply=True,
                         expected_fingerprint=inspected["fingerprint"])
    assert journal.resource_busy("skill:testing")


def test_proven_no_effect_revokes_suspended_worker(attempt):
    cfg, journal, request = attempt
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    inspected = skills.reconcile(cfg, journal, request["request_id"])
    assert inspected["decision"] == "proven_no_effect"
    skills.reconcile(cfg, journal, request["request_id"], apply=True,
                     expected_fingerprint=inspected["fingerprint"])
    with pytest.raises(OperationFenceLost):
        skills.install(cfg, request)


def test_legacy_absence_does_not_prove_failure(attempt):
    cfg, journal, request = attempt
    # Represent an older receipt with no effect protocol.
    with journal._connect() as db:
        db.execute("DELETE FROM operation_evidence")
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "manual_review"
    assert journal.resource_busy("skill:testing")


@pytest.mark.parametrize("exc,code", [
    (CatalogFailure(CatalogStatus.RATE_LIMIT), "SOURCE_RATE_LIMIT"),
    (SkillSourceError("Skill contains a symlink, submodule, or unsupported file"),
     "PACKAGE_UNSUPPORTED_ENTRY"),
    (RuntimeError("Authorization: Bearer private-secret"), "UNEXPECTED_FAILURE"),
    (ValueError("Authorization: Bearer private-secret"), "UNEXPECTED_FAILURE"),
])
def test_download_failure_is_safe_durable_and_retryable(attempt, monkeypatch, exc, code):
    cfg, journal, request = attempt

    def download(*args, **kwargs):
        raise exc

    monkeypatch.setattr("klaude_knowledge.skill_management.download_resolved_skill", download)
    result = skills.install(cfg, request)
    assert result["rejected"]
    assert result["failure"]["code"] == code
    evidence = journal.evidence(request["request_id"], skills.OWNER)
    assert evidence["effect_started"] is False
    assert "private-secret" not in json.dumps(evidence)
    assert not (cfg.skills_dir / "testing").exists()


def test_effect_intent_survives_index_failure(attempt, monkeypatch):
    cfg, journal, request = attempt

    def interrupted(cfg, record, *, before_effect, checkpoint, **kwargs):
        with skill_mutation_lock(cfg):
            before_effect()
            checkpoint("knowledge_index")
            raise RuntimeError("private-secret")

    monkeypatch.setattr("klaude_knowledge.skill_management.import_remote_skill", interrupted)
    result = skills.install(cfg, request)
    assert not result["rejected"]
    assert result["failure"]["code"] == "INDEX_WRITE_FAILED"
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "manual_review"


def test_cancelled_gate_never_publishes(attempt, monkeypatch):
    cfg, journal, request = attempt

    def cancelled(cfg, record, *, before_effect, **kwargs):
        journal.request_cancel(request["request_id"], skills.OWNER)
        before_effect()

    monkeypatch.setattr("klaude_knowledge.skill_management.import_remote_skill", cancelled)
    with pytest.raises(OperationFenceLost):
        skills.install(cfg, request)
    assert not journal.evidence(request["request_id"], skills.OWNER)["effect_started"]


def test_evidence_cas_rejects_stale_checkpoint(attempt):
    _, journal, request = attempt
    old = journal.evidence(request["request_id"], skills.OWNER)
    journal.save_evidence(request["request_id"], skills.OWNER, request["fence"],
                          {**old, "effect_started": True}, expected=old)
    with pytest.raises(OperationFenceLost):
        journal.save_evidence(request["request_id"], skills.OWNER, request["fence"],
                              old, expected=old)


def test_checkpoint_rechecks_cancellation_in_its_own_transaction(attempt):
    _, journal, request = attempt
    journal.check_effect(request["request_id"], skills.OWNER, request["fence"])
    journal.request_cancel(request["request_id"], skills.OWNER)
    with pytest.raises(OperationFenceLost):
        journal.save_evidence(request["request_id"], skills.OWNER, request["fence"],
                              {"effect_started": True}, require_running=True)
    assert not journal.evidence(request["request_id"], skills.OWNER)["effect_started"]


@pytest.mark.parametrize("stage,decision", [
    ("before_gate", "proven_no_effect"),
    ("install_package", "manual_review"),
    ("knowledge_index", "manual_review"),
    ("finalize_package", "manual_review"),
    ("verify_postcondition", "verified_complete"),
    ("acknowledgement", "verified_complete"),
])
def test_process_death_at_real_installer_boundaries(attempt, stage, decision):
    cfg, journal, request = attempt
    # os._exit bypasses Python finally blocks, including tempfile and lock cleanup.
    script = r'''
import hashlib, json, os, sys
from klaude_core.config import Config
from klaude_application import skill_store_operations as skills
from klaude_knowledge import skill_management as sm
from tests.unit.test_skill_store_recovery import index
cfg = Config()
request, stage = json.loads(sys.argv[1]), sys.argv[2]
sm.download_resolved_skill = lambda *a, **k: {"SKILL.md": b"# Testing\nFocused tests."}
real = sm.import_remote_skill
class Knowledge:
    def replace_owner_snapshot_atomic(self, library, owner, documents):
        index(cfg, [[library, d.source, hashlib.sha256(d.text.encode()).hexdigest()]
                    for d in documents])
        return len(documents)
def imported(cfg, record, *, before_effect, checkpoint, **kwargs):
    def gate():
        if stage == "before_gate": os._exit(79)
        before_effect()
        if stage == "install_package": os._exit(79)
    def check(current, installed=None):
        checkpoint(current, installed)
        if stage == current: os._exit(79)
    return real(cfg, record, before_effect=gate, checkpoint=check,
                knowledge=Knowledge(), **kwargs)
sm.import_remote_skill = imported
result = skills.install(cfg, request)
if result != {"ok": True}:
    print(json.dumps(result), flush=True)
    sys.exit(1)
os._exit(79)
'''
    completed = subprocess.run(
        [sys.executable, "-c", script, json.dumps(request), stage],
        env={**os.environ, "KLAUDE_DATA_DIR": str(cfg.data_dir),
             "KLAUDE_CONFIG_DIR": str(cfg.config_dir)},
        capture_output=True, timeout=15,
    )
    assert completed.returncode == 79, (completed.stdout, completed.stderr)
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    result = skills.reconcile(cfg, journal, request["request_id"])
    assert result["decision"] == decision
    assert result["message"]


@pytest.mark.parametrize("command", [["inspect"], ["reconcile", "--dry-run"]])
def test_cli_legacy_inspection_returns_json_and_keeps_fence(attempt, command):
    from klaude_cli.skill_store import app
    from typer.testing import CliRunner

    _, journal, request = attempt
    with journal._connect() as db:
        db.execute("DELETE FROM operation_evidence")
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    result = CliRunner().invoke(app, [*command, request["request_id"], "--json"])
    assert result.exit_code == 2, result.output
    assert json.loads(result.output)["decision"] == "manual_review"
    assert journal.resource_busy("skill:testing")


@pytest.mark.parametrize("success,rejected", [(True, False), (False, True)])
def test_worker_booleans_cannot_claim_an_unproven_outcome(attempt, tmp_path, success, rejected):
    from klaude_application.library_management import LibraryManagement, ManagementReview

    cfg, journal, request = attempt
    service = LibraryManagement(cfg, tmp_path)
    service._journal = journal
    service._active[request["request_id"]] = (
        request["fence"],
        ManagementReview("review", "owner", "skill-store-install", "skill:testing", {}),
    )
    service._finish(request["request_id"], success, rejected=rejected)
    assert journal.status(request["request_id"], skills.OWNER).state == "unknown"
    service.close()


def test_recovery_refuses_a_worker_holding_the_mutation_lock(attempt):
    cfg, journal, request = attempt
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    with skill_mutation_lock(cfg), pytest.raises(BlockingIOError):
        skills.reconcile(cfg, journal, request["request_id"])
    assert journal.resource_busy("skill:testing")


def test_resuming_old_worker_cannot_publish_after_recovery(attempt):
    cfg, journal, request = attempt
    script = r'''
import json, sys
from klaude_core.config import Config
from klaude_application import skill_store_operations as skills
from klaude_application.operation_journal import OperationFenceLost
from klaude_knowledge import skill_management as sm
def download(*args, **kwargs):
    print("ready", flush=True)
    input()
    return {"SKILL.md": b"# Testing"}
sm.download_resolved_skill = download
try:
    skills.install(Config(), json.loads(sys.argv[1]))
except OperationFenceLost:
    sys.exit(0)
sys.exit(1)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script, json.dumps(request)],
        env={**os.environ, "KLAUDE_DATA_DIR": str(cfg.data_dir),
             "KLAUDE_CONFIG_DIR": str(cfg.config_dir)},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        import selectors

        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "Worker did not reach download"
        assert process.stdout.readline().strip() == "ready"
        journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
        inspected = skills.reconcile(cfg, journal, request["request_id"])
        skills.reconcile(cfg, journal, request["request_id"], apply=True,
                         expected_fingerprint=inspected["fingerprint"])
        output, error = process.communicate("resume\n", timeout=15)
        assert process.returncode == 0, (output, error)
        assert not (cfg.skills_dir / "testing").exists()
        assert skills.owner_state(cfg, "testing") == []
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def test_orphaned_knowledge_is_never_overwritten(attempt, monkeypatch):
    cfg, journal, request = attempt
    original = [["testing", "skill://testing/old.md", "old-checksum"]]
    index(cfg, original)
    monkeypatch.setattr("klaude_knowledge.skill_management.download_resolved_skill",
                        lambda *a, **k: {"SKILL.md": b"# Testing"})
    result = skills.install(cfg, request)
    assert result["rejected"] and result["failure"]["code"] == "DESTINATION_EXISTS"
    assert skills.owner_state(cfg, "testing") == original
    assert not journal.evidence(request["request_id"], skills.OWNER)["effect_started"]


def test_failure_receipt_survives_service_reconstruction(attempt, tmp_path, monkeypatch):
    from klaude_application.library_management import LibraryManagement, ManagementReview

    cfg, journal, request = attempt

    def unavailable(*args, **kwargs):
        raise CatalogFailure(CatalogStatus.RATE_LIMIT)

    monkeypatch.setattr("klaude_knowledge.skill_management.download_resolved_skill", unavailable)
    result = skills.install(cfg, request)
    service = LibraryManagement(cfg, tmp_path)
    service._journal = journal
    service._active[request["request_id"]] = (
        request["fence"],
        ManagementReview("review", "owner", "skill-store-install", "skill:testing", {}),
    )
    service._event("background_result", (request["request_id"], "job-id", result, ""))
    service.close()
    restored = LibraryManagement(cfg, tmp_path)
    try:
        receipt = restored.status(request["request_id"])
        assert receipt["state"] == "failed" and receipt["code"] == "SOURCE_RATE_LIMIT"
        assert receipt["retry_policy"] == "retry_allowed"
        assert not restored.journal.resource_busy("skill:testing")
    finally:
        restored.close()


def test_actual_indexer_accepts_empty_support_files_and_normalizes_newlines(attempt, monkeypatch):
    from types import SimpleNamespace

    from klaude_knowledge.hybrid import Knowledge
    from klaude_knowledge.indexing import KnowledgeIndexer
    from klaude_knowledge.store import KnowledgeStore

    cfg, journal, request = attempt
    cfg.models["embed"] = "fixture"
    knowledge = object.__new__(Knowledge)
    knowledge.store = KnowledgeStore(cfg.knowledge_dir)
    knowledge.indexer = KnowledgeIndexer(
        cfg, knowledge.store,
        SimpleNamespace(embed=lambda model, texts: [[0.1] * 8 for _ in texts]),
    )
    monkeypatch.setattr("klaude_knowledge.hybrid.Knowledge", lambda cfg: knowledge)
    monkeypatch.setattr("klaude_knowledge.skill_management.download_resolved_skill",
                        lambda *a, **k: {
        "SKILL.md": b"# Testing\r\nUse focused tests.\rKeep checks bounded.",
        "references/empty.md": b"",
        "references/whitespace.md": b" \r\n\t",
        "references.md": b"Supporting reference index.",
    })
    assert skills.install(cfg, request) == {"ok": True}
    evidence = journal.evidence(request["request_id"], skills.OWNER)
    assert len(evidence["expected"]["index"]) == 2
    assert skills.verify_complete(cfg, evidence)
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "verified_complete"


@pytest.mark.parametrize("change", ["missing", "staged", "wrong_owner"])
def test_inconsistent_owner_metadata_never_looks_absent(attempt, change):
    cfg, journal, request = attempt
    index(cfg, [["testing", "skill://testing/SKILL.md", "checksum"]])
    with sqlite3.connect(cfg.knowledge_dir / "fts.db") as db:
        if change == "missing":
            db.execute("DELETE FROM source_versions")
        elif change == "staged":
            db.execute("UPDATE source_versions SET status='staging'")
        else:
            db.execute("UPDATE source_versions SET owner='skill:other'")
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    with pytest.raises(ValueError, match="inconsistent"):
        skills.reconcile(cfg, journal, request["request_id"])
    assert journal.resource_busy("skill:testing")


@pytest.mark.parametrize("change", ["oversized", "fifo", "symlink", "bad_manifest", "bad_version"])
def test_unsafe_local_files_cannot_confirm_completion(attempt, tmp_path, change):
    cfg, journal, request = attempt
    installed, evidence = publish(attempt, tmp_path)
    if change == "oversized":
        with (installed.current_dir / "SKILL.md").open("wb") as stream:
            stream.truncate(2_000_001)
    elif change in {"fifo", "symlink"}:
        target = installed.current_dir / "SKILL.md"
        target.unlink()
        if change == "fifo":
            os.mkfifo(target)
        else:
            target.symlink_to(tmp_path / "source" / "SKILL.md")
    elif change == "bad_manifest":
        installed.manifest_path.write_text("[]")
    else:
        evidence["expected"]["version"] = "../../source"
    assert not skills.verify_complete(cfg, evidence)
    if change != "bad_version":
        assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "manual_review"
    assert journal.resource_busy("skill:testing")


@pytest.mark.parametrize("content", ["{broken", "[]", '{"schema_version": 1}',
                                    '{"schema_version": 1, "stage": ["secret"]}'])
def test_corrupt_evidence_is_not_recovery_authority_or_public_text(attempt, content):
    from klaude_application.library_management import LibraryManagement

    cfg, journal, request = attempt
    with journal._connect() as db:
        db.execute("UPDATE operation_evidence SET payload=?", (content,))
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    assert skills.reconcile(cfg, journal, request["request_id"])["decision"] == "manual_review"
    service = LibraryManagement(cfg, cfg.data_dir)
    try:
        status = service.status(request["request_id"])
        assert status["stage"] == "unavailable" and status["effect_status"] == "unproven"
        assert "secret" not in json.dumps(status)
    finally:
        service.close()


@pytest.mark.parametrize("answer,exit_code,state", [("y\n", 0, "failed"), ("n\n", 1, "unknown"),
                                                 ("", 1, "unknown")])
def test_cli_json_apply_keeps_prompt_off_stdout_and_decline_preserves_fence(
    attempt, answer, exit_code, state,
):
    from klaude_cli.skill_store import app
    from typer.testing import CliRunner

    _, journal, request = attempt
    journal.mark_unknown(request["request_id"], skills.OWNER, request["fence"])
    result = CliRunner().invoke(app, ["reconcile", request["request_id"], "--apply", "--json"],
                                input=answer)
    assert result.exit_code == exit_code, result.output
    assert json.loads(result.stdout)["state"] == state
    assert journal.resource_busy("skill:testing") == (state == "unknown")


def test_cli_json_storage_initialization_failure_is_sanitized(monkeypatch):
    from klaude_cli.skill_store import app
    from typer.testing import CliRunner

    def unavailable(*args, **kwargs):
        raise OSError("private filesystem details")

    monkeypatch.setattr("klaude_application.library_management.LibraryManagement", unavailable)
    result = CliRunner().invoke(app, ["inspect", "a" * 32, "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"] == "recovery_unavailable"
    assert "private filesystem" not in result.output


def test_manifest_metadata_change_rejects_a_stale_inspection(attempt, tmp_path):
    cfg, journal, request = attempt
    installed, _ = publish(attempt, tmp_path)
    inspected = skills.reconcile(cfg, journal, request["request_id"])
    manifest = json.loads(installed.manifest_path.read_text())
    manifest["checked_at"] = "changed since inspection"
    installed.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(OperationConflict):
        skills.reconcile(cfg, journal, request["request_id"], apply=True,
                         expected_fingerprint=inspected["fingerprint"])
    assert journal.resource_busy("skill:testing")
