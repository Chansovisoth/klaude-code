import json
import threading
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from klaude_core.anthropic_runtime import AnthropicRuntime
from klaude_core.compatible_runtime import CompatibleModelError, CompatibleRuntime
from klaude_core.config import Config, save_provider_secret
from klaude_core.deepseek_runtime import DeepSeekRuntime
from klaude_core.model_connections import (
    ModelConnection,
    connection_key,
    connection_registry,
    normalize_model_url,
    split_model_ref,
)
from klaude_core.model_discovery import ModelDiscoveryError, discover_connection, probe_connection
from klaude_core.model_runtime import (
    ModelInfo,
    load_model_cache,
    model_cache_generation,
    save_model_cache,
)
from klaude_core.settings_store import SettingsConflictError, atomic_write_private


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr("klaude_core.config.CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr("klaude_core.config.DATA_DIR", tmp_path / "data")
    return Config()


def test_shared_connection_service_preserves_registry_migration_and_duplicate_guard(cfg):
    from klaude_application.model_connections import ModelConnectionAdd, ModelConnectionService

    service = ModelConnectionService(cfg)
    connection = ModelConnection(
        "lab", "Lab", "openai_compatible", "http://localhost:8080", "Local",
        "KLAUDE_MODEL_LAB_KEY",
    )
    assert "default-ollama" in service.list()
    action = ModelConnectionAdd(connection, "secret")
    assert "secret" not in repr(action)
    service.add(action)
    assert service.list()["lab"].backend == "openai_compatible"
    with pytest.raises(SettingsConflictError):
        service.add(action)


@pytest.mark.parametrize(
    "adapter,url,expected",
    [
        ("ollama", "http://localhost:11434/api/", "http://localhost:11434"),
        ("ollama", "http://[::1]:11434/v1", "http://[::1]:11434"),
        ("ollama", "https://host/gateway/api", "https://host/gateway"),
        ("openai_compatible", "http://192.168.1.2:8080", "http://192.168.1.2:8080/v1"),
        ("openai_compatible", "http://localhost:11434/api", "http://localhost:11434/v1"),
        ("openai_compatible", "https://host/prefix/v1/", "https://host/prefix/v1"),
    ],
)
def test_url_normalization_preserves_api_prefix(adapter, url, expected):
    assert normalize_model_url(url, adapter) == expected
    assert normalize_model_url(expected, adapter) == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/models",
        "http://user:secret@host/v1",
        "http://host/v1?api_key=secret",
        "http://host/v1#secret",
        "http://host/%0a",
        "http://host\\bad",
        "http://host:bad",
    ],
)
def test_unsafe_urls_rejected_without_echoing_them(url):
    with pytest.raises(ValueError) as error:
        normalize_model_url(url, "openai_compatible")
    assert "secret" not in str(error.value)


def test_registry_migration_is_private_idempotent_and_preserves_selection(cfg):
    preferences = cfg.data_dir / "chat-preferences.json"
    atomic_write_private(
        preferences,
        json.dumps({"last_model": "openrouter/vendor/model", "permissions": {"read_file": "ask"}}),
    )
    original = preferences.read_bytes()
    registry = connection_registry(cfg)
    connections = registry.migrate(cfg, preferences)
    assert connections["default-ollama"].base_url == cfg.ollama_url
    assert connections["default-openai-api"].key_env == "OPENAI_API_KEY"
    assert registry.path.stat().st_mode & 0o777 == 0o600
    payload = json.loads(registry.path.read_text())
    assert payload["legacy"]["startup_model"] == "openrouter/vendor/model"
    assert payload["legacy"]["roles"] == cfg.models
    registry.add(ModelConnection("lab", "Lab", "openai_compatible", "http://localhost:8080"))
    before = registry.path.read_bytes()
    assert "lab" in registry.migrate(cfg, preferences)
    assert registry.path.read_bytes() == before
    assert preferences.read_bytes() == original
    payload = json.loads(before)
    payload["connections"]["lab"]["enabled"] = False
    del payload["connections"]["default-openrouter"]
    atomic_write_private(registry.path, json.dumps(payload))
    assert not registry.migrate(cfg)["lab"].enabled
    assert "default-openrouter" not in registry.load()


def test_registry_rejects_malformed_versions_secrets_and_duplicate_identity(cfg):
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    before = registry.path.read_bytes()
    with pytest.raises(ValueError):
        ModelConnection.from_record({"api_key": "private"})
    with pytest.raises(OSError):
        registry.add(registry.load()["default-ollama"])
    assert registry.path.read_bytes() == before
    atomic_write_private(registry.path, '{"version": 9, "connections": {}}')
    with pytest.raises(ValueError, match="version"):
        registry.migrate(cfg)


