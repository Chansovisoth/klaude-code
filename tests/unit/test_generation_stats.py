"""Reported token throughput, unknown usage and persisted browser projection."""

import asyncio

import pytest
from klaude_core.generation_stats import GenerationStats, public_generation_stats

from .test_application_bridge import ScriptedRuntime, _application, _collect


def test_average_uses_total_output_over_total_generation_time():
    stats = GenerationStats()
    stats.observe(100, 2_000_000_000, 20)
    stats.observe(20, 1_000_000_000, 10)
    assert stats.public() == {
        "output_tokens": 120, "generation_seconds": 3, "requests": 2,
        "timing": "provider", "average_tokens_per_second": 40,
    }


def test_request_time_fallback_and_unknown_usage():
    stats = GenerationStats()
    stats.observe(40, None, 2)
    stats.observe(60, 0, 3)
    assert stats.public()["average_tokens_per_second"] == 20
    assert stats.public()["timing"] == "request"
    stats.observe(None, None, 2)
    assert stats.public() is None
    assert GenerationStats().public() is None


@pytest.mark.parametrize("field,value", [
    ("output_tokens", True), ("output_tokens", -1), ("generation_seconds", 0),
    ("generation_seconds", float("nan")), ("generation_seconds", float("inf")),
    ("timing", []), ("requests", 0),
])
def test_invalid_statistics_do_not_reach_public_projection(field, value):
    data = {"output_tokens": 40, "generation_seconds": 2, "requests": 1, "timing": "provider"}
    data[field] = value
    assert public_generation_stats(data) is None


def test_agent_statistics_survive_saved_reply_reload(tmp_path):
    class Runtime(ScriptedRuntime):
        def __init__(self):
            super().__init__([{"role": "assistant", "content": "A quiet winter garden."}])
            self.last_chat_metadata = {}

        def chat(self, *args, **kwargs):
            result = super().chat(*args, **kwargs)
            self.last_chat_metadata = {"prompt_eval_count": 10, "eval_count": 100,
                                       "eval_duration": 2_000_000_000,
                                       "private_provider_payload": "must stay private"}
            return result

    runtime = Runtime()
    app = _application(tmp_path, runtime)
    try:
        handle = app.submit("Describe a winter garden", request_id="stats-fixture")
        asyncio.run(_collect(handle))
        assert handle.state == "completed"
        saved = app.snapshot()["messages"][-1]["generation_stats"]
        assert saved["average_tokens_per_second"] == 50
        assert saved["requests"] == 1
        assert "private_provider_payload" not in saved
        session = app.session_id
    finally:
        asyncio.run(app.close())
    resumed = _application(tmp_path, ScriptedRuntime(), session_id=session)
    try:
        assert resumed.snapshot()["messages"][-1]["generation_stats"] == saved
        assert resumed.agent.ollama.calls == 0
    finally:
        asyncio.run(resumed.close())
