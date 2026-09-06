from klaude_core.model_runtime import (
    ModelInfo,
    OpenAIRuntime,
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
    payload = OpenAIRuntime._input([
        {"role": "system", "content": "be useful"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "call_1", "function": {"name": "workspace_info", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_name": "workspace_info", "tool_call_id": "call_1", "content": "ok"},
    ])

    assert payload[1]["type"] == "function_call"
    assert payload[1]["call_id"] == "call_1"
    assert payload[2] == {"type": "function_call_output", "call_id": "call_1", "output": "ok"}


def test_newest_model_sort_uses_release_date_then_version_numbers():
    models = [
        ModelInfo("openai_api", "gpt-4.1", "gpt-4.1", released_at=10),
        ModelInfo("openai_api", "gpt-5", "gpt-5", released_at=20),
        ModelInfo("gemini_api", "gemini-2.5-flash", "gemini-2.5-flash"),
        ModelInfo("gemini_api", "gemini-3.0-flash", "gemini-3.0-flash"),
    ]

    ordered = sorted(models, key=newest_model_first_key)

    assert [model.model_id for model in ordered] == [
        "gpt-5", "gpt-4.1", "gemini-3.0-flash", "gemini-2.5-flash",
    ]


def test_model_sort_prefers_named_capability_tiers_before_recency():
    models = [
        ModelInfo("openai_api", "luna", "luna", released_at=300),
        ModelInfo("openai_api", "terra", "terra", released_at=200),
        ModelInfo("openai_api", "sol", "sol", released_at=100),
    ]

    assert [model.model_id for model in sorted(models, key=newest_model_first_key)] == [
        "sol", "terra", "luna",
    ]


def test_model_sort_prioritizes_generation_over_capability_tier():
    models = [
        ModelInfo("openai_api", "gpt-4-pro", "gpt-4-pro", released_at=300),
        ModelInfo("openai_api", "gpt-5-mini", "gpt-5-mini", released_at=100),
    ]

    assert [model.model_id for model in sorted(models, key=newest_model_first_key)] == [
        "gpt-5-mini", "gpt-4-pro",
    ]


def test_model_sort_does_not_treat_release_dates_as_generation_numbers():
    models = [
        ModelInfo("openai_api", "gpt-5-pro-2025-10-06", "gpt-5-pro-2025-10-06"),
        ModelInfo("openai_api", "gpt-5.6-sol", "gpt-5.6-sol"),
        ModelInfo("openai_api", "gpt-5-nano-2025-08-07", "gpt-5-nano-2025-08-07"),
    ]

    assert [model.model_id for model in sorted(models, key=newest_model_first_key)] == [
        "gpt-5.6-sol", "gpt-5-pro-2025-10-06", "gpt-5-nano-2025-08-07",
    ]


def test_cloud_model_cache_round_trips_public_catalog_data_only(tmp_path):
    cache = tmp_path / "model-cache.json"
    save_model_cache(cache, [
        ModelInfo("openai_api", "gpt-5", "GPT-5", released_at=123),
        ModelInfo("ollama", "qwen3", "qwen3"),
    ])

    assert load_model_cache(cache) == [
        ModelInfo("openai_api", "gpt-5", "GPT-5", released_at=123),
    ]


def test_local_model_sort_prefers_larger_parameter_tags():
    models = [
        ModelInfo("ollama", "qwen3.5:9b", "qwen3.5:9b"),
        ModelInfo("ollama", "gpt-oss:20b", "gpt-oss:20b"),
        ModelInfo("ollama", "qwen3-coder:30b", "qwen3-coder:30b"),
        ModelInfo("ollama", "untagged:latest", "untagged:latest"),
    ]

    assert [model.model_id for model in sorted(models, key=local_model_weight_first_key)] == [
        "qwen3-coder:30b", "gpt-oss:20b", "qwen3.5:9b", "untagged:latest",
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
