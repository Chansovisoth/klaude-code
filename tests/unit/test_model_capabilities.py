import json
import queue
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.ai_default_settings import AIDefaultSettings
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.model_capabilities import BATCH_SIZE, read_capabilities
from klaude_cli.model_settings import ModelSettings
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.ai_defaults import AIDefaults
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_runtime import ModelInfo
from prompt_toolkit.utils import get_cwidth


class Jobs:
    def __init__(self):
        self.requests = []
        self.cancelled = []

    def submit(self, key, request, **kwargs):
        self.requests.append((key, request, kwargs))
        return str(len(self.requests))

    def cancel(self, key):
        self.cancelled.append(key)


class Host:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session_id = "session"
        self.agent = SimpleNamespace(model="chat")
        self._choice_kind = ""
        self._panel = None
        self._background_jobs = Jobs()
        self._model_settings = SimpleNamespace(environment_keys=lambda: {})

    def _open_panel(self, page, kind, focus):
        if self._panel and self._panel.page.id == page.id:
            self._panel.replace(page)
        else:
            self._panel = PanelState(page, focus)
        self._choice_kind = kind

    def _set_panel_feedback(self, *args):
        pass


@pytest.fixture
def lab(tmp_path):
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        ollama_url="http://localhost:11434",
        models={"coder": "chat"},
    )
    connection_registry(cfg).migrate(cfg)
    connection = connection_registry(cfg).load()["default-ollama"]
    return cfg, connection


def picker(lab, kind="defaults", count=3):
    cfg, connection = lab
    host = Host(cfg)
    owner = AIDefaultSettings(host) if kind == "defaults" else ModelSettings(host)
    owner.connections = {connection.id: connection}
    owner.target = connection.id
    owner.models = [
        ModelInfo(
            "ollama",
            f"model-{i}",
            f"model-{i}",
            connection_id=connection.id,
            connection_revision=connection.revision,
        )
        for i in range(count)
    ]
    if kind == "models":
        owner.discovered = {model.ref for model in owner.models}
    owner.defaults = AIDefaults("ollama/chat")
    owner.role = "vision"
    owner.show("models" if kind == "defaults" else "catalog")
    return owner


def reply(owner, declarations):
    identity, models, connection = owner.capabilities.pending
    result = {
        "status": "ok",
        "connection": asdict(connection),
        "credential_revision": "",
        "models": [
            {"model": model, "declared": declarations[i % len(declarations)]}
            for i, model in enumerate(models)
        ],
    }
    owner.accept(owner.capabilities.key, identity, result, "")
    return result


def mock_metadata(monkeypatch, respond):
    client_type = httpx.Client
    monkeypatch.setattr(
        "klaude_core.http_model_transport.httpx.Client",
        lambda **kw: client_type(**kw, transport=httpx.MockTransport(respond)),
    )


def packet(lab, models=None):
    cfg, connection = lab
    return {
        "connection": asdict(connection),
        "models": models or ["misleading-name"],
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "ollama_url": cfg.ollama_url,
        "roles": cfg.models,
        "credential_revision": "",
    }


def test_metadata_uses_declared_capabilities_only_and_preserves_private_state(lab, monkeypatch):
    cfg, _ = lab
    before = (cfg.config_dir / "model-connections.json").read_bytes()
    seen = []

    def respond(request):
        seen.append(request)
        assert json.loads(request.content) == {"model": "misleading-name", "verbose": False}
        return httpx.Response(
            200,
            json={
                "capabilities": ["completion", "vision", "tools"],
                "modelfile": "PRIVATE SYSTEM PROMPT",
            },
        )

    mock_metadata(monkeypatch, respond)
    result = read_capabilities(packet(lab))
    assert result["models"] == [
        {"model": "misleading-name", "declared": ["completion", "tools", "vision"]}
    ]
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/api/show")]
    assert "PRIVATE" not in json.dumps(result)
    assert (cfg.config_dir / "model-connections.json").read_bytes() == before
    assert not cfg.data_dir.exists()


@pytest.mark.parametrize(
    "metadata", [None, "vision", ["vision", False], ["vision\n"], ["x"] * 33, ["x" * 65]]
)
def test_missing_or_malformed_metadata_stays_unknown(lab, monkeypatch, metadata):
    mock_metadata(monkeypatch, lambda _: httpx.Response(200, json={"capabilities": metadata}))
    record = read_capabilities(packet(lab))["models"][0]
    assert "declared" not in record and record["reason"]


