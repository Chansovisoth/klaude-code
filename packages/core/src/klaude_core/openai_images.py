"""Bounded Responses HTTP delivery; reuse the existing native response parser."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx

from .compatible_runtime import CompatibleModelError, CompatibleRuntime
from .http_model_transport import CancellableHTTPTransport


class _ResponseObject:
    """Expose bounded JSON to the shared SDK-shaped parser without an SDK import."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, key: str) -> Any:
        if key not in self._data:
            raise AttributeError(key)
        return _response_object(self._data[key])

    def model_dump(self, **_kwargs: Any) -> dict:
        return deepcopy(self._data)


def _response_object(value: Any) -> Any:
    if isinstance(value, dict):
        return _ResponseObject(value)
    if isinstance(value, list):
        return [_response_object(item) for item in value]
    return value


class OpenAIImageTransport(CancellableHTTPTransport):
    def __init__(self, endpoint: str, key: str, timeout: float | httpx.Timeout = 600):
        timeout = (
            httpx.Timeout(timeout, connect=3) if isinstance(timeout, (int, float)) else timeout
        )
        super().__init__(
            endpoint, timeout, headers={"Authorization": "Bearer " + key}, trust_env=False
        )

    @staticmethod
    def _terminal(response: Any) -> None:
        if not isinstance(response, dict) or response.get("status") != "completed":
            status = response.get("status") if isinstance(response, dict) else None
            raise CompatibleModelError(
                "OpenAI output limit reached or response incomplete"
                if status == "incomplete"
                else "OpenAI response did not complete successfully"
            )

    @staticmethod
    def _failure(event: dict) -> CompatibleModelError:
        response = event.get("response")
        response = response if isinstance(response, dict) else {}
        error = event.get("error") or response.get("error") or event
        code = error.get("code") if isinstance(error, dict) else None
        code = code if isinstance(code, str) else None
        details = response.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        reason = reason if isinstance(reason, str) else None
        labels = {
            "insufficient_quota": "OpenAI quota exhausted; check account billing and limits",
            "credit_balance_exhausted": "OpenAI credits exhausted; check billing and limits",
            "rate_limit_exceeded": "OpenAI rate limited; try again later",
            "invalid_api_key": "OpenAI authentication failed; check the configured key",
            "model_not_found": "OpenAI model unavailable for this account",
            "context_length_exceeded": "OpenAI context limit reached; shorten the request",
            "max_output_tokens": "OpenAI output limit reached; raise the budget or shorten input",
        }
        label = labels.get(code or "") or labels.get(reason or "")
        if not label:
            param = error.get("param") if isinstance(error, dict) else None
            param = param if isinstance(param, str) else None
            label = (
                "OpenAI rejected request setting: " + param
                if param
                in {
                    "reasoning",
                    "context_management",
                    "prompt_cache_key",
                    "include",
                    "max_output_tokens",
                    "input",
                    "model",
                    "tools",
                    "store",
                }
                else "OpenAI response failed or incomplete"
            )
        return CompatibleModelError(label)

    def create(self, payload: dict) -> Any:
        return self._stream(payload) if payload.get("stream") else self._single(payload)

    def _check_status(self, response: httpx.Response) -> None:
        if response.status_code != 200:
            # A quota failure is not a temporary rate limit. Inspect only a
            # bounded error envelope; provider messages never enter diagnostics.
            if response.status_code == 429:
                body = bytearray()
                try:
                    for chunk in response.iter_bytes(chunk_size=4096):
                        body.extend(chunk)
                        if len(body) > 64_000:
                            break
                    if len(body) <= 64_000:
                        envelope = json.loads(body)
                        error = envelope.get("error") if isinstance(envelope, dict) else None
                        if isinstance(error, dict) and (
                            error.get("code") in ("insufficient_quota", "credit_balance_exhausted")
                            or error.get("type") == "insufficient_quota"
                        ):
                            raise self._failure({"error": {"code": "credit_balance_exhausted"}})
                except (ValueError, httpx.HTTPError):
                    pass
            raise CompatibleModelError(
                f"OpenAI request rejected (HTTP {response.status_code})",
                status_code=response.status_code,
            )

    def _single(self, payload: dict) -> Any:
        client = self._chat_client_factory()
        self._track_request(client)
        try:
            with client.stream(
                "POST",
                "/responses",
                json=payload,
                extensions={"trace": self._request_trace(client)},
            ) as response:
                self._attach_response(client, response)
                self._check_status(response)
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.stream_response_limit:
                        raise CompatibleModelError("OpenAI response exceeds its size limit")
                result = json.loads(body)
                self._terminal(result)
                return _response_object(result)
        finally:
            self._finish_request(client)
            client.close()

    def _stream(self, payload: dict):
        client = self._chat_client_factory()
        self._track_request(client)
        terminal = None
        try:
            with client.stream(
                "POST",
                "/responses",
                json=payload,
                extensions={"trace": self._request_trace(client)},
            ) as response:
                self._attach_response(client, response)
                self._check_status(response)
                for event in CompatibleRuntime._events(
                    response,
                    response_limit=self.stream_response_limit,
                    event_limit=self.stream_event_limit,
                ):
                    if terminal is not None:
                        raise CompatibleModelError("OpenAI event after response completion")
                    kind = event.get("type")
                    if kind == "response.completed":
                        self._terminal(event.get("response"))
                        terminal = event
                    elif kind in {"error", "response.failed", "response.incomplete"}:
                        raise self._failure(event)
                    else:
                        yield _response_object(event)
            if terminal is None:
                raise CompatibleModelError("OpenAI stream ended without a completed response")
            # Buffered calls/private state cannot escape before clean termination.
            yield _response_object(terminal)
        finally:
            self._finish_request(client)
            client.close()
