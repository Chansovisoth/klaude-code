import httpx

from klaude_web.fetch import fetch_page


class FakeResponse:
    def __init__(self, text: str, content_type: str):
        self.text = text
        self.headers = httpx.Headers({"content-type": content_type})

    def raise_for_status(self) -> None:
        return None


def test_fetch_page_returns_plain_text_without_extraction(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse("# React docs\n\nhttps://react.dev/learn.md\n", "text/plain")

    monkeypatch.setattr("klaude_web.fetch.httpx.get", fake_get)

    assert fetch_page("https://react.dev/llms.txt") == (
        "# React docs\n\nhttps://react.dev/learn.md"
    )


def test_fetch_page_falls_back_for_html(monkeypatch):
    import trafilatura

    def fake_get(*args, **kwargs):
        return FakeResponse("<main><h1>Hello</h1><p>World</p></main>", "text/html; charset=utf-8")

    monkeypatch.setattr("klaude_web.fetch.httpx.get", fake_get)
    monkeypatch.setattr(trafilatura, "extract", lambda *args, **kwargs: "# Hello\n\nWorld")

    assert "Hello" in fetch_page("https://example.test")
