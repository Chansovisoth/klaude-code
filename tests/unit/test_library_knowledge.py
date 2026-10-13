"""Explicit Knowledge consumers, failure retention and owned task navigation."""

import json
import queue
import time

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.library_knowledge import library_name, run_operation, source_inventory
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.config import Config
from klaude_core.memory import Memory
from klaude_core.ollama import Ollama
from klaude_knowledge import (
    Knowledge,
    index_installed_docs,
    install_docs_source,
    recover_docs_sources,
)
from prompt_toolkit.utils import get_cwidth

from .test_library_workspace import library_host as base_library_host


def library_host(memory):
    host, calls = base_library_host(memory)
    host.cfg.models["embed"] = "fixture-embedding"
    return host, calls


@pytest.fixture
def memory(tmp_path):
    item = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    item.log_turn("saved", "user", "Conversation")
    yield item
    item.db.close()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    value = Config()
    value.models["embed"] = "fixture-embedding"
    value.ollama_url = "http://127.0.0.1:11434"
    monkeypatch.setattr(config, "load_config", lambda: value)
    return value


@pytest.fixture
def embeddings(monkeypatch):
    calls = []

    def embed(_self, model, texts):
        calls.append((model, list(texts)))
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(Ollama, "embed", embed)
    return calls


def request(cfg, operation, **values):
    return {
        "operation": operation,
        "library": "widgets",
        "ollama_url": cfg.ollama_url,
        "embedding_model": cfg.models["embed"],
        "workspace": str(cfg.data_dir.parent),
        **values,
    }


def act(host, kind, target=""):
    host._apply_panel_action(PanelAction("library-knowledge-" + kind, target))


def docs(cfg, embeddings):
    pages = {
        "https://example.com/llms.txt": "- [Guide](/guide.md)",
        "https://example.com/guide.md": "# Widget architecture\n\nPrevious verified architecture",
    }
    installed = install_docs_source(
        cfg,
        "https://example.com/llms.txt",
        pages.__getitem__,
        name="widget-docs",
        library="widgets",
    )
    knowledge = Knowledge(cfg)
    try:
        index_installed_docs(installed, knowledge)
    finally:
        knowledge.store.fts.close()
        knowledge.ollama.close()
    return installed, pages


def test_explicit_learning_is_idempotent_and_hybrid_query_uses_existing_service(cfg, embeddings):
    source = cfg.data_dir.parent / "architecture.md"
    source.write_text(
        "# Widget architecture\n\nWidget architecture uses bounded workers and retained content."
    )
    original = source.read_bytes()
    result = run_operation(request(cfg, "learn", source=str(source)))
    assert result["status"] == "learned" and result["chunks"] > 0
    used = len(embeddings)
    assert run_operation(request(cfg, "learn", source=str(source)))["status"] == "unchanged"
    assert len(embeddings) == used
    answer = run_operation(request(cfg, "query", query="Widget architecture"))
    assert answer["status"] == "queried" and "bounded workers" in str(answer["hits"])
    assert source.read_bytes() == original
    assert not (cfg.data_dir / "library").exists()


def test_learning_bounds_and_binary_failures_never_publish(cfg, embeddings):
    source = cfg.data_dir.parent / "binary"
    source.write_bytes(b"binary\0content")
    assert run_operation(request(cfg, "learn", source=str(source)))["status"] == "rejected"
    with source.open("wb") as opened:
        opened.truncate(2 * 1024 * 1024 + 1)
    assert run_operation(request(cfg, "learn", source=str(source)))["status"] == "rejected"
    link = source.with_name("linked")
    link.symlink_to(source)
    assert run_operation(request(cfg, "learn", source=str(link)))["status"] == "rejected"
    assert not embeddings and not (cfg.data_dir / "knowledge.lance").exists()


@pytest.mark.parametrize("name", ["../outside", "a/b", "a\\b", "..", "x" * 81, "bad\x1b"])
def test_learning_library_path_is_validated(name):
    with pytest.raises(ValueError):
        library_name(name)


def test_managed_inventory_is_readonly_bounded_and_filters_libraries(cfg, embeddings):
    missing = cfg.data_dir / "missing"
    assert source_inventory(missing)["items"] == [] and not missing.exists()
    installed, _ = docs(cfg, embeddings)
    before = installed.manifest_path.read_bytes()
    items = source_inventory(cfg.docs_sources_dir, "widgets")["items"]
    assert items[0]["id"] == "widget-docs" and len(items[0]["identity"]) == 64
    assert not source_inventory(cfg.docs_sources_dir, "other")["items"]
    assert installed.manifest_path.read_bytes() == before
    (cfg.docs_sources_dir / "linked").symlink_to(installed.root)
    assert len(source_inventory(cfg.docs_sources_dir)["items"]) == 1
    broken = cfg.docs_sources_dir / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text('{"name":"broken","library":"widgets","files":null}')
    result = source_inventory(cfg.docs_sources_dir)
    assert len(result["items"]) == 1 and result["unavailable"] == 1


