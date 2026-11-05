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
    state = {"calls": [], "slow": False, "bad_checksum": False, "redirect": "",
             "interrupt": False, "include_nested": False, "include_second": False,
             "ignore_range": False,
             "ranges": [], "bad_range": False, "gate": None, "started": []}

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
                        {"rfilename": "model-MLX-4bit.safetensors",
                         "lfs": {"size": len(PAYLOAD), "sha256": SHA}},
                        {"rfilename": "no-hash.safetensors", "size": 1024},
                        {"rfilename": "unet/weight.safetensors"},
                        {"rfilename": "../escape.gguf"},
                        {"rfilename": "model.ckpt"},
                    ] + ([{"rfilename": "split_files/vae/decoder.safetensors",
                           "lfs": {"size": len(PAYLOAD), "sha256": SHA}}]
                         if state["include_nested"] else []) + (
                        [{"rfilename": "another.safetensors",
                          "lfs": {"size": len(PAYLOAD), "sha256": SHA}}]
                        if state["include_second"] else []),
                }
            else:
                assert path in {
                    f"/fixture/Image/resolve/{REVISION}/checkpoint.safetensors",
                    f"/fixture/Image/resolve/{REVISION}/another.safetensors",
                    f"/fixture/Image/resolve/{REVISION}/split_files/vae/decoder.safetensors",
                }
                if state["redirect"]:
                    self.send_response(302)
                    self.send_header("Location", state["redirect"])
                    self.end_headers()
                    return
                state["started"].append(path)
                if state["gate"] is not None:
                    state["gate"].wait(timeout=10)
                offset = 0
                if self.headers.get("Range"):
                    state["ranges"].append(self.headers["Range"])
                    if not state["ignore_range"]:
                        offset = int(self.headers["Range"].split("=")[1].split("-")[0])
                self.send_response(206 if offset else 200)
                if offset:
                    start = offset + 1 if state["bad_range"] else offset
                    self.send_header("Content-Range",
                                     f"bytes {start}-{len(PAYLOAD)-1}/{len(PAYLOAD)}")
                self.send_header("Content-Length", str(len(PAYLOAD) - offset))
                self.end_headers()
                try:
                    payload = b"x" * len(PAYLOAD) if state["bad_checksum"] else PAYLOAD
                    payload = payload[offset:]
                    if state["interrupt"]:
                        self.wfile.write(payload[:len(payload)//2])
                        self.wfile.flush()
                        self.close_connection = True
                        return
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


def test_unknown_skill_does_not_block_independent_image_download(image_store):
    host, service, auth, state, directory = image_store
    rid = uuid.uuid4().hex
    skill = service.journal.admit(request_id=rid, owner_id=model_store.OWNER,
                                  kind="skill-store-install", resource="skill:legacy",
                                  payload={})
    service.journal.start(rid, model_store.OWNER, skill.fence)
    service.journal.mark_unknown(rid, model_store.OWNER, skill.fence)
    review = _review(host, auth, DRAFT)
    receipt, _ = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert installed_path(directory).read_bytes() == PAYLOAD
    assert service.journal.status(rid, model_store.OWNER).state == "unknown"
    assert service.journal.resource_busy("skill:legacy")


def test_mlx_variant_cannot_be_reviewed_for_sd(image_store):
    host, service, auth, state, directory = image_store
    code, _, result = _request(host, "POST", "/api/v1/library/review", body={
        "draft": {**DRAFT, "model": "hf.co/fixture/Image:model-MLX-4bit.safetensors"}
    }, **auth)
    assert code == 400
    assert not list(directory.iterdir())
    assert not any("/resolve/" in path for path in state["calls"])


def test_unknown_model_download_still_blocks_a_second_download(image_store):
    host, service, auth, state, directory = image_store
    rid, _ = unknown(service)
    review = _review(host, auth, DRAFT)
    code, _, _ = _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": uuid.uuid4().hex,
        "control_epoch": 0,
    }, **auth)
    assert code == 409
    assert service.journal.status(rid, model_store.OWNER).state == "unknown"
    assert not any("/resolve/" in path for path in state["calls"])


