"""Polite multi-page crawling for documentation ingestion."""

from __future__ import annotations

import fnmatch
import random
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

SKIP_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bmp",
    ".css",
    ".dmg",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".svg",
    ".tar",
    ".webm",
    ".webp",
    ".zip",
}


@dataclass
class CrawlPage:
    url: str
    markdown: str
    depth: int


@dataclass
class CrawlError:
    url: str
    depth: int
    error: str


@dataclass
class CrawlResult:
    start_url: str
    pages: list[CrawlPage]
    errors: list[CrawlError]
    skipped: list[str]
    seeded: list[str]


@dataclass
class HttpPage:
    url: str
    text: str
    content_type: str
    status_code: int
    retry_count: int = 0


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(value)


def _normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))


def _same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _skip_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in SKIP_EXTENSIONS)


def _matches_any(url: str, patterns: list[str]) -> bool:
    path = urlparse(url).path
    return any(
        fnmatch.fnmatch(url, pattern) or fnmatch.fnmatch(path, pattern)
        for pattern in patterns
    )


def _allowed_by_patterns(
    url: str,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> bool:
    if include_patterns and not _matches_any(url, include_patterns):
        return False
    if exclude_patterns and _matches_any(url, exclude_patterns):
        return False
    return True


def extract_html_links(html: str, base_url: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(html)
    links = []
    seen = set()
    for raw in parser.links:
        url = _normalize_url(urljoin(base_url, raw))
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            links.append(url)
    return links


def parse_retry_after(value: str, now: datetime | None = None) -> float | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return max(0.0, float(value))
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        now = now or datetime.now(UTC)
        return max(0.0, (when - now).total_seconds())
    except (TypeError, ValueError):
        return None


def _retry_delay(response: httpx.Response | None, attempt: int, max_delay: float) -> float:
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        parsed = parse_retry_after(retry_after)
        if parsed is not None:
            return min(parsed, max_delay)
    return min((0.5 * (2 ** attempt)) + random.uniform(0, 0.25), max_delay)


def _get_with_retries(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float = 30,
    max_attempts: int = 3,
    max_delay: float = 60,
    sleeper: Callable[[float], None] = time.sleep,
) -> HttpPage:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        response = None
        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )
            if response.status_code not in {429, 503}:
                response.raise_for_status()
                return HttpPage(
                    url=str(response.url),
                    text=response.text,
                    content_type=response.headers.get("content-type", "").split(";", 1)[0].lower(),
                    status_code=response.status_code,
                    retry_count=attempt,
                )
            if attempt == max_attempts - 1:
                raise RuntimeError(
                    f"status {response.status_code} after {attempt} retries for {url}"
                )
            sleeper(_retry_delay(response, attempt, max_delay))
            continue
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500 and exc.response.status_code != 429:
                raise
            last_error = exc
            if attempt == max_attempts - 1:
                raise RuntimeError(f"{exc} after {attempt} retries for {url}") from exc
            sleeper(_retry_delay(response or exc.response, attempt, max_delay))
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                raise
            sleeper(_retry_delay(None, attempt, max_delay))
    if last_error:
        raise last_error
    raise RuntimeError(f"failed to fetch {url}")


def _markdown_from_http_page(page: HttpPage) -> str:
    if page.content_type in {
        "text/plain",
        "text/markdown",
        "application/json",
        "application/xml",
        "text/xml",
    }:
        return page.text.strip()
    if page.content_type not in {"text/html", "application/xhtml+xml"}:
        return ""
    import trafilatura

    extracted = trafilatura.extract(
        page.text,
        output_format="markdown",
        include_formatting=True,
        include_links=True,
        include_tables=True,
    )
    if extracted and extracted.strip():
        return extracted.strip()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page.text)).strip()


