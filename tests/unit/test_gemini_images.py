"""Native Gemini pixels, signed history, completion gates and private Media."""

import base64
import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from klaude_core import Agent, PermissionGate, Tool, image_profiles, vision
from klaude_core.ai_defaults import DefaultsChange, migrate_defaults, save_defaults
from klaude_core.chat_images import ChatImages
from klaude_core.compatible_runtime import CompatibleModelError
from klaude_core.config import provider_secret_revision, save_provider_secret
from klaude_core.gemini_images import GeminiImages
from klaude_core.image_content import image_capability_label
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_runtime import (
    GeminiRuntime,
    ModelInfo,
    discover_gemini_models,
    gemini_capabilities,
)

from .test_library_artifacts import png

MODEL = "gemini-2.5-flash-lite"
SIGNATURE = base64.b64encode(b"private-signed-state").decode()


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
            self.send(
                json.dumps(
                    {
                        "name": "models/" + model,
                        "supportedGenerationMethods": mode.get("methods", ["generateContent"]),
                        "inputTokenLimit": mode.get("input_limit", 1_048_576),
                        "outputTokenLimit": 65_536,
                    }
                ).encode()
            )

        def do_POST(self):
            packet = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, packet, dict(self.headers)))
            arrived.set()
            if mode.get("slow"):
                time.sleep(2)
            if mode.get("http") and (not mode.get("fallback") or MODEL in self.path):
                self.send(b'{"error":{"message":"private-provider-body"}}', mode["http"])
                return
            tools = packet.get("tools") and not any(
                "functionResponse" in p for m in packet["contents"] for p in m["parts"]
            )
            parts = (
                [
                    {"text": "private thought", "thought": True, "thoughtSignature": SIGNATURE},
                    {"text": "I will inspect.", "thoughtSignature": SIGNATURE},
                    {
                        "functionCall": {
                            "name": "inspect",
                            "args": {},
                            **({"id": "call-1"} if mode.get("provider_id") else {}),
                        },
                        "thoughtSignature": SIGNATURE,
                    },
                ]
                if tools
                else [
                    {
                        "text": "x" * mode.get("text_size", 0) or "Red, Green, Blue",
                        "thoughtSignature": SIGNATURE,
                    }
                ]
            )
            candidate = {"content": {"role": "model", "parts": parts}, "index": 0}
            if not mode.get("unfinished"):
                candidate["finishReason"] = mode.get("finish", "STOP")
            events = [
                {
                    "candidates": [candidate],
                    "usageMetadata": {
                        "promptTokenCount": 20,
                        "candidatesTokenCount": 7,
                        "thoughtsTokenCount": 3,
                    },
                }
            ]
            if mode.get("split_signature") and not tools:
                text = parts[0]["text"]
                events.insert(
                    0,
                    {
                        "candidates": [
                            {"index": 0, "content": {"parts": [{"text": text}], "role": "model"}}
                        ]
                    },
                )
                events[-1]["candidates"][0]["content"]["parts"] = [
                    {"text": "", "thoughtSignature": SIGNATURE}
                ]
            if mode.get("late_error"):
                events.append({"error": {"message": "private-provider-body"}})
            if mode.get("after_stop"):
                events.append({"candidates": [{"content": {"parts": [{"text": "late"}]}}]})
            self.send("".join("data: " + json.dumps(e) + "\n\n" for e in events).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = httpx.Client._send_single_request

    def route(client, request):
        if request.url.host == "generativelanguage.googleapis.com":
            request.url = httpx.URL(
                f"http://127.0.0.1:{server.server_port}" + request.url.raw_path.decode()
            )
        return original(client, request)

    monkeypatch.setattr(httpx.Client, "_send_single_request", route)
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "text"},
        ollama_url="http://127.0.0.1:1",
    )
    conn = ModelConnection(
        "image",
        "Gemini fixture",
        "gemini_api",
        image_profiles.GEMINI_ROOT,
        source="Cloud",
        key_env="IMAGE_KEY",
    )
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    registry.add(conn)
    save_provider_secret(cfg.config_dir, conn.key_env, "fixture-private-key")
    migrate_defaults(cfg)
    save_defaults(cfg, DefaultsChange("vision_enabled", True, False))
    runtime = GeminiRuntime("fixture-private-key")
    info = ModelInfo(
        "gemini_api",
        MODEL,
        MODEL,
        connection_id=conn.id,
        connection_revision=conn.revision,
        credential_revision=provider_secret_revision(cfg.config_dir, conn.key_env),
    )
    agent = Agent(
        runtime,
        MODEL,
        [],
        PermissionGate({}, lambda *_: "n"),
        "Describe supplied pixels.",
        model_info=info,
        ollama_options={"num_ctx": 8192, "num_predict": 128},
    )
    agent.workdir = tmp_path
    agent.image_context = ChatImages(cfg, agent)
    source = tmp_path / "capture.png"
    source.write_bytes(png())
    try:
        yield SimpleNamespace(
            cfg=cfg, conn=conn, agent=agent, source=source, calls=calls, mode=mode, arrived=arrived
        )
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