def test_saved_key_removal_overrides_stale_environment(cfg, monkeypatch):
    connection = ModelConnection(
        "lab", "Lab", "openai_compatible", "http://localhost:8080", key_env="LAB_KEY"
    )
    save_provider_secret(cfg.config_dir, "LAB_KEY", "first-key")
    assert connection_key(cfg, connection) == "first-key"
    save_provider_secret(cfg.config_dir, "LAB_KEY", "")
    monkeypatch.setenv("LAB_KEY", "stale-key")
    assert connection_key(cfg, connection) == ""
    assert "first-key" not in connection.revision


def test_model_identity_and_cache_do_not_collapse_servers(tmp_path):
    one = ModelInfo("ollama", "same/model", "Same", connection_id="one")
    two = replace(one, connection_id="two")
    legacy = ModelInfo("openrouter", "vendor/model", "Cloud")
    assert one.ref != two.ref and one.request_identity != two.request_identity
    assert split_model_ref(one.ref) == ("ollama", "one", "same/model")
    assert split_model_ref(legacy.ref) is None
    assert legacy.request_identity == ("openrouter", "vendor/model")
    cache = tmp_path / "cache.json"
    assert save_model_cache(cache, [one, two, legacy])
    assert save_model_cache(cache, [], backend="ollama", connection_id="one")
    assert {model.ref for model in load_model_cache(cache)} == {two.ref, legacy.ref}
    assert save_model_cache(cache, [], backend="openrouter")
    assert load_model_cache(cache) == [two]
    generation = model_cache_generation(cache, "ollama@two")
    assert save_model_cache(cache, [], backend="ollama", connection_id="two", invalidate=True)
    assert not save_model_cache(
        cache, [two], backend="ollama", connection_id="two", expected_generation=generation
    )


def stream_body(events):
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"


def runtime_with_events(events, captured=None):
    runtime = CompatibleRuntime("http://model.test/gateway/v1", "private-key")

    def handler(request):
        if captured is not None:
            captured.append(request)
        return httpx.Response(200, content=stream_body(events))

    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=runtime.base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer private-key"},
    )
    return runtime


def test_compatible_stream_assembles_tool_fragments_usage_and_clean_history():
    captured = []
    events = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {"name": "read_", "arguments": '{"path":'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"name": "file", "arguments": '"README.md"}'}}
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {
            "choices": [],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "private_field": "private"},
        },
    ]
    runtime = runtime_with_events(events, captured)
    try:
        result = runtime.chat(
            "test",
            [
                {
                    "role": "assistant",
                    "content": "previous",
                    "openrouter_reasoning_details": [{"secret": "opaque"}],
                }
            ],
            options={"num_ctx": 8192, "num_predict": 123},
            think="high",
        )
        assert result["tool_calls"][0]["function"] == {
            "name": "read_file",
            "arguments": '{"path":"README.md"}',
        }
        assert captured[0].url.path == "/gateway/v1/chat/completions"
        body = json.loads(captured[0].content)
        assert body["max_tokens"] == 123
        assert "opaque" not in str(body) and "num_ctx" not in body and "think" not in body
        assert runtime.last_chat_metadata["usage"] == {
            "prompt_tokens": 20,
            "completion_tokens": 10,
        }
        child = runtime.fork_for_child()
        try:
            assert child.base_url == runtime.base_url and child.api_key == runtime.api_key
            assert child.last_chat_metadata is not runtime.last_chat_metadata
        finally:
            child.close()
    finally:
        runtime.close()


@pytest.mark.parametrize("arguments", ["{", "[]", '"string"'])
def test_compatible_bad_arguments_use_existing_agent_recovery_marker(arguments):
    runtime = runtime_with_events(
        [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call",
                                    "function": {"name": "read_file", "arguments": arguments},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        ]
    )
    try:
        call = runtime.chat("test", [])["tool_calls"][0]
        assert call["parse_status"] == "malformed" and call["function"]["name"] == ""
    finally:
        runtime.close()


@pytest.mark.parametrize("finish", [None, "length", "content_filter"])
def test_compatible_incomplete_call_never_reaches_agent(finish):
    runtime = runtime_with_events(
        [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call",
                                    "function": {"name": "write_file", "arguments": "{}"},
                                }
                            ]
                        },
                        "finish_reason": finish,
                    }
                ]
            }
        ]
    )
    try:
        with pytest.raises(CompatibleModelError, match="output limit|complete answer"):
            runtime.chat("test", [])
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "code,status",
    [
        (401, "authentication"),
        (403, "authentication"),
        (404, "missing_catalog"),
        (429, "rate_limit"),
        (503, "service"),
        (302, "service"),
    ],
)
def test_discovery_errors_are_precise_and_do_not_leak_response(monkeypatch, code, status):
    client_type = httpx.Client
    monkeypatch.setattr(
        "klaude_core.model_discovery.httpx.Client",
        lambda **kwargs: client_type(
            **kwargs,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    code,
                    content="secret error",
                    headers={"location": "https://elsewhere"},
                )
            ),
        ),
    )
    connection = ModelConnection("test", "Test", "openai_compatible", "http://model.test/v1")
    with pytest.raises(ModelDiscoveryError) as error:
        discover_connection(connection)
    assert error.value.status == status and "secret" not in str(error.value)