def test_refresh_uses_fresh_fetch_and_retains_old_index_after_partial_failure(
    cfg, embeddings, monkeypatch
):
    from klaude_web import Web

    installed, pages = docs(cfg, embeddings)
    identity = source_inventory(cfg.docs_sources_dir)["items"][0]["identity"]
    old_manifest = installed.manifest_path.read_bytes()
    calls = []

    def fetch(_self, url):
        calls.append(url)
        if url.endswith("guide.md"):
            raise RuntimeError("private provider response")
        return pages[url]

    monkeypatch.setattr(Web, "fetch_fresh", fetch)
    result = run_operation(request(cfg, "refresh", source="widget-docs", source_identity=identity))
    assert result["status"] == "rejected" and "previous indexed" in result["message"]
    assert "private provider" not in str(result)
    assert installed.manifest_path.read_bytes() == old_manifest
    knowledge = Knowledge(cfg)
    try:
        assert "Previous verified" in str(knowledge.query("Widget architecture", "widgets"))
    finally:
        knowledge.store.fts.close()
        knowledge.ollama.close()
    assert calls == list(pages)


def test_stale_source_review_cannot_fetch_or_change_new_definition(cfg, embeddings, monkeypatch):
    from klaude_web import Web

    installed, _ = docs(cfg, embeddings)
    identity = source_inventory(cfg.docs_sources_dir)["items"][0]["identity"]
    value = json.loads(installed.manifest_path.read_text())
    value["library"] = "new-library"
    installed.manifest_path.write_text(json.dumps(value))
    calls = []
    monkeypatch.setattr(Web, "fetch_fresh", lambda *args: calls.append(args) or "new text")
    result = run_operation(request(cfg, "refresh", source="widget-docs", source_identity=identity))
    assert result["status"] == "rejected" and "changed elsewhere" in result["message"]
    assert not calls


def test_cancelled_download_with_same_urls_cannot_be_recovered_as_indexed(cfg, embeddings):
    installed, pages = docs(cfg, embeddings)
    before = installed.manifest_path.read_bytes()
    pages["https://example.com/guide.md"] = "# Widget architecture\n\nUnindexed replacement"
    pending = install_docs_source(
        cfg,
        "https://example.com/llms.txt",
        pages.__getitem__,
        name="widget-docs",
        library="widgets",
    )
    assert recover_docs_sources(cfg) == 0
    assert installed.manifest_path.read_bytes() == before
    assert pending.pending_manifest_path.exists()
    knowledge = Knowledge(cfg)
    try:
        index_installed_docs(pending, knowledge)
        # Simulate interruption after activation but before publishing metadata.
        installed.manifest_path.write_bytes(before)
        pending_data = {
            "name": pending.name,
            "library": pending.library,
            "version_id": pending.version_id,
            "current_dir": str(pending.current_dir),
            "indexed_sources": pending.source_urls,
            "files": [
                {
                    "url": url,
                    "path": path.relative_to(pending.current_dir).as_posix(),
                    "checksum": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                }
                for path, url in zip(pending.files, pending.source_urls, strict=True)
            ],
        }
        pending.pending_manifest_path.write_text(json.dumps(pending_data))
        assert recover_docs_sources(cfg) == 1
        assert (
            json.loads(installed.manifest_path.read_text())["active_version"] == pending.version_id
        )
    finally:
        knowledge.store.fts.close()
        knowledge.ollama.close()


def test_owned_fresh_fetch_bypasses_cache_and_keeps_fetch_guards(monkeypatch):
    from klaude_web import Web

    web = Web.__new__(Web)
    web.cfg = Config()
    calls = []
    monkeypatch.setattr(
        web, "_fetch_uncached_detailed", lambda url: calls.append(url) or {"content": "fresh text"}
    )
    monkeypatch.setattr(web, "fetch_detailed", lambda url: pytest.fail("cached path used"))
    assert web.fetch_fresh("https://example.com/guide") == "fresh text"
    assert calls == ["https://example.com/guide"]
    with pytest.raises(ValueError):
        web.fetch_fresh("http://127.0.0.1/private")
    assert len(calls) == 1


def test_review_defaults_to_back_and_editors_never_add_chat_content(memory):
    host, _ = library_host(memory)
    host._library.open("knowledge")
    messages = list(host.agent.messages)
    act(host, "learn")
    assert host._settings_input_is_single_line()
    host._answer_settings_input("widgets")
    host._answer_settings_input("architecture.md")
    assert host._library.view == "knowledge-review" and host._panel.picker.selected_id == "back"
    assert not host._library.knowledge.busy
    assert host.agent.messages == messages and not host.input.text
    host._cancel_choice()
    assert host._library.view == "knowledge"


