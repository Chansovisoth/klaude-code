"""Real filesystem/process tests for reviewed, confined setup reclamation."""

import io
import json
import os
import queue
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.dependency_panel import READ, WORK
from klaude_cli.serving_jobs import ServingJobs
from klaude_core.managed_serving import process_identity, publish
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_dependencies import build, builds, prepare
from klaude_core.model_setup_removal import inspect, remove
from klaude_core.settings_store import settings_lock, update_settings

from .test_managed_serving import lab as lab
from .test_managed_serving import launch, wait_for
from .test_model_dependencies import source as source
from .test_model_recipes import panel
from .test_model_recipes import wheels as wheels


@pytest.fixture
def setup(tmp_path):
    cfg = SimpleNamespace(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        models={"coder": "keep:latest"},
        ollama_url="http://localhost:11434",
    )
    cfg.config_dir.mkdir()
    identity = uuid.uuid4().hex
    folder = cfg.data_dir / "model-builds" / identity
    folder.parent.mkdir(mode=0o700, parents=True)
    folder.mkdir(mode=0o700, parents=True)
    source = tmp_path / "original"
    source.mkdir()
    (source / "user.txt").write_text("User source content")
    (folder / "files").mkdir()
    (folder / "files" / "engine").write_bytes(b"setup content" * 2000)
    record = {
        "id": identity,
        "source": str(source),
        "commit": "a" * 40,
        "pid": 99999999,
        "start": "0",
        "state": "failed",
    }
    (folder / "status.json").write_text(json.dumps(record))
    return cfg, identity, folder, source


def test_review_is_read_only_and_exact_remove_keeps_originals(setup):
    cfg, identity, folder, original = setup
    evidence, _ = inspect(cfg, identity)
    assert evidence["bytes"] >= 24000 and evidence["entries"] == 3
    assert not evidence["blockers"]
    assert not connection_registry(cfg).path.exists()
    assert not (cfg.data_dir / "chat-preferences.json").exists()
    result = remove(cfg, evidence, "", lambda _: None)
    assert result["status"] == "ok" and result["removed"] == identity
    assert not folder.exists() and builds(cfg.data_dir) == []
    assert (original / "user.txt").read_text() == "User source content"
    assert not connection_registry(cfg).path.exists()


@pytest.mark.parametrize("change", ["content", "new", "metadata", "replace"])
def test_stale_review_never_deletes_changed_files(setup, change):
    cfg, identity, folder, _ = setup
    evidence, _ = inspect(cfg, identity)
    if change == "content":
        (folder / "files/engine").write_text("new content")
    elif change == "new":
        (folder / "extra").write_text("new file")
    elif change == "metadata":
        record = json.loads((folder / "status.json").read_text())
        record["commit"] = "b" * 40
        (folder / "status.json").write_text(json.dumps(record))
    else:
        folder.rename(folder.with_name("previous"))
        folder.mkdir(mode=0o700)
        (folder / "status.json").write_text(
            (folder.with_name("previous") / "status.json").read_text()
        )
    with pytest.raises(ValueError, match="changed"):
        remove(cfg, evidence, "", lambda _: None)
    assert folder.exists() and (folder / "status.json").exists()


def test_nested_symlinks_are_unlinked_without_touching_targets(setup):
    cfg, identity, folder, original = setup
    (folder / "original-link").symlink_to(original, target_is_directory=True)
    (folder / "python").symlink_to(sys.executable)
    before = Path(sys.executable).stat()
    evidence, _ = inspect(cfg, identity)
    remove(cfg, evidence, "", lambda _: None)
    assert (original / "user.txt").read_text() == "User source content"
    assert Path(sys.executable).stat() == before


