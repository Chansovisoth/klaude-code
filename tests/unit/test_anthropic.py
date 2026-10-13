import json
from copy import deepcopy

import httpx
import pytest
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.anthropic_runtime import (
    API_VERSION,
    MAX_THINKING_CHARS,
    AnthropicModelError,
    AnthropicRuntime,
    catalog_capabilities,
)
from klaude_core.model_connections import ModelConnection
from klaude_core.model_discovery import ModelDiscoveryError, discover_connection
from klaude_core.model_runtime import (
    ModelCapabilities,
    ModelInfo,
    chat_completion_messages,
    model_records,
    models_from_records,
    normalize_token_usage,
)
from klaude_core.ollama import _native_messages
from klaude_core.utility import eligible_failure

CAP = ModelCapabilities(thinking_types=("disabled", "adaptive"))


def stream(blocks, finish="end_turn", stop=True):
    events = [
        {
            "type": "message_start",
            "message": {
                "role": "assistant",
                "content": [],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 3,
                    "cache_creation_input_tokens": 4,
                },
            },
        }
    ]
    for index, block in enumerate(blocks):
        delta = None
        if block["type"] == "tool_use" and isinstance(block.get("input"), str):
            delta = {"type": "input_json_delta", "partial_json": block["input"]}
            block = {**block, "input": {}}
        events.append({"type": "content_block_start", "index": index, "content_block": block})
        if delta:
            events.append({"type": "content_block_delta", "index": index, "delta": delta})
        events.append({"type": "content_block_stop", "index": index})
    events.append(
        {"type": "message_delta", "delta": {"stop_reason": finish}, "usage": {"output_tokens": 9}}
    )
    if stop:
        events.append({"type": "message_stop"})
    return b"".join(
        b"event: " + event["type"].encode() + b"\ndata: " + json.dumps(event).encode() + b"\n\n"
        for event in events
    )


def runtime(responses, captured):
    client = AnthropicRuntime(
        "https://anthropic.example/gateway/v1",
        "private-key",
        model="catalog-model",
        capabilities=CAP,
    )

    def handle(request):
        captured.append(request)
        return httpx.Response(200, content=responses.pop(0))

    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handle)
    )
    return client


def tool(arguments="{}", identity="call-1"):
    return {"type": "tool_use", "id": identity, "name": "inspect", "input": arguments}


def thinking():
    return {
        "type": "thinking",
        "thinking": "private-reasoning-canary",
        "signature": "private-signature-canary",
    }


def agent(client, executed):
    return Agent(
        client,
        "catalog-model",
        [
            Tool(
                "inspect",
                "Inspect",
                {"type": "object"},
                lambda: executed.append(True) or "actual-result",
            )
        ],
        PermissionGate({"inspect": "allow"}, lambda *_args: "n"),
        "system",
        model_info=ModelInfo("anthropic", "catalog-model", "Catalog", CAP),
        tool_selector=lambda _message, available: list(available),
        ollama_think="medium",
    )


def test_native_agent_tools_private_signatures_final_restore_and_usage():
    captured, executed = [], []
    client = runtime(
        [
            stream([thinking(), tool()], "tool_use"),
            stream([thinking(), {"type": "text", "text": "Done."}]),
        ],
        captured,
    )
    try:
        session = agent(client, executed)
        events = list(session.run("Inspect and explain the result"))
        assert executed == [True] and len(captured) == 2
        body = json.loads(captured[1].content)
        assert body["system"].startswith("system\n\n<turn_capabilities>")
        assert all(message["role"] != "system" for message in body["messages"])
        assert body["messages"][-2]["content"][0] == thinking()
        assert body["messages"][-1]["content"][0] == {
            "type": "tool_result",
            "tool_use_id": "call-1",
            "content": "actual-result",
        }
        assert body["tools"][0]["input_schema"] == {"type": "object"}
        assert captured[1].url.path == "/gateway/v1/messages"
        assert normalize_token_usage(client.last_chat_metadata) == (19, 9)
        assert "private-" not in str([event.payload.get("content", "") for event in events])
        final = next(
            event.payload
            for event in events
            if event.kind == "text" and event.payload["content"] == "Done."
        )
        session.restore_session(
            [{"role": "assistant", "content": "Done.", "model_content": final["model_message"]}]
        )
        assert session.messages[-1]["anthropic_continuation"]["blocks"][0] == thinking()
    finally:
        client.close()