@pytest.mark.parametrize("failure", ["http", "timeout", "oversize"])
def test_provider_errors_are_bounded_and_redacted(lab, monkeypatch, failure):
    def respond(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("PRIVATE KEY AND URL", request=request)
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 1_000_001)
        return httpx.Response(401, text="PRIVATE KEY AND URL")

    mock_metadata(monkeypatch, respond)
    result = read_capabilities(packet(lab))
    assert "PRIVATE" not in json.dumps(result)
    assert "declared" not in result["models"][0]


def test_changed_connection_rejects_metadata_after_read(lab, monkeypatch):
    cfg, connection = lab

    def respond(_):
        registry = connection_registry(cfg)
        payload = registry._read()
        payload["connections"][connection.id] = asdict(replace(connection, name="Changed"))
        registry.path.write_text(json.dumps(payload))
        return httpx.Response(200, json={"capabilities": ["completion", "vision"]})

    mock_metadata(monkeypatch, respond)
    assert read_capabilities(packet(lab)) == {"status": "stale"}


@pytest.mark.parametrize("kind", ["defaults", "models"])
def test_both_pickers_auto_check_and_distinguish_native_capabilities(lab, kind):
    owner = picker(lab, kind)
    assert "Checking capabilities" in repr(owner.host._panel.page)
    reply(owner, [["completion", "vision", "tools"], ["completion", "thinking"], ["image"]])
    rows = {row.id: row for row in owner.host._panel.page.rows}
    assert rows["model:model-0"].description == "Vision · Tools"
    assert rows["model:model-1"].description == "Text only · Thinking"
    assert rows["model:model-2"].description == "Image generation (server)"
    if kind == "defaults":
        assert rows["model:model-0"].enabled
        assert rows["model:model-1"].value == "No vision"
        assert not rows["model:model-1"].enabled
        assert not rows["model:model-2"].enabled
        assert rows["vision-purpose"].value == "Read images"
    else:
        assert rows["model:model-2"].value == "Not chat"
        with pytest.raises(ValueError, match="chat completion"):
            owner.select("model-2")
    assert owner.capabilities.pending is None
    owner.show()
    assert len(owner.host._background_jobs.requests) == 1
    if kind == "defaults":
        owner.select("model-0")
        _, request, _ = owner.host._background_jobs.requests[-1]
        assert request["kind"] == "vision" and request["operation"] == "inspect"
        assert owner.pending is None  # Picker metadata never bypasses the fresh save gate.


def test_scan_batches_are_bounded_and_do_not_restart_during_long_navigation(lab, monkeypatch):
    owner = picker(lab, count=BATCH_SIZE + 1)
    now = 100.0
    monkeypatch.setattr("klaude_cli.model_capabilities.time.monotonic", lambda: now)
    reply(owner, [["completion", "vision"]])
    assert len(owner.host._background_jobs.requests) == 2
    assert len(owner.host._background_jobs.requests[0][1]["models"]) == BATCH_SIZE
    now += 120
    reply(owner, [["completion", "vision"]])
    assert owner.capabilities.pending is None
    assert len(owner.host._background_jobs.requests) == 2
    owner.show("endpoints")
    owner.show("models")
    assert owner.capabilities.pending is not None
    assert len(owner.host._background_jobs.requests) == 3


@pytest.mark.parametrize("change", ["navigate", "session", "endpoint", "credential"])
def test_stale_results_do_not_modify_new_navigation_or_scope(lab, change):
    owner = picker(lab)
    identity, models, connection = owner.capabilities.pending
    result = {
        "status": "ok",
        "connection": asdict(connection),
        "credential_revision": "",
        "models": [{"model": model, "declared": ["vision"]} for model in models],
    }
    if change == "navigate":
        owner.show("endpoints")
    elif change == "session":
        owner.host.session_id = "other"
    elif change == "endpoint":
        owner.connections[connection.id] = replace(connection, name="Changed")
    else:
        owner.credential_revisions[connection.id] = "changed"
    page = owner.host._panel.page
    owner.accept(owner.capabilities.key, identity, result, "")
    assert not owner.capabilities.cache
    assert owner.host._panel.page is page


def test_failed_check_is_unverified_and_only_refresh_retries(lab):
    owner = picker(lab, count=BATCH_SIZE + 1)
    identity = owner.capabilities.pending[0]
    owner.accept(owner.capabilities.key, identity, None, "Background job timed out; retry")
    rows = {row.id: row for row in owner.host._panel.page.rows}
    assert rows["model:model-0"].value == "Unverified"
    assert rows["model:model-0"].enabled
    assert "refresh to retry" in rows["model:model-0"].description
    assert len(owner.host._background_jobs.requests) == 1
    owner.action(PanelAction("ai-defaults-capabilities-reload"))
    assert len(owner.host._background_jobs.requests) == 2


