"""External observations are bounded, truthful and cannot own or replay mutations."""

import json
import os
import time
from types import SimpleNamespace

import pytest
from klaude_application import model_activity
from klaude_application.model_activity import ModelActivity
from klaude_core.model_connections import legacy_connections
from klaude_core.ollama_activity import process_identity, track_transfer

from .test_ollama_manager import cfg as cfg


@pytest.fixture(autouse=True)
def isolated_image_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("KLAUDE_IMAGE_MODEL_DIR", str(tmp_path / "image-models"))


def test_image_partial_activity_is_read_only_and_expires(cfg, monkeypatch, tmp_path):
    root = tmp_path / "image-models"
    root.mkdir()
    monkeypatch.setattr(model_activity, "_local_store", lambda: None)
    clock = [time.time()]
    monkeypatch.setattr(model_activity.time, "time", lambda: clock[0])
    partial = root / "example.safetensors.part"
    with partial.open("wb") as stream:
        stream.truncate(10**10)
    os.utime(partial, (clock[0], clock[0]))
    (root / "ignored.txt.part").write_text("private")
    (root / "link.gguf.part").symlink_to(partial)
    observer = ModelActivity()
    result = observer.read(cfg, [])
    assert len(result["observed"]) == 1
    row = result["observed"][0]
    assert row["source"] == "sdcpp" and row["model"] == "example.safetensors"
    assert row["state"] == "recent" and row["progress"] == {}
    assert str(root) not in json.dumps(result) and "10000000000" not in json.dumps(result)
    clock[0] += 20
    assert observer.read(cfg, [])["observed"][0]["state"] == "quiet"
    clock[0] += 50
    assert not observer.read(cfg, [])["observed"]
    os.utime(partial, (clock[0], clock[0]))
    assert observer.read(cfg, [])["observed"][0]["state"] == "recent"
    partial.unlink()
    assert not observer.read(cfg, [])["observed"]


def test_local_generation_proof_matches_only_native_loopback_daemon(monkeypatch):
    from klaude_core import ollama_activity

    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] < 1
        return SimpleNamespace(returncode=0, stdout=(
            b'MainPID=123\nExecMainStartTimestampMonotonic=500000000\n'
            b'Environment=SECRET=private OLLAMA_HOST=0.0.0.0:11434\n'))

    monkeypatch.setattr(ollama_activity.subprocess, "run", run)
    monkeypatch.setattr(ollama_activity, "process_identity", lambda _: "start-ticks")
    monkeypatch.setattr(ollama_activity, "time", SimpleNamespace(monotonic=lambda: 1000))
    assert ollama_activity.local_server_generation("http://localhost:11434") == (
        123, 500000000, "start-ticks")
    for url in ("http://remote.invalid:11434", "https://localhost:11434",
                "http://localhost:11434/proxy", "http://localhost:9999",
                "http://[::1]:11434"):
        assert ollama_activity.local_server_generation(url) is None
    monkeypatch.setattr(ollama_activity, "process_identity", lambda _: "")
    assert ollama_activity.local_server_generation("http://localhost:11434") is None
    assert calls


@pytest.mark.parametrize("case", ["match", "wrong_pid", "wrong_request", "unstructured",
                                 "changed_daemon", "invalid_json", "unavailable"])
def test_native_request_end_requires_exact_correlated_handler_record(monkeypatch, case):
    from klaude_core import ollama_activity

    identity = "a" * 32
    generation = (123, 500000000, "start-ticks")
    token = "b" * 32 if case == "wrong_request" else identity
    message = ('[GIN] 2026/10/25 - 21:38:24 | 200 | 33.38s | 127.0.0.1 | POST '
               f'"/api/pull?klaude_request={token}"')
    if case == "unstructured":
        message = "provider error: " + message
    payload = json.dumps({"_PID": "456" if case == "wrong_pid" else "123", "MESSAGE": message})

    def run(args, **kwargs):
        assert args[0] == "journalctl" and f"--grep=klaude_request={identity}" in args
        assert kwargs["timeout"] < 1
        return SimpleNamespace(returncode=int(case == "unavailable"),
                               stdout=(b"not-json" if case == "invalid_json" else payload.encode()))

    monkeypatch.setattr(ollama_activity.subprocess, "run", run)
    monkeypatch.setattr(ollama_activity, "local_server_generation",
                        lambda _: None if case == "changed_daemon" else generation)
    assert ollama_activity.local_request_ended(
        "http://localhost:11434", identity, generation=generation,
    ) == (case == "match")