@pytest.mark.parametrize(
    "unsafe", ["root-link", "folder-link", "metadata-link", "special", "writable"]
)
def test_unsafe_directory_or_metadata_blocks_review(setup, unsafe):
    cfg, identity, folder, original = setup
    if unsafe == "root-link":
        root = folder.parent
        root.rename(root.with_name("relocated"))
        root.symlink_to(root.with_name("relocated"), target_is_directory=True)
    elif unsafe == "folder-link":
        folder.rename(folder.with_name("relocated"))
        folder.symlink_to(folder.with_name("relocated"), target_is_directory=True)
    elif unsafe == "metadata-link":
        (folder / "status.json").unlink()
        (folder / "status.json").symlink_to(original / "user.txt")
    elif unsafe == "special":
        os.mkfifo(folder / "fifo")
    else:
        folder.chmod(0o777)
    with pytest.raises((ValueError, OSError)):
        inspect(cfg, identity)
    assert (original / "user.txt").read_text() == "User source content"


def test_live_build_worker_and_external_process_are_protected(setup):
    cfg, identity, folder, _ = setup
    record = json.loads((folder / "status.json").read_text())
    record.update(state="building", pid=os.getpid(), start=process_identity(os.getpid())["start"])
    (folder / "status.json").write_text(json.dumps(record))
    assert "Build/install worker is still running" in inspect(cfg, identity)[0]["blockers"]
    record["state"] = "failed"
    (folder / "status.json").write_text(json.dumps(record))
    process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], cwd=folder)
    try:
        evidence, _ = inspect(cfg, identity)
        assert any(str(process.pid) in reason for reason in evidence["blockers"])
        with pytest.raises(ValueError, match="Cannot remove"):
            remove(cfg, evidence, "", lambda _: None)
    finally:
        process.terminate()
        process.wait(timeout=3)


def record_server(cfg, folder, *, live=False, weights=False):
    endpoint = ModelConnection(
        "serve-qa", "QA", "openai_compatible", "http://127.0.0.1:29999/v1", enabled=False
    )
    connection_registry(cfg).migrate(cfg)
    connection_registry(cfg).add(endpoint)
    record = {
        "spec": {
            "executable": str(folder / "files/engine"),
            "model": str(folder / "weights") if weights else "/other/model.gguf",
        },
        "endpoint": asdict(endpoint),
        "state": "ready" if live else "stopped",
        "helper_pid": os.getpid(),
        "helper_start": process_identity(os.getpid())["start"],
    }
    publish(cfg.data_dir, uuid.uuid4().hex, record)
    return endpoint


@pytest.mark.parametrize(
    "role",
    ["current", "chat", "utility", "research", "fallback", "alias", "enabled", "live", "weights"],
)
def test_selected_roles_active_servers_and_model_paths_prevent_removal(setup, role):
    cfg, identity, folder, _ = setup
    endpoint = record_server(cfg, folder, live=role == "live", weights=role == "weights")
    ref = "openai_compatible@serve-qa/model"
    current = ref if role == "current" else ""
    defaults = {"chat": "ollama/keep:latest"}
    if role in {"chat", "utility", "research"}:
        defaults[role] = ref
    elif role == "fallback":
        defaults["fallbacks"] = [ref]
    elif role == "alias":
        connection_registry(cfg).add(replace(endpoint, id="alias"))
        defaults["chat"] = "openai_compatible@alias/model"
    elif role == "enabled":
        update_settings(
            connection_registry(cfg).path, {("connections", endpoint.id, "enabled"): True}
        )
    (cfg.data_dir / "chat-preferences.json").write_text(json.dumps({"ai_defaults": defaults}))
    evidence, _ = inspect(cfg, identity, current)
    assert evidence["blockers"]
    with pytest.raises(ValueError, match="Cannot remove"):
        remove(cfg, evidence, current, lambda _: None)
    assert (folder / "files/engine").exists()


def test_new_selection_after_review_is_rechecked(setup):
    cfg, identity, folder, _ = setup
    record_server(cfg, folder)
    evidence, _ = inspect(cfg, identity)
    assert not evidence["blockers"]
    (cfg.data_dir / "chat-preferences.json").write_text(
        json.dumps({"ai_defaults": {"chat": "openai_compatible@serve-qa/model"}})
    )
    with pytest.raises(ValueError, match="Default Chat"):
        remove(cfg, evidence, "", lambda _: None)
    assert (folder / "files/engine").exists()


