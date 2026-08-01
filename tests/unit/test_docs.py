import json
from pathlib import Path

from klaude_knowledge.docs import (
    extract_doc_links,
    finalize_docs_source,
    install_crawl_source,
    install_docs_source,
    list_docs_sources,
    update_docs_source,
)


class FakeConfig:
    def __init__(self, root: Path):
        self._root = root
        self.snapshot_retention = 1
        self.crawl_max_depth = 2
        self.crawl_max_pages = 50
        self.crawl_delay_min = 2.0
        self.crawl_delay_max = 5.0
        self.crawl_respect_robots = True

    @property
    def docs_sources_dir(self) -> Path:
        path = self._root / "docs-sources"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def knowledge_dir(self) -> Path:
        path = self._root / "knowledge"
        path.mkdir(parents=True, exist_ok=True)
        return path


def test_extract_doc_links_keeps_same_domain_markdown():
    index = """
    - [Learn](/learn.md)
    - [State](https://react.dev/reference/react/useState.md)
    - [External](https://example.com/nope.md)
    - https://react.dev/reference/react.md
    - https://react.dev/reference/react.md
    """

    assert extract_doc_links("https://react.dev/llms.txt", index) == [
        "https://react.dev/learn.md",
        "https://react.dev/reference/react/useState.md",
        "https://react.dev/reference/react.md",
    ]


def test_install_docs_source_fetches_links_and_writes_manifest(tmp_path):
    pages = {
        "https://react.dev/llms.txt": "- [Learn](/learn.md)\n- [Offsite](https://example.com/x.md)",
        "https://react.dev/learn.md": "# Learn React\n\nHooks and components.",
    }
    calls = []

    def fetcher(url):
        calls.append(url)
        return pages[url]

    installed = install_docs_source(
        FakeConfig(tmp_path),
        "https://react.dev/llms.txt",
        fetcher,
        name="react",
        library="react",
    )

    assert calls == ["https://react.dev/llms.txt", "https://react.dev/learn.md"]
    assert installed.source_urls == ["https://react.dev/llms.txt", "https://react.dev/learn.md"]
    assert any(path.read_text().startswith("- [Learn]") for path in installed.files)
    assert any(path.read_text().startswith("# Learn React") for path in installed.files)
    assert installed.pending_manifest_path and installed.pending_manifest_path.exists()
    assert list_docs_sources(FakeConfig(tmp_path)) == []
    finalize_docs_source(installed)
    assert (installed.root / "CURRENT").read_text().strip() == installed.version_id
    assert list_docs_sources(FakeConfig(tmp_path))[0]["indexed_sources"] == installed.source_urls


def test_docs_source_query_variants_get_distinct_files(tmp_path):
    pages = [
        {
            "url": "https://docs.example/page?tab=a",
            "markdown": "# A",
            "depth": 0,
        },
        {
            "url": "https://docs.example/page?tab=b",
            "markdown": "# B",
            "depth": 0,
        },
    ]

    installed = install_crawl_source(
        FakeConfig(tmp_path),
        "query-docs",
        "docs",
        "https://docs.example/page",
        pages,
    )

    names = sorted(path.name for path in installed.files)
    assert len(names) == 2
    assert names[0] != names[1]
    assert all("__" in name for name in names)


def test_unchanged_docs_source_moved_to_new_library_records_old_library(tmp_path):
    cfg = FakeConfig(tmp_path)

    def fetcher(url):
        return "# Same"

    first = install_docs_source(
        cfg, "https://docs.example/llms.txt", fetcher, name="demo", library="old"
    )
    finalize_docs_source(first)
    moved = install_docs_source(
        cfg, "https://docs.example/llms.txt", fetcher, name="demo", library="new"
    )

    assert moved.previous_library == "old"
    assert moved.previous_sources == ["https://docs.example/llms.txt"]
    assert moved.snapshot == ""


def test_update_docs_source_snapshots_old_current_and_prunes(tmp_path):
    cfg = FakeConfig(tmp_path)
    version = {"text": "# First"}

    def fetcher(url):
        return version["text"]

    first = install_docs_source(cfg, "https://docs.example/llms.txt", fetcher, name="demo")
    finalize_docs_source(first)
    version["text"] = "# Second"
    second = update_docs_source(cfg, "demo", fetcher)
    finalize_docs_source(second)
    version["text"] = "# Third"
    third = update_docs_source(cfg, "demo", fetcher)

    assert any(path.read_text() == "# Third\n" for path in third.files)
    assert (third.root / "CURRENT").read_text().strip() == second.version_id
    assert third.version_id != second.version_id
    assert second.previous_sources == ["https://docs.example/llms.txt"]


