"""Browser model lifecycle uses real HTTP fixtures and the existing owned worker."""

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from klaude_application import model_store
from klaude_application.browser_jobs import image_capabilities, prepare_generated_operation
from klaude_application.library_management import LibraryManagement
from klaude_core.model_connections import legacy_connections
from klaude_core.model_runtime import ModelInfo
from klaude_core.settings_store import update_settings

from .test_image_generation import enable
from .test_image_generation import generation_lab as generation_lab
from .test_library_management import _wait
from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def native(profile_browser):
    host, service, _, auth = profile_browser
    state = {"models": [], "running": [], "calls": [], "slow": False, "offline": False}

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, value, status=200):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            state["calls"].append(("GET", self.path))
            if state["offline"]:
                self.reply({}, 503)
            elif self.path == "/api/version":
                self.reply({"version": "fixture-1"})
            else:
                self.reply({"models": state["running" if self.path == "/api/ps" else "models"]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"].append(("POST", self.path.split("?", 1)[0]))
            state.setdefault("pull_targets", []).append(self.path)
            assert self.path.split("?", 1)[0] == "/api/pull"
            self.send_response(200)
            self.end_headers()
            if state.get("pull_error"):
                self.wfile.write(json.dumps({"error": state["pull_error"]}).encode() + b"\n")
                return
            if state.get("truncate"):
                self.wfile.write(b'{"status":"pulling manifest"}\n')
                return
            try:
                self.wfile.write(b'{"status":"pulling manifest"}\n')
                self.wfile.flush()
                while state["slow"]:
                    self.wfile.write(
                        b'{"status":"pulling layer","digest":"test","completed":10,"total":100}\n'
                    )
                    self.wfile.flush()
                    time.sleep(0.1)
                state["models"].append(
                    {"name": body["model"], "digest": "a" * 64, "size": 100, "details": {}}
                )
                self.wfile.write(b'{"status":"success"}\n')
            except (BrokenPipeError, ConnectionResetError):
                state["handler_closed"] = True
                pass

        def do_DELETE(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"].append(("DELETE", self.path))
            if not state.get("delete_unchanged"):
                state["models"][:] = [r for r in state["models"] if r["name"] != body["model"]]
            self.reply({})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg = service.cfg
    cfg.ollama_url = f"http://127.0.0.1:{server.server_port}"
    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    (cfg.config_dir / "config.toml").write_text(f'[services]\nollama_url="{cfg.ollama_url}"\n')
    identity = legacy_connections(cfg)[0].id
    try:
        yield host, service, auth, state, identity
    finally:
        state["slow"] = False
        server.shutdown()
        server.server_close()


def draft(endpoint, operation="model-pull", model="fresh:1b"):
    return {"operation": operation, "connection": endpoint, "model": model}


@pytest.mark.parametrize("operation", ["model-pull", "model-delete"])
@pytest.mark.parametrize("state", ["accepted", "running", "unknown"])
def test_chat_model_gate_keeps_exact_witness_and_mutation_fence(native, operation, state):
    from klaude_core.ollama_manager import endpoint

    host, service, auth, _, identity = native
    connection, credential = endpoint(service.cfg, identity)
    fields = {"endpoint": identity, "model": "fresh:1b", "revision": connection.revision,
              "credential_revision": credential, "digest": ""}
    rid = uuid.uuid4().hex
    receipt = service.journal.admit(request_id=rid, owner_id="web-admin", kind=operation,
                                    resource=model_store.RESOURCE, payload=fields)
    final = operation == "model-pull"
    service.journal.record_witness(rid, "web-admin", receipt.fence,
                                   before=model_store.witness(fields, not final),
                                   after=model_store.witness(fields, final))
    model_store.save_target(service.cfg, rid, fields)
    if state != "accepted":
        service.journal.start(rid, "web-admin", receipt.fence)
    if state == "unknown":
        service.journal.mark_unknown(rid, "web-admin", receipt.fence)
    same = ModelInfo("ollama", "fresh:1b", "Fresh", connection_id=identity)
    other = ModelInfo("ollama", "mistral:7b", "Mistral", connection_id=identity)
    cloud = ModelInfo("openai_api", "fixture", "Cloud fixture")
    assert service.model_chat_blocked(same)
    assert service.model_chat_blocked(other) == (operation == "model-delete")
    assert not service.model_chat_blocked(cloud)
    assert service.model_busy()
    assert service.journal.status(rid, "web-admin").state == state
    snapshot = _request(host, "GET", "/api/v1/session", **auth)[2]
    assert snapshot["chat_auto_queue"] is True
    assert snapshot["chat_model_blocked"] == (operation == "model-delete")
    # A private target edit cannot make a matching download look unrelated.
    if operation == "model-pull":
        model_store.save_target(service.cfg, rid, {**fields, "model": "different:1b"})
        assert service.model_chat_blocked(other)
        assert service.journal.status(rid, "web-admin").state == state


@pytest.mark.parametrize("failure", ["terminal", "preflight", "truncated"])
def test_pull_failure_receipt_distinguishes_confirmed_failure_from_lost_outcome(native, failure):
    host, service, auth, state, identity = native
    review = _review(host, auth, draft(identity))
    if failure == "terminal":
        state["pull_error"] = "unexpected EOF secret private server path"
    elif failure == "preflight":
        state["offline"] = True
    else:
        state["truncate"] = True
    receipt, _ = _submit(host, service, auth, review)
    assert receipt["state"] == ("unknown" if failure == "truncated" else "failed")
    assert service.model_busy() == (failure == "truncated")
    assert state["calls"].count(("POST", "/api/pull")) == (failure != "preflight")
    jobs = _request(host, "GET", "/api/v1/models/downloads", **auth)[2]
    assert "secret" not in json.dumps(jobs)


def test_external_shared_pull_appears_without_creating_browser_job_or_second_pull(native):
    from klaude_core.ollama_manager import endpoint, execute_manager

    host, service, auth, state, identity = native
    connection, credential = endpoint(service.cfg, identity)
    state["slow"] = True
    result = {}

    def run():
        result.update(execute_manager(service.cfg, {
            "operation": "pull", "endpoint": identity, "model": "external:1b", "digest": "",
            "revision": connection.revision, "credential_revision": credential,
        }))

    worker = threading.Thread(target=run)
    worker.start()
    try:
        for _ in range(100):
            jobs = _request(host, "GET", "/api/v1/models/downloads", **auth)[2]
            if jobs["observed"] and state["calls"].count(("POST", "/api/pull")) == 1:
                break
            time.sleep(0.03)
        assert jobs["items"] == []
        assert jobs["observed"][0]["model"] == "external:1b"
        assert jobs["observed"][0]["source"] == "klaude"
        assert "request_id" not in jobs["observed"][0]
        assert state["calls"].count(("POST", "/api/pull")) == 1
    finally:
        state["slow"] = False
        worker.join(5)
    assert result["status"] == "ok"
    assert _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["observed"] == []


def test_failed_download_history_removal_is_durable_idempotent_and_local_only(native):
    host, service, auth, state, identity = native
    state["pull_error"] = "unexpected EOF"
    receipt, _ = _submit(host, service, auth, _review(host, auth, draft(identity)))
    assert receipt["state"] == "failed"
    body = {"request_id": receipt["request_id"]}
    before = state["calls"][:]
    bad_auth = {**auth, "csrf": "invalid"}
    assert _request(host, "POST", "/api/v1/models/dismiss", body=body, **bad_auth)[0] == 403
    assert _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"]
    for _ in range(2):
        assert _request(host, "POST", "/api/v1/models/dismiss", body=body, **auth)[0] == 200
    assert _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"] == []
    assert service.journal.status(body["request_id"], "web-admin").state == "failed"
    assert state["calls"] == before
    reopened = LibraryManagement(service.cfg, service.workspace)
    try:
        assert reopened.model_jobs()["items"] == []
    finally:
        reopened.close()


def test_removing_unknown_history_retains_exact_recovery_and_resource_fence(native):
    host, service, auth, state, identity = native
    state["truncate"] = True
    receipt, _ = _submit(host, service, auth, _review(host, auth, draft(identity)))
    body = {"request_id": receipt["request_id"]}
    assert receipt["state"] == "unknown"
    before = state["calls"][:]
    assert _request(host, "POST", "/api/v1/models/dismiss", body=body, **auth)[0] == 200
    item = _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"][0]
    assert item["dismissed"] is True and item["state"] == "unknown"
    assert item["request_id"] == body["request_id"] and service.model_busy()
    assert state["calls"] == before
    assert _request(host, "POST", "/api/v1/models/reconcile", body=body, **auth)[0] == 409
    assert service.model_busy()
    state["models"] = [{"name": "fresh:1b", "digest": "a" * 64, "size": 100}]
    assert _request(host, "POST", "/api/v1/models/reconcile", body=body, **auth)[0] == 200
    assert not service.model_busy()
    assert _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"] == []
    assert state["calls"].count(("POST", "/api/pull")) == 1


@pytest.mark.parametrize("proof", ["new", "old", "missing", "changing", "offline", "tampered"])
def test_prior_inventory_recovery_requires_stable_newer_daemon_and_exact_witness(
    native, monkeypatch, proof,
):
    host, service, auth, state, identity = native
    state["truncate"] = True
    receipt, _ = _submit(host, service, auth, _review(host, auth, draft(identity)))
    body = {"request_id": receipt["request_id"]}
    assert receipt["state"] == "unknown"
    assert _request(host, "POST", "/api/v1/models/dismiss", body=body, **auth)[0] == 200
    # Simulate checking a minute later, after a daemon restart. Keep the actual
    # journal clock untouched; only the domain's generation-age calculation moves.
    now = time.time()
    monkeypatch.setattr(model_store, "time", SimpleNamespace(
        time=lambda: now + 60, monotonic=time.monotonic,
    ))
    started = int((time.monotonic() - (120 if proof == "old" else 0)) * 1e6)
    generation = (123, started, "start-ticks")
    reads = []

    def daemon(_):
        reads.append(1)
        if proof == "missing":
            return None
        if proof == "changing" and len(reads) > 1:
            return 456, started, "other-ticks"
        return generation

    monkeypatch.setattr(model_store, "local_server_generation", daemon)
    if proof == "offline":
        state["offline"] = True
    if proof == "tampered":
        path = model_store.target_path(service.cfg, body["request_id"])
        path.write_text(json.dumps({**json.loads(path.read_text()), "model": "different:1b"}))
    response = _request(host, "POST", "/api/v1/models/reconcile", body=body, **auth)
    assert response[0] == (200 if proof == "new" else 409)
    if proof == "new":
        assert response[2]["state"] == "failed" and response[2]["outcome"] == "reconciled"
        assert _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"] == []
    assert service.model_busy() == (proof != "new")
    assert state["calls"].count(("POST", "/api/pull")) == 1


@pytest.mark.parametrize("digest", ["a", "b"])
def test_restarted_daemon_delete_recovery_requires_original_digest(native, monkeypatch, digest):
    host, service, auth, state, identity = native
    state["models"] = [{"name": "fresh:1b", "digest": "a" * 64, "size": 100}]
    state["delete_unchanged"] = True
    receipt, _ = _submit(host, service, auth, _review(host, auth, draft(identity, "model-delete")))
    assert receipt["state"] == "unknown"
    now = time.time()
    monkeypatch.setattr(model_store, "time", SimpleNamespace(
        time=lambda: now + 60, monotonic=time.monotonic,
    ))
    generation = (123, int(time.monotonic() * 1e6), "new-start")
    monkeypatch.setattr(model_store, "local_server_generation", lambda _: generation)
    state["models"][0]["digest"] = digest * 64
    response = _request(host, "POST", "/api/v1/models/reconcile",
                        body={"request_id": receipt["request_id"]}, **auth)
    assert response[0] == (200 if digest == "a" else 409)
    assert service.model_busy() == (digest != "a")
    assert state["calls"].count(("DELETE", "/api/delete")) == 1


@pytest.mark.parametrize("action", ["reconcile", "dismiss"])
def test_ended_tagged_pull_releases_prior_inventory_without_daemon_restart(
    native, monkeypatch, action,
):
    host, service, auth, state, identity = native
    state["truncate"] = True
    receipt, _ = _submit(host, service, auth, _review(host, auth, draft(identity)))
    rid = receipt["request_id"]
    assert receipt["state"] == "unknown"
    assert state["pull_targets"] == [f"/api/pull?klaude_request={rid}"]
    generation = (123, 1, "old-daemon-still-running")
    monkeypatch.setattr(model_store, "local_server_generation", lambda _: generation)
    monkeypatch.setattr(model_store, "local_request_ended",
                        lambda _, token, **kwargs: token == rid)
    response = _request(host, "POST", f"/api/v1/models/{action}",
                        body={"request_id": rid}, **auth)
    assert response[0] == 200
    assert service.journal.status(rid, "web-admin").state == "failed"
    assert not service.model_busy()
    if action == "dismiss":
        assert _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"] == []
    assert state["calls"].count(("POST", "/api/pull")) == 1


def test_stop_rechecks_delayed_handler_end_without_restarting_pull(native, monkeypatch):
    host, service, auth, state, identity = native
    state["slow"] = True
    generation = (123, 1, "same-daemon")
    monkeypatch.setattr(model_store, "local_server_generation", lambda _: generation)
    monkeypatch.setattr(model_store, "local_request_ended",
                        lambda *args, **kwargs: bool(state.get("handler_closed")))
    review = _review(host, auth, draft(identity))
    rid = uuid.uuid4().hex
    assert _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": rid, "control_epoch": 0,
    }, **auth)[0] == 202
    for _ in range(100):
        if state.get("pull_targets"):
            break
        time.sleep(0.03)
    assert _request(host, "POST", "/api/v1/models/cancel",
                    body={"request_id": rid}, **auth)[0] == 200
    for _ in range(200):
        if service.status(rid)["state"] == "failed":
            break
        time.sleep(0.05)
    assert state["handler_closed"] and service.status(rid)["state"] == "failed"
    assert not service.model_busy()
    assert state["calls"].count(("POST", "/api/pull")) == 1


def test_store_catalog_is_dated_exact_and_read_only(native):
    host, service, auth, state, identity = native
    result = _request(host, "GET", "/api/v1/models/store", **auth)[2]
    assert result["source"] == "bundled" and result["rankings"] is False
    assert result["verified"] == "2026-10-25"
    assert all(":" in v["tag"] for m in result["models"] for v in m["variants"])
    assert not state["calls"]
    data = _request(host, "GET", f"/api/v1/models/installed?connection={identity}", **auth)[2]
    assert data["models"] == []
    assert not any(
        key in json.dumps(data) for key in [service.cfg.ollama_url, "credential", "base_url"]
    )
    cache = next((service.data / "model-manager" / "inventory").glob("*.json"))
    cached = json.loads(cache.read_text())
    cached["models"] = [{"name": "safe:1b", "private_extra": "must-not-project"}]
    cache.write_text(json.dumps(cached))
    state["offline"] = True
    offline = _request(host, "GET", f"/api/v1/models/installed?connection={identity}", **auth)[2]
    assert offline["stale"] and offline["checked_at"] == data["checked_at"]
    assert "private_extra" not in json.dumps(offline)
    assert _request(host, "GET", "/api/v1/models/store")[0] == 401


def test_review_pull_duplicate_receipt_and_delete_do_not_select_models(native):
    host, service, auth, state, identity = native
    before = host.application.agent.model
    review = _review(host, auth, draft(identity))
    assert not any(method == "POST" for method, _ in state["calls"])
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert state["calls"].count(("POST", "/api/pull")) == 1
    assert host.application.agent.model == before
    assert not (service.data / "chat-preferences.json").exists()
    jobs = _request(host, "GET", "/api/v1/models/downloads", **auth)[2]
    assert jobs["items"][0]["model"] == "fresh:1b"
    # A new service instance reads the same durable receipt and exact target.
    reopened = LibraryManagement(service.cfg, service.workspace)
    try:
        assert reopened.model_jobs()["items"][0]["model"] == "fresh:1b"
    finally:
        reopened.close()
    review = _review(host, auth, draft(identity, "model-delete"))
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert state["models"] == []


def test_lan_csrf_and_exact_tag_validation(native):
    host, _, auth, state, identity = native
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/review",
            body={"draft": draft(identity)},
            **{**auth, "csrf": "invalid"},
        )[0]
        == 403
    )
    for model in ["fresh", "https://bad.invalid/model", "../bad", "x:tag\n"]:
        assert (
            _request(
                host,
                "POST",
                "/api/v1/library/review",
                body={"draft": draft(identity, model=model)},
                **auth,
            )[0]
            == 400
        )
    review = _review(host, auth, draft(identity))
    host.http.host_lan = True
    assert (
        _request(host, "POST", "/api/v1/library/review", body={"draft": draft(identity)}, **auth)[0]
        == 403
    )
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/submit",
            body={
                "review_id": review["review_id"],
                "request_id": uuid.uuid4().hex,
                "control_epoch": 0,
            },
            **auth,
        )[0]
        == 403
    )
    assert not any(method == "POST" for method, _ in state["calls"])


