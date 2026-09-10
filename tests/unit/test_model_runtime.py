import pytest
from klaude_core.model_runtime import (
    CodexRuntime,
    GeminiRuntime,
    ModelInfo,
    OpenAIRuntime,
    discover_codex_models,
    grouped_local_models,
    load_model_cache,
    local_model_weight_first_key,
    newest_model_first_key,
    save_model_cache,
)


def test_model_info_has_stable_canonical_ref_and_derived_metadata():
    local = ModelInfo("ollama", "qwen3.5:9b", "qwen3.5:9b")
    cloud = ModelInfo("openai_api", "gpt-test", "gpt-test")

    assert local.ref == "ollama/qwen3.5:9b"
    assert (local.source, local.provider) == ("Local", "Ollama")
    assert cloud.ref == "openai_api/gpt-test"
    assert (cloud.source, cloud.provider) == ("Cloud", "OpenAI")


def test_openai_input_preserves_manual_tool_call_and_result_identity():
    payload = OpenAIRuntime._input(
        [
            {"role": "system", "content": "be useful"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "workspace_info", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_name": "workspace_info",
                "tool_call_id": "call_1",
                "content": "ok",
            },
        ]
    )

    assert payload[1]["type"] == "function_call"
    assert payload[1]["call_id"] == "call_1"
    assert payload[2] == {"type": "function_call_output", "call_id": "call_1", "output": "ok"}


def test_cloud_runtimes_reject_missing_credentials():
    from klaude_core.model_runtime import GeminiRuntime

    with pytest.raises(ValueError, match="OpenAI API key"):
        OpenAIRuntime("")
    with pytest.raises(ValueError, match="Gemini API key"):
        GeminiRuntime("  ")


def test_openai_responses_explicitly_disable_provider_storage(monkeypatch):
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"output": [], "output_text": "ok", "usage": None})()

    client = type("Client", (), {"responses": Responses()})()
    runtime = OpenAIRuntime("sk-test-not-a-real-key")
    monkeypatch.setattr(runtime, "_client", lambda: client)

    runtime.chat("gpt-test", [{"role": "user", "content": "hello"}])

    assert captured["store"] is False


