import time
from dataclasses import replace

import pytest
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_cli.skill_discovery import (
    DETAIL_KIND,
    INSTALL_KIND,
    SEARCH_KIND,
    STALE_TTL,
    SkillDiscovery,
    detail_page,
)
from klaude_core.skill_catalog import CatalogStatus, SearchResult, SkillRecord


class Jobs:
    def __init__(self):
        self.requests = []
        self.cancelled = []

    def submit(self, key, request, *, timeout):
        self.requests.append((key, request, timeout))
        return str(len(self.requests))

    def cancel(self, key):
        self.cancelled.append(key)


class Panels:
    def __init__(self):
        self.states = {}
        self.current = None
        self.kind = None

    def show(self, page, kind, default):
        if page.id not in self.states:
            self.states[page.id] = PanelState(page, default)
        else:
            self.states[page.id].replace(page)
        self.current, self.kind = self.states[page.id], kind
        if default:
            self.current.picker.focus(default)


def setup():
    jobs, panels, edits, parents = Jobs(), Panels(), [], []
    scope = ["session-1"]
    discovery = SkillDiscovery(jobs, panels.show, edits.append, lambda: parents.append(True),
                               lambda: scope[0])
    return discovery, jobs, panels, edits, parents, scope


def deliver(discovery, panels, result):
    key, identity, _scope, _logical = discovery.pending
    discovery.accept(key, identity, result.payload(), "", panels.kind)


def result():
    return SearchResult(CatalogStatus.OK, (
        SkillRecord("skillsmp", "one", "testing", ("A useful long description " * 30).strip(),
                    repository="org/repo", fetched_at=time.time()),
        SkillRecord("skillsmp", "two", "testing", "Other result", repository="other/repo"),
    ), has_next=True, fetched_at=time.time())


def test_empty_entry_is_local_suggestions_and_controls_only():
    discovery, jobs, panels, *_ = setup()
    discovery.open()
    assert jobs.requests == []
    assert panels.current.page.breadcrumb == ("Settings", "Skills", "Search")
    assert any(row.label == "SUGGESTIONS" for row in panels.current.page.rows)
    assert not any(row.label == "POPULAR" for row in panels.current.page.rows)
    assert panels.current.picker.selected_id == "query"


def test_search_source_sort_pagination_are_explicit_and_bounded():
    discovery, jobs, panels, *_ = setup()
    discovery.action(PanelAction("discover-search", "python"))
    assert jobs.requests[-1][1] == {"kind": "skill_search", "request": {
        "query": "python", "provider": "skillsmp", "sort": "stars", "page": 1}}
    deliver(discovery, panels, result())
    discovery.action(PanelAction("discover-page", "2"))
    assert discovery.request.page == 2
    discovery.action(PanelAction("discover-sort"))
    assert discovery.request.sort == "recent" and discovery.request.page == 1
    assert panels.current.picker.selected_id == "sort"
    discovery.action(PanelAction("discover-provider"))
    assert discovery.request.provider == "skills.sh" and discovery.request.sort == "relevance"
    assert panels.current.picker.selected_id == "provider"
    assert jobs.requests[-1][2] == 15


def test_source_focus_survives_live_reply_and_cached_return():
    discovery, jobs, panels, *_ = setup()
    discovery.search("frontend design")
    deliver(discovery, panels, result())

    discovery.action(PanelAction("discover-provider"))
    assert panels.current.picker.selected_id == "provider"
    deliver(discovery, panels, SearchResult(CatalogStatus.OK, (
        SkillRecord("skills.sh", "one", "frontend-design", repository="anthropics/skills"),
    ), fetched_at=time.time()))
    assert panels.current.picker.selected_id == "provider"

    discovery.action(PanelAction("discover-provider"))
    assert len(jobs.requests) == 2  # SkillsMP comes from the successful cache.
    assert panels.current.picker.selected_id == "provider"