def test_load_installed_image_model_while_download_worker_is_running(image_store):
    from klaude_core.image_generation import read

    from .test_image_model_selection import draft, model_server

    host, service, auth, state, directory = image_store
    state["slow"] = True
    review = _review(host, auth, DRAFT)
    download = uuid.uuid4().hex
    assert _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": download, "control_epoch": 0,
    }, **auth)[0] == 202
    try:
        for _ in range(150):
            if any("/resolve/" in path for path in state["calls"]):
                break
            time.sleep(0.02)
        assert service.status(download)["state"] == "running"
        with model_server() as (url, runtime):
            load = _review(host, auth, draft(service, url))
            loaded, _ = _submit(host, service, auth, load)
            assert loaded["state"] == "completed"
            assert len(runtime["loads"]) == 1
            assert service.status(download)["state"] == "running"
            save = _review(host, auth, {
                "operation": "image-settings-save", "endpoint": url, "enabled": True,
                "revision": read(service.cfg)["revision"], "provider": "sdcpp",
                "model": "second.gguf",
            })
            saved, _ = _submit(host, service, auth, save)
            assert saved["state"] == "completed"
    finally:
        state["slow"] = False
    for _ in range(200):
        if service.status(download)["state"] == "completed":
            break
        time.sleep(0.02)
    assert service.status(download)["state"] == "completed"
    assert installed_path(directory).read_bytes() == PAYLOAD


@pytest.mark.parametrize("ignore_range", [False, True])
def test_failed_download_retry_resumes_or_safely_restarts(image_store, ignore_range):
    host, service, auth, state, directory = image_store
    state["interrupt"] = True
    first, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    assert first["state"] == "failed"
    partial, = directory.rglob("*.part")
    retained = partial.stat().st_size
    assert 0 < retained < len(PAYLOAD)
    assert not installed_path(directory).exists()
    state.update(interrupt=False, ignore_range=ignore_range)
    second, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    assert second["state"] == "completed"
    assert state["ranges"] == [f"bytes={retained}-"]
    assert installed_path(directory).read_bytes() == PAYLOAD
    assert not list(directory.rglob("*.part"))


def test_bad_range_never_appends_or_publishes(image_store):
    host, service, auth, state, directory = image_store
    state["interrupt"] = True
    _submit(host, service, auth, _review(host, auth, DRAFT))
    partial, = directory.rglob("*.part")
    before = partial.read_bytes()
    state.update(interrupt=False, bad_range=True)
    receipt, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    assert receipt["state"] == "failed"
    assert partial.read_bytes() == before
    assert not installed_path(directory).exists()


def test_complete_retained_partial_is_verified_without_redownload(image_store):
    host, service, auth, state, directory = image_store
    state["interrupt"] = True
    _submit(host, service, auth, _review(host, auth, DRAFT))
    partial, = directory.rglob("*.part")
    partial.write_bytes(PAYLOAD)
    before = sum("/resolve/" in call for call in state["calls"])
    receipt, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    assert receipt["state"] == "completed"
    assert sum("/resolve/" in call for call in state["calls"]) == before
    assert installed_path(directory).read_bytes() == PAYLOAD


def test_corrupted_retained_prefix_is_never_published(image_store):
    host, service, auth, state, directory = image_store
    state["interrupt"] = True
    _submit(host, service, auth, _review(host, auth, DRAFT))
    partial, = directory.rglob("*.part")
    partial.write_bytes(b"x" * partial.stat().st_size)
    state["interrupt"] = False
    receipt, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    assert receipt["state"] == "failed"
    assert not installed_path(directory).exists()
    assert not partial.exists()


