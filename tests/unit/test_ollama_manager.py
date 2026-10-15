"""Native lifecycle protocol, stale reviews, scoped cache and workspace navigation."""

import json
import queue
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.model_manager import ModelManager, worker_request
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.config import save_provider_secret
from klaude_core.model_connections import ModelConnection, connection_registry, legacy_connections
from klaude_core.model_runtime import ModelInfo, load_model_cache, save_model_cache
from klaude_core.ollama_manager import ManagerError, execute_manager, model_name
from klaude_core.settings_store import update_settings
from prompt_toolkit.utils import get_cwidth
from typer.testing import CliRunner

from .test_model_settings import Host


@pytest.fixture
def cfg(tmp_path):
    item = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "keep:latest", "embed": "embedding:latest"},
        ollama_url="http://localhost:11434",
        huggingface_base_url="https://huggingface.co",
        huggingface_api_key="",
    )
    item.data_dir.mkdir()
    return item


def record(name="unused:latest", digest="a" * 64):
    return {
        "name": name,
        "digest": digest,
        "size": 1000,
        "details": {"parameter_size": "1B", "quantization_level": "Q4_K_M"},
    }


@pytest.fixture
def service(monkeypatch):
    requests = []
    models = [record(), record("keep:latest", "b" * 64)]
    running = []
    failure = {}
    original = httpx.Client

    def handle(request):
        requests.append(request)
        path = request.url.path
        if path in failure:
            return failure[path](request)
        if path == "/api/tags":
            return httpx.Response(200, json={"models": models})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": running})
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.fixture"})
        if path == "/api/pull":
            name = json.loads(request.content)["model"]
            models.append(record(name, "c" * 64))
            return httpx.Response(
                200,
                content=(
                    json.dumps({"status": "pulling manifest"})
                    + "\n"
                    + json.dumps({"status": "success"})
                    + "\n"
                ).encode(),
            )
        if path == "/api/delete":
            name = json.loads(request.content)["model"]
            models[:] = [m for m in models if m["name"] != name]
            return httpx.Response(200)
        if path == "/api/models":
            assert request.url.params["filter"] == "gguf"
            return httpx.Response(200, json=[{"id": "org/model-GGUF", "downloads": 42}])
        raise AssertionError(f"Unexpected model operation: {path}")

    monkeypatch.setattr(
        httpx, "Client", lambda *a, **kw: original(*a, **kw, transport=httpx.MockTransport(handle))
    )
    return SimpleNamespace(requests=requests, models=models, running=running, failure=failure)


def review(cfg, operation="delete", model="unused:latest", digest="a" * 64):
    connection = legacy_connections(cfg)[0]
    return {
        "operation": operation,
        "endpoint": connection.id,
        "model": model,
        "revision": connection.revision,
        "credential_revision": "",
        "digest": digest,
    }


def test_inventory_reads_only_and_keeps_native_roles_and_registry(cfg, service):
    result = execute_manager(cfg, {"operation": "inventory"})
    assert [r.url.path for r in service.requests] == ["/api/tags", "/api/ps", "/api/version"]
    assert len(result["models"]) == 2 and result["running"] == []
    assert result["bindings"]["keep:latest"] == ["Configured coder", "Default Chat"]
    assert not connection_registry(cfg).path.exists()
    assert not (cfg.data_dir / "model-cache.json").exists()


def test_download_requires_terminal_success_and_observed_installation(cfg, service):
    events = []
    result = execute_manager(cfg, review(cfg, "pull", "new", ""), events.append)
    assert result["status"] == "ok" and result["model"] == "new:latest"
    assert events[0]["stage"] == "Checking manifest" and events[-1]["stage"] == "Complete"
    assert all(
        r.url.path not in {"/api/chat", "/api/generate", "/api/create"} for r in service.requests
    )


def test_deletion_is_explicit_revalidated_and_retains_other_endpoints_and_roles(cfg, service):
    keep = ModelInfo("ollama", "keep:latest", "Keep")
    other = ModelInfo("ollama", "remote", "Remote", connection_id="another")
    save_model_cache(cfg.data_dir / "model-cache.json", [keep, other])
    result = execute_manager(cfg, review(cfg))
    assert result["status"] == "ok" and result["cache_invalidated"]
    assert len(service.models) == 1 and service.models[0]["name"] == "keep:latest"
    assert load_model_cache(cfg.data_dir / "model-cache.json") == [other]
    assert cfg.models["coder"] == "keep:latest"
    assert not connection_registry(cfg).path.exists()


