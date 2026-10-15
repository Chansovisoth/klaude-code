"""Actual bounded image requests, explicit review/defaults and failure behavior."""

import base64
import json
import queue
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.settings_panel import PanelState, render_body
from klaude_cli.vision_panel import VisionPanel
from klaude_core.ai_defaults import DefaultsChange, migrate_defaults, read_defaults, save_defaults
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.model_connections import DEFAULT_IDS, connection_registry
from klaude_core.model_management import ModelChange, apply_model_change
from klaude_core.ollama_manager import role_models
from klaude_core.settings_store import SettingsConflictError, update_settings
from klaude_core.vision import VisionHTTP, analyze, inspect_model, prepare

from .test_library_artifacts import png


@pytest.fixture
def vision_lab(tmp_path):
    calls, mode = [], {"value": "good"}
    arrived = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, data))
            if self.path == "/api/show":
                value = {
                    "capabilities": ["completion"] + ([] if data["model"] == "text" else ["vision"])
                }
                body = json.dumps(value).encode()
            else:
                arrived.set()
                if mode["value"] == "slow":
                    time.sleep(3)
                if data["model"] == "vision" and mode["value"] in {"503", "401"}:
                    self.send_response(int(mode["value"]))
                    self.end_headers()
                    return
                events = [
                    {"message": {"content": mode.get("text", "Three colored rectangles.")}},
                    {
                        "message": {"content": ""},
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 42,
                        "eval_count": 5,
                    },
                ]
                if mode["value"] == "incomplete":
                    events.pop()
                elif mode["value"] == "tools":
                    events[0]["message"]["tool_calls"] = [{"function": {"name": "shell"}}]
                elif mode["value"] == "limit":
                    events[-1]["done_reason"] = "length"
                body = b"".join(json.dumps(e).encode() + b"\n" for e in events)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "small:3b", "embed": "embedding"},
        ollama_url=f"http://127.0.0.1:{server.server_port}",
    )
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    connection = registry.load()[DEFAULT_IDS["ollama"]]
    migrate_defaults(cfg)
    source = tmp_path / "input.png"
    source.write_bytes(png())
    store = ArtifactStore(cfg.data_dir / "library")
    item = store.import_file(source, "media")

    def select(field, value):
        current = read_defaults(cfg)
        refs = value if isinstance(value, tuple) else (value,) if isinstance(value, str) else ()
        return save_defaults(
            cfg,
            DefaultsChange(
                field,
                value,
                getattr(current, field),
                tuple((ref, connection.revision, "") for ref in refs),
            ),
        )

    select("vision", connection.model_ref("vision"))
    select("vision_enabled", True)
    yield cfg, connection, store, item, calls, mode, arrived, select
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def spec(lab):
    cfg, _, _, item, *_ = lab
    return prepare(cfg, item["id"], item["revision"], "Describe the image")


def test_actual_pixel_request_preserves_images_roles_and_store(vision_lab):
    cfg, connection, store, item, calls, _, _, _ = vision_lab
    before = read_defaults(cfg)
    reviewed = spec(vision_lab)
    assert all(path != "/api/chat" for path, _ in calls)
    result = analyze(cfg, reviewed)
    assert result["status"] == "complete" and result["model"] == connection.model_ref("vision")
    sent = next(data for path, data in calls if path == "/api/chat")
    assert base64.b64decode(sent["messages"][-1]["images"][0]) == png()
    assert sent["options"] == {"num_ctx": 4096, "num_predict": 512}
    assert "tools" not in sent and sent["think"] is False
    assert read_defaults(cfg) == before and store.get(item["id"]) == item
    assert not (cfg.data_dir / "sessions.db").exists()


@pytest.mark.parametrize("failure", ["disabled", "text", "archive", "checksum", "question"])
def test_invalid_input_or_capability_cannot_generate(vision_lab, failure):
    cfg, connection, store, item, calls, _, _, select = vision_lab
    if failure == "disabled":
        select("vision_enabled", False)
    elif failure == "text":
        select("vision", connection.model_ref("text"))
    elif failure == "archive":
        store.change(item["id"], item["revision"], "archive")
    elif failure == "checksum":
        with store.database(write=True) as db:
            db.execute(
                "UPDATE artifacts SET content=? WHERE id=?", (png() + b"changed", item["id"])
            )
    with pytest.raises(ValueError):
        prepare(cfg, item["id"], item["revision"], "\x1b" if failure == "question" else "Describe")
    assert all(path != "/api/chat" for path, _ in calls)


