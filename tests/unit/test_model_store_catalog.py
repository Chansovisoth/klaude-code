"""Verified HF API metadata, exact file tags and bounded offline cache behavior."""

import json
from types import SimpleNamespace

import httpx
import pytest
from klaude_application.model_store_catalog import catalog, detail
from klaude_web.huggingface import hub_gguf_files


@pytest.fixture
def hub(tmp_path, monkeypatch):
    cfg = SimpleNamespace(data_dir=tmp_path, huggingface_base_url="https://hf.fixture")
    calls, state = [], {"offline": False}
    original = httpx.Client

    def handle(request):
        calls.append(request)
        assert "authorization" not in request.headers
        if state["offline"]:
            return httpx.Response(503)
        if request.url.path == "/api/models":
            assert request.url.params["filter"] == "gguf"
            assert request.url.params["direction"] == "-1"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "org/Small-GGUF",
                        "downloads": 123,
                        "lastModified": "2026-10-25T00:00:00Z",
                    },
                    {"id": "org/Unknown-GGUF"},
                ],
            )
        return httpx.Response(
            200,
            json={
                "id": "org/Small-GGUF",
                "cardData": {"license": "apache-2.0"},
                "siblings": [
                    {"rfilename": "model-Q4_K_M.gguf", "lfs": {"size": 1024}},
                    {"rfilename": "model-Q8_0.gguf", "size": 2048},
                    {"rfilename": "model-00001-of-00002.gguf"},
                    {"rfilename": "../unsafe.gguf"},
                    {"rfilename": "subdir/model.gguf"},
                    {"rfilename": "mmproj-model.gguf"},
                ],
            },
        )

    monkeypatch.setattr(
        httpx, "Client", lambda *a, **kw: original(*a, **kw, transport=httpx.MockTransport(handle))
    )
    return cfg, calls, state


def test_real_metadata_counts_exact_tags_and_no_weight_requests(hub):
    cfg, calls, _ = hub
    found = catalog(cfg)
    assert found["models"][0]["downloads"] == 123
    assert found["models"][1]["downloads"] is None
    assert not found["models"][0]["capabilities"]
    full = detail(cfg, found["models"][0]["id"])
    assert full["license"] == "apache-2.0"
    assert [v["tag"] for v in full["variants"]] == [
        "hf.co/org/Small-GGUF:model-Q4_K_M.gguf",
        "hf.co/org/Small-GGUF:model-Q8_0.gguf",
    ]
    assert full["variants"][0]["size"] == 1024
    assert len(calls) == 2 and all(r.method == "GET" for r in calls)
    assert all("/resolve/" not in r.url.path for r in calls)
    assert catalog(cfg)["checked_at"] == found["checked_at"] and len(calls) == 2


def test_cache_age_offline_and_query_bounds(hub):
    cfg, calls, state = hub
    first = catalog(cfg)
    state["offline"] = True
    failed = catalog(cfg, refresh=True)
    assert failed["stale"] and failed["checked_at"] == first["checked_at"]
    assert failed["models"] == first["models"]
    assert catalog(cfg, "different")["stale"]
    assert "models" not in catalog(cfg, "different")
    for query in ["x" * 201, "control\n"]:
        with pytest.raises(ValueError):
            catalog(cfg, query)
    with pytest.raises(ValueError):
        catalog(cfg, sort="invented")
    with pytest.raises(ValueError):
        hub_gguf_files(cfg.huggingface_base_url, "", "../invalid")
    assert all("private" not in json.dumps(dict(r.headers)) for r in calls)
