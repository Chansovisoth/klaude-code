"""Reviewed bundle effects, retained partial installs and uncertain recovery."""

import json
import os
import uuid
from types import SimpleNamespace

import pytest
from klaude_application import comfyui_install as app
from klaude_application.operation_journal import OperationConflict, OperationJournal
from klaude_core import comfyui_managed as managed
from klaude_core.comfyui_bundle import digest
from klaude_core.settings_store import atomic_write_private, read_settings


@pytest.fixture
def context(tmp_path, monkeypatch):
    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.data_dir.mkdir()
    weights = tmp_path / "weights"
    weights.mkdir()
    monkeypatch.setattr(app.image_model_store, "root", lambda: weights)
    journal = OperationJournal(cfg.data_dir / "operations.db")
    return cfg, journal


def admit(cfg, journal):
    fields, resource, summary = app.prepare(cfg, {"operation": "comfy-install"})
    rid = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=rid, owner_id=app.OWNER, kind="comfy-install", resource=resource, payload=fields
    )
    return {"operation": "comfy-install", "request_id": rid, "fence": receipt.fence, **fields}


def recover(cfg, journal, target):
    fields, resource, _ = app.prepare(cfg, {"operation": "comfy-recover", "target": target})
    rid = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=rid, owner_id=app.OWNER, kind="comfy-recover", resource=resource, payload=fields
    )
    journal.start(rid, app.OWNER, receipt.fence)
    try:
        result = app.run(
            cfg,
            {"operation": "comfy-recover", "request_id": rid, "fence": receipt.fence, **fields},
            lambda _: None,
        )
    except Exception:
        journal.finish(rid, app.OWNER, receipt.fence, state="failed", outcome="failed")
        raise
    journal.finish(rid, app.OWNER, receipt.fence, state="completed", outcome="ok")
    return result


def test_read_and_review_do_not_install_or_change_defaults(context):
    cfg, journal = context
    before = list(cfg.data_dir.iterdir())
    data = app.inventory(cfg)
    assert not data["installed"] and data["bundle"]["install_available"]
    fields, _, summary = app.prepare(cfg, {"operation": "comfy-install"})
    assert fields["definition"] == digest(managed.definition())
    assert "CreativeML OpenRAIL-M" in summary and "Does not load weights" in summary
    assert list(cfg.data_dir.iterdir()) == before and not cfg.config_dir.exists()
    with pytest.raises(ValueError):
        app.prepare(cfg, {"operation": "comfy-install", "source": "/arbitrary"})


def test_changed_install_snapshot_rejects_before_effect(context, monkeypatch):
    cfg, journal = context
    request = admit(cfg, journal)
    request["definition"] = "changed"
    monkeypatch.setattr(managed, "install", lambda *a, **kw: pytest.fail("Unexpected install"))
    assert app.run(cfg, request, lambda _: None) == {"rejected": True}


def test_lost_completion_ack_recovers_exact_install_without_replay(context, monkeypatch):
    cfg, journal = context
    request = admit(cfg, journal)
    calls = []

    def install(cfg, rid, source, fetch, check, progress, before_publish):
        calls.append(rid)
        with managed.install_lock(cfg):
            check()
            record = {"request_id": rid, "definition": digest(managed.definition())}
            before_publish(record)
            atomic_write_private(managed.root(cfg) / "installed.json", json.dumps(record))
            return record

    monkeypatch.setattr(managed, "install", install)
    monkeypatch.setattr(
        managed,
        "installed",
        lambda cfg, full=False: read_settings(managed.root(cfg) / "installed.json"),
    )
    assert app.run(cfg, request, lambda _: None)["ok"]
    journal.mark_unknown(request["request_id"], app.OWNER, request["fence"])
    assert recover(cfg, journal, request["request_id"])["ok"]
    assert journal.status(request["request_id"], app.OWNER).state == "completed"
    assert calls == [request["request_id"]]


def test_stopped_partial_install_releases_fence_only_after_check(context, monkeypatch):
    cfg, journal = context
    request = admit(cfg, journal)

    def interrupted(cfg, *args, **kwargs):
        with managed.install_lock(cfg):
            (managed.root(cfg) / "source.part").write_bytes(b"retained")
            raise KeyboardInterrupt()

    monkeypatch.setattr(managed, "install", interrupted)
    with pytest.raises(KeyboardInterrupt):
        app.run(cfg, request, lambda _: None)
    journal.mark_unknown(request["request_id"], app.OWNER, request["fence"])
    assert journal.resource_busy(app.resource(cfg))
    assert recover(cfg, journal, request["request_id"])["ok"]
    assert journal.status(request["request_id"], app.OWNER).state == "failed"
    assert (managed.root(cfg) / "source.part").read_bytes() == b"retained"


