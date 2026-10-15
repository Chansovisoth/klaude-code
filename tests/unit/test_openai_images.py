"""Exact documented profiles, real Responses HTTP and private image continuity."""

import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from klaude_core import Agent, PermissionGate, Tool, image_profiles, vision
from klaude_core.ai_defaults import DefaultsChange, migrate_defaults, save_defaults
from klaude_core.chat_images import ChatImages
from klaude_core.compatible_runtime import CompatibleModelError
from klaude_core.config import provider_secret_revision, save_provider_secret
from klaude_core.image_content import image_capability_label
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_discovery import discover_connection
from klaude_core.model_runtime import ModelInfo, OpenAIRuntime

from .test_library_artifacts import png

MODEL = "gpt-4.1-mini"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    calls, mode, arrived = [], {}, threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, body, code=200):
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            calls.append((self.path, {}, dict(self.headers)))
            if mode.get("slow_metadata"):
                time.sleep(0.3)
            model = "another-model" if mode.get("identity") else self.path.rsplit("/", 1)[-1]
            data = (
                {"data": [{"id": MODEL}, {"id": "text-only-unknown"}]}
                if self.path == "/v1/models"
                else {"id": model}
            )
            self.send(json.dumps(data).encode(), mode.get("metadata_status", 200))

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, data, dict(self.headers)))
            arrived.set()
            if mode.get("slow"):
                time.sleep(2)
            if mode.get("http") and (not mode.get("fallback") or data["model"] == MODEL):
                self.send(
                    json.dumps(
                        {
                            "error": {
                                "message": "private-provider-body",
                                "code": mode.get("error_code"),
                            }
                        }
                    ).encode(),
                    mode["http"],
                )
                return
            tools = data.get("tools") and not any(
                i.get("type") == "function_call_output" for i in data["input"]
            )
            text = "x" * mode.get("text_size", 0) or "Red, Green, Blue"
            items = (
                [
                    {
                        "type": "reasoning",
                        "id": "r1",
                        "encrypted_content": "private-opaque",
                        "summary": [],
                    },
                    {
                        "type": "function_call",
                        "id": "f1",
                        "call_id": "c1",
                        "name": "inspect",
                        "arguments": "{}",
                        "status": "completed",
                    },
                ]
                if tools
                else [
                    {
                        "type": "message",
                        "id": "m1",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": text, "annotations": []}],
                    }
                ]
            )
            result = {
                "id": "resp1",
                "status": mode.get("status", "completed"),
                "output": [] if mode.get("empty_terminal") else items,
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 7,
                    "input_tokens_details": {"cached_tokens": 5},
                },
            }
            if not data.get("stream"):
                self.send(json.dumps(result).encode())
                return
            events = [{"type": "response.output_item.done", "item": i} for i in items]
            if not tools and not mode.get("no_deltas"):
                events.insert(0, {"type": "response.output_text.delta", "delta": text})
            if not mode.get("incomplete"):
                events.append({"type": "response.completed", "response": result})
            if mode.get("late_error"):
                events.append({"type": "error", "message": "private-provider-body"})
            body = "".join("data: " + json.dumps(e) + "\n\n" for e in events)
            self.send((body + "data: [DONE]\n\n").encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1"
    # Only the fixture moves the trusted root. Production rejects custom origins.
    monkeypatch.setattr(image_profiles, "OPENAI_ROOT", url)
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "text"},
        ollama_url="http://127.0.0.1:1",
    )
    conn = ModelConnection("image", "OpenAI fixture", "openai_api", url, key_env="IMAGE_KEY")
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    registry.add(conn)
    save_provider_secret(cfg.config_dir, conn.key_env, "fixture-private-key")
    migrate_defaults(cfg)
    save_defaults(cfg, DefaultsChange("vision_enabled", True, False))
    creds = provider_secret_revision(cfg.config_dir, conn.key_env)
    runtime = OpenAIRuntime("fixture-private-key", base_url=url)
    info = ModelInfo(
        "openai_api",
        MODEL,
        MODEL,
        connection_id=conn.id,
        connection_revision=conn.revision,
        credential_revision=creds,
    )
    agent = Agent(
        runtime,
        MODEL,
        [],
        PermissionGate({}, ask=lambda *_args: False),
        "Answer the user's request accurately.",
        model_info=info,
        ollama_options={"num_ctx": 8192, "num_predict": 128},
    )
    agent.reasoning_mode = "standard"
    agent.workdir = tmp_path
    agent.image_context = ChatImages(cfg, agent)
    source = tmp_path / "capture.png"
    source.write_bytes(png())
    value = SimpleNamespace(
        cfg=cfg, conn=conn, agent=agent, source=source, calls=calls, mode=mode, arrived=arrived
    )
    try:
        yield value
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def compose(lab):
    return lab.agent.image_context.compose("Describe the pixels", (lab.source,), "fixture")


