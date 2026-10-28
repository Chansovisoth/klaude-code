"""Image Store transfers use isolated HTTP fixtures, real workers and durable receipts."""

import hashlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from klaude_application import image_model_store, model_store
from klaude_application.operation_journal import OperationConflict

from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request

PAYLOAD = b"image-model-fixture" * 32768
SHA = hashlib.sha256(PAYLOAD).hexdigest()
REVISION = "b" * 40
MODEL = "hf.co/fixture/Image:checkpoint.safetensors"
DRAFT = {"operation": "model-image-download", "connection": "image:sdcpp", "model": MODEL}


@pytest.fixture
def image_store(profile_browser, tmp_path, monkeypatch):
    host, service, _, auth = profile_browser
    directory = tmp_path / "image-models"
    directory.mkdir()
    monkeypatch.setenv("KLAUDE_IMAGE_MODEL_DIR", str(directory))
    state = {"calls": [], "slow": False, "bad_checksum": False, "redirect": ""}

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state["calls"].append(self.path)
            path = self.path.split("?")[0]
            if path == "/api/models":
                payload = [
                    {
                        "id": "fixture/Image",
                        "pipeline_tag": "text-to-image",
                        "downloads": 100,
                        "lastModified": "2026-10-28T00:00:00Z",
                    }
                ]
            elif path == "/api/models/fixture/Image":
                payload = {
                    "id": "fixture/Image",
                    "sha": REVISION,
                    "pipeline_tag": "text-to-image",
                    "cardData": {"license": "mit"},
                    "siblings": [
                        {
                            "rfilename": "checkpoint.safetensors",
                            "lfs": {"size": len(PAYLOAD), "sha256": SHA},
                        },
                        {"rfilename": "no-hash.safetensors", "size": 1024},
                        {"rfilename": "unet/weight.safetensors"},
                        {"rfilename": "../escape.gguf"},
                        {"rfilename": "model.ckpt"},
                    ],
                }
            else:
                assert path == f"/fixture/Image/resolve/{REVISION}/checkpoint.safetensors"
                if state["redirect"]:
                    self.send_response(302)
                    self.send_header("Location", state["redirect"])
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(PAYLOAD)))
                self.end_headers()
                try:
                    payload = b"x" * len(PAYLOAD) if state["bad_checksum"] else PAYLOAD
                    for offset in range(0, len(payload), 8192):
                        self.wfile.write(payload[offset : offset + 8192])
                        self.wfile.flush()
                        if state["slow"]:
                            time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    service.cfg.huggingface_base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield host, service, auth, state, directory
    finally:
        state["slow"] = False
        server.shutdown()
        server.server_close()


def installed_path(directory):
    return directory / "checkpoints" / "fixture" / "Image" / "checkpoint.safetensors"


def test_browse_review_download_inventory_and_durable_history(image_store):
    host, service, auth, state, directory = image_store
    snapshot = _request(host, "GET", "/api/v1/session", **auth)[2]
    assert snapshot["model_store_sdcpp"] is True
    assert snapshot["model_store_sdcpp_revision"] == 1
    route = "/api/v1/models/store?source=huggingface&runtime=sdcpp"
    catalog = _request(host, "GET", route, **auth)[2]
    assert catalog["models"][0]["task"] == "text-to-image"
    assert "filter=text-to-image" in state["calls"][0]
    detail = _request(
        host, "GET", "/api/v1/models/store/detail?id=hf:fixture/Image&runtime=sdcpp", **auth
    )[2]
    assert [row["tag"] for row in detail["variants"]] == [MODEL]
    review = _review(host, auth, DRAFT)
    assert not list(directory.iterdir())
    assert not any("/resolve/" in path for path in state["calls"])
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert installed_path(directory).read_bytes() == PAYLOAD
    assert not list(directory.rglob("*.part"))
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert sum("/resolve/" in path for path in state["calls"]) == 1
    local = _request(host, "GET", "/api/v1/models/installed?connection=image:sdcpp", **auth)[2]
    assert local["models"][0]["name"] == MODEL
    jobs = _request(host, "GET", "/api/v1/models/downloads", **auth)[2]
    assert jobs["items"][0]["size"] == len(PAYLOAD)
    assert jobs["items"][0]["progress"]["completed"] == len(PAYLOAD)
    assert str(directory) not in json.dumps(jobs)
    assert not (service.cfg.config_dir / "image-generation.json").exists()
    assert not service.model_busy()
    assert (
        _request(
            host, "POST", "/api/v1/models/dismiss", body={"request_id": body["request_id"]}, **auth
        )[0]
        == 200
    )
    assert installed_path(directory).exists()
    assert not _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"]


