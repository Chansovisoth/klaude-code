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
            assert "lastModified" in request.url.params.get_list("expand")
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


def test_catalog_upgrades_cached_metadata_and_retains_offline_fallback(hub):
    cfg, calls, state = hub
    first = catalog(cfg)
    path = next((cfg.data_dir / "model-manager" / "discovery").glob("*.json"))
    old = json.loads(path.read_text())
    old.pop("metadata_version")
    old["models"][0]["modified"] = ""
    path.write_text(json.dumps(old))
    updated = catalog(cfg)
    assert len(calls) == 2
    assert updated["models"][0]["modified"] == "2026-10-25T00:00:00Z"
    assert updated["metadata_version"] == 2
    path.write_text(json.dumps(old))
    state["offline"] = True
    fallback = catalog(cfg)
    assert fallback["stale"] and fallback["models"] == old["models"]
    assert fallback["checked_at"] == first["checked_at"]


@pytest.mark.parametrize("limit", [18, 21, 24, 50])
def test_catalog_accepts_bounded_responsive_grid_page_sizes(hub, limit):
    cfg, calls, _ = hub
    result = catalog(cfg, limit=limit)
    assert result["page_size"] == limit
    assert calls[-1].url.params["limit"] == str(limit)
    for invalid in [0, 51, True]:
        with pytest.raises(ValueError, match="bounded"):
            catalog(cfg, limit=invalid)


def test_catalog_tops_up_short_filtered_batches_without_skipping_next_page(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from klaude_application import model_store_catalog as store

    cfg = SimpleNamespace(data_dir=tmp_path, huggingface_base_url="http://catalog.test")
    calls = []

    def row(identity):
        return {"id": identity, "summary": "", "downloads": 1, "downloads_known": True}

    def search(*args, cursor="", **kwargs):
        calls.append((cursor, args[4]))
        if not cursor:
            return [row("maker/first"), row("invalid"), row("maker/first")], "fill"
        if cursor == "fill":
            return [row(f"maker/m-{i}") for i in range(20)], "second"
        assert cursor == "second"
        return [row(f"maker/n-{i}") for i in range(21)], ""

    monkeypatch.setattr(store, "hub_repo_search", search)
    first = catalog(cfg, limit=21)
    second = catalog(cfg, limit=21, page=2)
    assert len(first["models"]) == len(second["models"]) == 21
    assert not {item["id"] for item in first["models"]} & {
        item["id"] for item in second["models"]
    }
    assert calls == [("", 21), ("fill", 20), ("second", 21)]


def test_runtime_catalog_pages_and_exact_files_have_separate_caches(tmp_path, monkeypatch):
    from klaude_application import model_store_catalog as store

    cfg = SimpleNamespace(data_dir=tmp_path, huggingface_base_url="https://hf.fixture")
    calls = []

    def search(*args, filter_tag, cursor="", **kwargs):
        calls.append((filter_tag, cursor))
        assert not cursor or cursor == filter_tag + "-next"
        return [{"id": "org/shared", "summary": "", "downloads": 10,
                 "downloads_known": True}], "" if cursor else filter_tag + "-next"

    def files(*args, image=False):
        calls.append(("files", image))
        return {"files": [{"filename": "model.safetensors" if image else "model.gguf",
                           "size": 1234}], "license": "mit"}

    monkeypatch.setattr(store, "hub_repo_search", search)
    monkeypatch.setattr(store, "hub_gguf_files", files)
    for runtime in ("sdcpp", "ollama"):
        assert catalog(cfg, runtime=runtime, limit=1)["models"]
        assert catalog(cfg, runtime=runtime, limit=1, page=2)["models"]
        exact = detail(cfg, "hf:org/shared", runtime=runtime)
        assert exact["variants"][0]["tag"].endswith(
            ".safetensors" if runtime == "sdcpp" else ".gguf")
    assert calls == [("text-to-image", ""), ("text-to-image", "text-to-image-next"),
                     ("files", True), ("gguf", ""), ("gguf", "gguf-next"), ("files", False)]
    for runtime in ("sdcpp", "ollama"):
        catalog(cfg, runtime=runtime, limit=1, page=2)
        detail(cfg, "hf:org/shared", runtime=runtime)
    assert len(calls) == 6
    with pytest.raises(ValueError):
        catalog(cfg, runtime="arbitrary")
    with pytest.raises(ValueError):
        detail(cfg, "hf:org/shared", runtime="arbitrary")