def review(lab):
    cfg, conn = lab.cfg, lab.conn
    save_defaults(
        cfg,
        DefaultsChange(
            "vision",
            conn.model_ref(MODEL),
            None,
            (
                (
                    conn.model_ref(MODEL),
                    conn.revision,
                    provider_secret_revision(cfg.config_dir, conn.key_env),
                ),
            ),
        ),
    )
    store = ArtifactStore(cfg.data_dir / "library")
    item = store.import_file(lab.source, "media")
    return (
        store,
        item,
        vision.prepare(
            cfg, item["id"], item["revision"], "Describe the colors", context=2048, output=128
        ),
    )


@pytest.mark.parametrize("model", [MODEL, "gpt-4.1-mini-2025-04-14"])
def test_profiles_are_exact_and_official_only(model):
    assert image_profiles.openai_image_profile("https://api.openai.com/v1", model)
    assert not image_profiles.openai_image_profile("https://proxy.example/v1", model)
    for unknown in (model + "-future", "ft:" + model, model.upper()):
        assert not image_profiles.openai_image_profile("https://api.openai.com/v1", unknown)


def test_inventory_distinguishes_documentation_from_catalog(lab):
    models = discover_connection(lab.conn, "fixture-private-key")
    known = next(m for m in models if m.model_id == MODEL)
    assert (
        image_capability_label(
            known.capabilities.supports_images, known.capabilities.images_evidence
        )
        == "Images: documented"
    )
    assert (
        next(m for m in models if m.model_id == "text-only-unknown").capabilities.supports_images
        is None
    )


@pytest.mark.parametrize("streaming", [True, False])
def test_native_pixels_budget_and_private_continuation(lab, streaming):
    compose(lab)
    runtime = lab.agent.runtime
    messages = [
        {
            "role": "user",
            "content": "Colors?",
            "image_content": [
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "data": __import__("base64").b64encode(lab.source.read_bytes()).decode(),
                }
            ],
        }
    ]
    if streaming:
        result = list(runtime.chat_stream(MODEL, messages, options={"num_predict": 128}))[-1]
    else:
        result = runtime.chat(MODEL, messages, options={"num_predict": 128})
    packet = lab.calls[-1][1]
    assert packet["max_output_tokens"] == 128 and packet["store"] is False
    assert packet["input"][0]["content"][0]["type"] == "input_image"
    assert result["openai_response_items"][0]["type"] == "message"
    assert runtime.last_chat_metadata["usage"]["input_tokens_details"]["cached_tokens"] == 5


def test_chat_tool_pairs_and_restore_keep_pixels_private(lab):
    lab.mode["empty_terminal"] = True
    ran = []
    lab.agent.tools = {
        "inspect": Tool("inspect", "", {"type": "object"}, lambda: ran.append(True) or "observed")
    }
    lab.agent.gate.policies["inspect"] = "allow"
    prepared = compose(lab)
    events = list(lab.agent.run(prepared))
    assert ran == [True] and not [e for e in events if e.kind == "error"]
    packets = [p for _, p, _ in lab.calls if "input" in p]
    assert any(i.get("type") == "function_call_output" for i in packets[-1]["input"])
    assert any(i.get("encrypted_content") == "private-opaque" for i in packets[-1]["input"])
    assert "private-opaque" not in str([e.payload.get("text") for e in events if e.kind == "text"])
    lab.source.unlink()
    lab.agent.restore_session(
        [{"role": "user", "content": prepared["request"], "model_content": prepared}]
    )
    events = list(lab.agent.run("Look at the attached pixels again"))
    assert not [e for e in events if e.kind == "error"]
    assert "data:image/png;base64," in str(lab.calls[-1][1]["input"])


