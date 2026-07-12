"""Fetch cascade: direct text -> Crawl4AI (if configured) -> raw HTTP + trafilatura.

Plain-text and Markdown docs should not go through HTML extraction. Crawl4AI
handles JS-heavy pages via the optional Docker service; Trafilatura is the
pure-Python HTML fallback.
"""

from __future__ import annotations

import httpx

UA = "Mozilla/5.0 (X11; Linux x86_64) klaude-code/0.1 (+local research agent)"
TEXT_CONTENT_TYPES = {
    "application/json",
    "application/markdown",
    "application/xml",
    "text/markdown",
    "text/plain",
    "text/xml",
}


def _content_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _direct_text_fetch(url: str) -> str | None:
    r = httpx.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept": (
                "text/plain,text/markdown,text/html,application/xhtml+xml,"
                "application/json,application/xml,text/xml;q=0.9,*/*;q=0.8"
            ),
        },
        timeout=30,
        follow_redirects=True,
    )
    r.raise_for_status()
    if _content_type(r.headers) not in TEXT_CONTENT_TYPES:
        return None
    text = r.text.strip()
    if not text:
        raise RuntimeError(f"empty text response from {url}")
    return text


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

    r = httpx.get(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        timeout=30,
        follow_redirects=True,
    )
    r.raise_for_status()
    text = trafilatura.extract(
        r.text,
        output_format="markdown",
        include_formatting=True,
        include_links=True,
        include_tables=True,
    )
    if not text or not text.strip():
        raise RuntimeError("trafilatura extracted no content")
    return text.strip()


def fetch_page(url: str, crawl4ai_url: str = "") -> str:
    errors: list[str] = []
    try:
        direct_text = _direct_text_fetch(url)
        if direct_text is not None:
            return direct_text
    except Exception as e:
        errors.append(f"direct text: {e}")
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