def test_pause_preserves_bytes_and_resume_uses_range(image_store):
    host, service, auth, state, directory = image_store
    state["slow"] = True
    review = _review(host, auth, DRAFT)
    rid = uuid.uuid4().hex
    assert _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": rid, "control_epoch": 0,
    }, **auth)[0] == 202
    for _ in range(200):
        partials = list(directory.rglob("*.part"))
        if partials and partials[0].stat().st_size > 0:
            break
        time.sleep(0.02)
    assert partials and partials[0].stat().st_size > 0
    assert _request(host, "POST", "/api/v1/models/pause", body={"request_id": rid},
                    **auth)[0] == 200
    for _ in range(150):
        if service.status(rid)["state"] in {"failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert service.status(rid)["state"] in {"failed", "cancelled"}
    retained = partials[0].stat().st_size
    assert retained > 0
    assert not service.model_busy()
    # Public pause state is reconstructed from private durable target metadata,
    # not the host's in-memory worker map or progress callbacks.
    row = next(x for x in model_store.jobs(service.cfg, service.journal)["items"]
               if x["request_id"] == rid)
    assert row["paused"]
    state["slow"] = False
    resumed_id = uuid.uuid4().hex
    before_metadata = state["calls"].count("/api/models/fixture/Image?blobs=true")
    assert _request(host, "POST", "/api/v1/models/resume", body={
        "request_id": rid, "new_request_id": resumed_id,
    }, **auth)[0] == 200
    for _ in range(200):
        if service.status(resumed_id)["state"] == "completed":
            break
        time.sleep(0.02)
    assert service.status(resumed_id)["state"] == "completed"
    assert state["calls"].count("/api/models/fixture/Image?blobs=true") == before_metadata
    assert state["ranges"] == [f"bytes={retained}-"]
    assert installed_path(directory).read_bytes() == PAYLOAD
    assert _request(host, "POST", "/api/v1/models/resume", body={
        "request_id": rid, "new_request_id": resumed_id,
    }, **auth)[0] == 200
    assert state["ranges"] == [f"bytes={retained}-"]


def test_pause_requires_admin_and_csrf(image_store):
    host, service, auth, state, directory = image_store
    denied = {**auth, "csrf": "bad"}
    assert _request(host, "POST", "/api/v1/models/pause",
                    body={"request_id": uuid.uuid4().hex}, **denied)[0] == 403


def test_resume_rejects_changed_original_target(image_store):
    host, service, auth, state, directory = image_store
    state["interrupt"] = True
    receipt, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    rid = receipt["request_id"]
    path = model_store.target_path(service.cfg, rid)
    target = json.loads(path.read_text())
    target["sha256"] = "a" * 64
    path.write_text(json.dumps(target))
    resumed_id = uuid.uuid4().hex
    code, _, _ = _request(host, "POST", "/api/v1/models/resume", body={
        "request_id": rid, "new_request_id": resumed_id,
    }, **auth)
    assert code == 409
    with pytest.raises(ValueError):
        service.status(resumed_id)
    assert not installed_path(directory).exists()


def test_resume_preserves_active_conversation_guard(image_store, monkeypatch):
    host, service, auth, state, directory = image_store
    monkeypatch.setattr(host, "_application_busy", lambda app: True)
    code, _, _ = _request(host, "POST", "/api/v1/models/resume", body={
        "request_id": uuid.uuid4().hex, "new_request_id": uuid.uuid4().hex,
    }, **auth)
    assert code == 409
    assert not state["calls"]



def test_nested_dependency_publishes_in_reviewed_category_and_recovers(image_store):
    host, service, auth, state, directory = image_store
    state["include_nested"] = True
    component = {**DRAFT, "category": "vae", "model":
                 "hf.co/fixture/Image:split_files/vae/decoder.safetensors"}
    review = _review(host, auth, component)
    receipt, _ = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    path = directory / "vae/fixture/Image/split_files/vae/decoder.safetensors"
    assert path.read_bytes() == PAYLOAD
    assert not (directory / "checkpoints/fixture/Image/split_files").exists()
    assert any(x["name"] == component["model"]
               for x in image_model_store.inventory(service.cfg)["models"])
    target = model_store.read_record(model_store.target_path(service.cfg, receipt["request_id"]))
    assert model_store.private_target(target)["category"] == "vae"


@pytest.mark.parametrize("category", ["../outside", "/tmp", "scripts", []])
def test_dependency_category_cannot_escape_model_root(image_store, category):
    host, service, auth, state, directory = image_store
    code, _, _ = _request(host, "POST", "/api/v1/library/review", body={
        "draft": {**DRAFT, "category": category},
    }, **auth)
    assert code == 400
    assert not list(directory.iterdir())



def test_two_files_transfer_concurrently_and_pause_is_independent(image_store):
    host, service, auth, state, directory = image_store
    state["include_nested"] = True
    gate = threading.Event()
    state["gate"] = gate
    component = {**DRAFT, "category": "vae", "model":
                 "hf.co/fixture/Image:split_files/vae/decoder.safetensors"}
    requests = []
    try:
        for draft in (DRAFT, component):
            review = _review(host, auth, draft)
            rid = uuid.uuid4().hex
            code, _, result = _request(host, "POST", "/api/v1/library/submit", body={
                "review_id": review["review_id"], "request_id": rid, "control_epoch": 0,
            }, **auth)
            assert code == 202, result
            requests.append(rid)
        for _ in range(200):
            if len(state["started"]) == 2:
                break
            time.sleep(.02)
        assert len(state["started"]) == 2
        assert all(service.status(rid)["state"] == "running" for rid in requests)
        assert _request(host, "POST", "/api/v1/models/pause", body={
            "request_id": requests[0],
        }, **auth)[0] == 200
        for _ in range(100):
            if service.status(requests[0])["state"] in {"failed", "cancelled"}:
                break
            time.sleep(.02)
        assert service.status(requests[0])["state"] in {"failed", "cancelled"}
        assert service.status(requests[1])["state"] == "running"
        resume = uuid.uuid4().hex
        assert _request(host, "POST", "/api/v1/models/resume", body={
            "request_id": requests[0], "new_request_id": resume,
        }, **auth)[0] == 200
    finally:
        gate.set()
    for _ in range(250):
        if all(service.status(rid)["state"] == "completed" for rid in (resume, requests[1])):
            break
        time.sleep(.02)
    assert service.status(resume)["state"] == "completed"
    assert service.status(requests[1])["state"] == "completed"
    assert installed_path(directory).read_bytes() == PAYLOAD
    component_path = directory / "vae/fixture/Image/split_files/vae/decoder.safetensors"
    assert component_path.read_bytes() == PAYLOAD


def test_resume_adopts_the_older_checksum_only_partial_name(image_store):
    host, service, auth, state, directory = image_store
    path = installed_path(directory).parent
    path.mkdir(parents=True)
    retained = len(PAYLOAD) // 2
    (path / f".klaude-{SHA}.part").write_bytes(PAYLOAD[:retained])
    receipt, _ = _submit(host, service, auth, _review(host, auth, DRAFT))
    assert receipt["state"] == "completed"
    assert state["ranges"] == [f"bytes={retained}-"]
    assert installed_path(directory).read_bytes() == PAYLOAD


def test_legacy_unknown_global_download_still_requires_reconciliation(image_store):
    host, service, auth, state, directory = image_store
    rid = uuid.uuid4().hex
    old = service.journal.admit(request_id=rid, owner_id=model_store.OWNER,
                               kind="model-image-download", resource=model_store.RESOURCE,
                               payload={})
    service.journal.start(rid, model_store.OWNER, old.fence)
    service.journal.mark_unknown(rid, model_store.OWNER, old.fence)
    review = _review(host, auth, DRAFT)
    code, _, _ = _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": uuid.uuid4().hex, "control_epoch": 0,
    }, **auth)
    assert code == 409
    assert service.journal.status(rid, model_store.OWNER).state == "unknown"
    assert not state["started"]