def test_task_cancellation_waits_for_worker_stop_and_preserves_new_navigation(memory):
    host, calls = library_host(memory)
    host._library.open("knowledge")
    act(host, "learn")
    assert host._settings_input_is_single_line()
    host._answer_settings_input("widgets")
    host._answer_settings_input("architecture.md")
    act(host, "start")
    controller = host._library.knowledge
    assert controller.busy and calls[-1][2]["notify_cancel"]
    identity = controller.task[0]
    act(host, "stop")
    assert controller.busy and controller.stopping
    host._library.open("media")
    controller.stopped(identity)
    assert not controller.busy and host._library.view == "media"
    assert "verify indexing" in str(host._panel_feedback)


def test_task_result_drops_other_session_content_and_restores_exact_parent(memory):
    host, calls = library_host(memory)
    host._library.open("knowledge")
    act(host, "learn")
    assert host._settings_input_is_single_line()
    host._answer_settings_input("widgets")
    host._answer_settings_input("architecture.md")
    act(host, "start")
    controller = host._library.knowledge
    identity = controller.task[0]
    host.session_id = "another-session"
    controller.accept(
        identity,
        {"status": "queried", "hits": [{"source": "private", "text": "do not publish"}]},
        "",
    )
    assert not controller.busy and "do not publish" not in str(host._panel.page)
    assert not controller.result


def test_repeated_hybrid_query_keeps_original_back_destination(memory):
    host, _ = library_host(memory)
    controller = host._library.knowledge
    host._library.parent, host._library.target = "knowledge", "widgets"
    host._library.detail = {"id": "widgets", "sources": 1, "chunks": 1}
    host._library.show("detail")
    act(host, "hybrid")
    host._answer_settings_input("Widget architecture")
    identity = controller.task[0]
    controller.accept(identity, {"status": "queried", "hits": []}, "")
    assert host._library.view == "knowledge-hybrid"
    act(host, "hybrid")
    host._answer_settings_input("Another architecture query")
    controller.accept(controller.task[0], {"status": "queried", "hits": []}, "")
    assert controller.parent == "detail" and controller.name == "widgets"
    act(host, "back", "detail")
    assert host._library.view == "detail" and host._library.target == "widgets"


def test_managed_source_back_does_not_cycle_between_list_and_detail(memory):
    host, _ = library_host(memory)
    controller = host._library.knowledge
    controller.sources_parent, controller.parent = "knowledge", "knowledge-source-detail"
    controller.source = {
        "id": "widget-docs",
        "library": "widgets",
        "kind": "llms.txt",
        "url": "https://example.com/llms.txt",
        "files": 2,
        "checked": "",
        "identity": "a" * 64,
    }
    host._library.show("knowledge-sources")
    page = host._panel.page
    assert next(row for row in page.rows if row.id == "back").action.target == "knowledge"


def test_running_knowledge_task_blocks_generation_after_library_closes(memory):
    host, _ = library_host(memory)
    host._library.knowledge.task = ("id", host.session_id, host._library.scope, "learn")
    host._library.show("home")
    host._library.action(PanelAction("library-close"))
    host.pending.append("Inspect project")
    host._start_next()
    assert not host.running and host.pending
    assert host._session_action_is_busy()
    controller = host._library.knowledge
    controller.task_started = time.monotonic() - 4
    status = "".join(text for _, text in host._status_fragments())
    assert "LEARNING" in status and ("queue 1" in status or "q:1" in status) and "ctx" in status


def test_refresh_crawl_uses_cumulative_fetch_budget_and_keeps_current_index(
    cfg, embeddings, monkeypatch
):
    from klaude_knowledge import install_crawl_source
    from klaude_web import Web

    installed = install_crawl_source(
        cfg,
        "crawl-docs",
        "widgets",
        "https://example.com/",
        [
            {
                "url": "https://example.com/guide.md",
                "markdown": "# Widget architecture\n\nOld retained source",
            }
        ],
        options={"max_pages": 20},
    )
    knowledge = Knowledge(cfg)
    index_installed_docs(installed, knowledge)
    knowledge.store.fts.close()
    knowledge.ollama.close()
    before = installed.manifest_path.read_bytes()
    identity = source_inventory(cfg.docs_sources_dir)["items"][0]["identity"]
    monkeypatch.setattr(Web, "fetch_fresh", lambda *args: "x" * (5 * 1024 * 1024))

    def crawl(_self, url, **kwargs):
        assert kwargs["fresh"] and kwargs["max_pages"] == 20
        kwargs["fetcher"](url + "first")
        kwargs["fetcher"](url + "second")
        pytest.fail("Cumulative fetch bound did not stop the crawl")

    monkeypatch.setattr(Web, "crawl_site", crawl)
    result = run_operation(request(cfg, "refresh", source="crawl-docs", source_identity=identity))
    assert result["status"] == "rejected" and "8 MiB" in result["message"]
    assert installed.manifest_path.read_bytes() == before


