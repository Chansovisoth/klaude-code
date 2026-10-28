"""Native image service boundaries, owned jobs and retained Media provenance."""

import base64
import json
import queue
import struct
import threading
import time
import uuid
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_core import image_generation as gen
from klaude_core.library_artifacts import ArtifactStore


def test_shared_image_generation_command_is_fixed_and_private(tmp_path):
    from klaude_application.image_generation import ImageGenerationCommand

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    command = ImageGenerationCommand.for_client(
        cfg, "prepare", prompt="private prompt", options={"width": 512}
    )
    request = command.worker_request()
    assert ImageGenerationCommand.from_worker(request).worker_request() == request
    assert "private prompt" not in repr(command)
    with pytest.raises(ValueError, match="Invalid image generation"):
        ImageGenerationCommand.from_worker({**request, "operation": "arbitrary"})
    with pytest.raises(ValueError, match="Invalid image generation"):
        ImageGenerationCommand.from_worker({**request, "shell": "unexpected"})


def test_journaled_image_settings_recover_after_lost_ack(tmp_path, monkeypatch):
    from klaude_application.image_settings import (
        ImageSettingsUnconfirmed,
        image_settings_resource,
        recover_image_settings,
        save_image_settings,
    )
    from klaude_application.operation_journal import OperationJournal

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    journal = OperationJournal(cfg.data_dir / "operations.db")
    request_id = uuid.uuid4().hex

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    with pytest.raises(ImageSettingsUnconfirmed, match="recover"):
        save_image_settings(
            cfg, {"enabled": False, "endpoint": "", "model": ""}, "",
            journal, request_id, "cli",
        )
    original = gen.read(cfg)
    assert original["revision"]
    assert journal.resource_busy(image_settings_resource(cfg.config_dir))
    recovered = OperationJournal(journal.path)
    receipt = recover_image_settings(cfg, recovered, request_id, "cli")
    assert receipt.state == "completed"
    assert not recovered.resource_busy(image_settings_resource(cfg.config_dir))
    assert gen.read(cfg) == original


def test_journaled_image_settings_lost_start_ack_has_recovery_path(tmp_path, monkeypatch):
    from klaude_application.image_settings import (
        ImageSettingsUnconfirmed,
        recover_image_settings,
        save_image_settings,
    )
    from klaude_application.operation_journal import OperationJournal

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    journal = OperationJournal(cfg.data_dir / "operations.db")
    request_id = uuid.uuid4().hex
    start = journal.start

    def lose_start_ack(*args):
        start(*args)
        raise OSError("start acknowledgement lost")

    monkeypatch.setattr(journal, "start", lose_start_ack)
    with pytest.raises(ImageSettingsUnconfirmed, match="recover"):
        save_image_settings(
            cfg, {"enabled": False, "endpoint": "", "model": ""}, "",
            journal, request_id, "cli",
        )
    assert gen.read(cfg)["revision"] == ""
    assert journal.status(request_id, "cli").state == "unknown"
    assert recover_image_settings(
        cfg, OperationJournal(journal.path), request_id, "cli",
    ).state == "failed"