@pytest.mark.parametrize("payload", [{}, {"data": "wrong"}, {"data": [{"id": "bad\nname"}]}])
def test_discovery_rejects_malformed_catalog(monkeypatch, payload):
    client_type = httpx.Client
    monkeypatch.setattr(
        "klaude_core.model_discovery.httpx.Client",
        lambda **kwargs: client_type(
            **kwargs,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        ),
    )
    with pytest.raises(ModelDiscoveryError) as error:
        discover_connection(ModelConnection("test", "Test", "openai_compatible", "http://host"))
    assert error.value.status == "malformed"


@pytest.mark.parametrize("change", ["definition", "credential", "generation"])
def test_probe_rejects_stale_publication(cfg, monkeypatch, change):
    from klaude_core.config import provider_secret_revision

    registry = connection_registry(cfg)
    registry.migrate(cfg)
    connection = ModelConnection(
        "test", "Test", "openai_compatible", "http://host", key_env="LAB_KEY"
    )
    registry.add(connection)
    save_provider_secret(cfg.config_dir, "LAB_KEY", "first")
    cache = cfg.data_dir / "model-cache.json"
    model = ModelInfo(
        connection.backend,
        "test",
        "Test",
        connection_id=connection.id,
        connection_revision=connection.revision,
    )

    def discover(*_):
        if change == "definition":
            payload = json.loads(registry.path.read_text())
            payload["connections"]["test"]["base_url"] = "http://other/v1"
            atomic_write_private(registry.path, json.dumps(payload))
        elif change == "credential":
            save_provider_secret(cfg.config_dir, "LAB_KEY", "second")
        else:
            save_model_cache(
                cache, [], backend=connection.backend, connection_id=connection.id, invalidate=True
            )
        return [model]

    monkeypatch.setattr("klaude_core.model_discovery.discover_connection", discover)
    result = probe_connection(
        {
            "connection": asdict(connection),
            "config_dir": str(cfg.config_dir),
            "key": "first",
            "credential_revision": provider_secret_revision(cfg.config_dir, "LAB_KEY"),
            "cache_file": str(cache),
            "generation": "",
        }
    )
    assert result["status"] == "stale" and not load_model_cache(cache)


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("adapter", [CompatibleRuntime, DeepSeekRuntime, AnthropicRuntime])
def test_compatible_cancel_before_headers_wakes_real_request(streamed, adapter):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            started.set()
            release.wait(5)
            self.close_connection = True

        def log_message(self, *_):
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except OSError:
        pytest.skip("test sandbox blocks loopback HTTP listener")
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    runtime = adapter(f"http://127.0.0.1:{server.server_port}/v1", "test-key", timeout=30)

    def request():
        try:
            if streamed:
                list(runtime.chat_stream("test", []))
            else:
                runtime.chat("test", [])
        except Exception as error:
            errors.append(error)
        finally:
            finished.set()

    worker = threading.Thread(target=request, daemon=True)
    worker.start()
    try:
        assert started.wait(2) and runtime._active_response is None
        assert runtime.cancel_active()
        assert finished.wait(1) and errors
        assert not runtime.cancel_active()
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(2)
        runtime.close()


def test_cli_selection_uses_endpoint_and_rejects_changed_definition(cfg):
    from klaude_cli.main import _resolve_requested_chat_model, _set_agent_model

    registry = connection_registry(cfg)
    registry.migrate(cfg)
    connection = ModelConnection("lab", "Lab", "openai_compatible", "http://other:8080")
    registry.add(connection)
    agent = SimpleNamespace(
        session_id="", model="old", model_info=ModelInfo("ollama", "old", "Old")
    )
    info = _resolve_requested_chat_model(cfg, None, connection.model_ref("same-model"))
    _set_agent_model(agent, cfg, None, info)
    try:
        assert agent.model_info.ref == "openai_compatible@lab/same-model"
        assert agent.runtime.base_url == "http://other:8080/v1"
        payload = json.loads(registry.path.read_text())
        payload["connections"]["lab"]["enabled"] = False
        atomic_write_private(registry.path, json.dumps(payload))
        old_runtime = agent.runtime
        with pytest.raises(ValueError, match="disabled"):
            _set_agent_model(agent, cfg, None, info)
        assert agent.runtime is old_runtime
    finally:
        agent.runtime.close()