def compose(lab):
    return lab.agent.image_context.compose("Describe the pixels", (lab.source,), "fixture")


def messages(lab):
    return [
        {"role": "system", "content": "Private image question"},
        {
            "role": "user",
            "content": "Colors?",
            "image_content": [
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "data": base64.b64encode(lab.source.read_bytes()).decode(),
                }
            ],
        },
    ]


def review(lab):
    ref = lab.conn.model_ref(MODEL)
    save_defaults(
        lab.cfg,
        DefaultsChange(
            "vision",
            ref,
            None,
            (
                (
                    ref,
                    lab.conn.revision,
                    provider_secret_revision(lab.cfg.config_dir, lab.conn.key_env),
                ),
            ),
        ),
    )
    store = ArtifactStore(lab.cfg.data_dir / "library")
    item = store.import_file(lab.source, "media")
    return (
        store,
        item,
        vision.prepare(lab.cfg, item["id"], item["revision"], "Colors?", context=2048, output=128),
    )


@pytest.mark.parametrize("model", [MODEL, "gemini-2.5-flash", *image_profiles.GEMINI_LEVELS])
def test_profiles_are_exact_and_official_only(model):
    assert image_profiles.gemini_image_profile(image_profiles.GEMINI_ROOT, model)
    assert not image_profiles.gemini_image_profile("https://proxy.example", model)
    for unknown in (model + "-future", model.upper(), "gemini-4-argon"):
        assert not image_profiles.gemini_image_profile(image_profiles.GEMINI_ROOT, unknown)


def test_inventory_marks_only_reviewed_models_as_documented(monkeypatch):
    entries = [
        SimpleNamespace(name="models/" + m, supported_generation_methods=["generateContent"])
        for m in (MODEL, "gemini-4-argon")
    ]
    entries.append(
        SimpleNamespace(name="models/gemini-embedding-001", supported_actions=["embedContent"])
    )
    entries.append(
        SimpleNamespace(
            name="models/gemini-2.5-flash-preview-tts", supported_actions=["generateContent"]
        )
    )
    genai = SimpleNamespace(
        Client=lambda **_: SimpleNamespace(models=SimpleNamespace(list=lambda: entries))
    )
    monkeypatch.setattr(GeminiRuntime, "_sdk", lambda _: (genai, object()))
    models = {m.model_id: m for m in discover_gemini_models("fixture-key")}
    caps = models[MODEL].capabilities
    assert (
        image_capability_label(caps.supports_images, caps.images_evidence) == "Images: documented"
    )
    assert models["gemini-4-argon"].capabilities.supports_images is None
    assert "gemini-embedding-001" not in models
    assert "gemini-2.5-flash-preview-tts" not in models