def test_journaled_image_settings_prior_state_and_changed_state(tmp_path, monkeypatch):
    from klaude_application.image_settings import (
        ImageSettingsUnconfirmed,
        image_settings_resource,
        recover_image_settings,
        save_image_settings,
    )
    from klaude_application.operation_journal import OperationConflict, OperationJournal

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    journal = OperationJournal(cfg.data_dir / "operations.db")
    request_id = uuid.uuid4().hex
    original_write = gen.atomic_write_private

    def fail_publish(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(gen, "atomic_write_private", fail_publish)
    with pytest.raises(ImageSettingsUnconfirmed):
        save_image_settings(
            cfg, {"enabled": False, "endpoint": "", "model": ""}, "",
            journal, request_id, "cli",
        )
    assert gen.read(cfg)["revision"] == ""
    assert recover_image_settings(
        cfg, OperationJournal(journal.path), request_id, "cli",
    ).state == "failed"
    monkeypatch.setattr(gen, "atomic_write_private", original_write)

    current = gen.save(cfg, {"enabled": False, "endpoint": "", "model": ""}, "")
    request_id = uuid.uuid4().hex

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    with pytest.raises(ImageSettingsUnconfirmed):
        save_image_settings(
            cfg, {"enabled": False, "endpoint": "", "model": ""},
            current["revision"], journal, request_id, "cli",
        )
    changed = gen.read(cfg)
    gen.save(cfg, {"enabled": False, "endpoint": "", "model": ""}, changed["revision"])
    with pytest.raises(OperationConflict, match="differs from both"):
        recover_image_settings(cfg, OperationJournal(journal.path), request_id, "cli")
    assert journal.resource_busy(image_settings_resource(cfg.config_dir))


def test_image_settings_worker_save_uses_same_journal(tmp_path):
    from klaude_application.image_generation import ImageGenerationCommand
    from klaude_application.operation_journal import OperationJournal

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    request_id = uuid.uuid4().hex
    command = ImageGenerationCommand.for_client(
        cfg, "save", settings={"enabled": False, "endpoint": "", "model": ""},
        revision="", request_id=request_id, owner_id="cli",
    )
    assert ImageGenerationCommand.from_worker(command.worker_request()).execute()[
        "settings"
    ]["revision"]
    receipt = OperationJournal(cfg.data_dir / "operations.db").status(request_id, "cli")
    assert receipt is not None and receipt.state == "completed"


def test_invalid_image_settings_worker_does_not_probe_network(tmp_path, monkeypatch):
    from klaude_application.image_generation import ImageGenerationCommand

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    monkeypatch.setattr(gen, "inspect", lambda *_: pytest.fail("No network probe"))
    command = ImageGenerationCommand.for_client(
        cfg, "save", settings={"enabled": "yes", "endpoint": "http://localhost:1234",
                               "model": "invalid"},
        revision="", request_id=uuid.uuid4().hex, owner_id="cli",
    )
    assert command.execute()["status"] == "error"
    assert not (cfg.data_dir / "operations.db").exists()


def test_cli_image_service_recovery_checks_exact_state(tmp_path, monkeypatch, capsys):
    from klaude_application.image_settings import ImageSettingsUnconfirmed, save_image_settings
    from klaude_application.operation_journal import OperationJournal
    from klaude_cli import library_commands

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    journal = OperationJournal(cfg.data_dir / "operations.db")
    request_id = uuid.uuid4().hex

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    with pytest.raises(ImageSettingsUnconfirmed):
        save_image_settings(
            cfg, {"enabled": False, "endpoint": "", "model": ""}, "",
            journal, request_id, "cli",
        )
    monkeypatch.setattr(library_commands, "load_config", lambda: cfg)
    library_commands.image_service_recover(yes=True)
    assert "Recovered" in capsys.readouterr().out
    assert OperationJournal(journal.path).status(request_id, "cli").state == "completed"


def test_image_settings_writer_requires_journal(tmp_path):
    from klaude_cli.session_actions import ImageGenerationUpdate, SessionActionWriter

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    events = queue.Queue()
    writer = SessionActionWriter(
        object(), lambda kind, value: events.put((kind, value)),
        require_image_journal=True,
    )
    request = ImageGenerationUpdate(
        "session", uuid.uuid4().hex, cfg,
        {"enabled": False, "endpoint": "", "model": ""}, "",
    )
    assert writer.submit(request)
    assert not writer.close(wait=True)
    kind, payload = events.get(timeout=2)
    assert kind == "image_generation_saved" and "journal unavailable" in payload[2]
    assert not (cfg.config_dir / "image-generation.json").exists()


def test_image_settings_writer_records_completed_receipt(tmp_path):
    from klaude_application.operation_journal import OperationJournal
    from klaude_cli.session_actions import ImageGenerationUpdate, SessionActionWriter

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    journal = OperationJournal(cfg.data_dir / "operations.db")
    events = queue.Queue()
    writer = SessionActionWriter(
        object(), lambda kind, value: events.put((kind, value)),
        image_journal=journal, require_image_journal=True,
    )
    request_id = uuid.uuid4().hex
    request = ImageGenerationUpdate(
        "session", request_id, cfg,
        {"enabled": False, "endpoint": "", "model": ""}, "",
    )
    assert writer.submit(request)
    assert writer.close(wait=True)
    kind, payload = events.get(timeout=2)
    assert kind == "image_generation_saved" and not payload[2]
    assert journal.status(request_id, "session").state == "completed"


def png(width=512, height=512):
    def part(kind, content):
        return (
            struct.pack(">I", len(content))
            + kind
            + content
            + struct.pack(">I", zlib.crc32(kind + content))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + part(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + part(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0" * width) * height))
        + part(b"IEND", b"")
    )


@pytest.fixture
def generation_lab(tmp_path):
    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    caps = {
        "model": {"name": "local-test-model"},
        "supported_modes": ["img_gen"],
        "output_formats_by_mode": {"img_gen": ["png"]},
        "defaults_by_mode": {
            "img_gen": {"sample_params": {"sample_method": "euler", "scheduler": "discrete"}}
        },
        "samplers": ["euler"],
        "schedulers": ["discrete"],
        "features_by_mode": {"img_gen": {"cancel_queued": True, "cancel_generating": True}},
        "limits": {"min_width": 256, "max_width": 2048, "min_height": 256, "max_height": 2048},
    }
    calls = []
    state = {
        "wait": False,
        "bad_id": False,
        "bad_image": False,
        "lost": False,
        "cancelled": False,
        "changed": False,
        "finish_on_cancel": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, data, code=200):
            payload = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            calls.append(("GET", self.path, None))
            if self.path.endswith("/capabilities"):
                self.answer(caps)
                return
            if self.path == "/sdcpp/v1/jobs/job_test":
                status = (
                    "cancelled"
                    if state["cancelled"]
                    else "failed"
                    if state.get("failed")
                    else "generating"
                    if state["wait"]
                    else "completed"
                )
                if state["changed"]:
                    caps["model"]["name"] = "different-model"
                self.answer(
                    {
                        "id": "wrong" if state["bad_id"] else "job_test",
                        "kind": "img_gen",
                        "status": status,
                        "result": {
                            "images": [
                                {
                                    "b64_json": "bad"
                                    if state["bad_image"]
                                    else base64.b64encode(png()).decode()
                                }
                            ]
                        },
                    }
                )
                return
            self.answer({}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(("POST", self.path, body))
            if self.path == "/sdcpp/v1/img_gen":
                if state["lost"]:
                    self.answer({}, 500)
                    return
                self.answer({"id": "job_test", "kind": "img_gen", "status": "queued"}, 202)
                return
            if self.path == "/sdcpp/v1/jobs/job_test/cancel":
                if state["wait"] and not caps["features_by_mode"]["img_gen"]["cancel_generating"]:
                    self.answer({"error": "job is generating"}, 409)
                    return
                state["cancelled"] = not state["finish_on_cancel"]
                if state["finish_on_cancel"]:
                    state["wait"] = False
                self.answer({"status": "completed" if state["finish_on_cancel"] else "cancelled"})
                return
            self.answer({}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield cfg, url, caps, calls, state
    finally:
        server.shutdown()
        server.server_close()


def enable(lab):
    cfg, url, *_ = lab
    gen.save(cfg, {"enabled": True, "endpoint": url, "model": "local-test-model"}, "")


def test_disabled_never_contacts_service(generation_lab):
    cfg, _, _, calls, _ = generation_lab
    assert gen.read(cfg)["enabled"] is False
    with pytest.raises(ValueError, match="OFF"):
        gen.prepare(cfg, "An icon")
    assert not calls and not cfg.data_dir.exists()


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/server",
        "http://u:secret@host",
        "http://host/?key=secret",
        "http://host/#x",
        "http://host/\n",
        "http://host/\\x",
    ],
)
def test_endpoint_rejects_unsafe_values(url):
    with pytest.raises(ValueError):
        gen.endpoint(url)


def test_inspection_is_metadata_only_and_requires_capabilities(generation_lab):
    _, url, caps, calls, _ = generation_lab
    assert gen.inspect(url)["model"] == "local-test-model"
    assert all(method == "GET" for method, _, _ in calls)
    caps["supported_modes"] = ["vid_gen"]
    with pytest.raises(ValueError, match="does not declare"):
        gen.inspect(url)


@pytest.mark.parametrize(
    "options",
    [
        {"width": 255},
        {"height": 1088},
        {"width": True},
        {"steps": 0},
        {"steps": 51},
        {"seed": -2},
        {"seed": 2**32},
    ],
)
def test_invalid_budgets_never_generate(generation_lab, options):
    enable(generation_lab)
    cfg, _, _, calls, _ = generation_lab
    with pytest.raises(ValueError):
        gen.prepare(cfg, "A button", **options)
    assert all(method == "GET" for method, _, _ in calls)


def test_revisions_reject_stale_save_and_loaded_model(generation_lab):
    enable(generation_lab)
    cfg, _, caps, _, _ = generation_lab
    with pytest.raises(ValueError, match="Reload"):
        gen.save(cfg, gen.read(cfg), "")
    spec = gen.prepare(cfg, "A button")
    caps["model"]["name"] = "changed"
    with pytest.raises(ValueError, match="loaded model changed"):
        gen.run(cfg, spec)
    assert not (cfg.data_dir / "image-generation").exists()


def test_generated_pixels_and_provenance_are_atomic_private_and_independent(generation_lab):
    enable(generation_lab)
    cfg, _, _, calls, _ = generation_lab
    spec = gen.prepare(cfg, "A private purple button", session="session-one", seed=42)
    result = gen.run(cfg, spec)
    assert result["status"] == "complete"
    store = ArtifactStore(cfg.data_dir / "library")
    item = store.get(result["artifact"])
    assert item["job"] == spec["id"] and item["session"] == "session-one"
    assert not item["tags"] and item["model"] == "local-test-model"
    info = store.generation_info(item["id"])
    assert (
        info["prompt"] == spec["prompt"] and info["seed"] == 42 and info["remote_id"] == "job_test"
    )
    assert not (cfg.data_dir / "sessions.db").exists()
    assert "purple" not in str(store.listing("media"))
    assert gen.job(cfg, spec["id"])["artifact"] == item["id"]
    assert gen.job_path(cfg, spec["id"]).stat().st_mode & 0o777 == 0o600
    post = [data for method, path, data in calls if method == "POST" and path.endswith("/img_gen")]
    assert (
        len(post) == 1 and post[0]["batch_count"] == 1 and post[0]["embed_image_metadata"] is False
    )
    with pytest.raises(ValueError, match="already accepted"):
        gen.run(cfg, spec)
    archived = store.change(item["id"], item["revision"], "archive")
    assert store.generation_info(item["id"]) == info
    store.change(item["id"], archived["revision"], "delete")
    with store.database() as db:
        assert not db.execute("SELECT * FROM generated_images").fetchall()


@pytest.mark.parametrize("failure", ["bad_id", "bad_image", "changed", "lost"])
def test_invalid_or_uncertain_generation_does_not_save_or_retry(generation_lab, failure):
    enable(generation_lab)
    cfg, _, _, calls, state = generation_lab
    state[failure] = True
    spec = gen.prepare(cfg, "A button")
    with pytest.raises(ValueError):
        gen.run(cfg, spec)
    assert ArtifactStore(cfg.data_dir / "library").listing("media")["items"] == []
    assert sum(method == "POST" and path == "/sdcpp/v1/img_gen" for method, path, _ in calls) == 1
    outcome = gen.cancel(cfg, spec["id"])
    assert outcome["cleanup"] == ("Unconfirmed" if failure in {"lost", "bad_id"} else "Confirmed")
    assert not any(path.endswith("/interrupt") for _, path, _ in calls)


def test_owned_cancel_reaps_before_scoped_server_cleanup(generation_lab):
    enable(generation_lab)
    cfg, _, _, calls, state = generation_lab
    state["wait"] = True
    spec = gen.prepare(cfg, "A button")
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put((kind, value)))
    request = {
        "kind": "image_generation",
        "operation": "run",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "spec": spec,
    }
    identity = jobs.submit("image", request, timeout=20, notify_cancel=True)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if gen.job_path(cfg, spec["id"]).exists() and gen.job(cfg, spec["id"]).get("remote_id"):
                break
            time.sleep(0.02)
        else:
            pytest.fail("Owned worker did not accept job")
        jobs.cancel("image")
        kind, payload = events.get(timeout=5)
        assert kind == "background_stopped" and payload == ("image", identity)
        assert gen.cancel(cfg, spec["id"])["cleanup"] == "Confirmed"
        assert state["cancelled"]
        assert sum(path == "/sdcpp/v1/jobs/job_test/cancel" for _, path, _ in calls) == 1
    finally:
        jobs.close(wait=True)


def test_cancel_recovers_atomic_output_when_final_receipt_write_is_lost(
    generation_lab, monkeypatch
):
    enable(generation_lab)
    cfg, _, _, calls, _ = generation_lab
    spec = gen.prepare(cfg, "An icon")
    original = gen.publish

    def fail_last(cfg, record):
        if record.get("artifact"):
            raise OSError("Simulated receipt failure after commit")
        original(cfg, record)

    monkeypatch.setattr(gen, "publish", fail_last)
    with pytest.raises(OSError):
        gen.run(cfg, spec)
    monkeypatch.setattr(gen, "publish", original)
    assert gen.cancel(cfg, spec["id"])["status"] == "complete"
    assert len(ArtifactStore(cfg.data_dir / "library").listing("media")["items"]) == 1
    assert not any(path.endswith("/cancel") for _, path, _ in calls)


def test_generation_settings_drain_without_a_session_database(generation_lab):
    from klaude_cli.session_actions import ImageGenerationUpdate, SessionActionWriter

    cfg, url, *_ = generation_lab
    events = queue.Queue()
    writer = SessionActionWriter(object(), lambda kind, value: events.put((kind, value)))
    update = ImageGenerationUpdate(
        "session", "save", cfg, {"enabled": True, "endpoint": url, "model": "local-test-model"}, ""
    )
    assert writer.submit(update)
    assert writer.close(wait=True)
    kind, result = events.get(timeout=2)
    assert kind == "image_generation_saved" and result[0] == update and not result[2]
    assert gen.read(cfg)["enabled"]
    assert not (cfg.data_dir / "sessions.db").exists()


def test_late_failure_cleans_captured_root_without_replacing_new_session(generation_lab):
    from klaude_cli.generation_panel import GenerationPanel

    enable(generation_lab)
    cfg, *_ = generation_lab
    requests = []
    host = SimpleNamespace(
        cfg=SimpleNamespace(config_dir=cfg.config_dir / "new", data_dir=cfg.data_dir / "new"),
        session_id="new-session",
        _start_next=lambda: None,
        _background_jobs=SimpleNamespace(
            submit=lambda key, request, **kw: requests.append(request) or "cleanup"
        ),
    )
    library = SimpleNamespace(host=host, scope="new-scope", visible=False, view="home")
    panel = GenerationPanel(library)
    panel.roots = (str(cfg.config_dir), str(cfg.data_dir))
    panel.spec = gen.prepare(cfg, "A button")
    panel.task = ("original", "old-session", "old-scope", "run")
    panel.accept("original", {"status": "error", "message": "Lost reply"}, "")
    assert requests[0]["config_dir"] == str(cfg.config_dir)
    assert requests[0]["data_dir"] == str(cfg.data_dir)
    assert panel.task[1:3] == ("old-session", "old-scope")
    panel.accept("cleanup", {"status": "cancelled", "message": "Confirmed"}, "")
    assert not panel.busy and panel.result == {} and library.view == "home"


def test_graceful_shutdown_reaps_and_cancels_accepted_job(generation_lab):
    from klaude_cli.generation_panel import GenerationPanel

    enable(generation_lab)
    cfg, _, _, _, state = generation_lab
    spec = gen.prepare(cfg, "An icon")
    record = {**spec, "status": "running", "remote_id": "job_test"}
    gen.publish(cfg, record)
    host = SimpleNamespace(cfg=cfg)
    panel = GenerationPanel(SimpleNamespace(host=host))
    panel.roots = (str(cfg.config_dir), str(cfg.data_dir))
    panel.spec, panel.task = spec, ("request", "session", "scope", "run")
    assert "Confirmed" in panel.finish_shutdown()
    assert state["cancelled"] and not panel.busy


@pytest.mark.parametrize(
    "value,expected",
    [
        ("http://localhost:8080/sdcpp/v1/", "http://localhost:8080"),
        ("http://localhost:8080/prefix/sdcpp/v1", "http://localhost:8080/prefix"),
        ("http://localhost:8080/prefix", "http://localhost:8080/prefix"),
    ],
)
def test_native_endpoint_suffix_preserves_gateway_prefix(value, expected):
    assert gen.endpoint(value) == expected


def test_generation_settings_failure_is_not_reported_as_drained_success(
    generation_lab, monkeypatch
):
    from klaude_cli.session_actions import ImageGenerationUpdate, SessionActionWriter

    cfg, url, *_ = generation_lab

    def fail(*args):
        raise OSError("Simulated storage failure")

    monkeypatch.setattr(gen, "save", fail)
    events = queue.Queue()
    writer = SessionActionWriter(object(), lambda kind, value: events.put((kind, value)))
    update = ImageGenerationUpdate(
        "session", "save", cfg, {"enabled": True, "endpoint": url, "model": "local-test-model"}, ""
    )
    assert writer.submit(update)
    assert not writer.close(wait=True)
    kind, result = events.get(timeout=2)
    assert kind == "image_generation_saved" and result[1] is None and "unconfirmed" in result[2]


def accepted_job(lab):
    enable(lab)
    cfg, *_ = lab
    spec = gen.prepare(cfg, "A recovered blue tool icon", seed=42)
    gen.publish(cfg, {**spec, "status": "running", "remote_id": "job_test", "created": 1.0})
    return spec


def test_cancel_completion_race_retains_recoverable_state(generation_lab):
    cfg, _, _, calls, state = generation_lab
    spec = accepted_job(generation_lab)
    state["finish_on_cancel"] = True
    result = gen.cancel(cfg, spec["id"])
    assert result["status"] == "completed_remote"
    assert result["cleanup"] == "Confirmed"
    assert result["recoverable"]
    assert "completed" in result["message"].lower()
    assert gen.job(cfg, spec["id"])["status"] == "completed_remote"
    assert not ArtifactStore(cfg.data_dir / "library").listing("media")["items"]
    assert not any(path.endswith("/img_gen") for _, path, _ in calls)


def test_explicit_recovery_saves_once_without_submission(generation_lab):
    cfg, _, _, calls, _ = generation_lab
    spec = accepted_job(generation_lab)
    result = gen.recover(cfg, spec["id"])
    assert result["status"] == "complete"
    item = ArtifactStore(cfg.data_dir / "library").get(result["artifact"])
    assert item["job"] == spec["id"] and item["model"] == "local-test-model"
    first_calls = len(calls)
    assert gen.recover(cfg, spec["id"])["artifact"] == item["id"]
    assert len(calls) == first_calls
    assert all(method == "GET" for method, _, _ in calls)
    assert gen.job(cfg, spec["id"])["artifact"] == item["id"]


@pytest.mark.parametrize("failure", ["bad_id", "bad_image", "changed"])
def test_recovery_rechecks_identity_pixels_and_binding(generation_lab, failure):
    cfg, _, caps, calls, state = generation_lab
    spec = accepted_job(generation_lab)
    if failure == "changed":
        caps["model"]["name"] = "changed"
    else:
        state[failure] = True
    with pytest.raises(ValueError):
        gen.recover(cfg, spec["id"])
    assert not ArtifactStore(cfg.data_dir / "library").listing("media")["items"]
    assert all(method == "GET" for method, _, _ in calls)


def test_recovery_cannot_resurrect_a_deleted_saved_image(generation_lab):
    cfg, _, _, calls, _ = generation_lab
    spec = accepted_job(generation_lab)
    result = gen.recover(cfg, spec["id"])
    store = ArtifactStore(cfg.data_dir / "library")
    item = store.get(result["artifact"])
    archived = store.change(item["id"], item["revision"], "archive")
    store.change(item["id"], archived["revision"], "delete")
    count = len(calls)
    with pytest.raises(ValueError, match="removed"):
        gen.recover(cfg, spec["id"])
    assert len(calls) == count


def test_recovery_rejects_changed_review_and_incomplete_output(generation_lab):
    cfg, _, _, calls, state = generation_lab
    spec = accepted_job(generation_lab)
    reviewed = gen.recovery_review(cfg, spec["id"])
    changed = {**gen.job(cfg, spec["id"]), "prompt": "A different prompt"}
    gen.publish(cfg, changed)
    count = len(calls)
    with pytest.raises(ValueError, match="receipt changed"):
        gen.recover(cfg, spec["id"], reviewed)
    assert not any(path.startswith("/sdcpp/v1/jobs/") for _, path, _ in calls[count:])
    state["wait"] = True
    with pytest.raises(ValueError, match="not complete"):
        gen.recover(cfg, spec["id"])
    assert not ArtifactStore(cfg.data_dir / "library").listing("media")["items"]
    assert all(method == "GET" for method, _, _ in calls)


def test_receipt_cannot_redirect_job_identity(generation_lab):
    cfg, *_ = generation_lab
    spec = accepted_job(generation_lab)
    path = gen.job_path(cfg, spec["id"])
    path.write_text(json.dumps({**gen.job(cfg, spec["id"]), "id": "0" * 32}))
    with pytest.raises(ValueError, match="identity changed"):
        gen.recover(cfg, spec["id"])


def test_native_automatic_sampler_and_queue_only_cancel(generation_lab):
    enable(generation_lab)
    cfg, _, caps, calls, _ = generation_lab
    caps["defaults_by_mode"]["img_gen"]["sample_params"] = {
        "sample_method": "default", "scheduler": "default"
    }
    caps["features_by_mode"]["img_gen"]["cancel_generating"] = False
    spec = gen.prepare(cfg, "A native server default image")
    assert spec["evidence"]["sampler"] == "default"
    assert not spec["evidence"]["cancel_generating"]
    assert gen.run(cfg, spec)["status"] == "complete"
    payload = next(body for method, path, body in calls if path.endswith("/img_gen"))
    assert "sample_method" not in payload["sample_params"]
    assert "scheduler" not in payload["sample_params"]


def test_uncancellable_running_job_is_observed_and_recoverable(generation_lab):
    cfg, _, caps, calls, state = generation_lab
    caps["features_by_mode"]["img_gen"]["cancel_generating"] = False
    spec = accepted_job(generation_lab)
    state["wait"] = True
    result = gen.cancel(cfg, spec["id"])
    assert result["cleanup"] == "Unconfirmed" and result["status"] == "running_remote"
    assert "still generating" in result["message"]
    assert calls[-1][:2] == ("GET", "/sdcpp/v1/jobs/job_test")
    state["wait"] = False
    assert gen.recover(cfg, spec["id"])["status"] == "complete"
    assert not any(path.endswith("/img_gen") for _, path, _ in calls)


def test_queue_cancellation_still_required(generation_lab):
    enable(generation_lab)
    cfg, _, caps, calls, _ = generation_lab
    caps["features_by_mode"]["img_gen"]["cancel_queued"] = False
    with pytest.raises(ValueError, match="queued"):
        gen.prepare(cfg, "A safe request")
    assert all(method == "GET" for method, _, _ in calls)


def test_native_cancellation_limit_visible_before_acceptance(generation_lab):
    from klaude_cli.generation_panel import GenerationPanel

    enable(generation_lab)
    cfg, _, caps, _, _ = generation_lab
    caps["features_by_mode"]["img_gen"]["cancel_generating"] = False
    panel = GenerationPanel(SimpleNamespace(host=SimpleNamespace(), view="generation-review"))
    panel.spec = gen.prepare(cfg, "A reviewed image")
    rows = {row.id: row for row in panel.page().rows}
    assert rows["cancellation"].value_tone == "warning"
    assert "server may continue" in rows["cancellation"].description


def test_unacknowledged_submission_does_not_offer_output_recovery(generation_lab):
    from klaude_cli.generation_panel import GenerationPanel

    enable(generation_lab)
    cfg, _, _, calls, _ = generation_lab
    spec = gen.prepare(cfg, "An uncertain submission")
    gen.publish(cfg, {**spec, "status": "submitting"})
    result = gen.cancel(cfg, spec["id"])
    assert result["status"] == "unknown" and not result["recoverable"]
    panel = GenerationPanel(SimpleNamespace(host=SimpleNamespace(), view="generation-result"))
    panel.spec, panel.result = spec, result
    assert "recovery-review" not in {row.id for row in panel.page().rows}
    assert not any(path.startswith("/sdcpp/v1/jobs/") for _, path, _ in calls)


def test_history_is_metadata_only_and_forgetting_preserves_media(generation_lab):
    cfg, _, _, calls, _ = generation_lab
    spec = accepted_job(generation_lab)
    result = gen.recover(cfg, spec["id"])
    count = len(calls)
    listing = gen.history(cfg)
    assert listing["items"][0]["job"] == spec["id"]
    assert spec["prompt"] not in json.dumps(listing) and len(calls) == count
    record = gen.job(cfg, spec["id"])
    with pytest.raises(ValueError, match="changed"):
        gen.forget(cfg, spec["id"], {**record, "status": "cancelled"})
    assert gen.forget(cfg, spec["id"], record)["status"] == "forgotten"
    assert gen.history(cfg)["items"] == [] and len(calls) == count
    assert ArtifactStore(cfg.data_dir / "library").get(result["artifact"])["job"] == spec["id"]


def test_history_paging_and_invalid_receipts_are_bounded(generation_lab):
    cfg, *_ = generation_lab
    spec = accepted_job(generation_lab)
    for number in range(101):
        gen.publish(cfg, {**spec, "id": f"{number:032x}", "status": "cancelled", "created": number})
    gen.job_path(cfg, "f" * 32).write_text("invalid")
    first, second = gen.history(cfg), gen.history(cfg, 100)
    assert len(first["items"]) == 100 and first["more"] and first["invalid"] == 1
    assert len(second["items"]) == 2 and not second["more"]
    assert not ({x["job"] for x in first["items"]} & {x["job"] for x in second["items"]})


def test_explicit_refresh_does_not_cancel_or_submit_and_active_receipt_is_protected(generation_lab):
    cfg, _, _, calls, state = generation_lab
    spec = accepted_job(generation_lab)
    with pytest.raises(ValueError, match="before removing"):
        gen.forget(cfg, spec["id"], gen.job(cfg, spec["id"]))
    state["wait"] = True
    result = gen.refresh(cfg, spec["id"])
    assert result["status"] == "running_remote" and result["recoverable"]
    state["bad_id"] = True
    with pytest.raises(ValueError, match="identity"):
        gen.refresh(cfg, spec["id"])
    assert all(method == "GET" for method, _, _ in calls)


def test_job_review_controls_and_cleanup_default_to_back(generation_lab):
    from klaude_cli.generation_panel import GenerationPanel
    from klaude_cli.settings_panel import PanelState, render_body

    cfg, *_ = generation_lab
    spec = accepted_job(generation_lab)
    library = SimpleNamespace(host=SimpleNamespace(), view="generation-cancel-review")
    panel = GenerationPanel(library)
    panel.spec = gen.job(cfg, spec["id"])
    for view in ("generation-cancel-review", "generation-forget-review"):
        library.view = view
        for width in (40, 70, 120):
            state = PanelState(panel.page(), "back")
            render_body(state, width)
            assert state.picker.selected_id == "back"


def test_cli_job_ids_are_complete_and_prompts_private(generation_lab, monkeypatch):
    from klaude_cli import library_commands
    from typer.testing import CliRunner

    cfg, *_ = generation_lab
    spec = accepted_job(generation_lab)
    monkeypatch.setattr(library_commands, "load_config", lambda: cfg)
    for width in (40, 80, 120):
        monkeypatch.setattr(library_commands.console, "_width", width)
        result = CliRunner().invoke(library_commands.app, ["generation-jobs"])
        assert result.exit_code == 0, result.stdout
        assert spec["id"] in result.stdout and spec["prompt"] not in result.stdout


def test_unknown_receipt_requires_explicit_abandonment_without_network(generation_lab):
    cfg, _, _, calls, _ = generation_lab
    spec = accepted_job(generation_lab)
    unknown = {**spec, "status": "unknown"}
    gen.publish(cfg, unknown)
    count = len(calls)
    with pytest.raises(ValueError, match="confirm abandoning"):
        gen.forget(cfg, spec["id"], unknown)
    assert gen.forget(cfg, spec["id"], unknown, abandon=True)["status"] == "forgotten"
    assert not gen.job_path(cfg, spec["id"]).exists() and len(calls) == count


def test_legacy_text_image_receipts_survive_additive_edit_capability(generation_lab):
    import hashlib

    enable(generation_lab)
    cfg, _, _, calls, _ = generation_lab
    spec = gen.prepare(cfg, 'A red apple')
    spec['evidence'].pop('img2img')
    spec['evidence'].pop('revision')
    spec['evidence']['revision'] = hashlib.sha256(
        json.dumps(spec['evidence'], sort_keys=True).encode()).hexdigest()
    gen.reviewed_binding(cfg, spec)
    result = gen.run(cfg, spec)
    assert result['status'] == 'complete'
    assert sum(path == '/sdcpp/v1/img_gen' for _, path, _ in calls) == 1