@pytest.mark.parametrize("failure", ["incomplete", "late_error", "status", "http"])
def test_failed_stream_never_releases_tools_or_private_state(lab, failure):
    lab.mode[failure] = "incomplete" if failure == "status" else 401 if failure == "http" else True
    compose(lab)
    # The helper is also used by Media: feed a bounded native image request directly.
    raw = {
        "model": MODEL,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_image", "image_url": "data:image/png;base64,cGl4ZWxz"}],
            }
        ],
        "stream": True,
        "store": False,
        "tools": [{"type": "function", "name": "inspect"}],
    }
    events = []
    with pytest.raises(CompatibleModelError) as error:
        for event in lab.agent.runtime._response_create(**raw):
            events.append(event)
    assert not any(getattr(e, "type", "") == "response.completed" for e in events)
    assert "private-provider-body" not in str(error.value)


@pytest.mark.parametrize("change", ["identity", "unknown", "thinking", "credential"])
def test_preparation_failure_never_sends_pixels(lab, change):
    if change == "identity":
        lab.mode["identity"] = True
    elif change == "unknown":
        lab.agent.model_info = replace(lab.agent.model_info, model_id="unreviewed-model")
    elif change == "thinking":
        lab.agent.reasoning_mode = "thinking"
    else:
        save_provider_secret(lab.cfg.config_dir, lab.conn.key_env, "changed-key")
    with pytest.raises(ValueError):
        compose(lab)
    assert not [p for _, p, _ in lab.calls if "input" in p]


def test_private_media_has_no_tools_chat_or_saved_analysis(lab):
    store, item, spec = review(lab)
    before = store.get(item["id"]), list(lab.agent.messages)
    result = vision.analyze(lab.cfg, spec)
    assert result["status"] == "complete" and result["text"] == "Red, Green, Blue"
    packet = lab.calls[-1][1]
    assert packet["store"] is False and packet["max_output_tokens"] == 128
    assert "tools" not in packet and "reasoning" not in packet
    assert (store.get(item["id"]), list(lab.agent.messages)) == before
    assert not (lab.cfg.data_dir / "sessions.db").exists()


@pytest.mark.parametrize("size", [32_001, 300_000])
def test_media_output_and_event_bounds(lab, size):
    _, _, spec = review(lab)
    lab.mode["text_size"] = size
    with pytest.raises((ValueError, CompatibleModelError)):
        vision.analyze(lab.cfg, spec)


def test_cancel_wakes_image_request_before_headers(lab):
    prepared = compose(lab)
    lab.mode["slow"] = True
    result = []
    thread = threading.Thread(target=lambda: result.extend(lab.agent.run(prepared)))
    thread.start()
    assert lab.arrived.wait(5)
    lab.agent.cancellation_check = lambda: True
    lab.agent.runtime.cancel_active()
    thread.join(1)
    assert not thread.is_alive()


def test_compaction_retains_actual_images_without_old_task_instructions():
    import base64

    images = [{"type": "image", "mime_type": "image/png", "data": base64.b64encode(b"x").decode()}]
    messages = [
        {"role": "system", "content": "current rules"},
        {"role": "user", "content": "OLD TASK", "image_content": images},
        {
            "role": "assistant",
            "content": "",
            "openai_response_items": [
                {"type": "compaction", "id": "cmp", "encrypted_content": "opaque"}
            ],
        },
        {"role": "user", "content": "Look again"},
    ]
    packet = OpenAIRuntime._input(messages, include_images=True)
    assert packet[1]["type"] == "compaction"
    assert "input_image" in str(packet) and "OLD TASK" not in str(packet)
    assert packet[-1]["content"] == "Look again"


def test_text_sdk_stream_obeys_positive_output_budget(monkeypatch):
    runtime = OpenAIRuntime("fixture-key")
    sent = []
    terminal = SimpleNamespace(
        type="response.completed",
        response=SimpleNamespace(status="completed", output=[], usage=None),
    )
    monkeypatch.setattr(
        runtime, "_response_create", lambda **kw: sent.append(kw) or iter([terminal])
    )
    list(runtime.chat_stream(MODEL, [], options={"num_predict": 128}))
    assert sent[0]["max_output_tokens"] == 128


def test_metadata_deadline_is_a_clean_preparation_failure(lab, monkeypatch):
    original = threading.Timer
    lab.mode["slow_metadata"] = True
    monkeypatch.setattr(
        vision.threading, "Timer", lambda _delay, callback: original(0.05, callback)
    )
    with pytest.raises(ValueError, match="Could not verify image support"):
        compose(lab)
    assert not [p for _, p, _ in lab.calls if "input" in p]