@pytest.mark.parametrize("fail", [False, True])
def test_lazy_catalog_keeps_client_alive_and_closes_after_iteration(monkeypatch, fail):
    resources = []

    class Client:
        def __init__(self, **options):
            self.state = SimpleNamespace(closed=False, options=options)
            resources.append(self.state)
            state = self.state

            def listed():
                assert not state.closed
                yield SimpleNamespace(name="models/" + MODEL, supported_actions=["generateContent"])
                if fail:
                    raise ValueError("lazy catalog failure")

            self.models = SimpleNamespace(list=listed)

        def close(self):
            self.state.closed = True

        def __del__(self):
            self.close()

    monkeypatch.setattr(GeminiRuntime, "_sdk", lambda _: (SimpleNamespace(Client=Client), object()))
    if fail:
        with pytest.raises(ValueError, match="lazy catalog failure"):
            discover_gemini_models("fixture-key", strict=True)
        assert discover_gemini_models("fixture-key") == []
    else:
        assert discover_gemini_models("fixture-key")[0].model_id == MODEL
    assert all(r.closed for r in resources)
    assert resources[0].options["http_options"] == {
        "timeout": 5000,
        "retry_options": {"attempts": 1},
    }


@pytest.mark.parametrize("streaming", [True, False])
def test_native_pixels_thinking_and_usage_budgets(lab, streaming):
    compose(lab)
    runtime = lab.agent.runtime
    if streaming:
        result = list(
            runtime.chat_stream(MODEL, messages(lab), options={"num_predict": 128}, think=False)
        )[-1]
    else:
        result = runtime.chat(MODEL, messages(lab), options={"num_predict": 128}, think="low")
    path, packet, headers = lab.calls[-1]
    assert path.endswith(":streamGenerateContent?alt=sse")
    assert headers["x-goog-api-key"] == "fixture-private-key" and "Authorization" not in headers
    assert packet["store"] is False
    assert packet["systemInstruction"]["parts"][0]["text"] == "Private image question"
    assert packet["generationConfig"] == {
        "candidateCount": 1,
        "maxOutputTokens": 128,
        "thinkingConfig": {"thinkingBudget": 0 if streaming else 1024},
    }
    raw = packet["contents"][0]["parts"][0]["inlineData"]
    assert raw["mimeType"] == "image/png" and base64.b64decode(raw["data"]) == png()
    assert result["gemini_continuation"]["parts"][0]["thoughtSignature"] == SIGNATURE
    assert runtime.last_chat_metadata["usage"]["output_tokens"] == 10


@pytest.mark.parametrize("provider_id", [True, False])
def test_agent_tool_roundtrip_and_restored_pixels_are_private(lab, provider_id):
    lab.mode["provider_id"] = provider_id
    ran = []
    lab.agent.tools = {
        "inspect": Tool("inspect", "", {"type": "object"}, lambda: ran.append(True) or "observed")
    }
    lab.agent.gate.policies["inspect"] = "allow"
    prepared = compose(lab)
    events = list(lab.agent.run(prepared))
    assert ran == [True] and not [e for e in events if e.kind == "error"]
    packets = [p for _, p, _ in lab.calls if "contents" in p]
    assert packets[0]["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"]
    returned = [p for m in packets[-1]["contents"] for p in m["parts"]]
    assert any(p.get("thought") and p["thoughtSignature"] == SIGNATURE for p in returned)
    assert any(p.get("text") == "I will inspect." and p.get("thoughtSignature") for p in returned)
    response = next(p["functionResponse"] for p in returned if "functionResponse" in p)
    assert response["name"] == "inspect" and (response.get("id") == "call-1") == provider_id
    assert "private thought" not in str([e.payload for e in events if e.kind == "text"])
    state = lab.agent.messages[-1]
    lab.source.unlink()
    lab.agent.tools = {}
    lab.agent.restore_session(
        [
            {"role": "user", "content": prepared["request"], "model_content": prepared},
            {"role": "assistant", "content": state["content"], "model_content": state},
        ]
    )
    assert "gemini_continuation" in lab.agent.messages[-1]
    events = list(lab.agent.run("Look at the retained pixels again"))
    assert not [e for e in events if e.kind == "error"]
    assert "inlineData" in str(lab.calls[-1][1])


