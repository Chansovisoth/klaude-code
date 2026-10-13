import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.model_settings import PROVIDERS, ConnectionDraft
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.compatible_runtime import CompatibleModelError
from klaude_core.deepseek_runtime import MAX_REASONING_CHARS, DeepSeekRuntime
from klaude_core.model_connections import ModelConnection, connection_key, connection_registry
from klaude_core.model_discovery import discover_connection
from klaude_core.model_runtime import ModelInfo, chat_completion_messages
from klaude_core.ollama import _native_messages
from klaude_core.utility import eligible_failure, runtime_for_utility


def stream(delta, finish="stop"):
    events = [
        {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 6}},
    ]
    return (
        b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
        + b"data: [DONE]\n\n"
    )


def runtime(responses, captured):
    client = DeepSeekRuntime("https://deepseek.example/prefix/v1", "private-key")

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=responses.pop(0))

    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handle),
    )
    return client


def agent(client, executed):
    return Agent(
        client,
        "catalog-model",
        [
            Tool(
                "inspect",
                "Inspect",
                {"type": "object"},
                lambda: executed.append(True) or "verified tool result",
            )
        ],
        PermissionGate({"inspect": "allow"}, lambda *_args: "n"),
        "system",
        model_info=ModelInfo("deepseek", "catalog-model", "Catalog model"),
        tool_selector=lambda _message, available: list(available),
        ollama_think="medium",
    )


def call(arguments="{}"):
    return {"index": 0, "id": "call-1", "function": {"name": "inspect", "arguments": arguments}}


def test_reasoning_tool_round_trip_is_private_and_restorable():
    captured, executed = [], []
    client = runtime(
        [
            stream({"reasoning_content": "private-first", "tool_calls": [call()]}, "tool_calls"),
            stream({"reasoning_content": "private-final", "content": "Done."}),
        ],
        captured,
    )
    try:
        session = agent(client, executed)
        events = list(session.run("Inspect then explain the result"))
        assert executed == [True] and len(captured) == 2
        assert captured[0]["thinking"] == {"type": "enabled"}
        assert captured[0]["reasoning_effort"] == "high"
        assert captured[1]["messages"][-2]["reasoning_content"] == "private-first"
        assert captured[1]["messages"][-1]["tool_call_id"] == "call-1"
        assert client.last_chat_metadata["usage"]["completion_tokens"] == 6
        visible = [event.payload.get("content", "") for event in events]
        assert "private-" not in str(visible)
        final = next(
            event.payload
            for event in events
            if event.kind == "text" and event.payload["content"] == "Done."
        )
        assert (
            final["model_message"]["deepseek_continuation"]["reasoning_content"] == "private-final"
        )
        session.restore_session(
            [{"role": "assistant", "content": "Done.", "model_content": final["model_message"]}]
        )
        assert session.messages[-1]["deepseek_continuation"]["reasoning_content"] == "private-final"
    finally:
        client.close()


@pytest.mark.parametrize("changed", ["endpoint", "identity", "model", "generic", "tool-free"])
def test_continuation_never_crosses_endpoint_model_or_generic_boundary(changed):
    client = DeepSeekRuntime("https://deepseek.example/v1", "key")
    try:
        history = [
            {
                "role": "assistant",
                "content": "Visible",
                "deepseek_continuation": {
                    "scope": client.continuation_scope,
                    "model": "model",
                    "reasoning_content": "private-canary",
                },
            }
        ]
        original = deepcopy(history)
        tools = [{"type": "function", "function": {"name": "inspect"}}]
        if changed == "generic":
            payload = {"messages": chat_completion_messages(history)}
        elif changed in {"endpoint", "identity"}:
            other = DeepSeekRuntime(
                "https://other.example/v1" if changed == "endpoint" else client.base_url,
                "other-key",
                connection_scope="other-account",
            )
            try:
                payload = other._request_payload("model", history, tools, {}, True)
            finally:
                other.close()
        else:
            payload = client._request_payload(
                "other-model" if changed == "model" else "model",
                history,
                None if changed == "tool-free" else tools,
                {},
                True,
            )
        assert "private-canary" not in str(payload)
        assert "private-canary" not in str(_native_messages(history))
        assert history == original
        assert "private-canary" in str(client._request_payload("model", history, tools, {}, True))
    finally:
        client.close()


@pytest.mark.parametrize(
    "think,expected",
    [
        (None, None),
        (False, None),
        ("low", "low"),
        ("medium", "high"),
        ("high", "high"),
        ("max", "max"),
    ],
)
def test_modes_output_bound_and_child_transport(think, expected):
    client = DeepSeekRuntime(api_key="key", timeout=7)
    child = client.fork_for_child()
    try:
        body = client._request_payload(
            "model",
            [{"role": "user", "content": "hello"}],
            None,
            {"num_predict": 512, "num_gpu": 0, "num_ctx": 99999, "temperature": 0.2},
            think,
        )
        assert body["max_tokens"] == 512 and "num_gpu" not in body and "num_ctx" not in body
        assert body["thinking"]["type"] == ("enabled" if expected else "disabled")
        assert body.get("reasoning_effort") == expected
        assert ("temperature" in body) is (expected is None)
        assert isinstance(child, DeepSeekRuntime)
        assert child._client is not client._client and child.timeout == 7
        assert child.continuation_scope == client.continuation_scope
    finally:
        child.close()
        client.close()