def test_streamed_fragmented_thinking_signature_and_json_are_assembled_once():
    events = [
        {"type": "message_start", "message": {}},
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "private"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig-"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "end"},
        },
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": tool({})},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"path":'},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '"README.md"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
        {"type": "message_stop"},
    ]
    raw = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
    client = runtime([raw], [])
    try:
        message = client.chat("catalog-model", [{"role": "user", "content": "inspect"}])
        assert message["tool_calls"][0]["function"]["arguments"] == '{"path":"README.md"}'
        blocks = message["anthropic_continuation"]["blocks"]
        assert blocks[0] == {"type": "thinking", "thinking": "private", "signature": "sig-end"}
        assert blocks[1]["input"] == {"path": "README.md"}
        assert "private" not in message["content"]
    finally:
        client.close()


@pytest.mark.parametrize("boundary", ["endpoint", "identity", "model", "generic", "orphan"])
def test_private_blocks_never_cross_boundaries_or_mutate_shared_history(boundary):
    client = runtime([], [])
    other = AnthropicRuntime(
        "https://other.example/v1" if boundary == "endpoint" else client.base_url,
        "other-key",
        connection_scope="other" if boundary == "identity" else "",
    )
    try:
        history = [
            {
                "role": "assistant",
                "content": "Checking",
                "tool_calls": [
                    {"id": "call-1", "function": {"name": "inspect", "arguments": "{}"}}
                ],
                "anthropic_continuation": {
                    "scope": client.continuation_scope,
                    "model": "catalog-model",
                    "blocks": [thinking(), tool({})],
                },
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "result"},
        ]
        if boundary == "orphan":
            history.pop()
        original = deepcopy(history)
        converted = (
            chat_completion_messages(history)
            if boundary == "generic"
            else other._messages("other-model" if boundary == "model" else "catalog-model", history)
        )
        assert "private-reasoning-canary" not in str(converted)
        assert "private-reasoning-canary" not in str(_native_messages(history))
        assert history == original
    finally:
        client.close()
        other.close()


@pytest.mark.parametrize(
    "finish,stop", [("max_tokens", True), ("tool_use", False), ("pause_turn", True)]
)
def test_incomplete_tool_response_never_executes_or_publishes_state(finish, stop):
    executed = []
    client = runtime([stream([thinking(), tool()], finish, stop)], [])
    try:
        events = list(agent(client, executed).run("Inspect and explain"))
        assert not executed and any(event.kind == "error" for event in events)
        assert not any(event.payload.get("model_message") for event in events)
    finally:
        client.close()


def test_malformed_call_recovers_once_without_replaying_broken_signed_state():
    captured, executed = [], []
    client = runtime(
        [
            stream([thinking(), tool("{")], "tool_use"),
            stream([thinking(), tool()], "tool_use"),
            stream([{"type": "text", "text": "Recovered."}]),
        ],
        captured,
    )
    try:
        events = list(agent(client, executed).run("Inspect and explain"))
        assert executed == [True] and len(captured) == 3
        assert len([event for event in events if event.kind == "retry"]) == 1
        assert "private-reasoning-canary" not in captured[1].content.decode()
        assert any(
            event.kind == "text" and event.payload["content"] == "Recovered." for event in events
        )
    finally:
        client.close()


@pytest.mark.parametrize(
    "block",
    [
        {"type": "thinking", "thinking": "private", "signature": ""},
        {"type": "redacted_thinking", "data": "x" * (MAX_THINKING_CHARS + 1)},
        {"type": "text", "text": False},
    ],
)
def test_invalid_private_blocks_fail_before_calls_are_published(block):
    client = runtime([stream([block, tool()], "tool_use")], [])
    try:
        with pytest.raises(AnthropicModelError):
            client.chat("catalog-model", [])
    finally:
        client.close()


@pytest.mark.parametrize(
    "types,think,limit,expected",
    [
        (("disabled", "adaptive"), False, 512, {"type": "disabled"}),
        (("disabled", "adaptive"), "low", 512, {"type": "adaptive"}),
        (("disabled", "enabled"), "high", 1500, {"type": "enabled", "budget_tokens": 1499}),
    ],
)
def test_declared_modes_and_output_caps_without_provider_name_guesses(
    types, think, limit, expected
):
    client = AnthropicRuntime(
        api_key="key",
        model="arbitrary-name",
        capabilities=ModelCapabilities(thinking_types=types, max_output_tokens=2000),
    )
    child = client.fork_for_child()
    try:
        body = client._request_payload(
            "arbitrary-name",
            [{"role": "system", "content": "system"}, {"role": "user", "content": "hi"}],
            None,
            {"num_predict": limit, "num_ctx": 8192, "num_gpu": 0, "temperature": 0.2},
            think,
        )
        assert body["thinking"] == expected and body["max_tokens"] == limit
        assert "num_ctx" not in body and "num_gpu" not in body and "temperature" not in body
        assert (
            child._client is not client._client
            and child.continuation_scope == client.continuation_scope
        )
        assert child._client.headers["x-api-key"] == "key"
        assert child._client.headers["anthropic-version"] == API_VERSION
    finally:
        client.close()
        child.close()