@pytest.mark.parametrize("failure", ["checksum", "redirect", "existing", "symlink"])
def test_failed_transfer_never_publishes_or_replaces_existing_files(image_store, failure):
    host, service, auth, state, directory = image_store
    review = _review(host, auth, DRAFT)
    destination = installed_path(directory)
    if failure == "checksum":
        state["bad_checksum"] = True
    elif failure == "redirect":
        state["redirect"] = "http://127.0.0.1:9/private"
    elif failure == "existing":
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"keep me")
    else:
        outside = directory.parent / "outside"
        outside.mkdir()
        (directory / "checkpoints").symlink_to(outside, target_is_directory=True)
    receipt, _ = _submit(host, service, auth, review)
    assert receipt["state"] == "failed"
    assert not service.model_busy()
    if failure == "existing":
        assert destination.read_bytes() == b"keep me"
    else:
        assert not destination.exists()
    assert not list(directory.rglob("*.part"))
    if failure in {"existing", "symlink"}:
        assert not any("/resolve/" in path for path in state["calls"])


def test_stop_reaps_worker_cleans_partial_and_releases_fence(image_store):
    host, service, auth, state, directory = image_store
    state["slow"] = True
    review = _review(host, auth, DRAFT)
    identity = uuid.uuid4().hex
    body = {"review_id": review["review_id"], "request_id": identity, "control_epoch": 0}
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    for _ in range(150):
        if any("/resolve/" in path for path in state["calls"]):
            break
        time.sleep(0.02)
    assert any("/resolve/" in path for path in state["calls"])
    assert (
        _request(host, "POST", "/api/v1/models/cancel", body={"request_id": identity}, **auth)[0]
        == 200
    )
    for _ in range(150):
        if service.status(identity)["state"] in {"failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert service.status(identity)["state"] in {"failed", "cancelled"}
    assert not installed_path(directory).exists()
    assert not list(directory.rglob("*.part"))
    assert not service.model_busy()


def unknown(service):
    fields, resource, _ = model_store.prepare(service.cfg, DRAFT)
    identity = uuid.uuid4().hex
    receipt = service.journal.admit(
        request_id=identity,
        owner_id=model_store.OWNER,
        kind=DRAFT["operation"],
        resource=resource,
        payload=fields,
    )
    model_store.save_target(service.cfg, identity, fields)
    service.journal.record_witness(
        identity,
        model_store.OWNER,
        receipt.fence,
        before=model_store.witness(fields, False),
        after=model_store.witness(fields, True),
    )
    service.journal.start(identity, model_store.OWNER, receipt.fence)
    service.journal.mark_unknown(identity, model_store.OWNER, receipt.fence)
    return identity, fields


@pytest.mark.parametrize("outcome", ["present", "absent", "changed", "target", "active", "root"])
def test_recovery_checks_exact_local_file_without_network_or_replay(image_store, outcome):
    host, service, auth, state, directory = image_store
    identity, fields = unknown(service)
    destination = installed_path(directory)
    destination.parent.mkdir(parents=True)
    if outcome in {"present", "changed"}:
        destination.write_bytes(PAYLOAD if outcome == "present" else b"x" * len(PAYLOAD))
    if outcome == "target":
        model_store.save_target(service.cfg, identity, {**fields, "sha256": "a" * 64})
    if outcome == "root":
        directory.rename(directory.with_name("moved-models"))
    before = state["calls"][:]
    if outcome == "active":
        with image_model_store.directory(fields, lock=True):
            with pytest.raises(OperationConflict):
                service.reconcile_model(identity)
    elif outcome in {"changed", "target", "root"}:
        with pytest.raises((ValueError, OSError, OperationConflict)):
            service.reconcile_model(identity)
        assert service.status(identity)["state"] == "unknown"
        assert service.model_busy()
    else:
        result = service.reconcile_model(identity)
        assert result["state"] == ("completed" if outcome == "present" else "failed")
        assert not service.model_busy()
    assert state["calls"] == before
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["chat_model_blocked"] is False


def test_admin_and_csrf_required_for_review_and_submission(image_store):
    host, service, auth, state, directory = image_store
    bad = {**auth, "csrf": "invalid"}
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": DRAFT}, **bad)[0] == 403
    review = _review(host, auth, DRAFT)
    host.http.host_lan = True
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": DRAFT}, **auth)[0] == 403
    body = {"review_id": review["review_id"], "request_id": uuid.uuid4().hex, "control_epoch": 0}
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 403
    assert not list(directory.iterdir())
    assert not any("/resolve/" in path for path in state["calls"])


@pytest.mark.parametrize(
    "model",
    [
        "http://private/weight",
        "hf.co/../escape:file.gguf",
        "hf.co/fixture/Image:../escape.gguf",
        "hf.co/fixture/Image:no-hash.safetensors",
    ],
)
def test_exact_metadata_required_and_no_arbitrary_sources(image_store, model):
    _, service, _, state, _ = image_store
    with pytest.raises(ValueError):
        model_store.prepare(service.cfg, {**DRAFT, "model": model})
    assert not any("/resolve/" in path for path in state["calls"])