def test_partial_failure_keeps_recoverable_record_and_never_offers_servable_engine(
    setup, monkeypatch
):
    cfg, identity, folder, _ = setup
    evidence, _ = inspect(cfg, identity)
    unlink = os.unlink

    def fail(name, **values):
        if name == "engine":
            raise PermissionError("fixture deletion failure")
        unlink(name, **values)

    monkeypatch.setattr("klaude_core.model_setup_removal.os.unlink", fail)
    with pytest.raises(PermissionError):
        remove(cfg, evidence, "", lambda _: None)
    assert builds(cfg.data_dir)[0]["state"] == "removing"
    monkeypatch.setattr("klaude_core.model_setup_removal.os.unlink", unlink)
    fresh, _ = inspect(cfg, identity)
    remove(cfg, fresh, "", lambda _: None)
    assert not folder.exists()


def test_acceptance_serializes_with_build_and_server_acceptance(setup):
    cfg, identity, folder, _ = setup
    evidence, _ = inspect(cfg, identity)
    with settings_lock(folder.parent / "inventory.json"):
        with pytest.raises(OSError, match="busy"):
            remove(cfg, evidence, "", lambda _: None)
    assert (folder / "files/engine").exists()


@pytest.mark.parametrize("fixture_name,profile", [("source", "cpu"), ("wheels", "vllm_cuda")])
def test_real_cpu_build_and_vllm_environment_can_be_reclaimed(
    request, fixture_name, profile, tmp_path
):
    original, data = request.getfixturevalue(fixture_name)
    identity = uuid.uuid4().hex
    cfg = SimpleNamespace(
        config_dir=tmp_path / profile,
        data_dir=data,
        models={},
        ollama_url="http://localhost:11434",
    )
    cfg.config_dir.mkdir()
    build(data, identity, prepare(str(original), data, profile=profile), lambda _: None)
    evidence, _ = inspect(cfg, identity)
    assert not evidence["blockers"]
    remove(cfg, evidence, "", lambda _: None)
    assert builds(data) == [] and original.is_dir()


def test_tui_review_focuses_back_and_removal_keeps_accepted_target(tmp_path):
    instance, shown, _, queued = panel(tmp_path)
    instance.read = ("review", instance.manager.scope, instance.revision, "prepare_remove")
    evidence = {"id": "accepted", "blockers": [], "bytes": 1024}
    instance.accept(READ, "review", {"evidence": evidence}, "")
    assert shown[-1] == (("remove-review", "back"), {"fresh": True})
    instance.task = {
        "worker": "work",
        "id": "accepted",
        "scope": instance.manager.scope,
        "revision": instance.revision,
        "operation": "remove",
    }
    instance.result = {"id": "other", "state": "ready"}
    instance.items = [{"id": "accepted"}, {"id": "other"}]
    instance.accept(WORK, "work", {"status": "ok", "removed": "accepted"}, "")
    assert instance.result == {"id": "accepted", "state": "removed", "operation": "remove"}
    assert instance.items == [{"id": "other"}] and queued == [True]


def test_tui_blocked_review_and_cancel_never_claim_rollback(tmp_path):
    instance, _, _, queued = panel(tmp_path)
    instance.removal = {"id": "accepted", "blockers": ["active server"]}
    instance.view = "remove-review"
    assert not next(r for r in instance.page().rows if r.id == "remove").enabled
    instance.task = {
        "worker": "work",
        "id": "accepted",
        "scope": instance.manager.scope,
        "revision": instance.revision,
        "operation": "remove",
    }
    instance.stopped("work")
    assert "some files may have been removed" in instance.feedback[0] and queued == [True]


def test_new_files_during_removal_are_not_swept_up(setup):
    cfg, identity, folder, _ = setup
    evidence, _ = inspect(cfg, identity)

    def change(_):
        (folder / "unexpected").write_text("new user file")

    with pytest.raises(ValueError, match="changed during removal"):
        remove(cfg, evidence, "", change)
    assert (folder / "unexpected").read_text() == "new user file"
    assert builds(cfg.data_dir)[0]["state"] == "removing"