def test_loaded_and_default_roles_protect_deletion(native):
    host, service, auth, state, identity = native
    state["models"] = [{"name": "fresh:1b", "digest": "a" * 64, "size": 100}]
    state["running"] = state["models"][:]
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/review",
            body={"draft": draft(identity, "model-delete")},
            **auth,
        )[0]
        == 400
    )
    state["running"] = []
    review = _review(host, auth, draft(identity, "model-delete"))
    update_settings(
        service.data / "chat-preferences.json", {"default_model_ref": f"ollama@{identity}/fresh:1b"}
    )
    # The worker rechecks protections after review, before any DELETE.
    state["running"] = state["models"][:]
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not any(method == "DELETE" for method, _ in state["calls"])


def test_cancel_is_unknown_progress_and_no_automatic_retry(native):
    host, service, auth, state, identity = native
    state["slow"] = True
    review = _review(host, auth, draft(identity))
    other = _review(host, auth, draft(identity, model="another:1b"))
    request_id = uuid.uuid4().hex
    status, _, _ = _request(
        host,
        "POST",
        "/api/v1/library/submit",
        body={"review_id": review["review_id"], "request_id": request_id, "control_epoch": 0},
        **auth,
    )
    assert status == 202
    assert _request(host, "POST", "/api/v1/models/dismiss",
                    body={"request_id": request_id}, **auth)[0] == 409
    for _ in range(100):
        if service.model_jobs()["items"][0]["progress"]:
            break
        time.sleep(0.05)
    assert service.model_jobs()["items"][0]["progress"]
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/submit",
            body={
                "review_id": other["review_id"],
                "request_id": uuid.uuid4().hex,
                "control_epoch": 0,
            },
            **auth,
        )[0]
        == 409
    )
    assert (
        _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "during-download", "text": "hello", "disposition": "auto"},
            **auth,
        )[0]
        == 202
    )
    assert (
        _request(host, "POST", "/api/v1/models/cancel", body={"request_id": request_id}, **auth)[0]
        == 200
    )
    assert _wait(service, request_id)["state"] == "unknown"
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["chat_model_blocked"] is False
    assert _request(host, "POST", "/api/v1/turns", body={
        "request_id": "after-stopped-download", "text": "still usable", "disposition": "auto",
    }, **auth)[0] == 202
    assert service.model_busy()
    assert (
        _request(host, "POST", "/api/v1/models/reconcile", body={"request_id": request_id}, **auth)[
            0
        ]
        == 409
    )
    assert state["calls"].count(("POST", "/api/pull")) == 1
    # The server later reports the desired installation; explicit reconciliation
    # records the observation, never a second POST /api/pull.
    state["models"] = [{"name": "fresh:1b", "digest": "a" * 64, "size": 100},
                       {"name": "different:1b", "digest": "b" * 64, "size": 100}]
    target = model_store.target_path(service.cfg, request_id)
    original = target.read_text()
    target.write_text(json.dumps({**json.loads(original), "model": "different:1b"}))
    assert _request(host, "POST", "/api/v1/models/reconcile", body={"request_id": request_id},
                    **auth)[0] == 409
    assert service.model_busy()
    target.write_text(original)
    assert (
        _request(host, "POST", "/api/v1/models/reconcile", body={"request_id": request_id}, **auth)[
            2
        ]["state"]
        == "completed"
    )
    assert not service.model_busy()