@pytest.mark.parametrize("change", ["credential", "model"])
def test_signed_parts_never_cross_runtime_scopes(lab, change):
    compose(lab)
    runtime = lab.agent.runtime
    state = runtime.chat(MODEL, messages(lab), think=False)
    helper = runtime._image_transport
    model = "gemini-2.5-flash" if change == "model" else MODEL
    if change == "credential":
        helper.api_key = "other-key"
    projected = helper._contents(model, [state, {"role": "user", "content": "Next"}])
    assert "thoughtSignature" not in str(projected)
    assert "Red, Green, Blue" in str(projected)


@pytest.mark.parametrize(
    "change,value",
    [
        ("unfinished", True),
        ("finish", "MAX_TOKENS"),
        ("finish", "SAFETY"),
        ("finish", "MALFORMED_FUNCTION_CALL"),
        ("finish", "CONTINUATION"),
        ("late_error", True),
        ("after_stop", True),
        ("http", 401),
    ],
)
def test_failure_never_releases_calls_or_signed_state(lab, change, value):
    compose(lab)
    lab.mode[change] = value
    events = []
    with pytest.raises(CompatibleModelError) as error:
        for event in lab.agent.runtime.chat_stream(
            MODEL,
            messages(lab),
            tools=[
                {
                    "function": {"name": "inspect", "parameters": {"type": "object"}},
                }
            ],
        ):
            events.append(event)
    assert not any("tool_calls" in e or "gemini_continuation" in e for e in events)
    assert "private-provider-body" not in str(error.value)


@pytest.mark.parametrize("change", ["identity", "input_limit", "methods", "unknown", "credential"])
def test_fresh_preparation_rejects_invalid_metadata_or_binding(lab, change):
    if change == "unknown":
        lab.agent.model_info = replace(lab.agent.model_info, model_id="gemini-4-argon")
    elif change == "credential":
        save_provider_secret(lab.cfg.config_dir, lab.conn.key_env, "changed-key")
    else:
        lab.mode[change] = {"identity": True, "input_limit": True, "methods": []}[change]
    with pytest.raises(ValueError):
        compose(lab)
    assert not [p for _, p, _ in lab.calls if "contents" in p]