class Robots:
    def __init__(self, user_agent: str, timeout: float = 10.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: dict[str, RobotFileParser | None | bool] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            rp = RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            rp.set_url(robots_url)
            try:
                r = httpx.get(
                    robots_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
                if r.status_code in {401, 403}:
                    self._cache[origin] = False
                    return False
                if r.status_code >= 400:
                    self._cache[origin] = None
                else:
                    rp.parse(r.text.splitlines())
                    self._cache[origin] = rp
            except httpx.HTTPError:
                self._cache[origin] = False
                return False
        cached = self._cache[origin]
        if cached is False:
            return False
        return True if cached is None else cached.can_fetch(self.user_agent, url)

    def sitemap_urls(self, start_url: str) -> list[str]:
        parsed = urlparse(start_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        self.allowed(start_url)
        cached = self._cache.get(origin)
        if isinstance(cached, RobotFileParser):
            return list(cached.site_maps() or [])
        return []


def extract_text_links(text: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(match.strip() for match in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    candidates.extend(match.strip() for match in re.findall(r"https?://[^\s<>)\"']+", text))

    links = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.strip("`'\"").rstrip(".,;]")
        if not candidate or candidate.startswith("#"):
            continue
        url = _normalize_url(urljoin(base_url, candidate))
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _parse_sitemap_urls(xml_text: str) -> tuple[list[str], list[str]]:
    root = ElementTree.fromstring(xml_text)
    urls: list[str] = []
    sitemaps: list[str] = []
    root_tag = root.tag.rsplit("}", 1)[-1]
    for parent in root:
        parent_tag = parent.tag.rsplit("}", 1)[-1]
        if root_tag == "sitemapindex" and parent_tag != "sitemap":
            continue
        if root_tag == "urlset" and parent_tag != "url":
            continue
        for child in parent:
            if child.tag.rsplit("}", 1)[-1] == "loc" and child.text:
                loc = child.text.strip()
                if root_tag == "sitemapindex":
                    sitemaps.append(loc)
                else:
                    urls.append(loc)
                break
    return urls, sitemaps


def discover_sitemap_urls(
    start_url: str,
    *,
    user_agent: str,
    robots: Robots | None = None,
    max_sitemaps: int = 10,
    max_urls: int = 500,
) -> list[str]:
    start = _normalize_url(start_url)
    candidates = robots.sitemap_urls(start) if robots else []
    candidates.append(f"{_origin(start)}/sitemap.xml")

    seen_sitemaps = set()
    seen_urls = set()
    discovered: list[str] = []
    queue = deque(_normalize_url(url) for url in candidates)

    while queue and len(seen_sitemaps) < max_sitemaps and len(discovered) < max_urls:
        sitemap_url = queue.popleft()
        if sitemap_url in seen_sitemaps or not _same_domain(start, sitemap_url):
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            r = httpx.get(
                sitemap_url,
                headers={"User-Agent": user_agent, "Accept": "application/xml,text/xml,*/*;q=0.8"},
                timeout=30,
                follow_redirects=True,
            )
            if r.status_code >= 400:
                continue
            urls, nested_sitemaps = _parse_sitemap_urls(r.text)
        except Exception:
            continue
        for nested in nested_sitemaps:
            nested_url = _normalize_url(nested)
            if nested_url not in seen_sitemaps and _same_domain(start, nested_url):
                queue.append(nested_url)
        for url in urls:
            normalized = _normalize_url(url)
            if (
                normalized not in seen_urls
                and _same_domain(start, normalized)
                and not _skip_url(normalized)
            ):
                seen_urls.add(normalized)
                discovered.append(normalized)
            if len(discovered) >= max_urls:
                break
    return discovered


def crawl_site(
    start_url: str,
    fetch_markdown,
    *,
    max_depth: int = 2,
    max_pages: int = 50,
    pattern: str = "*",
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    use_sitemap: bool = False,
    respect_robots: bool = True,
    delay_min: float = 2.0,
    delay_max: float = 5.0,
    user_agent: str = "KlaudeBot/0.2 (+local documentation crawler)",
    on_progress: Callable[[dict], None] | None = None,
    max_attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> CrawlResult:
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0")
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    start = _normalize_url(start_url)
    queue = deque([(start, 0)])
    seen = {start}
    pages: list[CrawlPage] = []
    errors: list[CrawlError] = []
    skipped: list[str] = []
    seeded: list[str] = []
    robots = Robots(user_agent) if respect_robots else None
    includes = list(include_patterns or [])
    if pattern and pattern != "*":
        includes.append(pattern)
    excludes = list(exclude_patterns or [])

    delay_min = max(0.0, delay_min)
    delay_max = max(delay_min, delay_max)

    if use_sitemap:
        seeded = discover_sitemap_urls(
            start,
            user_agent=user_agent,
            robots=robots,
            max_urls=max(max_pages * 5, max_pages),
        )
        for url in seeded:
            if url not in seen:
                seen.add(url)
                queue.append((url, 0))

    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        if on_progress:
            on_progress({"event": "fetching", "url": url, "depth": depth, "pages": len(pages)})
        if not _same_domain(start, url) or _skip_url(url):
            skipped.append(url)
            if on_progress:
                on_progress(
                    {
                        "event": "skipped",
                        "url": url,
                        "depth": depth,
                        "reason": "domain-or-filetype",
                    }
                )
            continue
        if url != start and not _allowed_by_patterns(url, includes, excludes):
            skipped.append(url)
            if on_progress:
                on_progress({"event": "skipped", "url": url, "depth": depth, "reason": "pattern"})
            continue
        if robots and not robots.allowed(url):
            skipped.append(f"robots.txt: {url}")
            if on_progress:
                on_progress(
                    {"event": "skipped", "url": url, "depth": depth, "reason": "robots.txt"}
                )
            continue

        html = ""
        markdown = ""
        page_retry_count = 0
        try:
            fetched = _get_with_retries(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,text/plain,*/*;q=0.8",
                },
                max_attempts=max_attempts,
                sleeper=sleeper,
            )
            page_retry_count = fetched.retry_count
            if fetched.content_type in {"text/html", "application/xhtml+xml"}:
                html = fetched.text
            markdown = _markdown_from_http_page(fetched)
        except Exception as exc:
            errors.append(
                CrawlError(
                    url=url,
                    depth=depth,
                    error=f"request after {page_retry_count} retries: {exc}",
                )
            )
            if on_progress:
                on_progress(
                    {
                        "event": "error",
                        "url": url,
                        "depth": depth,
                        "error": f"request after {page_retry_count} retries: {exc}",
                    }
                )

        if not markdown:
            try:
                markdown = fetch_markdown(url).strip()
            except Exception as exc:
                errors.append(CrawlError(url=url, depth=depth, error=f"fetch: {exc}"))
                if on_progress:
                    on_progress(
                        {"event": "error", "url": url, "depth": depth, "error": f"fetch: {exc}"}
                    )
        if markdown:
            pages.append(CrawlPage(url=url, markdown=markdown, depth=depth))
            if on_progress:
                on_progress({"event": "indexed", "url": url, "depth": depth, "pages": len(pages)})

        if depth < max_depth:
            discovered = extract_html_links(html, url) if html else []
            discovered.extend(extract_text_links(markdown, url))
            for link in discovered:
                if (
                    link not in seen
                    and _same_domain(start, link)
                    and not _skip_url(link)
                    and _allowed_by_patterns(link, includes, excludes)
                ):
                    seen.add(link)
                    queue.append((link, depth + 1))

        if queue and len(pages) < max_pages and delay_max > 0:
            sleeper(random.uniform(delay_min, delay_max))

    return CrawlResult(start_url=start, pages=pages, errors=errors, skipped=skipped, seeded=seeded)
