from klaude_web.huggingface import (
    hub_repo_details,
    hub_repo_readme,
    hub_repo_search,
)


class FakeResponse:
    def __init__(self, payload=None, text="", status_code: int = 200):
        self.payload = payload
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def test_huggingface_search_requests_models(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return FakeResponse(
            [
                {
                    "modelId": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
                    "likes": 42,
                    "downloads": 9001,
                    "lastModified": "2026-07-01T00:00:00.000Z",
                    "tags": ["text-generation", "transformers"],
                    "pipeline_tag": "text-generation",
                }
            ]
        )

    monkeypatch.setattr("klaude_web.huggingface.httpx.get", fake_get)

    results = hub_repo_search(
        "https://huggingface.co",
        "secret",
        "model",
        "qwen coder",
        3,
    )

    assert calls[0]["url"] == "https://huggingface.co/api/models"
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"
    assert calls[0]["params"] == {
        "limit": 3,
        "search": "qwen coder",
        "sort": "downloads",
    }
    assert results[0]["id"] == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    assert results[0]["url"] == "https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct"


def test_huggingface_details_requests_dataset(monkeypatch):
    calls = []

    def fake_get(url, headers, timeout):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse({"id": "owner/data", "tags": ["parquet"]})

    monkeypatch.setattr("klaude_web.huggingface.httpx.get", fake_get)

    result = hub_repo_details("https://huggingface.co", "", "dataset", "owner/data")

    assert calls[0]["url"] == "https://huggingface.co/api/datasets/owner/data"
    assert "Authorization" not in calls[0]["headers"]
    assert result["type"] == "dataset"
    assert result["url"] == "https://huggingface.co/datasets/owner/data"


def test_huggingface_readme_requests_dataset_card(monkeypatch):
    calls = []

    def fake_get(url, headers, timeout, follow_redirects=False):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
                "follow_redirects": follow_redirects,
            }
        )
        if "/api/datasets/" in url:
            return FakeResponse({"id": "owner/data"})
        return FakeResponse(text="# Dataset Card\n\nUseful details")

    monkeypatch.setattr("klaude_web.huggingface.httpx.get", fake_get)

    text = hub_repo_readme("https://huggingface.co", "secret", "dataset", "owner/data")

    assert calls[0]["url"] == "https://huggingface.co/api/datasets/owner/data"
    assert calls[1]["url"] == "https://huggingface.co/datasets/owner/data/raw/main/README.md"
    assert calls[1]["headers"]["Authorization"] == "Bearer secret"
    assert calls[1]["follow_redirects"] is True
    assert text.startswith("# Dataset Card")


def test_huggingface_readme_uses_metadata_revision_when_main_unavailable(monkeypatch):
    calls = []

    def fake_get(url, headers, timeout, follow_redirects=False):
        calls.append(url)
        if "/api/models/" in url:
            return FakeResponse({"id": "owner/model", "default_branch": "refs-pruned"})
        if "/raw/refs-pruned/" in url:
            return FakeResponse(text="# Model Card")
        if "/raw/main/" in url:
            return FakeResponse(status_code=404)
        raise AssertionError(url)

    monkeypatch.setattr("klaude_web.huggingface.httpx.get", fake_get)

    text = hub_repo_readme("https://huggingface.co", "", "model", "owner/model")

    assert calls[0] == "https://huggingface.co/api/models/owner/model"
    assert calls[1] == "https://huggingface.co/owner/model/raw/refs-pruned/README.md"
    assert text == "# Model Card"