def test_same_content_distinct_files_have_independent_partials_and_fences(image_store):
    host, service, auth, state, directory = image_store
    state["include_second"] = True
    gate = threading.Event()
    state["gate"] = gate
    requests = []
    try:
        for name in ("checkpoint.safetensors", "another.safetensors"):
            review = _review(host, auth, {**DRAFT, "model": f"hf.co/fixture/Image:{name}"})
            rid = uuid.uuid4().hex
            code, _, result = _request(host, "POST", "/api/v1/library/submit", body={
                "review_id": review["review_id"], "request_id": rid, "control_epoch": 0,
            }, **auth)
            assert code == 202, result
            requests.append(rid)
        for _ in range(200):
            if len(state["started"]) == 2:
                break
            time.sleep(.02)
        assert len(state["started"]) == 2
        targets = [model_store.read_record(model_store.target_path(service.cfg, rid))
                   for rid in requests]
        assert len({image_model_store.partial_name(target) for target in targets}) == 2
        assert len({image_model_store.resource(target) for target in targets}) == 2
        alias = {**targets[0], "root": str(directory / ".." / directory.name)}
        assert image_model_store.resource(alias) == image_model_store.resource(targets[0])
        # An independently reviewed duplicate still cannot claim the same destination.
        duplicate = _review(host, auth, DRAFT)
        code, _, _ = _request(host, "POST", "/api/v1/library/submit", body={
            "review_id": duplicate["review_id"], "request_id": uuid.uuid4().hex,
            "control_epoch": 0,
        }, **auth)
        assert code == 409
    finally:
        gate.set()
    for _ in range(250):
        if all(service.status(rid)["state"] == "completed" for rid in requests):
            break
        time.sleep(.02)
    assert all(service.status(rid)["state"] == "completed" for rid in requests)
    assert installed_path(directory).read_bytes() == PAYLOAD
    assert (installed_path(directory).parent / "another.safetensors").read_bytes() == PAYLOAD


def test_new_download_obeys_legacy_root_lock(image_store):
    import fcntl

    host, service, auth, state, directory = image_store
    fields, _, _ = image_model_store.prepare(service.cfg, DRAFT)
    with (directory / ".klaude-download.lock").open("w") as legacy:
        fcntl.flock(legacy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(OperationConflict):
            with image_model_store.directory(fields, create=True, lock=True):
                pytest.fail("Legacy worker lock was bypassed")
    with image_model_store.directory(fields, create=True, lock=True) as descriptor:
        assert descriptor is not None


def test_download_rejects_nonregular_root_lock(image_store):
    import os

    host, service, auth, state, directory = image_store
    fields, _, _ = image_model_store.prepare(service.cfg, DRAFT)
    os.mkfifo(directory / ".klaude-download.lock")
    with pytest.raises(ValueError, match="Unsafe download lock"):
        with image_model_store.directory(fields, create=True, lock=True):
            pytest.fail("Nonregular download lock was accepted")
