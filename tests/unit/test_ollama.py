from __future__ import annotations

import json

import httpx
from klaude_core.ollama import Ollama


def test_chat_assembles_streamed_transport_for_tool_compatible_response():
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=(
                '{"message":{"role":"assistant","content":"hello "},"done":false}\n'
                '{"message":{"role":"assistant","content":"world",'
                '"tool_calls":[{"function":{"name":"read_file","arguments":{}}}]},'
                '"done":true,"done_reason":"stop","prompt_eval_count":12,'
                '"eval_count":2}\n'
            ),
        )

    ollama = Ollama("http://ollama.test")
    ollama._chat_client_factory = lambda: httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    message = ollama.chat(
        "small-model",
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert observed["stream"] is True
    assert message["content"] == "hello world"
    assert message["tool_calls"][0]["function"]["name"] == "read_file"
    assert ollama.last_chat_metadata["prompt_eval_count"] == 12
    assert ollama.last_chat_metadata["eval_count"] == 2


def test_cancel_active_closes_request_client():
    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    ollama = Ollama("http://ollama.test")
    active = FakeClient()
    ollama._track_request(active)

    assert ollama.cancel_active() is True
    assert active.closed is True


def test_chat_stream_yields_message_fragments_and_records_completion_metadata():
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=(
                '{"message":{"role":"assistant","content":"hello ",'
                '"thinking":"plan"},"done":false}\n'
                '{"message":{"role":"assistant","content":"world"},'
                '"done":true,"done_reason":"stop","eval_count":2}\n'
            ),
        )

    ollama = Ollama("http://ollama.test")
    ollama._client.close()
    ollama._client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    ollama._chat_client_factory = lambda: httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    fragments = list(
        ollama.chat_stream(
            "small-model",
            [{"role": "user", "content": "hi"}],
            options={"num_ctx": 4096},
            think=False,
        )
    )

    assert "".join(fragment["content"] for fragment in fragments) == "hello world"
    assert observed == {
        "model": "small-model",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "options": {"num_ctx": 4096},
        "think": False,
    }
    assert ollama.last_chat_metadata == {
        "done": True,
        "done_reason": "stop",
        "eval_count": 2,
        "thinking_characters": 4,
    }
    ollama._client.close()