@pytest.mark.parametrize("field", ["chat", "utility", "research", "fallbacks"])
def test_deletion_blocks_changed_default_roles_including_same_endpoint_alias(cfg, service, field):
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    registry.add(ModelConnection("alias", "Same server", "ollama", cfg.ollama_url))
    default = {"chat": "ollama/keep:latest", "fallbacks": []}
    default[field] = (
        ["ollama@alias/unused:latest"] if field == "fallbacks" else "ollama@alias/unused:latest"
    )
    update_settings(cfg.data_dir / "chat-preferences.json", {("ai_defaults",): default})
    result = execute_manager(cfg, review(cfg))
    assert result["status"] == "bound"
    assert not any(r.method == "DELETE" for r in service.requests)


@pytest.mark.parametrize("field", ["chat", "utility", "research", "fallbacks",
                                  "vision", "vision_fallbacks"])
def test_native_deletion_protects_compatible_roles_on_same_server(cfg, service, field):
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    registry.add(ModelConnection("compatible", "Same server", "openai_compatible",
                                 cfg.ollama_url.rstrip("/") + "/v1"))
    default = {"chat": "ollama/keep:latest", "fallbacks": []}
    default[field] = (["openai_compatible@compatible/unused:latest"]
                      if field.endswith("fallbacks")
                      else "openai_compatible@compatible/unused:latest")
    update_settings(cfg.data_dir / "chat-preferences.json", {("ai_defaults",): default})
    result = execute_manager(cfg, review(cfg))
    assert result["status"] == "bound"
    assert not any(r.method == "DELETE" for r in service.requests)


def test_loaded_models_and_unknown_running_state_block_mutations(cfg, service):
    service.running.append(record())
    assert execute_manager(cfg, review(cfg))["status"] == "busy"
    service.running.clear()
    service.failure["/api/ps"] = lambda _: httpx.Response(404)
    assert execute_manager(cfg, review(cfg))["status"] == "not_found"
    assert not any(r.method == "DELETE" for r in service.requests)


def test_stale_definition_credentials_and_digest_never_mutate(cfg, service):
    assert execute_manager(cfg, {**review(cfg), "revision": "old"})["status"] == "changed"
    assert service.requests == []
    assert execute_manager(cfg, {**review(cfg), "digest": "f" * 64})["status"] == "changed"
    assert not any(r.method == "DELETE" for r in service.requests)
    connection = replace(legacy_connections(cfg)[0], id="authed", key_env="CUSTOM_SECRET")
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    registry.add(connection)
    save_provider_secret(cfg.config_dir, "CUSTOM_SECRET", "private-value")
    assert (
        execute_manager(
            cfg, {**review(cfg), "endpoint": connection.id, "revision": connection.revision}
        )["status"]
        == "changed"
    )


@pytest.mark.parametrize(
    "payload,status",
    [
        (b'{"status":"pulling manifest"}\n', "incomplete"),
        (b'{"error":"no space left on device private-key"}\n', "disk"),
        (b'{"status":"pulling abc","total":1,"completed":2}\n', "malformed"),
        (b"not-json\n", "malformed"),
        (b'{"status":"success"}\n', "unconfirmed"),
        (b"x" * 8200, "malformed"),
    ],
)
def test_pull_failures_do_not_claim_success_or_expose_provider_text(cfg, service, payload, status):
    service.failure["/api/pull"] = lambda _: httpx.Response(200, content=payload)
    result = execute_manager(cfg, review(cfg, "pull", "new", ""))
    assert result["status"] == status
    assert "private-key" not in json.dumps(result)


def test_mutation_timeout_invalidates_cache_without_claiming_rollback(cfg, service):
    save_model_cache(
        cfg.data_dir / "model-cache.json", [ModelInfo("ollama", "unused:latest", "Unused")]
    )

    def timeout(request):
        raise httpx.ReadTimeout("private transport diagnostic", request=request)

    service.failure["/api/delete"] = timeout
    result = execute_manager(cfg, review(cfg))
    assert result["status"] == "timeout" and "outcome" in result["message"]
    assert "private" not in result["message"]
    assert load_model_cache(cfg.data_dir / "model-cache.json") == []