@pytest.mark.parametrize("reasoning", [{"invalid": True}, "x" * (MAX_REASONING_CHARS + 1)])
def test_invalid_or_oversized_reasoning_never_publishes_calls(reasoning):
    client = runtime(
        [stream({"reasoning_content": reasoning, "tool_calls": [call()]}, "tool_calls")], []
    )
    try:
        with pytest.raises(CompatibleModelError):
            client.chat("model", [{"role": "user", "content": "inspect"}])
    finally:
        client.close()


def test_malformed_call_uses_agent_recovery_once_and_preserves_tool_continuation():
    captured, executed = [], []
    client = runtime(
        [
            stream(
                {"reasoning_content": "discarded-private", "tool_calls": [call("{")]}, "tool_calls"
            ),
            stream({"reasoning_content": "valid-private", "tool_calls": [call()]}, "tool_calls"),
            stream({"content": "Recovered."}),
        ],
        captured,
    )
    try:
        events = list(agent(client, executed).run("Inspect then explain the result"))
        assert executed == [True] and len(captured) == 3
        assert "discarded-private" not in str(captured[1])
        assert "valid-private" in str(captured[2])
        assert len([event for event in events if event.kind == "retry"]) == 1
        assert any(
            event.kind == "text" and event.payload["content"] == "Recovered." for event in events
        )
    finally:
        client.close()


@pytest.mark.parametrize("finish", ["length", None, "aborted"])
def test_incomplete_response_never_executes_buffered_tool(finish):
    executed = []
    client = runtime([stream({"tool_calls": [call()]}, finish)], [])
    try:
        events = list(agent(client, executed).run("Inspect then explain the result"))
        assert not executed and any(event.kind == "error" for event in events)
    finally:
        client.close()


def test_deepseek_preset_and_explicit_registry_do_not_seed_or_rewrite_legacy(tmp_path, monkeypatch):
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "small"},
        ollama_url="http://localhost:11434",
    )
    registry = connection_registry(cfg)
    before = registry.migrate(cfg)
    assert "deepseek" not in {item.backend for item in before.values()}
    assert PROVIDERS["deepseek"] == "DeepSeek"
    draft = ConnectionDraft("Cloud", "deepseek", "https://api.deepseek.com/v1", key="private-key")
    assert "private-key" not in repr(draft)
    connection = draft.connection()
    registry.add(connection, secret=draft.key)
    assert connection_key(cfg, connection) == "private-key"
    assert registry.migrate(cfg)[connection.id] == connection
    assert all(registry.load()[identity] == item for identity, item in before.items())
    assert "private-key" not in registry.path.read_text()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "another-provider-key")
    utility = runtime_for_utility(connection, connection_key(cfg, connection), timeout=5)
    try:
        assert isinstance(utility, DeepSeekRuntime) and utility.timeout == 5
        assert utility.api_key == "private-key"
    finally:
        utility.close()


def test_catalog_is_metadata_only_with_unknown_tools(monkeypatch):
    captured = []
    original = httpx.Client

    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{"id": "catalog-model"}]})

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    connection = ModelConnection(
        "deep", "DeepSeek", "deepseek", "https://api.deepseek.com/v1", "Cloud", "DEEPSEEK_API_KEY"
    )
    models = discover_connection(connection, "catalog-private-key")
    assert len(captured) == 1 and captured[0].method == "GET"
    assert captured[0].url.path == "/v1/models"
    assert captured[0].headers["Authorization"] == "Bearer catalog-private-key"
    assert models[0].ref == connection.model_ref("catalog-model")
    assert models[0].capabilities.tools_evidence == "unknown"


def test_status_error_is_sanitized_and_only_transient_failures_are_eligible():
    for code in (400, 401, 403, 429, 503):
        client = DeepSeekRuntime(api_key="key")
        client._chat_client_factory = lambda code=code, client=client: httpx.Client(
            base_url=client.base_url,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(code, text="private-error-body")
            ),
        )
        try:
            with pytest.raises(CompatibleModelError) as error:
                client.chat("model", [{"role": "user", "content": "hello"}])
            assert "private-error-body" not in str(error.value)
            assert error.value.status_code == code
            assert eligible_failure(error.value) is (code in {429, 503})
        finally:
            client.close()


def test_cli_deepseek_registration_defaults_to_private_reference_and_https(tmp_path, monkeypatch):
    from klaude_cli import model_connections as command
    from typer.testing import CliRunner

    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "small"},
        ollama_url="http://localhost:11434",
    )
    monkeypatch.setattr(command, "load_config", lambda: cfg)
    runner = CliRunner()
    rejected = runner.invoke(
        command.app, ["add", "deep", "--adapter", "deepseek", "--url", "http://api.deepseek.com/v1"]
    )
    assert rejected.exit_code == 1 and "HTTPS" in rejected.stdout
    assert not connection_registry(cfg).path.exists()
    accepted = runner.invoke(
        command.app,
        ["add", "deep", "--adapter", "deepseek", "--url", "https://api.deepseek.com/v1"],
    )
    assert accepted.exit_code == 0
    connection = connection_registry(cfg).load()["deep"]
    assert connection.source == "Cloud" and connection.key_env == "DEEPSEEK_API_KEY"
    assert not (cfg.config_dir / ".env").exists()