def test_update_docs_source_skips_snapshot_when_unchanged(tmp_path):
    cfg = FakeConfig(tmp_path)

    def fetcher(url):
        return "# Same"

    first = install_docs_source(cfg, "https://docs.example/llms.txt", fetcher, name="demo")
    finalize_docs_source(first)
    updated = update_docs_source(cfg, "demo", fetcher)

    assert updated.previous_sources == ["https://docs.example/llms.txt"]
    assert updated.snapshot == ""
    assert not (updated.root / "snapshots").exists()


def test_install_and_update_crawl_source_uses_saved_options(tmp_path):
    cfg = FakeConfig(tmp_path)
    first = install_crawl_source(
        cfg,
        "demo-crawl",
        "demo",
        "https://docs.example/start",
        [{"url": "https://docs.example/start", "markdown": "# First", "depth": 0}],
        options={
            "max_depth": 1,
            "max_pages": 5,
            "pattern": "https://docs.example/*",
            "respect_robots": True,
            "delay_min": 0.5,
            "delay_max": 1.0,
        },
    )
    finalize_docs_source(first)
    calls = []

    def crawler(url, **kwargs):
        calls.append((url, kwargs))
        return {
            "pages": [{"url": url, "markdown": "# Second", "depth": 0}],
            "errors": [],
            "skipped": [],
        }

    updated = update_docs_source(cfg, "demo-crawl", lambda _url: "", crawler=crawler)

    assert calls == [
        (
            "https://docs.example/start",
            {
                "max_depth": 1,
                "max_pages": 5,
                "pattern": "https://docs.example/*",
                "include_patterns": [],
                "exclude_patterns": [],
                "use_sitemap": False,
                "respect_robots": True,
                "delay_min": 0.5,
                "delay_max": 1.0,
            },
        )
    ]
    assert updated.previous_sources == ["https://docs.example/start"]
    assert any(path.read_text() == "# Second\n" for path in updated.files)
    finalize_docs_source(updated)
    listed = list_docs_sources(cfg)[0]
    assert listed["kind"] == "crawl"
    assert listed["start_url"] == "https://docs.example/start"


def test_update_crawl_source_rejects_empty_refresh(tmp_path):
    import pytest

    cfg = FakeConfig(tmp_path)
    first = install_crawl_source(
        cfg,
        "demo-crawl",
        "demo",
        "https://docs.example/start",
        [{"url": "https://docs.example/start", "markdown": "# First", "depth": 0}],
    )
    finalize_docs_source(first)

    def crawler(_url, **_kwargs):
        return {"pages": [], "errors": [{"url": "x"}], "skipped": ["y"], "seeded": []}

    with pytest.raises(RuntimeError, match="no indexable pages"):
        update_docs_source(cfg, "demo-crawl", lambda _url: "", crawler=crawler)

    active = (cfg.docs_sources_dir / "demo-crawl" / "CURRENT").read_text().strip()
    assert (cfg.docs_sources_dir / "demo-crawl" / "versions" / active).is_dir()


def test_docs_staged_replacement_does_not_move_active_pointer_before_finalize(tmp_path):
    cfg = FakeConfig(tmp_path)
    version = {"text": "# First"}

    def fetcher(url):
        return version["text"]

    first = install_docs_source(cfg, "https://docs.example/llms.txt", fetcher, name="demo")
    finalize_docs_source(first)
    version["text"] = "# Second"

    staged = update_docs_source(cfg, "demo", fetcher)

    assert staged.version_id != first.version_id
    assert (staged.root / "CURRENT").read_text().strip() == first.version_id
    assert json.loads(staged.manifest_path.read_text())["active_version"] == first.version_id


def test_llms_child_failure_records_warning_and_keeps_other_pages(tmp_path):
    pages = {
        "https://react.dev/llms.txt": "- [Learn](/learn.md)\n- [Broken](/broken.md)",
        "https://react.dev/learn.md": "# Learn React",
    }

    def fetcher(url):
        if url.endswith("broken.md"):
            raise RuntimeError("boom")
        return pages[url]

    installed = install_docs_source(
        FakeConfig(tmp_path),
        "https://react.dev/llms.txt",
        fetcher,
        name="react",
        library="react",
    )

    assert installed.source_urls == ["https://react.dev/llms.txt", "https://react.dev/learn.md"]
    assert installed.warnings
    assert installed.warnings[0]["url"] == "https://react.dev/broken.md"


def test_url_variants_produce_distinct_file_paths(tmp_path):
    pages = [
        {"url": "https://docs.example/page", "markdown": "# A", "depth": 0},
        {"url": "https://docs.example/page/", "markdown": "# B", "depth": 0},
        {"url": "https://docs.example/page.md", "markdown": "# C", "depth": 0},
    ]

    installed = install_crawl_source(
        FakeConfig(tmp_path),
        "variants",
        "docs",
        "https://docs.example/page",
        pages,
    )

    names = [path.name for path in installed.files]
    assert len(names) == len(set(names))