def test_http_disk_error_is_classified_without_provider_diagnostics(cfg, service):
    service.failure["/api/pull"] = lambda _: httpx.Response(
        500, json={"error": "no space left on device /private/path secret-key"}
    )
    result = execute_manager(cfg, review(cfg, "pull", "new", ""))
    assert result["status"] == "disk" and "private" not in result["message"]


def test_real_owned_worker_delivers_progress_then_cancels_its_http_stream(cfg):
    closed = threading.Event()

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            payload = json.dumps({"models": []}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(100):
                    self.wfile.write(b'{"status":"pulling manifest"}\n')
                    self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                closed.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg.ollama_url = f"http://127.0.0.1:{server.server_port}"
    cfg.config_dir.mkdir()
    (cfg.config_dir / "config.toml").write_text(f'[services]\nollama_url="{cfg.ollama_url}"\n')
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, payload: events.put((kind, payload)))
    request = worker_request(
        cfg, "pull", **{k: v for k, v in review(cfg, "pull", "new", "").items() if k != "operation"}
    )
    identity = jobs.submit("manager", request, timeout=15, notify_cancel=True)
    try:
        kind, payload = events.get(timeout=8)
        assert kind == "background_progress" and payload[:2] == ("manager", identity)
        jobs.cancel("manager")
        while True:
            kind, payload = events.get(timeout=5)
            if kind == "background_stopped":
                break
        assert payload == ("manager", identity) and closed.wait(3)
        assert not jobs.current("manager", identity)
    finally:
        jobs.close(wait=True)
        server.shutdown()
        server.server_close()


def test_bad_metadata_and_missing_ps_keep_truthful_partial_inventory(cfg, service):
    service.failure["/api/ps"] = lambda _: httpx.Response(404)
    result = execute_manager(cfg, {"operation": "inventory"})
    assert result["models"] and result["running"] is None
    service.models[0]["digest"] = "not-a-digest"
    result = execute_manager(cfg, {"operation": "inventory"})
    assert result["models"] is None and result.get("models_error")