def test_failed_batch_stops_only_its_endpoint_even_with_large_foreign_inventory(lab):
    owner = picker(lab, count=BATCH_SIZE + 1)
    owner.models[:0] = [
        ModelInfo("openrouter", f"foreign-{i}", f"foreign-{i}", connection_id="foreign")
        for i in range(1001)
    ]
    identity = owner.capabilities.pending[0]
    owner.accept(owner.capabilities.key, identity, None, "Worker unavailable")
    assert owner.capabilities.pending is None
    assert len(owner.capabilities.cache) == BATCH_SIZE + 1
    assert len(owner.host._background_jobs.requests) == 1


def test_partial_metadata_failure_does_not_disable_unknown_models(lab):
    owner = picker(lab)
    identity, models, connection = owner.capabilities.pending
    owner.accept(
        owner.capabilities.key,
        identity,
        {
            "status": "ok",
            "connection": asdict(connection),
            "credential_revision": "",
            "models": [
                {"model": models[0], "declared": ["completion", "vision"]},
                {"model": models[1], "reason": "Metadata unavailable (HTTP 404)"},
                {"model": models[2], "declared": "vision"},
            ],
        },
        "",
    )
    rows = {row.id: row for row in owner.host._panel.page.rows}
    assert rows["model:model-0"].value == "Available"
    assert rows["model:model-1"].value == "Unverified" and rows["model:model-1"].enabled
    assert "HTTP 404" in rows["model:model-1"].description
    assert rows["model:model-2"].value == "Unverified"


def test_background_updates_preserve_the_focused_model(lab):
    owner = picker(lab)
    owner.host._panel.picker.selected_id = "model:model-2"
    reply(owner, [["completion", "vision"]])
    assert owner.host._panel.picker.selected_id == "model:model-2"


@pytest.mark.parametrize("width", [38, 80, 120])
def test_verified_picker_preserves_table_boundaries_and_terminal_width(lab, width):
    owner = picker(lab)
    reply(owner, [["completion", "vision", "tools", "thinking"], ["completion"], ["image"]])
    page = owner.host._panel.page
    ids = [row.id for row in page.rows]
    assert ids.index("capabilities-reload") < ids.index("models-columns")
    assert ids.index("vision-purpose") < ids.index("models-columns")
    owner.host._panel.picker.selected_id = "model:model-0"
    body = render_body(owner.host._panel, width)
    lines = ["".join(text for _, text in line) for line in body.lines]
    assert all(get_cwidth(line) <= width for line in lines)
    assert any("Vision" in line for line in lines)


def test_non_native_endpoints_use_existing_evidence_without_native_requests(lab):
    owner = picker(lab)
    owner.show("endpoints")
    remote = ModelConnection("remote", "Remote", "openai_compatible", "http://host/v1")
    owner.connections = {remote.id: remote}
    owner.target = remote.id
    owner.models = [ModelInfo(remote.backend, "model", "model", connection_id=remote.id)]
    owner.show("models")
    assert owner.capabilities.pending is None
    assert len(owner.host._background_jobs.requests) == 1
    assert "Vision: unknown" in repr(owner.host._panel.page)


def test_owned_metadata_cancellation_reaps_parallel_worker_without_result(lab):
    arrived, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            with lock:
                calls.append(self.path)
                if len(calls) == 4:
                    arrived.set()
            release.wait(15)
            self.send_response(200)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cfg, connection = lab
    connection = replace(connection, base_url=f"http://127.0.0.1:{server.server_port}")
    registry = connection_registry(cfg)
    payload = registry._read()
    payload["connections"][connection.id] = asdict(connection)
    registry.path.write_text(json.dumps(payload))
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    try:
        request = {
            **packet((cfg, connection), [f"model-{i}" for i in range(BATCH_SIZE)]),
            "kind": "model_capabilities",
        }
        jobs.submit("capability-test", request, timeout=20)
        assert arrived.wait(12), "Owned worker must reach four parallel metadata reads"
        started = time.monotonic()
        jobs.cancel("capability-test")
        deadline = started + 4
        while jobs._active and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not jobs._active
        assert events.empty()
        assert calls == ["/api/show"] * 4
    finally:
        release.set()
        jobs.close(wait=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
