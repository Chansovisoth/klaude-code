"""Bounded authenticated extraction requests to explicitly configured services."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .fetch import FetchPageError


def post_json(
    url: str, *, headers: dict[str, str], payload: dict[str, Any], timeout: float, max_bytes: int
) -> dict[str, Any]:
    try:
        with httpx.Client(
            timeout=max(0.1, timeout), trust_env=False, follow_redirects=False
        ) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                status = response.status_code
                if status in {401, 403, 429}:
                    raise FetchPageError(
                        "Extraction service rejected request",
                        failure_class="rate_limit" if status == 429 else "authentication",
                    )
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > max_bytes:
                        raise FetchPageError(
                            "Extraction response exceeded byte limit",
                            failure_class="response_too_large",
                        )
                    body.extend(chunk)
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError("Expected an object")
                return data
    except FetchPageError:
        raise
    except httpx.TimeoutException as exc:
        raise FetchPageError(
            "Extraction service timed out", failure_class="timeout", transient=True
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        # Upstream response/URLs may contain private data; keep feedback generic.
        raise FetchPageError(
            "Extraction service unavailable or malformed",
            failure_class="provider_failure",
            transient=True,
        ) from exc