def test_seed_capabilities_and_strict_limits(profile_browser, generation_lab):
    _, service, _, _ = profile_browser
    enable(generation_lab)
    caps = image_capabilities(service.cfg)
    assert caps["available"] and caps["backend"] == "stable-diffusion.cpp"
    assert "endpoint" not in caps and "prompt" not in caps
    values = {
        "operation": "image-generate",
        "prompt": "test",
        "width": 512,
        "height": 512,
        "steps": 10,
        "seed": 42,
    }
    fields, _, summary = prepare_generated_operation(service.cfg, values)
    assert fields["spec"]["seed"] == 42 and "seed 42" in summary
    for invalid in [
        {"seed": 2**32},
        {"seed": True},
        {"width": 4096},
        {"steps": 51},
        {"sampler": "unvalidated"},
    ]:
        with pytest.raises(ValueError):
            prepare_generated_operation(service.cfg, {**values, **invalid})
    assert model_store.discovery()["models"]


def test_atomic_model_exclusion_across_journal_instances(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from klaude_application.operation_journal import OperationConflict, OperationJournal

    path = tmp_path / 'operations.db'
    first, second = OperationJournal(path), OperationJournal(path)
    barrier = threading.Barrier(2)

    def admit(journal, model):
        barrier.wait()
        try:
            return journal.admit(
                request_id=uuid.uuid4().hex, owner_id='web-admin',
                kind='model-pull' if model else 'image-generate',
                resource=model_store.RESOURCE if model else 'image:test', payload={},
                conflicts_with=() if model else (model_store.RESOURCE,), exclusive=model,
            )
        except OperationConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(admit, first, True)
        b = pool.submit(admit, second, False)
        assert sum(result is not None for result in [a.result(), b.result()]) == 1


def test_private_credential_capture_never_enters_job_projection(native, monkeypatch):
    from dataclasses import replace

    from klaude_core.model_connections import connection_registry

    _, service, _, _, identity = native
    connection = legacy_connections(service.cfg)[0]
    registry = connection_registry(service.cfg)
    registry.migrate(service.cfg)
    registry.add(replace(connection, id="private-native", key_env="PRIVATE_MODEL_TOKEN"))
    identity = "private-native"
    monkeypatch.setenv('PRIVATE_MODEL_TOKEN', 'test-private-value')
    fields, _, _ = model_store.prepare(service.cfg, draft(identity))
    assert fields['environment_keys']['PRIVATE_MODEL_TOKEN'] == 'test-private-value'
    request_id = uuid.uuid4().hex
    model_store.save_target(service.cfg, request_id, fields)
    assert 'test-private-value' not in model_store.target_path(service.cfg, request_id).read_text()
