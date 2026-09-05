"""Thin client for Ollama's REST API.

We deliberately talk HTTP instead of using an SDK: /api/chat, /api/embed and
/api/tags are stable, documented endpoints, so nothing here breaks when a
client library redesigns itself.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import httpx


class OllamaError(RuntimeError):
    pass


class Ollama:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._chat_client_factory = lambda: httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        self.last_chat_metadata: dict[str, Any] = {}
        self._active_client: httpx.Client | None = None
        self._active_response: httpx.Response | None = None
        self._active_response_lock = threading.Lock()

    def _track_request(
        self,
        client: httpx.Client | None,
        response: httpx.Response | None = None,
    ) -> None:
        with self._active_response_lock:
            self._active_client = client
            self._active_response = response

    def cancel_active(self) -> bool:
        """Close the active response stream so a steering turn can proceed."""
        with self._active_response_lock:
            client = self._active_client
            response = self._active_response
        if client is None and response is None:
            return False
        if response is not None:
            response.close()
        if client is not None:
            client.close()
        return True

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        """One non-streaming chat turn. Returns the `message` object,
        which may contain `content` and/or `tool_calls`."""
        # Consume Ollama's streaming transport internally even though this
        # method returns one assembled message. That makes an in-flight local
        # generation cancellable when the user steers the persistent TUI.
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        assembled: dict[str, Any] = {"role": "assistant", "content": ""}
        request_client = self._chat_client_factory()
        self._track_request(request_client)
        try:
            with request_client.stream("POST", "/api/chat", json=payload) as response:
                self._track_request(request_client, response)
                if response.status_code != 200:
                    response.read()
                    raise OllamaError(
                        f"ollama /api/chat {response.status_code}: {response.text[:300]}"
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    message = event.get("message")
                    if isinstance(message, dict):
                        if message.get("role"):
                            assembled["role"] = message["role"]
                        for field in ("content", "thinking"):
                            if message.get(field):
                                assembled[field] = assembled.get(field, "") + str(
                                    message[field]
                                )
                        if isinstance(message.get("tool_calls"), list):
                            assembled.setdefault("tool_calls", []).extend(
                                message["tool_calls"]
                            )
                    if event.get("done"):
                        self.last_chat_metadata = {
                            key: event[key]
                            for key in (
                                "done",
                                "done_reason",
                                "total_duration",
                                "load_duration",
                                "prompt_eval_count",
                                "eval_count",
                            )
                            if key in event
                        }
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise OllamaError(f"ollama chat request interrupted or invalid: {exc}") from exc
        finally:
            self._track_request(None)
            request_client.close()
        return assembled

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        r = self._client.post("/api/embed", json={"model": model, "input": texts})
        if r.status_code != 200:
            raise OllamaError(f"ollama /api/embed {r.status_code}: {r.text[:300]}")
        return r.json()["embeddings"]

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream one tool-free chat turn as Ollama message fragments."""
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        thinking_characters = 0
        request_client = self._chat_client_factory()
        self._track_request(request_client)
        try:
            with request_client.stream("POST", "/api/chat", json=payload) as response:
                self._track_request(request_client, response)
                if response.status_code != 200:
                    response.read()
                    raise OllamaError(
                        f"ollama /api/chat {response.status_code}: {response.text[:300]}"
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    message = event.get("message")
                    if isinstance(message, dict):
                        thinking_characters += len(str(message.get("thinking", "")))
                    if event.get("done"):
                        self.last_chat_metadata = {
                            key: event[key]
                            for key in (
                                "done",
                                "done_reason",
                                "total_duration",
                                "load_duration",
                                "prompt_eval_count",
                                "eval_count",
                            )
                            if key in event
                        }
                        if thinking_characters:
                            self.last_chat_metadata["thinking_characters"] = thinking_characters
                    if isinstance(message, dict):
                        yield message
        finally:
            self._track_request(None)
            request_client.close()

    def list_models(self) -> list[str]:
        r = self._client.get("/api/tags")
        if r.status_code != 200:
            raise OllamaError(f"ollama /api/tags {r.status_code}")
        return [m["name"] for m in r.json().get("models", [])]

    def is_up(self) -> bool:
        try:
            return self._client.get("/api/tags").status_code == 200
        except httpx.HTTPError:
            return False
