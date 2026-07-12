"""SearXNG client. Requires 'json' in the instance's search.formats."""

from __future__ import annotations

import httpx


def searx_search(base_url: str, query: str, max_results: int = 8) -> list[dict]:
    r = httpx.get(
        f"{base_url.rstrip('/')}/search",
        params={"q": query, "format": "json"},
        timeout=20,
    )
    if r.status_code == 403:
        raise RuntimeError(
            "SearXNG returned 403 — JSON format is not enabled. "
            "Add 'json' under search.formats in deploy/searxng/settings.yml."
        )
    r.raise_for_status()
    results = r.json().get("results", [])[:max_results]
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        }
        for item in results
    ]
