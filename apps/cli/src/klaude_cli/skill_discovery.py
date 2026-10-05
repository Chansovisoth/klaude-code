"""Skills discovery pages, source resolution, and explicit install handoff."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime

from klaude_core.skill_catalog import (
    MAX_PAGE,
    STATUS_TEXT,
    CatalogStatus,
    SearchRequest,
    SearchResult,
    SkillRecord,
    github_location,
)

from .background_jobs import OwnedBackgroundJobs
from .installed_settings import list_preview
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

SEARCH_KIND = "skill discovery"
DETAIL_KIND = "skill discovery detail"
INSTALL_KIND = "skill discovery install"
SUGGESTIONS = ("python", "testing", "frontend design", "documentation")
CACHE_TTL = 3600
STALE_TTL = 7 * 86400


def back_row(action: str) -> PanelRow:
    return PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                    control=RowControl.BACK, action=PanelAction(action))


def source_page(current: str) -> PanelPage:
    rows = [PanelRow("sources", RowKind.SECTION, "SEARCH SOURCE")]
    for identity, label, description in (
        ("skillsmp", "SkillsMP", "Repository stars and recent sorting"),
        ("skills.sh", "skills.sh", "Provisional search · relevance order"),
    ):
        rows.append(PanelRow(identity, RowKind.CHOICE, label,
                             "Current" if identity == current else "",
                             description, action=PanelAction("discover-provider-apply", identity),
                             section_id="sources"))
    rows.append(back_row("discover-provider-back"))
    return PanelPage("skill-search-source", ("Settings", "Skills", "Search", "Source"),
                     tuple(rows))


def sort_page(current: str) -> PanelPage:
    rows = [PanelRow("sorts", RowKind.SECTION, "SORT RESULTS")]
    for identity, label in (("stars", "Repository stars"), ("recent", "Recent")):
        rows.append(PanelRow(identity, RowKind.CHOICE, label,
                             "Current" if identity == current else "",
                             action=PanelAction("discover-sort-apply", identity),
                             section_id="sorts"))
    rows.append(back_row("discover-sort-back"))
    return PanelPage("skill-search-sort", ("Settings", "Skills", "Search", "Sort"),
                     tuple(rows))


def search_page(request: SearchRequest | None, provider: str, sort: str,
                result: SearchResult | None = None, *, loading: bool = False,
                cache_age: int | None = None, error: CatalogStatus | None = None) -> PanelPage:
    query = request.query if request else ""
    rows = [
        PanelRow("search-heading", RowKind.SECTION, "SEARCH"),
        PanelRow("query", RowKind.ACTION, "Search query", query or "Enter keywords",
                 action=PanelAction("discover-query"), section_id="search-heading"),
        PanelRow("provider", RowKind.CHOICE, "Source", "SkillsMP" if provider == "skillsmp"
                 else "skills.sh (provisional)", action=PanelAction("discover-provider"),
                 section_id="search-heading"),
        PanelRow("sort", RowKind.CHOICE, "Sort", "Repository stars" if sort == "stars" else
                 "Recent" if sort == "recent" else "Relevance", enabled=provider == "skillsmp",
                 action=PanelAction("discover-sort"), section_id="search-heading"),
    ]
    if not request:
        rows.append(PanelRow("suggestions", RowKind.SECTION, "SUGGESTIONS",
                             description="Local query ideas",))
        rows.extend(PanelRow("suggest:" + query, RowKind.ACTION, query,
                             action=PanelAction("discover-search", query), section_id="suggestions")
                    for query in SUGGESTIONS)
    else:
        rows.append(PanelRow("results", RowKind.SECTION, "RESULTS",
                             description=f"Page {request.page}"))
        if loading:
            rows.append(PanelRow("loading", RowKind.STATUS, "Searching…", section_id="results"))
        if cache_age is not None:
            rows.append(PanelRow("cache", RowKind.STATUS,
                                 f"Cached metadata · {cache_age}s old" +
                                 (" · stale fallback" if error is not None else
                                  " · refreshing" if cache_age > CACHE_TTL and loading else
                                  " · stale" if cache_age > CACHE_TTL else ""),
                                 section_id="results"))
        if error is not None:
            rows.append(PanelRow("error", RowKind.STATUS, STATUS_TEXT.get(error, "Unavailable"),
                                 status_tone="warning" if result else "error",
                                 section_id="results"))
        if result is not None:
            if result.records:
                rows.append(PanelRow("results-table", RowKind.TABLE_HEADER, "SKILLS"))
            for record in result.records:
                metric = (f"{record.popularity.metric}: {record.popularity.value:,}"
                          if record.popularity else "")
                rows.append(PanelRow(record.identity, RowKind.NAVIGATION, record.name,
                                     list_preview(record.repository or "Source not resolved",
                                                  width=28),
                                     list_preview(" · ".join(filter(None, (
                                         record.description, metric, record.provider))), width=64),
                                     action=PanelAction("discover-detail", record.identity),
                                     section_id="results",
                                     search_terms=" ".join((record.repository,
                                                            record.description))))
            if result.status == CatalogStatus.EMPTY:
                rows.append(PanelRow("empty", RowKind.INFO, "No matches", section_id="results"))
        rows.append(PanelRow("retry", RowKind.ACTION,
                             "Retry search" if error is not None else "Refresh results",
                             enabled=not loading,
                             action=PanelAction("discover-retry")))
        if request.page > 1:
            rows.append(PanelRow("previous", RowKind.ACTION, "Previous page", enabled=not loading,
                                 action=PanelAction("discover-page", str(request.page - 1))))
        if result is not None and result.has_next and request.page < MAX_PAGE:
            rows.append(PanelRow("next", RowKind.ACTION, "Next page", enabled=not loading,
                                 action=PanelAction("discover-page", str(request.page + 1))))
    rows.append(back_row("discover-back"))
    return PanelPage("skill-search:" + (request.identity if request else "empty"),
                     ("Settings", "Skills", "Search"), tuple(rows),
                     column_headers=("SKILL", "SOURCE", "DESCRIPTION")
                     if result and result.records else None, table_section_id="results",
                     scroll_wrapped_rows=True)


def detail_page(record: SkillRecord, *, loading: bool = False,
                status: CatalogStatus | None = None, install_pending: bool = False,
                install_busy: bool = False, installed: bool = False,
                install_feedback: str = "", show_source: bool = False) -> PanelPage:
    fields = (
        ("Repository", record.repository or "Not resolved"),
        ("Source URL", record.source_url or "Not resolved"),
        ("Skill path", record.skill_path or "Not resolved"),
        ("Description", record.description or "Not supplied"),
        ("Provider", record.provider),
        ("Exact revision", record.revision or "Not resolved"),
        ("Source commit", record.source_activity or "Not resolved"),
        ("Skill license", record.license or "Unknown"),
        ("License source", record.license_source or "Not resolved"),
        ("Compatibility", record.compatibility or "Unknown"),
        ("First-party status", record.first_party),
        ("Audit status", record.audit),
        ("Content language", record.language or "Unknown"),
        ("Catalog update", record.catalog_updated or "Unknown"),
        ("Metadata fetched", datetime.fromtimestamp(record.fetched_at, UTC).isoformat()
         if record.fetched_at else "Unknown"),
    )
    rows = [
        PanelRow("detail", RowKind.SECTION, "SKILL", description=record.name),
        PanelRow("description", RowKind.INFO, "Description",
                 description=record.description or "Not supplied", section_id="detail"),
        PanelRow("repository", RowKind.INFO, "Repository",
                 description=record.repository or "Not resolved", section_id="detail"),
        PanelRow("license", RowKind.INFO, "Skill license",
                 description=record.license or "Unknown", section_id="detail"),
    ]
    location = github_location(record.source_url)
    resolvable = bool(location and location[1] and location[2])
    rows.append(PanelRow(
        "resolve", RowKind.ACTION, "Resolve original source",
        enabled=resolvable and not loading and not install_pending,
        description="Read SKILL.md at an exact GitHub commit" if resolvable else
        "Catalog does not supply a resolvable skill path", action=PanelAction("discover-resolve"),
    ))
    rows.append(PanelRow(
        "install", RowKind.ACTION, "Installed" if installed else "Install skill",
        enabled=bool(record.canonical_identity) and not loading and not install_busy
        and not installed,
        description="Available in local Skills inventory" if installed else
        "Source path unavailable; use a result with a GitHub folder URL" if not resolvable else
        "Resolve the original source first" if not record.canonical_identity else
        "Download the pinned skill folder after confirmation",
        action=PanelAction("discover-install"),
    ))
    if installed:
        rows.append(PanelRow("open-installed", RowKind.NAVIGATION,
                             "Open installed skill",
                             action=PanelAction("discover-open-installed")))
    if record.popularity:
        rows.append(PanelRow("metric", RowKind.INFO, record.popularity.metric,
                             str(record.popularity.value), section_id="detail"))
    rows.append(PanelRow("source-details", RowKind.ACTION,
                         "Hide source details" if show_source else "Source details",
                         action=PanelAction("discover-source-details")))
    if show_source:
        rows.append(PanelRow("source-heading", RowKind.SECTION, "SOURCE DETAILS"))
        rows.extend(PanelRow("field:" + label, RowKind.INFO, label, description=value,
                             section_id="source-heading") for label, value in fields)
        rows.append(PanelRow("scope", RowKind.INFO, "Compatibility",
                             description="Catalog metadata does not establish support for "
                             "runtime dependencies. Installation does not execute scripts."))
    if loading or status is not None:
        status_label = (
            "Resolving…" if loading else
            "Source resolved · install available" if status == CatalogStatus.OK else
            STATUS_TEXT.get(status or CatalogStatus.UNRESOLVED, "Unavailable")
        )
        rows.append(PanelRow("status", RowKind.STATUS, status_label,
                             status_tone="neutral" if loading else
                             "success" if status == CatalogStatus.OK else "error"))
    if install_pending or install_feedback:
        rows.append(PanelRow(
            "install-status", RowKind.STATUS,
            "Installing…" if install_pending else install_feedback,
            status_tone="neutral" if install_pending else
            "success" if installed else "warning",
        ))
    rows.append(back_row("discover-results"))
    return PanelPage("skill-search-detail:" + record.identity,
                     ("Settings", "Skills", "Search", record.name), tuple(rows),
                     scrollable_body=True)


def install_confirmation_page(record: SkillRecord) -> PanelPage:
    pinned_url = (f"https://github.com/{record.repository}/blob/{record.revision}/"
                  f"{record.skill_path}")
    rows = (
        PanelRow("confirm", RowKind.SECTION, "INSTALL SKILL"),
        PanelRow("name", RowKind.INFO, "Name", description=record.name),
        PanelRow("source", RowKind.INFO, "Pinned source", description=pinned_url),
        PanelRow("license", RowKind.INFO, "Skill license",
                 description=record.license or "Unknown"),
        PanelRow("warning", RowKind.INFO, "Review",
                 description="Remote skill instructions and files are untrusted. Installation "
                 "downloads and indexes them; it does not run scripts or grant permissions."),
        PanelRow("confirm-install", RowKind.ACTION, "Install skill",
                 action=PanelAction("discover-confirm-install")),
        back_row("discover-install-back"),
    )
    return PanelPage("skill-search-install:" + record.identity,
                     ("Settings", "Skills", "Search", record.name, "Install"), rows,
                     scrollable_body=True)


class SkillDiscovery:
    """Own catalog state and explicit install intent; PanelState owns navigation."""
    def __init__(self, jobs: OwnedBackgroundJobs,
                 show: Callable[[PanelPage, str, str], None],
                 edit: Callable[[str], None], parent: Callable[[], None],
                 scope: Callable[[], str],
                 install: Callable[[SkillRecord], bool] | None = None,
                 open_installed: Callable[[str], None] | None = None):
        self.jobs, self.show, self.edit, self.parent, self.scope = jobs, show, edit, parent, scope
        self.install = install
        self.open_installed = open_installed
        self.provider = "skillsmp"
        self.sort = "stars"
        self.request: SearchRequest | None = None
        self.result: SearchResult | None = None
        self.detail: SkillRecord | None = None
        self.pending: tuple[str, str, str, str] | None = None
        self.cache: OrderedDict[str, SearchResult] = OrderedDict()
        self.cache_age: int | None = None
        self.error: CatalogStatus | None = None
        self.detail_status: CatalogStatus | None = None
        self.install_pending = False
        self.install_identity = ""
        self.install_feedback = ""
        self.installed: set[str] = set()
        self.detail_expanded = False

    def show_detail(self, default: str = "") -> None:
        if self.detail is None:
            return
        self.show(detail_page(
            self.detail, status=self.detail_status,
            install_pending=self.install_pending and self.install_identity == self.detail.identity,
            install_busy=self.install_pending,
            installed=self.detail.identity in self.installed,
            install_feedback=self.install_feedback,
            show_source=self.detail_expanded,
        ), DETAIL_KIND, default)

    def cancel(self) -> None:
        for key in ("skill-search", "skill-source"):
            self.jobs.cancel(key)
        self.pending = None

    def open(self, default: str = "") -> None:
        if self.cache_age is not None and self.result is not None:
            self.cache_age = max(0, int(time.time() - self.result.fetched_at))
        self.show(search_page(self.request, self.provider, self.sort, self.result,
                              loading=self.pending is not None,
                              cache_age=self.cache_age, error=self.error), SEARCH_KIND, default)

    def reenter(self) -> None:
        """Reopen a prior query with an honest age and refresh expired metadata."""
        if self.request is None or self.pending is not None:
            self.open()
            return
        cached = self.cache.get(self.request.identity)
        age = time.time() - cached.fetched_at if cached else STALE_TTL + 1
        if not cached or age > CACHE_TTL or age < 0:
            self.search(self.request.query, page=self.request.page, refresh=True)
            return
        self.result, self.cache_age = cached, int(age)
        self.open()

    def search(self, query: str, *, page: int = 1, refresh: bool = False,
               focus: str = "") -> None:
        request = SearchRequest(query, self.provider, self.sort, page)
        changed = self.request != request
        self.cancel()
        self.request, self.result, self.cache_age, self.error = request, None, None, None
        cached = self.cache.get(request.identity)
        age = time.time() - cached.fetched_at if cached else STALE_TTL + 1
        if cached and 0 <= age <= STALE_TTL:
            self.result, self.cache_age = cached, int(age)
        if cached and 0 <= age <= CACHE_TTL and not refresh:
            self.open(focus or (cached.records[0].identity if changed and cached.records else ""))
            return
        identity = self.jobs.submit("skill-search", {"kind": "skill_search",
                                                     "request": asdict(request)}, timeout=15)
        self.pending = ("skill-search", identity, self.scope(), request.identity)
        self.open(focus)

    def answer_query(self, query: str | None) -> None:
        if query is None or not query:
            if query == "":
                self.request, self.result = None, None
                self.cache_age, self.error = None, None
            self.open()
        else:
            self.search(query)

    def action(self, action: PanelAction) -> bool:
        if not action.kind.startswith("discover-"):
            return False
        kind = action.kind
        if kind == "discover-query":
            self.cancel()
            self.edit(self.request.query if self.request else "")
        elif kind == "discover-search":
            self.search(action.target)
        elif kind == "discover-provider":
            self.cancel()
            self.show(source_page(self.provider), "skill discovery source", self.provider)
        elif kind == "discover-sort" and self.provider == "skillsmp":
            self.cancel()
            self.show(sort_page(self.sort), "skill discovery sort", self.sort)
        elif kind in {"discover-provider-apply", "discover-sort-apply"}:
            if kind == "discover-provider-apply":
                if action.target not in {"skillsmp", "skills.sh"}:
                    return True
                changed = action.target != self.provider
                self.provider = action.target
                if changed:
                    self.sort = "relevance" if self.provider == "skills.sh" else "stars"
                focus = "provider"
            else:
                if self.provider != "skillsmp" or action.target not in {"stars", "recent"}:
                    return True
                self.sort = action.target
                focus = "sort"
            if self.request:
                self.search(self.request.query, focus=focus)
            else:
                self.open(focus)
        elif kind in {"discover-provider-back", "discover-sort-back"}:
            self.open("provider" if kind == "discover-provider-back" else "sort")
        elif kind == "discover-retry" and self.request:
            self.search(self.request.query, page=self.request.page, refresh=True)
        elif kind == "discover-page" and self.request:
            self.search(self.request.query, page=int(action.target))
        elif kind == "discover-detail" and self.result:
            record = next((r for r in self.result.records if r.identity == action.target), None)
            if record:
                self.cancel()
                self.detail, self.detail_status = record, None
                self.detail_expanded = False
                self.install_feedback = ""
                self.show_detail("resolve")
        elif kind == "discover-source-details" and self.detail:
            self.detail_expanded = not self.detail_expanded
            self.show_detail("source-details")
        elif kind == "discover-resolve" and self.detail:
            self.cancel()
            identity = self.jobs.submit("skill-source", {
                "kind": "skill_source", "record": self.detail.payload(),
            }, timeout=15)
            self.pending = ("skill-source", identity, self.scope(), self.detail.identity)
            self.show(detail_page(self.detail, loading=True,
                                  install_pending=self.install_pending and
                                  self.install_identity == self.detail.identity,
                                  install_busy=self.install_pending), DETAIL_KIND, "")
        elif kind == "discover-install" and self.detail and self.install is not None:
            if self.detail.canonical_identity and not self.install_pending and (
                self.detail.identity not in self.installed
            ):
                self.show(install_confirmation_page(self.detail), INSTALL_KIND, "back")
        elif kind == "discover-open-installed" and self.detail and self.open_installed:
            if self.detail.identity in self.installed:
                self.open_installed(self.detail.name)
        elif kind == "discover-install-back":
            self.show_detail("install")
        elif kind == "discover-confirm-install" and self.detail and self.install is not None:
            if self.detail.canonical_identity and not self.install_pending and (
                self.detail.identity not in self.installed
            ):
                self.install_pending = self.install(self.detail)
                self.install_identity = self.detail.identity if self.install_pending else ""
                self.install_feedback = (
                    "" if self.install_pending else "Install could not be queued"
                )
                self.show_detail("install")
        elif kind == "discover-results":
            self.cancel()
            self.open()
        elif kind == "discover-back":
            self.cancel()
            self.parent()
        return True

    def accept(self, key: str, identity: str, data: object, error: str, kind: str | None) -> None:
        expected = self.pending
        logical = self.request.identity if key == "skill-search" and self.request else (
            self.detail.identity if self.detail else "")
        if expected != (key, identity, self.scope(), logical) or kind != (
            SEARCH_KIND if key == "skill-search" else DETAIL_KIND
        ):
            return
        self.pending = None
        try:
            if error or not isinstance(data, dict):
                raise ValueError
            if key == "skill-search":
                result = SearchResult.from_payload(data)
                if self.request is None or any(
                    r.provider != self.request.provider for r in result.records
                ):
                    raise ValueError
                if result.status in {CatalogStatus.OK, CatalogStatus.EMPTY}:
                    self.result, self.error, self.cache_age = result, None, None
                    self.cache[logical] = result
                    self.cache.move_to_end(logical)
                    while len(self.cache) > 64:
                        self.cache.popitem(last=False)
                    self.open()
                else:
                    self.error = result.status
                    self.open()
            else:
                record = SkillRecord.from_payload(data["record"])
                if self.detail is None or record.identity != self.detail.identity:
                    raise ValueError
                self.detail, self.detail_status = record, CatalogStatus(data["status"])
                if self.detail_status == CatalogStatus.OK and self.result and self.request:
                    self.result = replace(self.result, records=tuple(
                        record if r.identity == record.identity else r for r in self.result.records
                    ))
                    self.cache[self.request.identity] = self.result
                self.show_detail("install" if self.detail_status == CatalogStatus.OK else "")
        except (ValueError, TypeError, KeyError):
            status = CatalogStatus.TIMEOUT if "timed out" in error else (
                CatalogStatus.UNAVAILABLE if error else CatalogStatus.MALFORMED
            )
            if key == "skill-search":
                self.error = status
                self.open()
            elif self.detail:
                self.detail_status = status
                self.show_detail()

    def install_done(self, identity: str, success: bool, message: str,
                     kind: str | None) -> None:
        self.install_pending = False
        self.install_identity = ""
        if success:
            self.installed.add(identity)
        if self.detail is not None and self.detail.identity == identity:
            self.install_feedback = message
            if kind in {DETAIL_KIND, INSTALL_KIND}:
                self.show_detail("install")