@pytest.mark.parametrize("width", [18, 40, 80, 120])
def test_wrapping_footer_gap_and_missing_license(width):
    record = result().records[0]
    state = PanelState(detail_page(record))
    assert any(row.label == "Source commit" for row in state.page.rows)
    body = render_body(state, width)
    text = "\n".join("".join(t for _, t in line) for line in body.lines)
    assert "Unknown" in text and "…" not in text
    assert "long" in text and "description" in text
    back = next(i for i, identity in enumerate(body.row_for_line) if identity == "back")
    assert "".join(t for _, t in body.lines[back - 1]).strip() == ""
    assert not any(row.action and row.action.kind in {"skill-import", "skill-delete"}
                   for row in state.page.rows)


def test_back_restores_exact_focus_filter_and_viewport():
    discovery, jobs, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    state = panels.current
    state.filter("testing")
    state.search_active = True
    identity = discovery.result.records[1].identity
    state.picker.focus(identity)
    state.scroll_top = 4
    discovery.action(PanelAction("discover-detail", identity))
    assert panels.kind == DETAIL_KIND
    discovery.action(PanelAction("discover-results"))
    assert panels.current is state
    assert state.picker.query == "testing" and state.picker.selected_id == identity
    assert state.scroll_top == 4 and state.search_active


def test_resolved_skill_requires_separate_confirm_before_install():
    jobs, panels, submitted = Jobs(), Panels(), []
    revision = "a" * 40
    discovery = SkillDiscovery(
        jobs, panels.show, lambda _: None, lambda: None, lambda: "session-1",
        lambda record: submitted.append(record.identity) or True,
    )
    record = SkillRecord(
        "skillsmp", "one", "example", repository="org/repo",
        source_url="https://github.com/org/repo/tree/main/skills/example",
        skill_path="skills/example/SKILL.md", revision=revision,
    )
    discovery.detail = record
    discovery.show_detail()
    assert panels.kind == DETAIL_KIND
    assert next(row for row in panels.current.page.rows if row.id == "install").enabled
    assert submitted == []

    discovery.action(PanelAction("discover-install"))
    assert panels.kind == INSTALL_KIND
    assert panels.current.picker.selected_id == "back"
    assert submitted == []
    discovery.action(PanelAction("discover-install-back"))
    assert panels.kind == DETAIL_KIND and submitted == []
    discovery.action(PanelAction("discover-install"))
    discovery.action(PanelAction("discover-confirm-install"))
    assert submitted == [record.identity]
    assert discovery.install_pending and panels.kind == DETAIL_KIND
    discovery.install_done(record.identity, True, "Installed example", DETAIL_KIND)
    assert not discovery.install_pending
    assert next(row for row in panels.current.page.rows if row.id == "install").label == (
        "Installed"
    )
    discovery.action(PanelAction("discover-install"))
    assert submitted == [record.identity]


def test_successful_resolution_focuses_the_new_install_action():
    discovery, _jobs, panels, *_ = setup()
    record = SkillRecord(
        "skillsmp", "one", "example", repository="org/repo",
        source_url="https://github.com/org/repo/tree/main/skills/example",
    )
    discovery.detail = record
    discovery.show_detail("resolve")
    discovery.action(PanelAction("discover-resolve"))
    resolved = replace(record, skill_path="skills/example/SKILL.md", revision="a" * 40)
    key, identity, _scope, _logical = discovery.pending
    discovery.accept(key, identity, {"record": resolved.payload(), "status": "ok"},
                     "", panels.kind)
    assert panels.current.picker.selected_id == "install"
    assert next(row for row in panels.current.page.rows if row.id == "install").enabled


def test_unresolved_catalog_result_cannot_open_install_confirmation():
    jobs, panels, submitted = Jobs(), Panels(), []
    discovery = SkillDiscovery(
        jobs, panels.show, lambda _: None, lambda: None, lambda: "session-1",
        lambda record: submitted.append(record) or True,
    )
    discovery.detail = SkillRecord("skills.sh", "one", "example", repository="org/repo")
    discovery.show_detail()
    assert not next(row for row in panels.current.page.rows if row.id == "install").enabled
    discovery.action(PanelAction("discover-install"))
    assert panels.kind == DETAIL_KIND and submitted == []


