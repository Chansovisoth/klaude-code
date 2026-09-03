"""Thin client for Ollama's REST API.

We deliberately talk HTTP instead of using an SDK: /api/chat, /api/embed and
/api/tags are stable, documented endpoints, so nothing here breaks when a
client library redesigns itself.
"""

from __future__ import annotations

from typing import Any

import httpx


class OllamaError(RuntimeError):
    pass


class Ollama:
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.last_chat_metadata: dict[str, Any] = {}

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
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        r = self._client.post("/api/chat", json=payload)
        if r.status_code != 200:
            raise OllamaError(f"ollama /api/chat {r.status_code}: {r.text[:300]}")
        response = r.json()
        self.last_chat_metadata = {
            key: response[key]
            for key in (
                "done",
                "done_reason",
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "eval_count",
            )
            if key in response
        }
        return response["message"]

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        r = self._client.post("/api/embed", json={"model": model, "input": texts})
        if r.status_code != 200:
            raise OllamaError(f"ollama /api/embed {r.status_code}: {r.text[:300]}")
        return r.json()["embeddings"]

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