def test_openai_failed_response_surfaces_provider_message(monkeypatch):
    error = type("Error", (), {"message": "provider failed"})()
    response = type(
        "Response",
        (),
        {"output": [], "output_text": "", "usage": None, "status": "failed", "error": error},
    )()

    class Responses:
        def create(self, **_kwargs):
            return response

    runtime = OpenAIRuntime("sk-test-not-a-real-key")
    monkeypatch.setattr(
        runtime, "_client", lambda: type("Client", (), {"responses": Responses()})()
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        runtime.chat("gpt-test", [{"role": "user", "content": "hello"}])


def test_openai_nonstream_refusal_is_visible():
    part = type("Part", (), {"type": "refusal", "refusal": "Request declined"})()
    item = type("Item", (), {"type": "message", "content": [part]})()
    response = type("Response", (), {"output": [item], "output_text": ""})()

    assert OpenAIRuntime._message(response)["content"] == "Request declined"


def test_openai_records_sanitized_response_identity_and_status():
    usage = type("Usage", (), {"model_dump": lambda self: {"input_tokens": 3}})()
    response = type(
        "Response",
        (),
        {"id": "resp_123", "status": "completed", "usage": usage},
    )()
    runtime = OpenAIRuntime("secret")

    runtime._record(response)

    assert runtime.last_chat_metadata == {
        "provider": "openai_api",
        "response_id": "resp_123",
        "status": "completed",
        "usage": {"input_tokens": 3},
    }


@pytest.mark.parametrize(
    ("model", "effort", "expected"),
    [
        ("gemini-3.5-pro", "high", {"thinking_level": "high"}),
        ("gemini-2.5-flash", "medium", {"thinking_budget": 8192}),
        ("gemini-2.5-flash", False, {"thinking_budget": 0}),
    ],
)
def test_gemini_reasoning_uses_generation_specific_controls(monkeypatch, model, effort, expected):
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return object()

    client = type("Client", (), {"models": Models()})()
    genai = type("GenAI", (), {"Client": lambda **_kwargs: client})
    runtime = GeminiRuntime("test-key")
    monkeypatch.setattr(runtime, "_sdk", lambda: (genai, object()))

    runtime._request(model, [{"role": "user", "content": "hello"}], None, False, effort)

    assert captured["config"]["thinking_config"] == expected


def test_gemini_function_response_preserves_provider_call_id(monkeypatch):
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return object()

    client = type("Client", (), {"models": Models()})()
    genai = type("GenAI", (), {"Client": lambda **_kwargs: client})
    runtime = GeminiRuntime("test-key")
    monkeypatch.setattr(runtime, "_sdk", lambda: (genai, object()))

    runtime._request(
        "gemini-3.5-pro",
        [
            {
                "role": "tool",
                "tool_name": "workspace_info",
                "tool_call_id": "call-123",
                "content": "ok",
            }
        ],
        None,
        False,
        None,
    )

    response = captured["contents"][0]["parts"][0]["function_response"]
    assert response["id"] == "call-123"


def test_gemini_function_call_round_trip_preserves_thought_signature(monkeypatch):
    captured = {}
    signature = b"encrypted-reasoning-state"
    function_call = type("Call", (), {"id": "call-1", "name": "lookup", "args": {}})()
    part = type("Part", (), {"function_call": function_call, "thought_signature": signature})()
    content = type("Content", (), {"parts": [part]})()
    candidate = type("Candidate", (), {"content": content})()
    response = type(
        "Response", (), {"candidates": [candidate], "text": "", "usage_metadata": None}
    )()

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return response

    client = type("Client", (), {"models": Models()})()
    genai = type("GenAI", (), {"Client": lambda **_kwargs: client})
    runtime = GeminiRuntime("test-key")
    monkeypatch.setattr(runtime, "_sdk", lambda: (genai, object()))

    message = runtime.chat("gemini-3.5-pro", [{"role": "user", "content": "lookup"}])
    runtime._request(
        "gemini-3.5-pro",
        [message, {"role": "tool", "tool_name": "lookup", "content": "ok"}],
        None,
        False,
        "high",
    )

    returned_part = captured["contents"][0]["parts"][0]
    assert returned_part["thought_signature"] == signature


def test_newest_model_sort_uses_release_date_then_version_numbers():
    models = [
        ModelInfo("openai_api", "gpt-4.1", "gpt-4.1", released_at=10),
        ModelInfo("openai_api", "gpt-5", "gpt-5", released_at=20),
        ModelInfo("gemini_api", "gemini-2.5-flash", "gemini-2.5-flash"),
        ModelInfo("gemini_api", "gemini-3.0-flash", "gemini-3.0-flash"),
    ]

    ordered = sorted(models, key=newest_model_first_key)

    assert [model.model_id for model in ordered] == [
        "gpt-5",
        "gpt-4.1",
        "gemini-3.0-flash",
        "gemini-2.5-flash",
    ]


def test_model_sort_prefers_named_capability_tiers_before_recency():
    models = [
        ModelInfo("openai_api", "luna", "luna", released_at=300),
        ModelInfo("openai_api", "terra", "terra", released_at=200),
        ModelInfo("openai_api", "sol", "sol", released_at=100),
    ]

    assert [model.model_id for model in sorted(models, key=newest_model_first_key)] == [
        "sol",
        "terra",
        "luna",
    ]


def test_model_sort_prioritizes_generation_over_capability_tier():
    models = [
        ModelInfo("openai_api", "gpt-4-pro", "gpt-4-pro", released_at=300),
        ModelInfo("openai_api", "gpt-5-mini", "gpt-5-mini", released_at=100),
    ]

    assert [model.model_id for model in sorted(models, key=newest_model_first_key)] == [
        "gpt-5-mini",
        "gpt-4-pro",
    ]


def test_model_sort_does_not_treat_release_dates_as_generation_numbers():
    models = [
        ModelInfo("openai_api", "gpt-5-pro-2025-10-06", "gpt-5-pro-2025-10-06"),
        ModelInfo("openai_api", "gpt-5.6-sol", "gpt-5.6-sol"),
        ModelInfo("openai_api", "gpt-5-nano-2025-08-07", "gpt-5-nano-2025-08-07"),
    ]

    assert [model.model_id for model in sorted(models, key=newest_model_first_key)] == [
        "gpt-5.6-sol",
        "gpt-5-pro-2025-10-06",
        "gpt-5-nano-2025-08-07",
    ]


def test_cloud_model_cache_round_trips_public_catalog_data_only(tmp_path):
    cache = tmp_path / "model-cache.json"
    save_model_cache(
        cache,
        [
            ModelInfo("openai_api", "gpt-5", "GPT-5", released_at=123),
            ModelInfo("openai_codex", "gpt-5.6-sol", "GPT-5.6 Sol"),
            ModelInfo("ollama", "qwen3", "qwen3"),
        ],
    )

    assert load_model_cache(cache) == [
        ModelInfo("openai_api", "gpt-5", "GPT-5", released_at=123),
        ModelInfo("openai_codex", "gpt-5.6-sol", "GPT-5.6 Sol"),
    ]


def test_cloud_model_cache_excludes_endpoint_specific_openai_models(tmp_path):
    cache = tmp_path / "model-cache.json"
    save_model_cache(
        cache,
        [
            ModelInfo("openai_api", "gpt-5", "gpt-5"),
            ModelInfo("openai_api", "gpt-5-search-api", "gpt-5-search-api"),
            ModelInfo("openai_api", "sora-2", "sora-2"),
            ModelInfo("openai_api", "whisper-1", "whisper-1"),
        ],
    )

    assert [item.model_id for item in load_model_cache(cache)] == ["gpt-5"]


def test_codex_model_discovery_uses_account_catalog_and_efforts():
    class Auth:
        def list_models(self):
            return [
                {
                    "model": "gpt-5.6-sol",
                    "displayName": "GPT-5.6 Sol",
                    "hidden": False,
                    "supportedReasoningEfforts": [
                        {"reasoningEffort": "low"},
                        {"reasoningEffort": "high"},
                    ],
                },
                {"model": "hidden", "hidden": True},
            ]

    models = discover_codex_models(Auth())

    assert [item.ref for item in models] == ["openai_codex/gpt-5.6-sol"]
    assert models[0].capabilities.effort_levels == ("low", "high")


def test_codex_runtime_retries_one_unauthorized_request_with_refresh(monkeypatch):
    calls = []
    request_options = []
    response = type("Response", (), {"output": [], "output_text": "ok", "usage": None})()
    delta = type("Event", (), {"type": "response.output_text.delta", "delta": "ok"})()
    completed = type("Event", (), {"type": "response.completed", "response": response})()

    class Unauthorized(Exception):
        status_code = 401

    class Responses:
        def __init__(self, refresh):
            self.refresh = refresh

        def create(self, **kwargs):
            calls.append(self.refresh)
            request_options.append(kwargs)
            if not self.refresh:
                raise Unauthorized()
            return iter([delta, completed])

    runtime = CodexRuntime(auth=object())
    monkeypatch.setattr(
        runtime,
        "_client",
        lambda *, refresh=False: type("Client", (), {"responses": Responses(refresh)})(),
    )

    assert runtime.chat("gpt-test", [{"role": "user", "content": "hello"}])["content"] == "ok"
    assert calls == [False, True]
    assert request_options[0]["stream"] is True
    assert request_options[1]["stream"] is True


def test_codex_transport_forces_streaming_for_every_internal_caller(monkeypatch):
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return iter(())

    runtime = CodexRuntime(auth=object())
    monkeypatch.setattr(
        runtime,
        "_client",
        lambda *, refresh=False: type("Client", (), {"responses": Responses()})(),
    )

    runtime._response_create(model="gpt-test", input=[], stream=False)

    assert captured["stream"] is True


def test_codex_runtime_surfaces_revoked_auth_after_one_refresh(monkeypatch):
    class Unauthorized(Exception):
        status_code = 401

    class Responses:
        def create(self, **_kwargs):
            raise Unauthorized()

    runtime = CodexRuntime(auth=object())
    monkeypatch.setattr(
        runtime,
        "_client",
        lambda *, refresh=False: type("Client", (), {"responses": Responses()})(),
    )

    with pytest.raises(RuntimeError, match="expired or was revoked"):
        runtime.chat("gpt-test", [{"role": "user", "content": "hello"}])


def test_codex_runtime_streaming_preserves_deltas(monkeypatch):
    reasoning = type(
        "Reasoning",
        (),
        {
            "id": "rs_123",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "opaque-state",
            "content": [],
        },
    )()
    response = type(
        "Response", (), {"output": [reasoning], "output_text": "hello", "usage": None}
    )()
    events = [
        type("Event", (), {"type": "response.output_text.delta", "delta": "hel"})(),
        type("Event", (), {"type": "response.output_text.delta", "delta": "lo"})(),
        type("Event", (), {"type": "response.output_item.done", "item": reasoning})(),
        type("Event", (), {"type": "response.completed", "response": response})(),
    ]
    runtime = CodexRuntime(auth=object())
    monkeypatch.setattr(runtime, "_response_create", lambda **_kwargs: iter(events))

    chunks = list(runtime.chat_stream("gpt-test", []))

    assert [item["content"] for item in chunks] == ["hel", "lo", ""]
    assert chunks[-1]["codex_reasoning_items"] == [
        {
            "id": "rs_123",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "opaque-state",
        }
    ]


def test_openai_stream_requires_terminal_completion_event(monkeypatch):
    runtime = OpenAIRuntime("secret")
    events = [type("Event", (), {"type": "response.output_text.delta", "delta": "partial"})()]
    monkeypatch.setattr(runtime, "_response_create", lambda **_kwargs: iter(events))

    stream = runtime.chat_stream("gpt-test", [])
    assert next(stream)["content"] == "partial"
    with pytest.raises(RuntimeError, match="without a completed response"):
        next(stream)


def test_openai_stream_rejects_completion_without_response(monkeypatch):
    runtime = OpenAIRuntime("secret")
    event = type("Event", (), {"type": "response.completed", "response": None})()
    monkeypatch.setattr(runtime, "_response_create", lambda **_kwargs: iter([event]))

    with pytest.raises(RuntimeError, match="without a terminal response"):
        list(runtime.chat_stream("gpt-test", []))


def test_codex_stream_rejects_completion_without_response(monkeypatch):
    runtime = CodexRuntime(auth=object())
    event = type("Event", (), {"type": "response.completed", "response": None})()
    monkeypatch.setattr(runtime, "_response_create", lambda **_kwargs: iter([event]))

    with pytest.raises(RuntimeError, match="without a terminal response"):
        list(runtime.chat_stream("gpt-test", []))


@pytest.mark.parametrize(
    ("call_id", "name", "arguments", "message"),
    [
        ("", "read_file", "{}", "malformed function call"),
        ("call-1", "", "{}", "malformed function call"),
        ("call-1", "read_file", "{", "malformed function arguments"),
        ("call-1", "read_file", "[]", "non-object function arguments"),
        ("call-1", "read_file", {}, "non-text function arguments"),
    ],
)
def test_codex_runtime_rejects_malformed_native_tool_items(
    call_id, name, arguments, message
):
    item = type(
        "Call",
        (),
        {
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        },
    )()

    with pytest.raises(RuntimeError, match=message):
        CodexRuntime._tool_call_item(item)


def test_codex_runtime_replays_only_opaque_reasoning_state():
    message = {
        "role": "assistant",
        "content": "done",
        "codex_reasoning_items": [
            {
                "id": "rs_123",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": "opaque-state",
            }
        ],
    }

    assert CodexRuntime._input([message]) == [
        {
            "id": "rs_123",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "opaque-state",
        },
        {"role": "assistant", "content": "done"},
    ]


def test_codex_runtime_drops_incomplete_reasoning_continuation_items():
    incomplete = type(
        "Reasoning",
        (),
        {"type": "reasoning", "encrypted_content": "opaque-state", "summary": []},
    )()

    assert CodexRuntime._reasoning_item(incomplete) is None


def test_openai_input_drops_orphaned_function_call_outputs():
    messages = [
        {"role": "system", "content": "system"},
        {
            "role": "tool",
            "tool_call_id": "orphan",
            "tool_name": "read_file",
            "content": "stale result",
        },
        {"role": "user", "content": "continue"},
    ]

    assert OpenAIRuntime._input(messages) == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "continue"},
    ]


