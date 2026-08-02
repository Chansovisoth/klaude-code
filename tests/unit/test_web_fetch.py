import httpx
from klaude_web.fetch import fetch_page, fetch_page_detailed


class FakeResponse:
    def __init__(self, text: str, content_type: str, data: dict | None = None):
        self.text = text
        self.headers = httpx.Headers({"content-type": content_type})
        self._data = data or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


def test_fetch_page_returns_plain_text_without_extraction(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse("# React docs\n\nhttps://react.dev/learn.md\n", "text/plain")

    monkeypatch.setattr("klaude_web.fetch.httpx.get", fake_get)

    assert fetch_page("https://react.dev/llms.txt") == (
        "# React docs\n\nhttps://react.dev/learn.md"
    )
    detailed = fetch_page_detailed("https://react.dev/llms.txt")
    assert detailed.provider == "direct"
    assert detailed.successful_provider == "direct"


def test_fetch_page_falls_back_for_html(monkeypatch):
    import trafilatura

    def fake_get(*args, **kwargs):
        return FakeResponse("<main><h1>Hello</h1><p>World</p></main>", "text/html; charset=utf-8")

    monkeypatch.setattr("klaude_web.fetch.httpx.get", fake_get)
    monkeypatch.setattr(trafilatura, "extract", lambda *args, **kwargs: "# Hello\n\nWorld")

    assert "Hello" in fetch_page("https://example.test")
    detailed = fetch_page_detailed("https://example.test")
    assert detailed.provider == "trafilatura"
    assert detailed.attempted_providers == ("direct", "trafilatura")


def test_fetch_page_preserves_html_metadata(monkeypatch):
    import trafilatura

    html = """
    <html>
      <head>
        <title>FlazeSlayer - YouTube</title>
        <meta property="og:description" content="I record games like Minecraft and Roblox.">
        <meta property="og:video:tag" content="gaming">
      </head>
      <body><footer>Privacy Terms</footer></body>
    </html>
    """

    def fake_get(*args, **kwargs):
        return FakeResponse(html, "text/html; charset=utf-8")

    monkeypatch.setattr("klaude_web.fetch.httpx.get", fake_get)
    monkeypatch.setattr(trafilatura, "extract", lambda *args, **kwargs: "Privacy Terms")

    fetched = fetch_page("https://www.youtube.com/@Flazeslayer/videos")

    assert "# FlazeSlayer - YouTube" in fetched
    assert "Minecraft and Roblox" in fetched
    assert "Tags: gaming" in fetched


def test_fetch_page_sends_crawl4ai_api_key(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse("<main><h1>Hello</h1></main>", "text/html")

    def fake_post(url, headers, json, timeout):
        assert url == "http://crawl.test/md"
        assert headers["Authorization"] == "Bearer secret"
        assert headers["X-API-Key"] == "secret"
        assert json == {"url": "https://example.test", "f": "fit"}
        return FakeResponse("", "application/json", {"markdown": "# Crawled"})

    monkeypatch.setattr("klaude_web.fetch.httpx.get", fake_get)
    monkeypatch.setattr("klaude_web.fetch.httpx.post", fake_post)

    assert fetch_page("https://example.test", "http://crawl.test", "secret") == "# Crawled"
    detailed = fetch_page_detailed("https://example.test", "http://crawl.test", "secret")
    assert detailed.provider == "crawl4ai"
    assert detailed.attempted_providers == ("direct", "crawl4ai")