def test_private_media_has_no_tools_thinking_or_saved_analysis(lab):
    store, item, spec = review(lab)
    before = store.get(item["id"]), list(lab.agent.messages)
    result = vision.analyze(lab.cfg, spec)
    assert result["status"] == "complete" and result["text"] == "Red, Green, Blue"
    assert result["usage"] == {"prompt_eval_count": 20, "eval_count": 10}
    packet = lab.calls[-1][1]
    assert "tools" not in packet and packet["store"] is False
    assert packet["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert (store.get(item["id"]), list(lab.agent.messages)) == before
    assert not (lab.cfg.data_dir / "sessions.db").exists()


@pytest.mark.parametrize("size", [32_001, 300_000])
def test_media_text_and_event_limits(lab, size):
    _, _, spec = review(lab)
    lab.mode["text_size"] = size
    with pytest.raises((ValueError, CompatibleModelError)):
        vision.analyze(lab.cfg, spec)


def test_cancel_wakes_before_headers(lab):
    prepared = compose(lab)
    lab.mode["slow"] = True
    events = []
    thread = threading.Thread(target=lambda: events.extend(lab.agent.run(prepared)))
    thread.start()
    assert lab.arrived.wait(5)
    lab.agent.cancellation_check = lambda: True
    lab.agent.runtime.cancel_active()
    thread.join(1)
    assert not thread.is_alive()


def test_metadata_deadline_is_clean_and_sends_no_pixels(lab, monkeypatch):
    original = threading.Timer
    lab.mode["slow_metadata"] = True
    monkeypatch.setattr(vision.threading, "Timer", lambda _, callback: original(0.05, callback))
    with pytest.raises(ValueError, match="Could not verify image support"):
        compose(lab)
    assert not [p for _, p, _ in lab.calls if "contents" in p]


def test_only_reviewed_fallback_runs(lab):
    ref = lab.conn.model_ref("gemini-2.5-flash")
    save_defaults(
        lab.cfg,
        DefaultsChange(
            "vision_fallbacks",
            (ref,),
            (),
            (
                (
                    ref,
                    lab.conn.revision,
                    provider_secret_revision(lab.cfg.config_dir, lab.conn.key_env),
                ),
            ),
        ),
    )
    _, _, spec = review(lab)
    lab.mode.update(http=503, fallback=True)
    result = vision.analyze(lab.cfg, spec)
    assert result["status"] == "complete" and result["model"] == ref
    assert len([p for _, p, _ in lab.calls if "contents" in p]) == 2


def test_inline_20mb_and_output_limits_fail_before_network(lab):
    compose(lab)
    raw = messages(lab)
    pixel = raw[-1]["image_content"][0]
    pixel["data"] = base64.b64encode(b"x" * (8 * 1024 * 1024)).decode()
    raw[-1]["image_content"].append(dict(pixel))
    with pytest.raises(CompatibleModelError, match="20 MB"):
        lab.agent.runtime.chat(MODEL, raw)
    with pytest.raises(CompatibleModelError, match="Output budget"):
        lab.agent.runtime.chat(MODEL, messages(lab), options={"num_predict": 65537})
    assert not [p for _, p, _ in lab.calls if "contents" in p]


def test_orphan_calls_and_foreign_signed_history_are_not_replayed():
    runtime = GeminiImages("key")
    state = {
        "role": "assistant",
        "content": "Summary",
        "tool_calls": [
            {
                "id": "orphan",
                "function": {"name": "inspect", "arguments": "{}"},
            }
        ],
        "gemini_continuation": {
            "scope": runtime.scope(MODEL),
            "parts": [
                {
                    "functionCall": {"name": "inspect", "args": {}},
                    "thoughtSignature": SIGNATURE,
                }
            ],
        },
    }
    assert runtime._contents(MODEL, [state]) == []
    state["gemini_continuation"]["scope"] = "foreign"
    assert "thoughtSignature" not in str(runtime._contents(MODEL, [state]))
    runtime.close()


def test_unavailable_generation_does_not_trigger_an_unreviewed_model_switch(lab):
    _, _, spec = review(lab)
    lab.mode["http"] = 404
    with pytest.raises(CompatibleModelError, match="metadata visibility"):
        vision.analyze(lab.cfg, spec)
    assert len([p for _, p, _ in lab.calls if "contents" in p]) == 1


@pytest.mark.parametrize(
    "parts",
    [
        [{"functionCall": {"name": "inspect", "args": []}}],
        [{"text": "answer", "thoughtSignature": "not-base64!"}],
        [{"inlineData": {"mimeType": "image/png", "data": "eA=="}}],
    ],
)
def test_invalid_native_parts_fail_without_private_state(parts):
    with pytest.raises(CompatibleModelError):
        GeminiImages._parts(parts)


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("model", [MODEL, "gemini-3.8-flash"])
def test_parallel_native_round_is_atomic_and_groups_responses(partial, model):
    runtime = GeminiImages("fixture-key")
    calls = [{"id": str(i), "function": {"name": "inspect", "arguments": "{}"}} for i in range(2)]
    parts = [
        {
            "functionCall": {"name": "inspect", "args": {"index": i}},
            **({"thoughtSignature": SIGNATURE} if i == 0 else {}),
        }
        for i in range(2)
    ]
    history = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": calls,
            "gemini_continuation": {"scope": runtime.scope(model), "parts": parts},
        }
    ]
    history.extend(
        {"role": "tool", "tool_name": "inspect", "tool_call_id": str(i), "content": "observed"}
        for i in ([1] if partial else [0, 1])
    )
    try:
        contents = runtime._contents(model, history)
        if partial:
            assert contents == []
        else:
            assert contents[0]["parts"] == parts
            assert len(contents) == 2
            assert len(contents[-1]["parts"]) == 2
            assert all("functionResponse" in p for p in contents[-1]["parts"])
    finally:
        runtime.close()


