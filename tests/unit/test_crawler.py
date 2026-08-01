from datetime import UTC, datetime

import httpx
from klaude_web.crawler import (
    crawl_site,
    discover_sitemap_urls,
    extract_html_links,
    extract_text_links,
    parse_retry_after,
)


class FakeResponse:
    def __init__(
        self,
        text: str,
        content_type: str = "text/html",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        url: str = "https://docs.example",
    ):
        self.text = text
        self.headers = httpx.Headers({"content-type": content_type, **(headers or {})})
        self.status_code = status_code
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "bad status",
                request=httpx.Request("GET", "https://docs.example"),
                response=httpx.Response(self.status_code),
            )


def test_extract_links_from_html_and_markdown():
    html = '<a href="/docs/a">A</a><a href="https://other.example/x">X</a>'
    text = "- [B](/docs/b.md)\n- https://docs.example/docs/c.md"

    assert extract_html_links(html, "https://docs.example/docs/") == [
        "https://docs.example/docs/a",
        "https://other.example/x",
    ]
    assert extract_text_links(text, "https://docs.example/docs/index.md") == [
        "https://docs.example/docs/b.md",
        "https://docs.example/docs/c.md",
    ]


def test_crawl_site_stays_same_domain_and_follows_markdown_links(monkeypatch):
    pages = {
        "https://docs.example/robots.txt": FakeResponse("User-agent: *\nAllow: /", "text/plain"),
        "https://docs.example/docs/index": FakeResponse(
            '<a href="/docs/a">A</a><a href="https://other.example/nope">Nope</a>'
        ),
        "https://docs.example/docs/a": FakeResponse('<a href="/docs/b">B</a>'),
        "https://docs.example/docs/b": FakeResponse("<h1>B</h1>"),
    }

    def fake_get(url, *args, **kwargs):
        return pages[url]

    def fetch_markdown(url):
        if url.endswith("/docs/index"):
            return "# Index\n\n- [A](/docs/a)\n- [C](/docs/c.md)"
        return f"# {url.rsplit('/', 1)[-1]}"

    monkeypatch.setattr("klaude_web.crawler.httpx.get", fake_get)
    monkeypatch.setattr("klaude_web.crawler.time.sleep", lambda *_args: None)
    monkeypatch.setattr("klaude_web.crawler.random.uniform", lambda *_args: 0)

    result = crawl_site(
        "https://docs.example/docs/index",
        fetch_markdown,
        max_depth=1,
        max_pages=10,
        delay_min=0,
        delay_max=0,
    )

    assert [page.url for page in result.pages] == [
        "https://docs.example/docs/index",
        "https://docs.example/docs/a",
    ]
    assert "https://other.example/nope" not in [page.url for page in result.pages]
    assert "https://docs.example/docs/b" not in [page.url for page in result.pages]


def test_normal_html_page_is_requested_once_without_markdown_refetch(monkeypatch):
    calls = []
    markdown_calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return FakeResponse("<html><body><h1>Docs</h1><p>Hello docs.</p></body></html>", url=url)

    def fetch_markdown(url):
        markdown_calls.append(url)
        return "# fallback"

    monkeypatch.setattr("klaude_web.crawler.httpx.get", fake_get)

    result = crawl_site(
        "https://docs.example/page",
        fetch_markdown,
        max_depth=0,
        max_pages=1,
        respect_robots=False,
        delay_min=0,
        delay_max=0,
    )

    assert calls == ["https://docs.example/page"]
    assert markdown_calls == []
    assert result.pages[0].markdown


def test_crawl_site_respects_robots_txt(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse("User-agent: *\nDisallow: /private", "text/plain")
        return FakeResponse("<h1>Private</h1>")

    monkeypatch.setattr("klaude_web.crawler.httpx.get", fake_get)

    result = crawl_site(
        "https://docs.example/private/page",
        lambda _url: "# Private",
        max_depth=0,
        max_pages=5,
        delay_min=0,
        delay_max=0,
    )

    assert result.pages == []
    assert result.skipped == ["robots.txt: https://docs.example/private/page"]


def test_crawl_site_seeds_from_sitemap_and_applies_filters(monkeypatch):
    sitemap = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://docs.example/docs/a</loc></url>
      <url><loc>https://docs.example/docs/draft</loc></url>
      <url><loc>https://other.example/docs/nope</loc></url>
    </urlset>
    """
    pages = {
        "https://docs.example/robots.txt": FakeResponse(
            "User-agent: *\nAllow: /\nSitemap: https://docs.example/sitemap.xml",
            "text/plain",
        ),
        "https://docs.example/sitemap.xml": FakeResponse(sitemap, "application/xml"),
        "https://docs.example/start": FakeResponse("<h1>Start</h1>"),
        "https://docs.example/docs/a": FakeResponse("<h1>A</h1>"),
    }

    def fake_get(url, *args, **kwargs):
        return pages[url]

    monkeypatch.setattr("klaude_web.crawler.httpx.get", fake_get)

    seeded = discover_sitemap_urls(
        "https://docs.example/start",
        user_agent="TestBot",
        robots=None,
    )
    assert seeded == [
        "https://docs.example/docs/a",
        "https://docs.example/docs/draft",
    ]

    result = crawl_site(
        "https://docs.example/start",
        lambda url: f"# {url.rsplit('/', 1)[-1]}",
        max_depth=0,
        max_pages=5,
        include_patterns=["*/docs/*"],
        exclude_patterns=["*draft*"],
        use_sitemap=True,
        delay_min=0,
        delay_max=0,
    )

    assert result.seeded == [
        "https://docs.example/docs/a",
        "https://docs.example/docs/draft",
    ]
    assert [page.url for page in result.pages] == [
        "https://docs.example/start",
        "https://docs.example/docs/a",
    ]
    assert "https://docs.example/docs/draft" in result.skipped


def test_429_followed_by_success_is_retried(monkeypatch):
    calls = []
    sleeps = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(
                "slow down",
                status_code=429,
                headers={"retry-after": "2"},
                url=url,
            )
        return FakeResponse("# OK", "text/plain", url=url)

    monkeypatch.setattr("klaude_web.crawler.httpx.get", fake_get)

    result = crawl_site(
        "https://docs.example/page",
        lambda _url: "# fallback",
        max_depth=0,
        max_pages=1,
        respect_robots=False,
        delay_min=0,
        delay_max=0,
        sleeper=sleeps.append,
    )

    assert len(calls) == 2
    assert sleeps == [2.0]
    assert result.pages[0].markdown == "# OK"


def test_retry_exhaustion_records_final_failure(monkeypatch):
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return FakeResponse("unavailable", status_code=503, url=url)

    monkeypatch.setattr("klaude_web.crawler.httpx.get", fake_get)
    monkeypatch.setattr("klaude_web.crawler.random.uniform", lambda *_args: 0)

    result = crawl_site(
        "https://docs.example/page",
        lambda _url: "",
        max_depth=0,
        max_pages=1,
        respect_robots=False,
        delay_min=0,
        delay_max=0,
        max_attempts=2,
        sleeper=lambda _seconds: None,
    )

    assert len(calls) == 2
    assert result.pages == []
    assert "request after 0 retries" in result.errors[0].error


def test_retry_after_parses_seconds_and_http_dates():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert parse_retry_after("7", now) == 7.0
    assert parse_retry_after("Wed, 01 Jan 2026 12:00:05 GMT", now) == 5.0
