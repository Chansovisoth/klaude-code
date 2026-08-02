import hashlib
import logging

from klaude_web.exa import exa_fetch, exa_search


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_exa_search_requests_highlights(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(
            {
                "results": [
                    {
                        "title": "Result",
                        "url": "https://example.test",
                        "highlights": ["Useful excerpt"],
                    }
                ]
            }
        )

    monkeypatch.setattr("klaude_web.exa.httpx.post", fake_post)

    results = exa_search("https://api.exa.ai", "  key  ", "React hooks", 3)

    assert results[0]["snippet"] == "Useful excerpt"
    assert calls[0]["headers"]["x-api-key"] == "key"
    assert calls[0]["headers"]["Content-Type"] == "application/json"
    assert "Authorization" not in calls[0]["headers"]
    assert not calls[0]["headers"]["x-api-key"].startswith("Bearer ")
    assert calls[0]["json"]["query"] == "React hooks"
    assert calls[0]["json"]["type"] == "auto"
    assert calls[0]["json"]["contents"]["highlights"] is True
    assert calls[0]["json"]["numResults"] == 3


def test_exa_auth_debug_log_is_fingerprinted_not_secret(monkeypatch, caplog):
    calls = []
    secret = "secret-exa-key"

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse({"results": []})

    monkeypatch.setattr("klaude_web.exa.httpx.post", fake_post)

    with caplog.at_level(logging.DEBUG, logger="klaude_web.exa"):
        exa_search("https://api.exa.ai", secret, "American Intercon School Cambodia", 3)

    logs = "\n".join(record.getMessage() for record in caplog.records)
    fingerprint = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:10]
    assert f"fingerprint={fingerprint}" in logs
    assert "header=x-api-key" in logs
    assert secret not in logs
    assert "Bearer" not in logs


def test_exa_fetch_requests_markdown_text(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse({"results": [{"text": "# Docs\n\nBody"}]})

    monkeypatch.setattr("klaude_web.exa.httpx.post", fake_post)

    assert exa_fetch("https://api.exa.ai", "key", "https://example.test") == "# Docs\n\nBody"
    assert calls[0]["json"]["urls"] == ["https://example.test"]
    assert calls[0]["json"]["text"] is True
