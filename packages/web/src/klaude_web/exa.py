"""Optional Exa web provider.

Exa is not the default because klaude-code should work free/local forever.
When configured with EXA_API_KEY, it can provide cleaner search highlights and
remote page extraction.
"""

from __future__ import annotations

import hashlib
import logging

import httpx

logger = logging.getLogger(__name__)


class ExaConfigError(RuntimeError):
    pass


def _headers(api_key: str) -> dict[str, str]:
    api_key = api_key.strip()
    if not api_key:
        raise ExaConfigError("EXA_API_KEY is required for the Exa web provider")
    fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:10]
    logger.debug(
        "Exa auth configured=%s length=%d fingerprint=%s header=x-api-key",
        bool(api_key),
        len(api_key),
        fingerprint,
    )
    return {"x-api-key": api_key, "Content-Type": "application/json"}


def exa_search(
    base_url: str,
    api_key: str,
    query: str,
    max_results: int = 8,
    *,
    code_context: bool = False,
) -> list[dict]:
    if code_context:
        query = f"{query} code examples official documentation GitHub Stack Overflow"
    r = httpx.post(
        f"{base_url.rstrip('/')}/search",
        headers=_headers(api_key),
        json={
            "query": query,
            "type": "auto",
            "numResults": max_results,
            "contents": {"highlights": True},
        },
        timeout=30,
    )
    r.raise_for_status()
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": "\n".join(item.get("highlights") or []) or item.get("text", ""),
        }
        for item in r.json().get("results", [])
    ][:max_results]


def exa_fetch(base_url: str, api_key: str, url: str, max_characters: int = 15_000) -> str:
    r = httpx.post(
        f"{base_url.rstrip('/')}/contents",
        headers=_headers(api_key),
        json={"urls": [url], "text": True},
        timeout=60,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        raise RuntimeError(f"Exa returned no content for {url}")
    text = results[0].get("text") or ""
    if not text.strip():
        raise RuntimeError(f"Exa returned empty content for {url}")
    return text.strip()[:max_characters]