def test_openai_input_keeps_complete_function_call_pairs():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "tool_name": "read_file",
            "content": "contents",
        },
    ]

    assert [item["type"] for item in OpenAIRuntime._input(messages)] == [
        "function_call",
        "function_call_output",
    ]


def test_codex_runtime_preserves_structured_tool_calls(monkeypatch):
    call = type(
        "Call",
        (),
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "read_file",
            "arguments": "{}",
            "content": [],
        },
    )()
    response = type("Response", (), {"output": [call], "output_text": "", "usage": None})()
    runtime = CodexRuntime(auth=object())
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return iter(
            [
                type("Event", (), {"type": "response.output_item.done", "item": call})(),
                type("Event", (), {"type": "response.completed", "response": response})(),
            ]
        )

    monkeypatch.setattr(runtime, "_response_create", create)

    message = runtime.chat("gpt-test", [], tools=[])

    assert message["tool_calls"] == [
        {"id": "call-1", "function": {"name": "read_file", "arguments": "{}"}}
    ]
    assert captured["stream"] is True


def test_codex_runtime_recovers_terminal_items_when_done_events_are_missing(monkeypatch):
    call = type(
        "Call",
        (),
        {
            "type": "function_call",
            "call_id": "call-terminal",
            "name": "read_file",
            "arguments": '{"path":"README.md"}',
            "content": [],
        },
    )()
    reasoning = type(
        "Reasoning",
        (),
        {
            "id": "rs_terminal",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "opaque-terminal-state",
        },
    )()
    response = type(
        "Response",
        (),
        {
            "id": "resp_terminal",
            "status": "completed",
            "output": [reasoning, call],
            "output_text": "terminal fallback",
            "usage": None,
        },
    )()
    runtime = CodexRuntime(auth=object())
    monkeypatch.setattr(
        runtime,
        "_response_create",
        lambda **_kwargs: iter(
            [type("Event", (), {"type": "response.completed", "response": response})()]
        ),
    )

    message = runtime.chat("gpt-test", [], tools=[])

    assert message["content"] == "terminal fallback"
    assert message["tool_calls"] == [
        {
            "id": "call-terminal",
            "function": {
                "name": "read_file",
                "arguments": '{"path":"README.md"}',
            },
        }
    ]
    assert message["codex_reasoning_items"] == [
        {
            "id": "rs_terminal",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "opaque-terminal-state",
        }
    ]
    assert runtime.last_chat_metadata["response_id"] == "resp_terminal"


