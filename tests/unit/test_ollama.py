from __future__ import annotations

import json

import httpx
import pytest
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


def test_cancel_active_is_best_effort_and_idempotent_when_closers_fail():
    class RaisingClient:
        close_calls = 0

        def close(self):
            self.close_calls += 1
            raise OSError("client already closed")

    class RaisingResponse:
        extensions = {}
        close_calls = 0

        def close(self):
            self.close_calls += 1
            raise OSError("response already closed")

    ollama = Ollama("http://ollama.test")
    client = RaisingClient()
    response = RaisingResponse()
    ollama._track_request(client, response)

    assert ollama.cancel_active() is True
    assert ollama.cancel_active() is False
    assert response.close_calls == 1
    assert client.close_calls == 1


def test_cancel_active_wakes_a_blocked_socket_reader():
    import socket
    import threading
    from types import SimpleNamespace

    probe_reader, probe_writer = socket.socketpair()
    try:
        try:
            probe_reader.shutdown(socket.SHUT_RDWR)
        except PermissionError:
            pytest.skip("test sandbox blocks socket shutdown")
    finally:
        probe_reader.close()
        probe_writer.close()

    reader, writer = socket.socketpair()
    finished = threading.Event()

    def receive():
        try:
            reader.recv(1)
        finally:
            finished.set()

    worker = threading.Thread(target=receive, daemon=True)
    worker.start()
    ollama = Ollama("http://ollama.test")
    response = SimpleNamespace(
        extensions={"network_stream": SimpleNamespace(get_extra_info=lambda _key: reader)},
        close=lambda: None,
    )
    ollama._track_request(SimpleNamespace(close=lambda: None), response)
    try:
        ollama.cancel_active()
        assert finished.wait(1), "Cancellation must wake recv without waiting for server data"
    finally:
        writer.close()
        worker.join(timeout=1)
        reader.close()
        ollama._client.close()


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