@pytest.mark.parametrize("change", ["query", "leave", "session"])
def test_stale_response_rejected(change):
    discovery, jobs, panels, _, parents, scope = setup()
    discovery.search("old")
    pending = discovery.pending
    if change == "query":
        discovery.search("new")
    elif change == "leave":
        discovery.action(PanelAction("discover-back"))
    else:
        scope[0] = "session-2"
    discovery.accept(pending[0], pending[1], result().payload(), "", SEARCH_KIND)
    assert discovery.result is None
    assert len(discovery.cache) == 0
    if change == "leave":
        assert parents and "skill-search" in jobs.cancelled


@pytest.mark.parametrize("status", [CatalogStatus.TIMEOUT, CatalogStatus.AUTH,
                                   CatalogStatus.RATE_LIMIT, CatalogStatus.UNAVAILABLE,
                                   CatalogStatus.NETWORK, CatalogStatus.MALFORMED])
def test_failure_states_never_cached_as_success(status):
    discovery, _, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, SearchResult(status))
    assert discovery.error == status and not discovery.cache
    assert any(row.id == "error" for row in panels.current.page.rows)


def test_search_and_resolution_feedback_use_semantic_status_tones():
    discovery, _, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, SearchResult(CatalogStatus.TIMEOUT))
    error = next(row for row in panels.current.page.rows if row.id == "error")
    assert error.status_tone == "warning"
    body = render_body(panels.current, 80)
    warning_line = next(line for line, owner in zip(
        body.lines, body.row_for_line, strict=True,
    ) if owner == "error")
    assert warning_line[0][0] == "class:panel.status.warning"

    record = result().records[0]
    assert next(row for row in detail_page(record, status=CatalogStatus.OK).rows
                if row.id == "status").status_tone == "success"
    assert next(row for row in detail_page(record, status=CatalogStatus.NETWORK).rows
                if row.id == "status").status_tone == "warning"


def test_success_cache_and_stale_fallback_with_real_age():
    discovery, jobs, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    discovery.search("python")
    assert len(jobs.requests) == 1 and discovery.cache_age is not None
    key = discovery.request.identity
    cached = replace(discovery.cache[key], fetched_at=time.time() - 4000)
    discovery.cache[key] = cached
    discovery.search("python")
    assert len(jobs.requests) == 2 and discovery.result is cached
    deliver(discovery, panels, SearchResult(CatalogStatus.NETWORK))
    assert discovery.result is cached and discovery.cache_age >= 4000
    assert "stale fallback" in next(r.label for r in panels.current.page.rows if r.id == "cache")
    assert discovery.cache[key] is cached


def test_reenter_shows_fresh_cache_age_without_network_request():
    discovery, jobs, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    key = discovery.request.identity
    discovery.cache[key] = replace(discovery.cache[key], fetched_at=time.time() - 30)
    discovery.action(PanelAction("discover-back"))

    discovery.reenter()

    assert len(jobs.requests) == 1
    assert discovery.cache_age is not None and discovery.cache_age >= 30
    assert "Cached metadata" in next(r.label for r in panels.current.page.rows if r.id == "cache")


def test_reenter_refreshes_stale_metadata_without_losing_focus_or_filter():
    discovery, jobs, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    record = discovery.result.records[1]
    state = panels.current
    state.filter("testing")
    state.picker.focus(record.identity)
    key = discovery.request.identity
    discovery.cache[key] = replace(discovery.cache[key], fetched_at=time.time() - 4000)
    discovery.action(PanelAction("discover-back"))

    discovery.reenter()

    assert len(jobs.requests) == 2 and discovery.pending is not None
    assert discovery.cache_age is not None and discovery.cache_age >= 4000
    assert panels.current is state and state.picker.selected_id == record.identity
    assert state.picker.query == "testing"
    assert "refreshing" in next(r.label for r in state.page.rows if r.id == "cache")

    deliver(discovery, panels, result())
    assert panels.current is state and state.picker.selected_id == record.identity
    assert state.picker.query == "testing" and discovery.cache_age is None


def test_reenter_drops_metadata_older_than_stale_fallback_limit():
    discovery, jobs, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    key = discovery.request.identity
    discovery.cache[key] = replace(discovery.cache[key], fetched_at=time.time() - STALE_TTL - 1)
    discovery.action(PanelAction("discover-back"))

    discovery.reenter()

    assert len(jobs.requests) == 2 and discovery.pending is not None
    assert discovery.result is None and discovery.cache_age is None
    assert not any(row.id.startswith("skillsmp:") for row in panels.current.page.rows)