def test_cancelled_owned_removal_reaps_and_allows_fresh_review(setup):
    cfg, identity, folder, original = setup
    for index in range(12_000):
        (folder / "files" / str(index)).touch()
    evidence, _ = inspect(cfg, identity)
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *value: events.put(value))
    try:
        worker = jobs.submit(
            "remove",
            {
                "kind": "model_dependencies",
                "operation": "remove",
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "evidence": evidence,
            },
            timeout=30,
            notify_cancel=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            kind, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if kind == "background_progress":
                jobs.cancel("remove")
                break
            if kind == "background_result":
                pytest.fail("Removal ended before cancellation: " + str(payload))
        while time.monotonic() < deadline:
            kind, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if kind == "background_stopped":
                assert payload == ("remove", worker)
                break
        else:
            pytest.fail("Removal cleanup was not acknowledged")
        assert folder.exists() and (folder / "status.json").is_file()
        fresh, _ = inspect(cfg, identity)
        assert not fresh["blockers"]
        remove(cfg, fresh, "", lambda _: None)
        assert not folder.exists() and (original / "user.txt").is_file()
    finally:
        jobs.close(wait=True)


def test_protected_os_processes_do_not_hide_accessible_engine_arguments(setup, monkeypatch):
    cfg, identity, folder, _ = setup
    process = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)", str(folder / "files/engine")]
    )
    readlink = os.readlink

    def restricted(path, *args, **kwargs):
        if str(path).startswith(f"/proc/{process.pid}/"):
            raise PermissionError("protected QA process")
        return readlink(path, *args, **kwargs)

    try:
        monkeypatch.setattr("klaude_core.model_setup_removal.os.readlink", restricted)
        evidence, _ = inspect(cfg, identity)
        assert evidence["warnings"]
        assert any(str(process.pid) in reason for reason in evidence["blockers"])
    finally:
        process.terminate()
        process.wait(timeout=3)


def test_partially_removed_setup_cannot_start_an_engine(lab):
    cfg, spec = lab
    identity = uuid.uuid4().hex
    folder = cfg.data_dir / "model-builds" / identity
    folder.mkdir(parents=True)
    target = folder / "llama-server"
    shutil.copy2(spec.executable, target)
    (folder / "status.json").write_text(json.dumps({"state": "removing"}))
    events = queue.Queue()
    jobs = ServingJobs(lambda *value: events.put(value))
    try:
        launch(cfg, replace(spec, executable=str(target)), jobs)
        event = wait_for(events, "failed")
        assert "removal is incomplete" in event["message"]
        assert not connection_registry(cfg).path.exists()
    finally:
        jobs.close(wait=True)


def test_warning_wording_is_not_a_filesystem_revision(setup):
    cfg, identity, folder, _ = setup
    evidence, _ = inspect(cfg, identity)
    evidence["warnings"] = ["Earlier client wording/count for partial process visibility"]
    remove(cfg, evidence, "", lambda _: None)
    assert not folder.exists()


def test_new_visibility_limit_requires_a_fresh_review(setup, monkeypatch):
    cfg, identity, folder, _ = setup
    monkeypatch.setattr("klaude_core.model_setup_removal.process_users", lambda *args: ([], []))
    evidence, _ = inspect(cfg, identity)
    monkeypatch.setattr(
        "klaude_core.model_setup_removal.process_users", lambda *args: ([], ["Now partial"])
    )
    with pytest.raises(ValueError, match="changed since review"):
        remove(cfg, evidence, "", lambda _: None)
    assert (folder / "files/engine").exists()


def test_same_filesystem_bind_mount_is_rejected_before_removal(setup, monkeypatch):
    cfg, identity, folder, _ = setup
    # A mount target can include spaces, and retain the same st_dev as its parent.
    nested = folder / "bound files"
    nested.mkdir()
    target = str(nested).replace(" ", r"\040")
    raw = f"100 50 8:1 /original {target} rw - ext4 /dev/example rw\n".encode()
    opening = Path.open

    def mountinfo(path, *args, **kwargs):
        if str(path) == "/proc/self/mountinfo":
            return io.BytesIO(raw)
        return opening(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", mountinfo)
    with pytest.raises(ValueError, match="contains a mount"):
        inspect(cfg, identity)
    assert (folder / "files/engine").exists()