@pytest.mark.parametrize("mode", ["incomplete", "tools", "limit", "401"])
def test_protocol_and_auth_failures_never_use_fallbacks(vision_lab, mode):
    cfg, connection, _, _, calls, behavior, _, select = vision_lab
    select("vision_fallbacks", (connection.model_ref("other"),))
    reviewed = spec(vision_lab)
    behavior["value"] = mode
    with pytest.raises((ValueError, httpx.HTTPStatusError)):
        analyze(cfg, reviewed)
    assert [data["model"] for path, data in calls if path == "/api/chat"] == ["vision"]


def test_only_reviewed_fallback_runs_and_actual_used_model_is_reported(vision_lab):
    cfg, connection, _, _, calls, behavior, _, select = vision_lab
    select("vision_fallbacks", (connection.model_ref("other"),))
    reviewed = spec(vision_lab)
    behavior["value"] = "503"
    result = analyze(cfg, reviewed)
    assert result["model"] == connection.model_ref("other")
    assert len(result["attempts"]) == 1
    assert [data["model"] for path, data in calls if path == "/api/chat"] == ["vision", "other"]


def test_changed_endpoint_or_artifact_requires_new_review(vision_lab):
    cfg, connection, store, item, calls, *_ = vision_lab
    reviewed = spec(vision_lab)
    store.change(item["id"], item["revision"], "tags", "changed")
    with pytest.raises(ValueError):
        analyze(cfg, reviewed)
    update_settings(
        connection_registry(cfg).path,
        {("connections", connection.id): asdict(replace(connection, name="Changed"))},
    )
    with pytest.raises(ValueError):
        inspect_model(cfg, connection.model_ref("vision"), reviewed["models"][0])
    assert all(path != "/api/chat" for path, _ in calls)


def test_vision_roles_protect_model_visibility_and_native_deletion(vision_lab):
    cfg, connection, *_ = vision_lab
    with pytest.raises(SettingsConflictError, match="Vision"):
        apply_model_change(
            cfg, ModelChange("choice", (connection,), "vision", "enabled", False, True)
        )
    assert any("Vision" in roles for roles in role_models(cfg, connection).values())


def test_review_paging_keeps_back_and_has_explicit_models_and_budgets(vision_lab):
    cfg, connection, _, item, *_ = vision_lab
    host = SimpleNamespace(_ai_defaults=SimpleNamespace(defaults=read_defaults(cfg)))
    library = SimpleNamespace(host=host, view="vision-review")
    panel = VisionPanel(library)
    panel.item = item
    panel.spec = spec(vision_lab)
    for width in (40, 70, 120):
        state = PanelState(panel.page(), "back")
        body = render_body(state, width)
        assert state.picker.selected_id == "back"
        state.scroll_row(-10000, body)
        state.scroll_row(10000, body)
        assert state.picker.selected_id == "back"
        assert connection.model_ref("vision") in "".join(
            text for line in body.lines for _, text in line
        )


def test_real_cli_declined_review_sends_no_pixels(vision_lab):
    import os

    cfg, _, _, item, calls, *_ = vision_lab
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from klaude_cli.main import app;app()",
            "library",
            "analyze",
            item["id"],
            "Describe",
        ],
        input="n\n",
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "KLAUDE_CONFIG_DIR": str(cfg.config_dir),
            "KLAUDE_DATA_DIR": str(cfg.data_dir),
        },
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Send this image" in result.stdout
    assert all(path != "/api/chat" for path, _ in calls)


def test_owned_analysis_cancellation_reaps_worker_before_releasing_task(vision_lab):
    cfg, _, _, _, _, behavior, arrived, _ = vision_lab
    reviewed = spec(vision_lab)
    behavior["value"] = "slow"
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    try:
        identity = jobs.submit(
            "vision",
            {
                "kind": "vision",
                "operation": "analyze",
                "spec": reviewed,
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "roles": cfg.models,
                "ollama_url": cfg.ollama_url,
            },
            timeout=15,
            notify_cancel=True,
        )
        assert arrived.wait(5)
        jobs.cancel("vision")
        deadline = time.monotonic() + 5
        while True:
            kind, payload = events.get(timeout=max(0.1, deadline - time.monotonic()))
            if kind == "background_stopped" and payload[1] == identity:
                break
        assert identity not in jobs._active
    finally:
        jobs.close(wait=True)


def test_vision_allows_delayed_headers_within_advertised_request_deadline(vision_lab):
    cfg, _, _, _, _, behavior, _, _ = vision_lab
    behavior["value"] = "slow"
    client = VisionHTTP(cfg.ollama_url, timeout=0.1, trust_env=False)
    try:
        result = client.request("/api/chat", {"model": "vision"}, stream=True)
        assert result["text"] == "Three colored rectangles."
    finally:
        client.close()