@pytest.mark.parametrize("change", ["credential", "definition", "artifact", "disabled"])
def test_stale_media_review_sends_no_pixels(lab, change):
    from dataclasses import asdict

    from klaude_core.model_management import write_registry

    store, item, spec = review(lab)
    if change == "credential":
        save_provider_secret(lab.cfg.config_dir, lab.conn.key_env, "new-key")
    elif change == "artifact":
        store.change(item["id"], item["revision"], "archive")
    else:
        registry = connection_registry(lab.cfg)
        data = registry._read()
        data["connections"][lab.conn.id] = asdict(
            replace(lab.conn, enabled=change != "disabled", name="Changed")
        )
        write_registry(registry, data)
    with pytest.raises(ValueError):
        vision.analyze(lab.cfg, spec)
    assert not [p for _, p, _ in lab.calls if "input" in p]


def test_only_reviewed_fallback_runs_after_temporary_http_failure(lab):
    fallback = lab.conn.model_ref("gpt-4.1-mini-2025-04-14")
    save_defaults(
        lab.cfg,
        DefaultsChange(
            "vision_fallbacks",
            (fallback,),
            (),
            (
                (
                    fallback,
                    lab.conn.revision,
                    provider_secret_revision(lab.cfg.config_dir, lab.conn.key_env),
                ),
            ),
        ),
    )
    _, _, spec = review(lab)
    lab.mode.update(http=429, fallback=True)
    result = vision.analyze(lab.cfg, spec)
    assert result["status"] == "complete" and result["model"] == fallback
    assert [p["model"] for _, p, _ in lab.calls if "input" in p] == [
        MODEL,
        "gpt-4.1-mini-2025-04-14",
    ]


def test_cached_image_evidence_cannot_enable_unsupported_reasoning(lab):
    prepared = compose(lab)
    lab.agent.ollama_think = "low"
    events = list(lab.agent.run(prepared))
    assert any(e.kind == "error" and "Standard mode" in str(e.payload) for e in events)
    assert not [p for _, p, _ in lab.calls if "input" in p]


@pytest.mark.parametrize("code", ["insufficient_quota", "max_output_tokens", "invalid_api_key"])
def test_structured_failure_diagnostics_do_not_echo_provider_messages(code):
    from klaude_core.openai_images import OpenAIImageTransport

    error = OpenAIImageTransport._failure(
        {"type": "error", "code": code, "message": "private-provider-body"}
    )
    assert "private-provider-body" not in str(error)
    assert str(error) != "OpenAI response failed or incomplete"


def test_credit_exhaustion_is_not_a_temporary_fallback(lab):
    fallback = lab.conn.model_ref("gpt-4.1-mini-2025-04-14")
    save_defaults(
        lab.cfg,
        DefaultsChange(
            "vision_fallbacks",
            (fallback,),
            (),
            (
                (
                    fallback,
                    lab.conn.revision,
                    provider_secret_revision(lab.cfg.config_dir, lab.conn.key_env),
                ),
            ),
        ),
    )
    _, _, spec = review(lab)
    lab.mode.update(http=429, error_code="credit_balance_exhausted", fallback=True)
    with pytest.raises(CompatibleModelError, match="credits exhausted"):
        vision.analyze(lab.cfg, spec)
    assert [p["model"] for _, p, _ in lab.calls if "input" in p] == [MODEL]


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [(429, "credit_balance_exhausted", "credits exhausted"),
     (401, "invalid_api_key", "HTTP 401")],
)
def test_owned_vision_errors_retain_redacted_provider_diagnostics(lab, status, code, expected):
    _, _, spec = review(lab)
    lab.mode.update(http=status, error_code=code)
    result = vision.execute({
        "operation": "analyze", "config_dir": str(lab.cfg.config_dir),
        "data_dir": str(lab.cfg.data_dir), "roles": lab.cfg.models,
        "ollama_url": lab.cfg.ollama_url, "spec": spec,
    })
    assert result["status"] == "error" and expected in result["message"]
    assert "private-provider-body" not in result["message"]
    assert "fixture-private-key" not in result["message"]
    assert len([p for _, p, _ in lab.calls if "input" in p]) == 1


def test_chat_rejects_output_budget_above_documented_limit_before_network(lab):
    import base64

    compose(lab)
    messages = [
        {
            "role": "user",
            "content": "",
            "image_content": [
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "data": base64.b64encode(lab.source.read_bytes()).decode(),
                }
            ],
        }
    ]
    with pytest.raises(RuntimeError, match="documented limit"):
        list(lab.agent.runtime.chat_stream(MODEL, messages, options={"num_predict": 40_000}))
    assert not [p for _, p, _ in lab.calls if "input" in p]