def current_model(lab, model):
    lab.agent.model = model
    lab.agent.model_info = replace(
        lab.agent.model_info, model_id=model, capabilities=gemini_capabilities(model)
    )
    lab.agent.reasoning_mode = "thinking"
    effort = image_profiles.GEMINI_LEVELS[model][0]
    lab.agent.ollama_think = lab.agent.ollama_code_think = effort
    return effort


@pytest.mark.parametrize(
    "model,effort",
    [
        (model, effort)
        for model, levels in image_profiles.GEMINI_LEVELS.items()
        for effort in levels
    ],
)
def test_current_profiles_use_levels_and_bounded_native_pixels(lab, model, effort):
    current_model(lab, model)
    compose(lab)
    reply = lab.agent.runtime.chat(model, messages(lab), think=effort, options={"num_predict": 128})
    packet = lab.calls[-1][1]
    assert packet["generationConfig"]["thinkingConfig"] == {"thinkingLevel": effort}
    assert packet["generationConfig"]["maxOutputTokens"] == 128
    assert packet["store"] is False and "inlineData" in str(packet["contents"])
    assert reply["content"] == "Red, Green, Blue"


@pytest.mark.parametrize("model", image_profiles.GEMINI_LEVELS)
def test_current_native_route_preserves_signatures_before_first_image(lab, model, monkeypatch):
    effort = current_model(lab, model)
    monkeypatch.setattr(lab.agent.runtime, "_sdk", lambda: pytest.fail("native route needs no SDK"))
    lab.mode["split_signature"] = True
    reply = lab.agent.runtime.chat(
        model,
        [{"role": "user", "content": "Text question"}],
        think=effort,
        options={"num_predict": 128},
    )
    state = reply["gemini_continuation"]
    assert state["parts"] == [
        {"text": "Red, Green, Blue"},
        {"text": "", "thoughtSignature": SIGNATURE},
    ]
    lab.agent.runtime.chat(model, [reply, {"role": "user", "content": "Follow up"}], think=effort)
    assert lab.calls[-1][1]["contents"][0]["parts"] == state["parts"]
    assert "inlineData" not in str(lab.calls[-1][1])


@pytest.mark.parametrize("model", image_profiles.GEMINI_LEVELS)
def test_current_profiles_reject_media_and_standard_chat_without_pixels(lab, model):
    current_model(lab, model)
    ref = lab.conn.model_ref(model)
    save_defaults(
        lab.cfg,
        DefaultsChange(
            "vision",
            ref,
            None,
            (
                (
                    ref,
                    lab.conn.revision,
                    provider_secret_revision(lab.cfg.config_dir, lab.conn.key_env),
                ),
            ),
        ),
    )
    store = ArtifactStore(lab.cfg.data_dir / "library")
    item = store.import_file(lab.source, "media")
    with pytest.raises(ValueError, match="requires Thinking"):
        vision.prepare(lab.cfg, item["id"], item["revision"], "Colors?", context=2048, output=128)
    lab.agent.reasoning_mode = "standard"
    with pytest.raises(ValueError, match="Thinking"):
        compose(lab)
    assert not [p for _, p, _ in lab.calls if "contents" in p]