@pytest.mark.parametrize(
    "types,think,limit",
    [
        (("adaptive",), False, 512),
        (None, "high", 2048),
        (("disabled",), "high", 2048),
        (("disabled", "enabled"), "high", 1024),
    ],
)
def test_unsupported_modes_do_not_silently_enable_thinking_or_raise_budget(types, think, limit):
    client = AnthropicRuntime(
        api_key="key", model="model", capabilities=ModelCapabilities(thinking_types=types)
    )
    try:
        with pytest.raises(AnthropicModelError):
            client._request_payload("model", [], None, {"num_predict": limit}, think)
    finally:
        client.close()


def test_native_catalog_pagination_capability_roundtrip_and_headers(monkeypatch):
    requests = []
    original = httpx.Client

    def handle(request):
        requests.append(request)
        second = "after_id" in request.url.params
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "last" if second else "first",
                        "display_name": "Catalog model",
                        "max_tokens": 2048,
                        "capabilities": {
                            "thinking": {
                                "types": {
                                    "disabled": {"supported": False},
                                    "adaptive": {"supported": True},
                                }
                            }
                        },
                    }
                ],
                "has_more": not second,
                "last_id": "last" if second else "first",
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    connection = ModelConnection(
        "anth",
        "Anthropic",
        "anthropic",
        "https://api.anthropic.com/v1",
        "Cloud",
        "ANTHROPIC_API_KEY",
    )
    models = discover_connection(connection, "private-key")
    assert len(requests) == 2 and all(request.method == "GET" for request in requests)
    assert requests[1].url.params["after_id"] == "first"
    assert (
        requests[0].headers["x-api-key"] == "private-key"
        and "Authorization" not in requests[0].headers
    )
    assert (
        models[0].capabilities.requires_thinking
        and models[0].capabilities.tools_evidence == "unknown"
    )
    assert models_from_records(model_records(models)) == models


@pytest.mark.parametrize(
    "code,status",
    [(401, "authentication"), (404, "missing_catalog"), (429, "rate_limit"), (529, "service")],
)
def test_catalog_errors_do_not_expose_response_bodies(monkeypatch, code, status):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(
            **kwargs,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(code, text="private-error-body")
            ),
        ),
    )
    connection = ModelConnection(
        "anth",
        "Anthropic",
        "anthropic",
        "https://api.anthropic.com/v1",
        "Cloud",
        "ANTHROPIC_API_KEY",
    )
    with pytest.raises(ModelDiscoveryError) as error:
        discover_connection(connection, "key")
    assert error.value.status == status and "private-error-body" not in str(error.value)


def test_overloaded_stream_uses_typed_explicit_fallback_only():
    client = runtime(
        [
            b'data: {"type":"error","error":{"type":"overloaded_error",'
            b'"message":"private-error-body"}}\n\n'
        ],
        [],
    )
    try:
        with pytest.raises(AnthropicModelError) as error:
            client.chat("catalog-model", [])
        assert eligible_failure(error.value) and error.value.status_code == 529
        assert "private-error-body" not in str(error.value)
    finally:
        client.close()


def test_native_catalog_repeated_cursor_and_capability_corruption_fail_safely(monkeypatch):
    original = httpx.Client
    page = {"data": [{"id": "same"}], "has_more": True, "last_id": "same"}
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(
            **kwargs, transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=page))
        ),
    )
    connection = ModelConnection("anth", "Anthropic", "anthropic", "https://api.anthropic.com/v1")
    with pytest.raises(ModelDiscoveryError, match="Malformed"):
        discover_connection(connection, "key")
    with pytest.raises(ValueError):
        catalog_capabilities(
            {"capabilities": {"thinking": {"types": {"disabled": {"supported": "yes"}}}}}
        )
    record = model_records([ModelInfo("anthropic", "m", "m", connection_id="anth")])[0]
    record["thinking_types"] = [{"invalid": "shape"}]
    assert models_from_records([record])[0].capabilities.thinking_types is None