@pytest.mark.parametrize("width", [40, 70, 120])
def test_knowledge_action_pages_wrap_and_keep_controls_above_header(memory, width):
    host, _ = library_host(memory)
    host._library.open("knowledge")
    rows = list(host._panel.page.rows)
    assert next(i for i, row in enumerate(rows) if row.id == "learn-source") < next(
        i for i, row in enumerate(rows) if row.id == "columns"
    )
    act(host, "learn")
    assert host._settings_input_is_single_line()
    host._answer_settings_input("widgets")
    host._answer_settings_input("Very long 設計 filename " * 10 + ".md")
    body = render_body(PanelState(host._panel.page), width)
    assert all(get_cwidth("".join(text for _, text in line)) <= width for line in body.lines)


def test_background_cancel_notification_is_optional_and_after_cleanup(monkeypatch):
    import subprocess

    events = queue.Queue()
    stopped = []

    class Process:
        pid = 12345
        stdin = stdout = None

        def communicate(self, payload, timeout):
            time.sleep(0.01)
            raise subprocess.TimeoutExpired("worker", timeout)

    monkeypatch.setattr(
        "klaude_cli.background_jobs.subprocess.Popen", lambda *args, **kwargs: Process()
    )
    monkeypatch.setattr(
        OwnedBackgroundJobs, "_stop_process", lambda self, process: stopped.append(process.pid)
    )
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    identity = jobs.submit("knowledge", {}, notify_cancel=True)
    jobs.cancel("knowledge")
    jobs.close(wait=True)
    assert events.get(timeout=2) == ("background_stopped", ("knowledge", identity))
    # If cancellation won the race before process creation, no process existed
    # to clean up; otherwise cleanup must precede the acknowledgement.
    assert stopped in ([], [12345])


def test_terminal_resize_pairs_panel_cursor_with_rendered_lines(memory, monkeypatch):
    from klaude_cli.main import TwoClickPanelControl
    from klaude_cli.settings_panel import PanelPage, PanelRow, RowKind

    host, _ = library_host(memory)
    page = PanelPage(
        "resize-test",
        ("Library", "Knowledge"),
        (
            PanelRow("text", RowKind.INFO, "Source", description="long text " * 120),
            PanelRow("reload", RowKind.ACTION, "Reload", action=PanelAction("library-reload")),
        ),
        scrollable_body=True,
    )
    host._panel = PanelState(page)
    host._panel.picker.focus("reload")
    widths = iter((120, 40, 70, 40))
    calls = []

    def body():
        width = next(widths)
        calls.append(width)
        return render_body(host._panel, width)

    monkeypatch.setattr(host, "_panel_body", body)
    control = TwoClickPanelControl(host)
    for _ in range(4):
        fragments = control._render_fragments()
        line_count = 1 + sum(text.count("\n") for _, text in fragments)
        assert 0 <= control.get_cursor_position().y < line_count
    assert calls == [120, 40, 70, 40]


def test_two_column_knowledge_counts_use_available_width(memory):
    host, _ = library_host(memory)
    host._library.open("knowledge")
    host._library.cache[host._library.key()] = (
        {"items": [{"id": "widgets", "sources": 123, "chunks": 456}], "more": False},
        time.monotonic(),
    )
    host._library.show()
    for width in (70, 120):
        body = render_body(PanelState(host._panel.page), width)
        rows = [
            line
            for line, owner in zip(body.lines, body.row_for_line, strict=True)
            if owner == "record:widgets"
        ]
        assert len(rows) == 1
        assert "123 sources · 456 chunks" in "".join(text for _, text in rows[0])


def test_fresh_text_rejects_truncation_but_research_excerpts_remain_available(monkeypatch):
    from klaude_web import Web
    from klaude_web.fetch import FetchPageError

    web = Web.__new__(Web)
    web.cfg = Config()
    monkeypatch.setattr(
        web, "_fetch_uncached_detailed",
        lambda _url: {"content": "Bounded source excerpt", "content_truncated": True},
    )
    with pytest.raises(FetchPageError, match="extraction limits"):
        web.fetch_fresh("https://example.com/guide")
    assert web.fetch_fresh_detailed("https://example.com/guide")["content_truncated"] is True