@pytest.mark.parametrize("model", image_profiles.GEMINI_LEVELS)
@pytest.mark.parametrize("effort", [False, None, "off", "unsupported"])
def test_current_cached_image_support_cannot_authorize_invalid_thinking(lab, model, effort):
    valid_effort = current_model(lab, model)
    compose(lab)
    lab.agent.runtime.chat(model, messages(lab), think=valid_effort)
    assert lab.agent.runtime.last_chat_metadata["usage"]["output_tokens"] == 10
    with pytest.raises(CompatibleModelError, match="requires Thinking"):
        lab.agent.runtime.chat(model, messages(lab), think=effort)
    assert not lab.agent.runtime.last_chat_metadata.get("usage")
    assert len([p for _, p, _ in lab.calls if "contents" in p]) == 1


def test_foreign_tool_history_remains_context_without_fabricated_signatures():
    runtime = GeminiImages("key")
    messages = [
        {
            "role": "assistant",
            "content": "Checked the project",
            "tool_calls": [
                {
                    "id": "earlier",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_name": "read_file",
            "tool_call_id": "earlier",
            "content": "Relevant project context",
        },
    ]
    try:
        contents = runtime._contents("gemini-3.8-flash", messages)
        assert "Relevant project context" in str(contents)
        assert "Checked the project" in str(contents)
        assert "functionCall" not in str(contents) and "functionResponse" not in str(contents)
        assert "thoughtSignature" not in str(contents)
        assert "Historical tool result; context only" in str(contents)
    finally:
        runtime.close()


@pytest.mark.parametrize("role", ["vision", "vision_fallbacks", "utility", "fallbacks", "research"])
def test_settings_manual_selection_cannot_enable_thinking_off_consumers(lab, role):
    from klaude_cli.ai_default_settings import AIDefaultSettings

    controller = AIDefaultSettings(SimpleNamespace())
    controller.connections = {lab.conn.id: lab.conn}
    controller.target, controller.role = lab.conn.id, role
    with pytest.raises(ValueError, match="requires Thinking"):
        controller.select("gemini-3.5-flash-lite")
    assert not lab.calls


def test_standard_utility_rejects_current_chat_before_model_work(lab, monkeypatch):
    from klaude_core.memory import Memory
    from klaude_core.utility import run_utility

    memory = Memory(lab.cfg.data_dir / "memory.md", lab.cfg.data_dir / "sessions.db")
    try:
        memory.log_turn("fixture", "user", "Summarize this public task")
        monkeypatch.setattr(
            "klaude_core.utility.runtime_for_utility",
            lambda *_: pytest.fail("must reject before runtime creation"),
        )
        with pytest.raises(ValueError, match="Utility uses Standard mode"):
            run_utility(
                {
                    "task": "recap",
                    "config_dir": str(lab.cfg.config_dir),
                    "data_dir": str(lab.cfg.data_dir),
                    "roles": lab.cfg.models,
                    "ollama_url": lab.cfg.ollama_url,
                    "session_id": "fixture",
                    "chat_ref": lab.conn.model_ref("gemini-3.5-flash-lite"),
                }
            )
        assert not lab.calls
    finally:
        memory.db.close()


def test_standard_research_rejects_current_model_before_retrieval(lab, monkeypatch):
    from klaude_core.research import (
        ResearchDefaults,
        ResearchError,
        ResearchStore,
        make_spec,
        run_research,
    )

    spec = make_spec(
        lab.cfg,
        "Compare documentation",
        lab.conn.model_ref("gemini-3.8-flash"),
        ResearchDefaults().public(),
    )
    item = ResearchStore(lab.cfg.data_dir / "library").create(spec)
    monkeypatch.setattr(
        "klaude_core.utility.runtime_for_utility",
        lambda *_: pytest.fail("must reject before runtime creation"),
    )
    with pytest.raises(ResearchError, match="Research uses Standard mode"):
        run_research(lab.cfg, item["id"])
    assert not lab.calls