def test_query_editor_is_explicit_and_cancel_returns_without_network():
    discovery, jobs, panels, edits, *_ = setup()
    discovery.action(PanelAction("discover-query"))
    assert edits == [""] and not jobs.requests
    discovery.answer_query(None)
    assert panels.kind == SEARCH_KIND and jobs.requests == []


def test_resolve_reply_after_back_cannot_change_page():
    discovery, _, panels, *_ = setup()
    discovery.search("python")
    record = replace(result().records[0], source_url="https://github.com/org/repo/tree/main/test")
    deliver(discovery, panels, replace(result(), records=(record,)))
    discovery.action(PanelAction("discover-detail", record.identity))
    discovery.action(PanelAction("discover-resolve"))
    pending = discovery.pending
    discovery.action(PanelAction("discover-results"))
    discovery.accept(pending[0], pending[1], {"status": "ok", "record": record.payload()}, "",
                     SEARCH_KIND)
    assert panels.kind == SEARCH_KIND and discovery.detail_status is None


def test_opening_cached_result_cancels_refresh_and_rejects_late_reply():
    discovery, jobs, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    record = discovery.result.records[0]
    discovery.search("python", refresh=True)
    pending = discovery.pending
    assert pending is not None and discovery.result is not None

    discovery.action(PanelAction("discover-detail", record.identity))
    assert discovery.pending is None and "skill-search" in jobs.cancelled
    assert panels.kind == DETAIL_KIND and discovery.detail == record

    discovery.accept(pending[0], pending[1], SearchResult(CatalogStatus.EMPTY).payload(), "",
                     DETAIL_KIND)
    assert discovery.result.records[0] == record
    assert panels.kind == DETAIL_KIND


def test_long_detail_pages_scroll_without_making_info_selectable():
    state = PanelState(detail_page(result().records[0]), "resolve")
    body = render_body(state, 40)
    selected = state.picker.selected_id
    assert not any(r.selectable for r in state.page.rows if r.id.startswith("field:"))
    assert state.scroll_row(12, body)
    top = state.viewport(8, body)
    assert top > 0 and state.picker.selected_id == selected
    assert state.scroll_row(-12, body)
    assert state.viewport(8, body) < top


def test_loaded_refresh_keeps_filter_focus_and_wrapped_row_scroll():
    discovery, _, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    state = panels.current
    identity = discovery.result.records[0].identity
    state.picker.focus(identity)
    state.filter("testing")
    body = render_body(state, 30)
    assert state.scroll_row(8, body)
    offset = state.focus_line(body)
    discovery.search("python", refresh=True)
    deliver(discovery, panels, result())
    assert panels.current is state and state.picker.query == "testing"
    assert state.picker.selected_id == identity
    assert state.focus_line(render_body(state, 30)) == offset


def test_malformed_worker_response_and_deadline_are_visible_and_not_cached():
    for data, error, status in [({}, "", CatalogStatus.MALFORMED),
                                (None, "Background job timed out; retry", CatalogStatus.TIMEOUT)]:
        discovery, _, panels, *_ = setup()
        discovery.search("python")
        key, identity, *_ = discovery.pending
        discovery.accept(key, identity, data, error, SEARCH_KIND)
        assert discovery.error == status and not discovery.cache


@pytest.mark.parametrize("width", [24, 70, 120])
def test_result_table_wraps_full_descriptions_without_ellipsis(width):
    discovery, _, panels, *_ = setup()
    discovery.search("python")
    deliver(discovery, panels, result())
    body = render_body(panels.current, width)
    record = discovery.result.records[0]
    lines = ["".join(text for _, text in line) for line, owner in zip(
        body.lines, body.row_for_line, strict=True) if owner == record.identity]
    assert "…" not in "".join(lines)
    assert sum(line.count("description") for line in lines) == 30
    assert panels.current.page.column_headers == ("SKILL", "SOURCE", "DESCRIPTION")