def test_codex_runtime_deduplicates_streamed_and_terminal_items(monkeypatch):
    call = type(
        "Call",
        (),
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "read_file",
            "arguments": "{}",
            "content": [],
        },
    )()
    response = type(
        "Response",
        (),
        {"output": [call], "output_text": "", "usage": None},
    )()
    events = [
        type("Event", (), {"type": "response.output_item.done", "item": call})(),
        type("Event", (), {"type": "response.completed", "response": response})(),
    ]
    runtime = CodexRuntime(auth=object())
    monkeypatch.setattr(runtime, "_response_create", lambda **_kwargs: iter(events))

    message = runtime.chat("gpt-test", [], tools=[])

    assert len(message["tool_calls"]) == 1


def test_local_model_sort_prefers_larger_parameter_tags():
    models = [
        ModelInfo("ollama", "qwen3.5:9b", "qwen3.5:9b"),
        ModelInfo("ollama", "gpt-oss:20b", "gpt-oss:20b"),
        ModelInfo("ollama", "qwen3-coder:30b", "qwen3-coder:30b"),
        ModelInfo("ollama", "untagged:latest", "untagged:latest"),
    ]

    assert [model.model_id for model in sorted(models, key=local_model_weight_first_key)] == [
        "qwen3-coder:30b",
        "gpt-oss:20b",
        "qwen3.5:9b",
        "untagged:latest",
    ]


def test_local_models_group_by_family_then_rank_families_by_strongest_variant():
    models = [
        ModelInfo("ollama", "qwen3.5:9b", "qwen3.5:9b"),
        ModelInfo("ollama", "gpt-oss:20b", "gpt-oss:20b"),
        ModelInfo("ollama", "qwen3-coder:30b", "qwen3-coder:30b"),
        ModelInfo("ollama", "llama3.2:8b", "llama3.2:8b"),
        ModelInfo("ollama", "llama3.1:3b", "llama3.1:3b"),
    ]

    grouped = grouped_local_models(models)

    assert [(family, [item.model_id for item in members]) for family, members in grouped] == [
        ("Qwen", ["qwen3-coder:30b", "qwen3.5:9b"]),
        ("OpenAI", ["gpt-oss:20b"]),
        ("Meta Llama", ["llama3.2:8b", "llama3.1:3b"]),
    ]