def test_compatible_malformed_call_repairs_through_real_agent_loop():
    from klaude_core import Agent, PermissionGate, Tool

    responses = iter(
        [
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "id": "bad",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path":"private-bad-path',
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ],
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "id": "good",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path":"proof.txt"}',
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ],
            [
                {
                    "choices": [
                        {"delta": {"content": "Verified cobalt-731."}, "finish_reason": "stop"}
                    ]
                }
            ],
        ]
    )
    runtime = CompatibleRuntime("http://model.test/v1")
    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=runtime.base_url,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=stream_body(next(responses))),
        ),
    )
    calls = []
    tool = Tool(
        "read_file",
        "Read a file",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        lambda path: calls.append(path) or "cobalt-731",
    )
    agent = Agent(
        runtime,
        "test",
        [tool],
        PermissionGate({"read_file": "allow"}, lambda *_: "n"),
        "system",
        model_info=ModelInfo("openai_compatible", "test", "Test"),
    )
    try:
        events = list(agent.run("Read proof.txt"))
        assert calls == ["proof.txt"]
        assert any(event.kind == "retry" for event in events)
        assert any(
            event.kind == "text" and "cobalt-731" in event.payload["content"] for event in events
        )
        assert "private-bad-path" not in str(agent.messages)
    finally:
        runtime.close()


@pytest.mark.parametrize("source", ["Local", "Cloud"])
def test_local_compatible_context_budget_is_bounded_and_endpoint_scoped(source):
    from klaude_cli.main import _subagent_parallelism
    from klaude_core import Agent, PermissionGate

    runtime = CompatibleRuntime("http://model.test/v1")
    one = ModelInfo(
        "openai_compatible", "same", "Same", connection_id="one", connection_source=source
    )
    agent = Agent(
        runtime,
        "same",
        [],
        PermissionGate({}, lambda *_: "n"),
        "system",
        model_info=one,
        ollama_options={"num_ctx": 8192},
    )
    try:
        agent._last_request_options = {"num_ctx": 4096}
        agent._last_request_model = one.request_identity
        assert agent.request_context_window == 4096
        assert _subagent_parallelism(agent) == 1
        agent.model_info = replace(one, connection_id="two")
        assert agent.request_context_window == 8192
    finally:
        runtime.close()


def test_changed_default_url_does_not_relabel_legacy_catalog(cfg):
    from klaude_cli.main import _available_chat_models

    cfg.openrouter_api_key = "key"
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    cache = cfg.data_dir / "model-cache.json"
    save_model_cache(cache, [ModelInfo("openrouter", "old-host/model", "Old")])
    payload = json.loads(registry.path.read_text())
    payload["connections"]["default-openrouter"]["base_url"] = "https://changed/v1"
    atomic_write_private(registry.path, json.dumps(payload))
    assert not _available_chat_models(cfg, None, False)


@pytest.mark.parametrize("kind", ["symlink", "oversized", "fifo"])
def test_registry_rejects_unsafe_file_types_on_reads_and_writes(cfg, kind):
    import os

    registry = connection_registry(cfg)
    registry.path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        target = registry.path.with_suffix(".target")
        target.write_text("{}")
        registry.path.symlink_to(target)
    elif kind == "oversized":
        registry.path.write_bytes(b" " * 1_000_001)
    else:
        os.mkfifo(registry.path)
    with pytest.raises(ValueError):
        registry.load()
    with pytest.raises(ValueError):
        registry.migrate(cfg)
    with pytest.raises(ValueError):
        registry.add(ModelConnection("lab", "Lab", "ollama", "http://localhost:11434"))


def test_native_catalog_error_is_not_reported_as_a_successful_empty_connection(monkeypatch):
    class AuthenticationError(RuntimeError):
        status_code = 401

    def fail(*_args, **_kwargs):
        raise AuthenticationError("private-key-must-not-leak")

    monkeypatch.setattr("klaude_core.model_discovery.discover_gemini_models", fail)
    connection = ModelConnection(
        "gemini",
        "Gemini",
        "gemini_api",
        "https://generativelanguage.googleapis.com",
        "Cloud",
        "GEMINI_KEY",
    )
    with pytest.raises(ModelDiscoveryError) as error:
        discover_connection(connection, "private")
    assert error.value.status == "authentication"
    assert "private" not in str(error.value)


def test_large_merged_catalog_keeps_each_endpoint_instead_of_silently_slicing(tmp_path):
    cache = tmp_path / "cache.json"
    first = [ModelInfo("openrouter", f"one/model-{index}", "Model") for index in range(3000)]
    second = [
        ModelInfo("openai_compatible", f"model-{index}", "Model", connection_id="two")
        for index in range(1500)
    ]
    assert save_model_cache(cache, first, backend="openrouter")
    assert save_model_cache(cache, second, backend="openai_compatible", connection_id="two")
    loaded = load_model_cache(cache)
    assert len(loaded) == 4500
    assert {item.ref for item in loaded} == {item.ref for item in first + second}
