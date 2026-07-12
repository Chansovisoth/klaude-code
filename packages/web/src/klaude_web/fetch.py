"""Fetch cascade: Crawl4AI (if configured) -> raw HTTP + trafilatura.

Tier 1 handles JS-heavy pages via the optional Docker service; tier 2 is
pure Python and always available. Each tier is a fallback for the one above.
"""

from __future__ import annotations

import httpx

UA = "Mozilla/5.0 (X11; Linux x86_64) klaude-code/0.1 (+local research agent)"


def _crawl4ai(base_url: str, url: str) -> str:
    r = httpx.post(
        f"{base_url.rstrip('/')}/md",
        json={"url": url, "f": "fit"},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    md = data.get("markdown") or data.get("result", {}).get("markdown") or ""
    if not md.strip():
        raise RuntimeError("crawl4ai returned empty markdown")
    return md


def _trafilatura(url: str) -> str:
    import trafilatura

    r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    text = trafilatura.extract(
        r.text, output_format="markdown", include_links=False, include_tables=True
    )
    if not text or not text.strip():
        raise RuntimeError("trafilatura extracted no content")
    return text


def fetch_page(url: str, crawl4ai_url: str = "") -> str:
    errors = []
    if crawl4ai_url:
        try:
            return _crawl4ai(crawl4ai_url, url)
        except Exception as e:
            errors.append(f"crawl4ai: {e}")
    try:
        return _trafilatura(url)
    except Exception as e:
        errors.append(f"trafilatura: {e}")
    raise RuntimeError(f"all fetch tiers failed for {url}: " + " | ".join(errors))