def test_shared_progress_visible_while_worker_alive_and_removed_on_exit(cfg):
    connection = legacy_connections(cfg)[0]
    observer = ModelActivity()
    events = []
    with track_transfer(cfg, connection, "qwen3:0.6b", events.append) as report:
        report({"stage": "Downloading file", "completed": 42, "total": 100})
        result = observer.read(cfg, [])
        assert result["observed"][0]["model"] == "qwen3:0.6b"
        assert result["observed"][0]["progress"]["completed"] == 42
        assert events[0]["completed"] == 42
        public = json.dumps(result)
        assert "pid" not in public and str(cfg.data_dir) not in public
        assert "request_id" not in public and "cancellable" not in public
        owned = [{"connection": connection.id, "model": "qwen3:0.6b", "state": "running"}]
        assert observer.read(cfg, owned)["observed"] == []
        # An old unknown receipt must not hide a genuinely observed new transfer.
        owned[0]["state"] = "unknown"
        assert len(observer.read(cfg, owned)["observed"]) == 1
    assert observer.read(cfg, [])["observed"] == []


def test_stale_process_revision_and_unsafe_records_are_not_live_transfers(cfg, monkeypatch):
    monkeypatch.setattr(model_activity, "_local_store", lambda: None)
    connection = legacy_connections(cfg)[0]
    root = cfg.data_dir / "model-manager" / "activity"
    root.mkdir(parents=True)
    path = root / ("a" * 32 + ".json")
    record = {"connection": connection.id, "revision": connection.revision, "pid": os.getpid(),
              "process": "old-start-ticks", "model": "safe:1b", "progress": {}}
    path.write_text(json.dumps(record))
    observer = ModelActivity()
    assert observer.read(cfg, [])["observed"] == []
    record.update(process=process_identity(os.getpid()), revision="old-revision")
    path.write_text(json.dumps(record))
    assert observer.read(cfg, [])["observed"] == []
    record["revision"] = connection.revision
    record["progress"] = {"stage": "private/path secret", "completed": 200, "total": 100}
    path.write_text(json.dumps(record))
    public = observer.read(cfg, [])["observed"][0]
    assert public["progress"] == {"stage": "Preparing download", "completed": None, "total": None}
    path.unlink()
    private = cfg.data_dir / "private.json"
    private.write_text(json.dumps(record))
    path.symlink_to(private)
    assert observer.read(cfg, [])["observed"] == []


def test_local_partial_activity_never_uses_preallocated_file_size_as_progress(
    cfg, monkeypatch, tmp_path,
):
    root = tmp_path / "blobs"
    root.mkdir()
    monkeypatch.setattr(model_activity, "_local_store", lambda: (root, 11434))
    clock = [time.time()]
    monkeypatch.setattr(model_activity.time, "time", lambda: clock[0])
    partial = root / ("sha256-" + "a" * 64 + "-partial")
    with partial.open("wb") as stream:
        stream.truncate(10**10)  # sparse preallocation is NOT ten GB downloaded
    os.utime(partial, (clock[0], clock[0]))
    observer = ModelActivity()
    result = observer.read(cfg, [])
    row = result["observed"][0]
    assert row["source"] == "ollama" and row["state"] == "recent"
    assert row["model"] == "Ollama transfer activity" and row["files"] == 1
    assert row["progress"] == {} and "10000000000" not in json.dumps(result)
    clock[0] += 20
    assert observer.read(cfg, [])["observed"][0]["state"] == "quiet"
    clock[0] += 50
    assert observer.read(cfg, [])["observed"] == []
    # A fresh write on an existing partial is picked up, even if first seen stale.
    os.utime(partial, (clock[0], clock[0]))
    assert observer.read(cfg, [])["observed"][0]["state"] == "recent"
    partial.unlink()
    assert observer.read(cfg, [])["observed"] == []


def test_stale_partial_and_remote_endpoints_do_not_claim_a_live_transfer(
    cfg, monkeypatch, tmp_path,
):
    root = tmp_path / "blobs"
    root.mkdir()
    partial = root / ("sha256-" + "b" * 64 + "-partial")
    partial.write_bytes(b"stale")
    os.utime(partial, (1, 1))
    monkeypatch.setattr(model_activity, "_local_store", lambda: (root, 11434))
    assert ModelActivity().read(cfg, [])["observed"] == []
    cfg.ollama_url = "http://remote.invalid:11434"
    os.utime(partial, None)
    result = ModelActivity().read(cfg, [])
    assert result["observed"] == []
    assert result["observation"]["remote"] == "unsupported"


def test_system_service_discovery_only_uses_allowlisted_settings(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=(
            b'MainPID=123\nUser=ollama\nEnvironment=SECRET=do-not-project '
            b'OLLAMA_HOST=0.0.0.0:11434 OLLAMA_MODELS=/some/models\n'))

    monkeypatch.setattr(model_activity.subprocess, "run", run)
    root, port = model_activity._local_store()
    assert str(root) == "/some/models/blobs" and port == 11434
    assert calls[0][1]["timeout"] < 1 and "shell" not in calls[0][1]