def test_active_installer_or_changed_inventory_cannot_be_reconciled(context):
    cfg, journal = context
    request = admit(cfg, journal)
    journal.save_evidence(
        request["request_id"],
        app.OWNER,
        request["fence"],
        {"definition": request["definition"], "before": {}},
    )
    journal.start(request["request_id"], app.OWNER, request["fence"])
    journal.mark_unknown(request["request_id"], app.OWNER, request["fence"])
    with managed.install_lock(cfg), pytest.raises(BlockingIOError):
        recover(cfg, journal, request["request_id"])
    atomic_write_private(managed.root(cfg) / "installed.json", '{"request_id":"someone-else"}')
    with pytest.raises(OperationConflict, match="differs"):
        recover(cfg, journal, request["request_id"])
    assert journal.resource_busy(app.resource(cfg))


def test_generation_lock_excludes_repair_and_output_rejects_links(context, tmp_path):
    cfg, _ = context
    with managed.install_lock(cfg, shared=True), pytest.raises(BlockingIOError):
        with managed.install_lock(cfg):
            pytest.fail("Repair acquired exclusive lock during generation")
    original = tmp_path / "original"
    original.write_bytes(b"retain me")
    linked = tmp_path / "linked"
    os.link(original, linked)
    with pytest.raises(ValueError, match="Unsafe"):
        with managed.owned_output(linked):
            pass
    assert original.read_bytes() == b"retain me"
    symlink = tmp_path / "symlink"
    symlink.symlink_to(original)
    with pytest.raises(ValueError):
        with managed.owned_output(symlink):
            pass


def test_pause_keeps_progress_and_blocks_publication_until_recovery(context, monkeypatch):
    from klaude_application.operation_journal import OperationFenceLost

    cfg, journal = context
    request = admit(cfg, journal)

    def interrupted(cfg, rid, source, fetch, check, progress, before_publish):
        with managed.install_lock(cfg):
            progress({"stage": "Downloading file", "completed": 128, "total": 1024})
            assert app.inventory(cfg)["pending"]["progress"]["completed"] == 128
            journal.request_cancel(rid, app.OWNER)
            # Even if a recent chunk check was throttled, publication always
            # rechecks the exact fence and rejects the cancelled owner.
            before_publish({})
            pytest.fail("Cancelled installer published a selectable bundle")

    monkeypatch.setattr(managed, "install", interrupted)
    with pytest.raises(OperationFenceLost):
        app.run(cfg, request, lambda _: None)
    journal.mark_unknown(request["request_id"], app.OWNER, request["fence"])
    assert not app.inventory(cfg)["installed"]
    assert app.inventory(cfg)["pending"]["progress"]["completed"] == 128
    assert recover(cfg, journal, request["request_id"])["ok"]
    assert not app.inventory(cfg)["pending"]


def test_interrupted_repair_does_not_advertise_old_bundle_as_installed(context):
    cfg, _ = context
    base = managed.root(cfg)
    base.mkdir()
    atomic_write_private(base / "installed.json", json.dumps({"request_id": "prior-success"}))
    atomic_write_private(base / "installing.json", json.dumps({"request_id": "partial-repair"}))
    with pytest.raises(ValueError, match="incomplete"):
        managed.installed(cfg)
    assert not app.inventory(cfg)["installed"]


def test_interrupted_read_only_recovery_can_be_checked_again(context):
    cfg, journal = context
    original = admit(cfg, journal)
    journal.save_evidence(
        original["request_id"],
        app.OWNER,
        original["fence"],
        {"definition": original["definition"], "before": {}},
    )
    journal.start(original["request_id"], app.OWNER, original["fence"])
    journal.mark_unknown(original["request_id"], app.OWNER, original["fence"])
    fields, resource, _ = app.prepare(
        cfg, {"operation": "comfy-recover", "target": original["request_id"]}
    )
    check_id = uuid.uuid4().hex
    checked = journal.admit(
        request_id=check_id,
        owner_id=app.OWNER,
        kind="comfy-recover",
        resource=resource,
        payload=fields,
    )
    journal.save_evidence(
        check_id, app.OWNER, checked.fence, {"version": 1, "target": original["request_id"]}
    )
    journal.start(check_id, app.OWNER, checked.fence)
    journal.mark_unknown(check_id, app.OWNER, checked.fence)
    assert recover(cfg, journal, original["request_id"])["ok"]
    assert journal.status(check_id, app.OWNER).state == "failed"
    assert journal.status(original["request_id"], app.OWNER).state == "failed"
