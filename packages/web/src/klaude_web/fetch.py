"""Safe page retrieval and the direct -> Crawl4AI -> trafilatura cascade."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

UA = "Mozilla/5.0 (X11; Linux x86_64) klaude-code/0.2 (+local research agent)"
TEXT_CONTENT_TYPES = {
    "application/json",
    "application/markdown",
    "application/xml",
    "text/markdown",
    "text/plain",
    "text/xml",
}
HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref_src",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}


class UnsafeURL(ValueError):
    """Raised when an untrusted fetch target crosses the public-web boundary."""


class FetchPageError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        failure_class: str,
        transient: bool = False,
        final_url: str = "",
        redirect_count: int = 0,
        attempted_providers: tuple[str, ...] = (),
    ):
        super().__init__(reason)
        self.failure_class = failure_class
        self.transient = transient
        self.final_url = final_url
        self.redirect_count = redirect_count
        self.attempted_providers = attempted_providers


@dataclass(frozen=True)
class FetchLimits:
    timeout_seconds: float = 30.0
    max_download_bytes: int = 2_000_000
    max_content_characters: int = 20_000
    max_redirects: int = 5


@dataclass(frozen=True)
class DownloadedPage:
    requested_url: str
    final_url: str
    body: bytes
    content_type: str
    status_code: int
    redirect_count: int
    truncated: bool


@dataclass(frozen=True)
class FetchPageResult:
    content: str
    provider: str
    requested_url: str
    final_url: str
    title: str = ""
    published_at: str | None = None
    author: str | None = None
    fetched_at: str = ""
    redirect_count: int = 0
    download_status: str = "succeeded"
    extraction_status: str = "succeeded"
    downloaded_bytes: int = 0
    download_truncated: bool = False
    content_truncated: bool = False
    attempted_providers: tuple[str, ...] = ()
    successful_provider: str | None = None


class _MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True
            return
        if tag.lower() != "meta":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        key = (attr_map.get("property") or attr_map.get("name") or "").lower()
        content = attr_map.get("content", "").strip()
        if key and content:
            self.meta.setdefault(key, []).append(unescape(content))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def _normalized_host(parsed) -> str:
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURL("URL must include a hostname")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UnsafeURL("URL hostname is invalid") from exc


def _blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _validate_host_syntax(host: str) -> None:
    lowered = host.casefold()
    if lowered in BLOCKED_HOSTNAMES or lowered.endswith(".localhost") or lowered.endswith(".local"):
        raise UnsafeURL(f"local or private host is not allowed: {host}")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if _blocked_ip(address):
        raise UnsafeURL(f"local or private address is not allowed: {host}")


def canonicalize_public_url(url: str) -> str:
    """Normalize a syntactically public HTTP(S) URL without resolving DNS."""
    raw = str(url or "").strip()
    if not raw:
        raise UnsafeURL("URL is required")
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeURL("only http and https URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("URLs containing user credentials are not allowed")
    host = _normalized_host(parsed)
    _validate_host_syntax(host)
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL("URL port is invalid") from exc
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    host_for_netloc = f"[{host}]" if ":" in host else host
    netloc = host_for_netloc if port is None or default_port else f"{host_for_netloc}:{port}"
    filtered_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_QUERY_KEYS
        ],
        doseq=True,
    )
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            parsed.params,
            filtered_query,
            "",
        )
    )


def canonical_url_key(url: str) -> str:
    """Return a conservative equivalence key for registry/cache deduplication."""
    normalized = canonicalize_public_url(url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunparse((parsed.scheme, netloc, path, parsed.params, parsed.query, ""))


def validate_public_url(
    url: str,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    """Resolve a URL and reject targets that map to non-public networks."""
    normalized = canonicalize_public_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        answers = resolver(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchPageError(
            f"could not resolve public host {host}",
            failure_class="dns_failure",
            transient=True,
        ) from exc
    addresses: set[str] = set()
    for answer in answers:
        sockaddr = answer[4]
        if sockaddr:
            addresses.add(str(sockaddr[0]).split("%", 1)[0])
    if not addresses:
        raise FetchPageError(
            f"could not resolve public host {host}",
            failure_class="dns_failure",
            transient=True,
        )
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise UnsafeURL(f"host resolved to an invalid address: {value}") from exc
        if _blocked_ip(address):
            raise UnsafeURL(f"host resolves to a local or private address: {value}")
    return normalized


def _content_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _download_public_page(
    url: str,
    limits: FetchLimits,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
) -> DownloadedPage:
    requested_url = canonicalize_public_url(url)
    current_url = requested_url
    redirect_count = 0
    headers = {
        "User-Agent": UA,
        "Accept": (
            "text/plain,text/markdown,text/html,application/xhtml+xml,"
            "application/json,application/xml,text/xml;q=0.9,*/*;q=0.8"
        ),
    }
    try:
        with httpx.Client(
            headers=headers,
            timeout=limits.timeout_seconds,
            follow_redirects=False,
            transport=transport,
            trust_env=False,
        ) as client:
            while True:
                current_url = validate_public_url(current_url, resolver)
                with client.stream("GET", current_url) as response:
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location", "").strip()
                        if not location:
                            raise FetchPageError(
                                "redirect response did not include a location",
                                failure_class="invalid_redirect",
                            )
                        if redirect_count >= limits.max_redirects:
                            raise FetchPageError(
                                f"redirect limit ({limits.max_redirects}) exceeded",
                                failure_class="redirect_limit",
                            )
                        current_url = canonicalize_public_url(urljoin(current_url, location))
                        redirect_count += 1
                        continue
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    for chunk in response.iter_bytes():
                        remaining = limits.max_download_bytes - total
                        if remaining <= 0:
                            truncated = True
                            break
                        chunks.append(chunk[:remaining])
                        total += min(len(chunk), remaining)
                        if len(chunk) > remaining:
                            truncated = True
                            break
                    return DownloadedPage(
                        requested_url=requested_url,
                        final_url=current_url,
                        body=b"".join(chunks),
                        content_type=_content_type(response.headers),
                        status_code=response.status_code,
                        redirect_count=redirect_count,
                        truncated=truncated,
                    )
    except UnsafeURL:
        raise
    except FetchPageError:
        raise
    except httpx.TimeoutException as exc:
        raise FetchPageError(
            "page request timed out", failure_class="timeout", transient=True
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise FetchPageError(
            f"page returned HTTP {exc.response.status_code}",
            failure_class=f"http_{exc.response.status_code}",
            transient=exc.response.status_code in {408, 425, 429, 500, 502, 503, 504},
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise FetchPageError(
            f"page request failed: {exc}",
            failure_class="network_failure",
            transient=True,
        ) from exc


def _decode_body(page: DownloadedPage) -> str:
    return page.body.decode("utf-8", errors="replace").strip()


def resolve_public_url(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    max_redirects: int = 5,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
) -> tuple[str, int]:
    """Resolve and revalidate an HTTP redirect chain without retaining the page body."""
    page = _download_public_page(
        url,
        FetchLimits(
            timeout_seconds=timeout_seconds,
            max_download_bytes=1,
            max_content_characters=1,
            max_redirects=max_redirects,
        ),
        resolver=resolver,
        transport=transport,
    )
    return page.final_url, page.redirect_count


def _html_metadata(html: str) -> tuple[str, str | None, str | None, str]:
    parser = _MetadataParser()
    parser.feed(html)
    title = " ".join(" ".join(parser.title_parts).split())
    title = next(iter(parser.meta.get("og:title", [])), title)
    author = next(
        iter(parser.meta.get("article:author", []) or parser.meta.get("author", [])),
        None,
    )
    published_at = next(
        iter(
            parser.meta.get("article:published_time", [])
            or parser.meta.get("date", [])
            or parser.meta.get("datepublished", [])
        ),
        None,
    )
    descriptions: list[str] = []
    for key in ("og:description", "description", "twitter:description"):
        for value in parser.meta.get(key, []):
            normalized = " ".join(value.split())
            if normalized and normalized not in descriptions:
                descriptions.append(normalized)
    tags: list[str] = []
    for key in ("og:video:tag", "article:tag"):
        for value in parser.meta.get(key, []):
            normalized = " ".join(value.split())
            if normalized and normalized not in tags:
                tags.append(normalized)
    lines: list[str] = []
    if title:
        lines.append(f"# {title}")
    if descriptions:
        lines.append("Description:")
        lines.extend(descriptions)
    if tags:
        lines.append("Tags: " + ", ".join(tags[:20]))
    return title, published_at, author, "\n\n".join(lines)


def _bound_content(content: str, limit: int) -> tuple[str, bool]:
    text = content.strip()
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    marker = "\n\n...[content bounded by fetch_url]...\n\n"
    if limit <= len(marker):
        return text[:limit], True
    available = limit - len(marker)
    head_length = max(1, int(available * 0.8))
    tail_length = available - head_length
    tail = text[-tail_length:].lstrip() if tail_length else ""
    return f"{text[:head_length].rstrip()}{marker}{tail}", True


def crawl4ai_headers(api_key: str = "") -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}", "X-API-Key": api_key}


def _crawl4ai(
    base_url: str,
    url: str,
    api_key: str = "",
    *,
    timeout_seconds: float = 60.0,
) -> str:
    response = httpx.post(
        f"{base_url.rstrip('/')}/md",
        headers=crawl4ai_headers(api_key),
        json={"url": url, "f": "fit"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    markdown = data.get("markdown") or data.get("result", {}).get("markdown") or ""
    if not str(markdown).strip():
        raise FetchPageError("crawl4ai returned empty markdown", failure_class="empty_extraction")
    return str(markdown).strip()


def _trafilatura_html(html: str, metadata: str) -> str:
    import trafilatura

    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_formatting=True,
        include_links=True,
        include_tables=True,
    )
    extracted = str(text or "").strip()
    if metadata and extracted:
        return f"{metadata}\n\n{extracted}"
    if metadata:
        return metadata
    if not extracted:
        raise FetchPageError("trafilatura extracted no content", failure_class="empty_extraction")
    return extracted


def fetch_page_detailed(
    url: str,
    crawl4ai_url: str = "",
    crawl4ai_api_key: str = "",
    *,
    limits: FetchLimits | None = None,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
) -> FetchPageResult:
    """Fetch one public page and return bounded, extracted evidence plus diagnostics."""
    active_limits = limits or FetchLimits()
    try:
        page = _download_public_page(url, active_limits, resolver=resolver, transport=transport)
    except FetchPageError as exc:
        if not exc.attempted_providers:
            exc.attempted_providers = ("direct",)
        raise
    body = _decode_body(page)
    if not body:
        raise FetchPageError("page returned empty content", failure_class="empty_download")
    attempted = ["direct"]
    provider = "direct"
    title = ""
    published_at = None
    author = None
    extraction_status = "plain_text"

    try:
        if page.content_type in TEXT_CONTENT_TYPES:
            content = body
        elif page.content_type in HTML_CONTENT_TYPES or not page.content_type:
            title, published_at, author, metadata = _html_metadata(body)
            content = ""
            if crawl4ai_url:
                attempted.append("crawl4ai")
                try:
                    content = _crawl4ai(
                        crawl4ai_url,
                        page.final_url,
                        crawl4ai_api_key,
                        timeout_seconds=active_limits.timeout_seconds,
                    )
                    provider = "crawl4ai"
                    extraction_status = "main_content"
                except Exception:
                    content = ""
            if not content:
                attempted.append("trafilatura")
                content = _trafilatura_html(body, metadata)
                provider = "trafilatura"
                extraction_status = "main_content"
        elif crawl4ai_url:
            attempted.append("crawl4ai")
            content = _crawl4ai(
                crawl4ai_url,
                page.final_url,
                crawl4ai_api_key,
                timeout_seconds=active_limits.timeout_seconds,
            )
            provider = "crawl4ai"
            extraction_status = "main_content"
        else:
            raise FetchPageError(
                f"unsupported page content type: {page.content_type or 'unknown'}",
                failure_class="unsupported_content_type",
            )
    except FetchPageError as exc:
        exc.final_url = page.final_url
        exc.redirect_count = page.redirect_count
        exc.attempted_providers = tuple(attempted)
        raise

    bounded, content_truncated = _bound_content(content, active_limits.max_content_characters)
    if not bounded:
        raise FetchPageError("page extraction was empty", failure_class="empty_extraction")
    return FetchPageResult(
        content=bounded,
        provider=provider,
        requested_url=page.requested_url,
        final_url=page.final_url,
        title=title,
        published_at=published_at,
        author=author,
        fetched_at=datetime.now(UTC).isoformat(),
        redirect_count=page.redirect_count,
        extraction_status=extraction_status,
        downloaded_bytes=len(page.body),
        download_truncated=page.truncated,
        content_truncated=content_truncated,
        attempted_providers=tuple(attempted),
        successful_provider=provider,
    )


def fetch_page(
    url: str,
    crawl4ai_url: str = "",
    crawl4ai_api_key: str = "",
    *,
    limits: FetchLimits | None = None,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    transport: httpx.BaseTransport | None = None,
) -> str:
    return fetch_page_detailed(
        url,
        crawl4ai_url,
        crawl4ai_api_key,
        limits=limits,
        resolver=resolver,
        transport=transport,
    ).content