@pytest.mark.parametrize("variable", ("CUSTOM_TOKEN", "KLAUDE_MODEL_QA"))
def test_real_cli_inventory_keeps_inherited_endpoint_credentials_private(
    cfg, monkeypatch, variable,
):
    from klaude_cli import model_manager_commands

    authorized = []

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            correct = self.headers.get("Authorization") == "Bearer private-inherited-value"
            authorized.append(correct)
            body = json.dumps(
                {"version": "fixture"} if self.path == "/api/version" else {"models": [record()]}
            ).encode()
            self.send_response(200 if correct else 401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cfg.config_dir.mkdir()
    (cfg.config_dir / "config.toml").write_text("[ollama]\nthink=false\n")
    connection_registry(cfg).add(ModelConnection(
        "secured", "Secured", "ollama", f"http://127.0.0.1:{server.server_port}",
        key_env=variable,
    ))
    monkeypatch.setenv(variable, "private-inherited-value")
    monkeypatch.setattr(model_manager_commands, "load_config", lambda: cfg)
    try:
        result = CliRunner().invoke(model_manager_commands.app, ["list", "--endpoint", "secured"])
        assert result.exit_code == 0, result.stdout
        assert "unused:latest" in result.stdout and "private-inherited-value" not in result.stdout
        assert authorized == [True, True, True]
    finally:
        server.shutdown()
        server.server_close()


def test_discovery_filters_gguf_and_does_not_download_or_generate(cfg, service):
    result = execute_manager(cfg, {"operation": "search", "query": "small"})
    assert result["results"][0]["id"] == "org/model-GGUF"
    assert len(service.requests) == 1 and service.requests[0].method == "GET"


@pytest.mark.parametrize(
    "value", ["../model", "model --flag", "https://bad/model", "model\n", "model?key=value", None]
)
def test_model_identity_rejects_paths_urls_and_control_text(value):
    with pytest.raises(ManagerError):
        model_name(value)


def controller(cfg):
    host = Host(cfg)
    host.agent.model = "keep:latest"
    host.running = False
    host._settings_input_request = None
    host._watching_remote = False
    host._setup_job = None
    host._library = SimpleNamespace(
        knowledge=SimpleNamespace(busy=False), research=SimpleNamespace(busy=False)
    )
    host._ai_defaults = SimpleNamespace(utility=None)
    host._start_next = lambda: None
    manager = ModelManager(host)
    host._model_manager = manager
    c = legacy_connections(cfg)[0]
    manager.connections = [{**asdict(c), "revision": c.revision, "credential_revision": ""}]
    manager.snapshots[c.id] = {
        "endpoint": manager.connections[0],
        "models": [{**record(), "parameters": "1B", "quantization": "Q4_K_M", "modified": "now"}],
        "running": [],
        "bindings": {},
        "checked_at": 10.0,
    }
    manager.model = "unused:latest"
    return manager, host


def test_controls_precede_inventory_and_review_starts_on_back_at_all_widths(cfg):
    manager, host = controller(cfg)
    manager.show("installed")
    ids = [r.id for r in host._panel.page.rows]
    assert ids.index("filter") < ids.index("columns") < ids.index("model:unused:latest")
    for width in (40, 70, 120):
        body = render_body(PanelState(host._panel.page), width)
        assert all(get_cwidth("".join(t for _, t in line)) <= width for line in body.lines)
        if width >= 60:
            headings = "".join(t for _, t in body.lines[body.row_for_line.index("columns")])
            assert "SIZE / STATE" in headings and "DETAILS" in headings
    manager.action(PanelAction("model-manager-delete"))
    assert host._panel.row().id == "back"
    assert host._background_jobs.requests == {}


def test_review_cancel_and_late_navigation_never_start_or_retarget_mutations(cfg):
    manager, host = controller(cfg)
    manager.show("detail")
    manager.action(PanelAction("model-manager-delete"))
    manager.action(PanelAction("model-manager-back", "detail"))
    assert host._background_jobs.requests == {}
    manager.action(PanelAction("model-manager-delete"))
    manager.start()
    request = list(host._background_jobs.requests.values())[0][1]
    assert request["model"] == "unused:latest" and request["endpoint"] == "default-ollama"
    manager.endpoint = "other"
    manager.accept_progress(manager.task["id"], {"stage": "Downloading file", "completed": 12})
    assert manager.progress["completed"] == 12
    identity = manager.task["id"]
    manager.stop()
    assert manager.busy and manager.stopping
    manager.stopped(identity)
    assert not manager.busy and manager.last_task["endpoint"] == "default-ollama"


def test_unavailable_loaded_state_is_unknown_and_blocks_download_review(cfg):
    manager, host = controller(cfg)
    manager.snapshot()["running"] = None
    manager.filter = "loaded"
    manager.show("installed")
    rows = {r.id: r for r in host._panel.page.rows}
    assert rows["loaded-status"].value == "Unknown"
    assert "unavailable" in rows["empty"].label
    manager.action(PanelAction("model-manager-update"))
    assert host._panel.row("blocked").label == "Cannot download yet"
    manager.action(PanelAction("model-manager-confirm"))
    assert not manager.busy and host._background_jobs.requests == {}


def test_new_review_clears_old_filter_and_keeps_back_focused(cfg):
    manager, host = controller(cfg)
    manager.show("detail")
    manager.action(PanelAction("model-manager-delete"))
    old = host._panel
    old.filter("back")
    old.search_active = True
    host._panel_states = {old.page.id: old}
    manager.show("review", "back")
    assert old.picker.query == "" and not old.search_active
    assert host._panel.row().id == "back"


def test_fresh_navigation_reuses_snapshot_but_explicit_reload_is_owned(cfg):
    manager, host = controller(cfg)
    manager.snapshot()["checked_at"] = time.time()
    manager.show("home")
    manager.action(PanelAction("model-manager-installed"))
    manager.action(PanelAction("model-manager-service"))
    assert host._background_jobs.requests == {}
    manager.action(PanelAction("model-manager-reload", "inventory"))
    assert len(host._background_jobs.requests) == 1


def test_failed_reload_retains_true_snapshot_age_and_stale_scope_is_rejected(cfg):
    manager, host = controller(cfg)
    manager.show("installed")
    manager.load("inventory")
    identity = manager.read[0]
    manager.accept("model-manager:read", identity, {"models": None, "models_error": "Offline"}, "")
    assert manager.snapshot()["checked_at"] == 10.0 and manager.snapshot()["stale"]
    manager.load("inventory")
    identity = manager.read[0]
    host.session_id = "other-session"
    manager.accept("model-manager:read", identity, {"models": []}, "")
    assert manager.snapshot()["checked_at"] == 10.0
