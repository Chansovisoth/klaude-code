"""Library navigation over distinct durable stores, outside Settings."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from .library_artifact_panel import ArtifactPanel
from .library_inventory import PAGE_SIZE, public_text
from .library_knowledge_panel import KnowledgePanel
from .research_panel import ResearchPanel
from .session_actions import LibrarySessionChange
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

VIEWS = ("Sessions", "Knowledge", "Documents", "Research", "Media", "Archive")


def action_row(identity: str, label: str, target: str = "", **kwargs: Any) -> PanelRow:
    return PanelRow(
        identity, RowKind.ACTION, label, action=PanelAction("library-" + identity, target), **kwargs
    )


def back(view: str) -> PanelRow:
    return action_row("back", "Back", view, control=RowControl.BACK)


class LibraryWorkspace:
    def __init__(self, host: Any):
        self.host = host
        self.view = "home"
        self.parent = "sessions"
        self.target = ""
        self.query = {"sessions": "", "archive": ""}
        self.offset = {"sessions": 0, "archive": 0}
        self.cache: dict[tuple[str, str, int], tuple[dict[str, Any], float]] = {}
        self.pending: tuple[str, str, tuple[str, str, int]] | None = None
        self.changes: dict[str, LibrarySessionChange] = {}
        self.detail: dict[str, Any] = {}
        self.feedback: tuple[str, str] | None = None
        self.error = ""
        self.scope: str = ""
        self.artifacts = ArtifactPanel(self)
        self.knowledge = KnowledgePanel(self)
        self.research = ResearchPanel(self)

    @property
    def visible(self) -> bool:
        return str(self.host._choice_kind).startswith("library ")

    def open(self, view: str = "home") -> None:
        if view not in {"home", *(item.lower() for item in VIEWS)}:
            raise ValueError("Use /library [sessions|knowledge|documents|research|media|archive]")
        scope = str(getattr(self.host.memory, "sessions_db", ""))
        if self.scope != scope:
            self.leave()
            self.cache.clear()
            self.scope = scope
        self.feedback, self.error = None, ""
        if view == "research":
            self.research.open()
            return
        if view in {"documents", "media"}:
            self.artifacts.open(view)
            return
        self.show(view)
        if view in {"sessions", "archive", "knowledge"}:
            self.load()

    def key(self) -> tuple[str, str, int]:
        if self.research.active and not self.artifacts.active:
            return self.research.key()
        if self.knowledge.active:
            return self.knowledge.key()
        if self.artifacts.active:
            return self.artifacts.key()
        query = self.query.get(self.view, "")
        if self.view in {"preview", "query"}:
            query = self.target + "\0" + query
        return (self.view, query, self.offset.get(self.view, 0))

    def snapshot(self) -> dict[str, Any]:
        return self.cache.get(self.key(), ({"items": [], "more": False}, 0))[0]

    def show(self, view: str | None = None, focus: str = "") -> None:
        if view is not None:
            self.view = view
        page = self.page()
        self.host._open_panel(page, "library " + self.view, focus)
        if focus:
            self.host._panel.picker.focus(focus)
            self.host._apply_picker_state()
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)
        elif self.pending:
            self.host._set_panel_feedback("Loading Library…", "neutral")
        elif self.error:
            self.host._set_panel_feedback("Library unavailable; Reload to retry", "error")
        else:
            self.host._set_panel_feedback("")

    def load(self, *, force: bool = False) -> None:
        key = self.key()
        cached = self.cache.get(key)
        if not force and cached and time.monotonic() - cached[1] < 30:
            return
        self.feedback, self.error = None, ""
        database = self.scope
        if not database:
            self.error = "unavailable"
            self.show()
            return
        request = {
            "kind": "library",
            "operation": self.view,
            "database": database,
            "knowledge_root": str(Path(database).parent / "knowledge.lance"),
            "query": self.query.get(self.view, ""),
            "offset": key[2],
            "target": self.target,
        }
        if self.artifacts.active:
            request.update(self.artifacts.request())
        if self.knowledge.active:
            request.update(self.knowledge.request())
        if self.research.active and not self.artifacts.active:
            request.update(self.research.request())
        identity = self.host._background_jobs.submit(
            "library", request,
            timeout=8,
        )
        self.pending = (identity, self.host.session_id, key)
        self.show()

    def leave(self) -> None:
        self.host._background_jobs.cancel("library")
        self.pending = None

    def accept(self, identity: str, result: object, error: str) -> None:
        expected = self.pending
        if expected is None or expected[:2] != (identity, self.host.session_id):
            return
        self.pending = None
        if not self.visible or expected[2] != self.key():
            return
        if error or not isinstance(result, dict):
            self.error = "unavailable"
        else:
            self.error = ""
            if self.research.active and not self.artifacts.active:
                self.research.snapshot(result)
            if self.view == "artifact-detail" and isinstance(result.get("item"), dict):
                self.artifacts.detail = result["item"]
            self.cache[expected[2]] = (result, time.monotonic())
            if len(self.cache) > 16:
                del self.cache[min(self.cache, key=lambda item: self.cache[item][1])]
        self.show()

    def page(self) -> PanelPage:
        if self.research.active and not self.artifacts.active:
            return self.research.page()
        if self.knowledge.active:
            return self.knowledge.page()
        if self.artifacts.active:
            return self.artifacts.page()
        crumbs: tuple[str, ...] = ("Library",)
        rows: list[PanelRow] = []
        if self.view == "home":
            descriptions = (
                "Browse, search, resume and archive conversations",
                "Existing named knowledge libraries and indexed text",
                "Stored documents, import, tags and export",
                "Bounded research jobs and sourced reports",
                "Images and screenshots, metadata, tags and export",
                "Archived conversations and artifacts · content retained",
            )
            rows = [
                PanelRow(
                    name.lower(),
                    RowKind.NAVIGATION,
                    name,
                    description=description,
                    action=PanelAction("library-view", name.lower()),
                )
                for name, description in zip(VIEWS, descriptions, strict=True)
            ]
            rows.append(action_row("close", "Close", control=RowControl.CLOSE))
        elif self.view in {"sessions", "archive", "knowledge"}:
            crumbs += (self.view.title(),)
            rows = [action_row("reload", "Reload", description="Refresh this store's inventory")]
            if self.view == "knowledge":
                rows = [PanelRow("learn-source", RowKind.ACTION, "Learn source…",
                                 action=PanelAction("library-knowledge-learn")),
                        PanelRow("managed-sources", RowKind.NAVIGATION, "Managed sources",
                                 action=PanelAction("library-knowledge-sources")), *rows]
                if self.knowledge.busy:
                    rows.insert(0, PanelRow(
                        "knowledge-task", RowKind.NAVIGATION, "Current Knowledge task",
                        action=PanelAction("library-knowledge-task"),
                    ))
            if self.view == "archive":
                rows.append(PanelRow(
                    "artifact-archive", RowKind.NAVIGATION, "Documents and Media",
                    description="Browse, restore or delete archived artifacts",
                    action=PanelAction("library-artifact-archive-list"),
                ))
            if self.view != "knowledge":
                rows.append(
                    action_row(
                        "search",
                        "Search all sessions",
                        description=self.query[self.view]
                        or "Search names and public conversation text",
                    )
                )
                if self.query[self.view]:
                    rows.append(action_row("clear-search", "Clear session search"))
            data = self.snapshot()
            cached = self.cache.get(self.key())
            updated = ""
            if cached:
                updated = "Snapshot " + time.strftime(
                    "%H:%M:%S", time.localtime(time.time() - (time.monotonic() - cached[1]))
                )
            rows.append(
                PanelRow("inventory", RowKind.SECTION, self.view.upper(), description=updated)
            )
            rows.append(
                PanelRow(
                    "columns",
                    RowKind.TABLE_HEADER,
                    "LIBRARY / INDEX" if self.view == "knowledge" else "SESSION / TURNS / UPDATED",
                    section_id="inventory",
                )
            )
            for item in data["items"]:
                identity = item["id"]
                if self.view == "knowledge":
                    value = (
                        f"{item['sources']} source{'s' if item['sources'] != 1 else ''} · "
                        f"{item['chunks']} chunk{'s' if item['chunks'] != 1 else ''}"
                        if item["sources"] is not None
                        else "Metadata unavailable"
                    )
                    label, description, badge = public_text(identity, 160), "", ""
                else:
                    value = str(item["turns"]) + (" turn" if item["turns"] == 1 else " turns")
                    label, description = (
                        item["title"],
                        item["date"] + " · " + public_text(identity, 80),
                    )
                    badge = (
                        "ACTIVE"
                        if item["active"]
                        else ("CURRENT" if identity == self.host.session_id else "")
                    )
                rows.append(
                    PanelRow(
                        "record:" + identity,
                        RowKind.NAVIGATION,
                        label,
                        value,
                        description=description,
                        section_id="inventory",
                        label_badge=badge,
                        search_terms=public_text(identity),
                        action=PanelAction("library-record", identity),
                    )
                )
            if not data["items"]:
                message = (
                    "Loading…"
                    if self.pending
                    else "Unavailable · Reload to retry"
                    if self.error
                    else "This page is empty · Previous returns to earlier records"
                    if self.offset.get(self.view, 0)
                    else "No matching sessions"
                    if self.query.get(self.view)
                    else "No "
                    + (
                        "archived sessions"
                        if self.view == "archive"
                        else "knowledge libraries"
                        if self.view == "knowledge"
                        else "saved sessions"
                    )
                    + " yet"
                )
                rows.append(PanelRow("empty", RowKind.INFO, message))
            if self.view != "knowledge":
                start = self.offset[self.view]
                rows.append(
                    PanelRow(
                        "range",
                        RowKind.INFO,
                        f"Showing {start + 1}–{start + len(data['items'])} · newest first"
                        if data["items"]
                        else "No records on this page",
                    )
                )
                if start:
                    rows.append(action_row("previous", "Previous 100 sessions"))
                if data["more"]:
                    rows.append(action_row("next", "Next 100 sessions"))
            elif data["more"]:
                rows.append(
                    PanelRow(
                        "bounded",
                        RowKind.INFO,
                        "Showing the first 1000 libraries · klaude libraries lists all",
                    )
                )
            rows.append(back("home"))
        elif self.view in {"detail", "confirm"}:
            crumbs += (
                self.parent.title(),
                "Confirm deletion" if self.view == "confirm" else "Detail",
            )
            title = self.detail.get("title", self.target)
            rows = [
                PanelRow("title", RowKind.INFO, public_text(title, 160)),
                PanelRow("identity", RowKind.INFO, "ID", public_text(self.target, 500)),
            ]
            if self.parent == "knowledge":
                rows += [
                    action_row(
                        "query",
                        "Search indexed text",
                        description="Local keyword search · no model or embedding calls",
                    ),
                    PanelRow("learn", RowKind.ACTION, "Learn source…",
                             description="Add one text file or public page to this library",
                             action=PanelAction("library-knowledge-learn")),
                    PanelRow("hybrid", RowKind.ACTION, "Hybrid query…",
                             description="Uses the configured embedding model · no chat generation",
                             action=PanelAction("library-knowledge-hybrid")),
                    PanelRow("refresh", RowKind.NAVIGATION, "Managed sources",
                             description="Review and refresh this library's installed docs/crawls",
                             action=PanelAction("library-knowledge-sources")),
                ]
            elif self.view == "confirm":
                rows.append(
                    PanelRow(
                        "effect",
                        RowKind.INFO,
                        "Permanently delete this archived conversation?",
                        description="Removes its turns, events, name and session state. "
                        "Saved memories and learned knowledge are retained.",
                    )
                )
                rows.append(
                    action_row(
                        "delete", "Permanently delete session", enabled=not bool(self.changes)
                    )
                )
            else:
                rows.append(PanelRow("date", RowKind.INFO, "Updated", self.detail["date"]))
                rows.append(
                    action_row("preview", "View recent turns", description="Last 8 public turns")
                )
                current = self.target == self.host.session_id
                active = self.detail.get("active", False)
                if self.parent == "archive":
                    rows.append(
                        action_row("restore", "Restore session", enabled=not bool(self.changes))
                    )
                    rows.append(
                        action_row(
                            "confirm",
                            "Delete permanently…",
                            enabled=not current and not active and not self.changes,
                        )
                    )
                else:
                    rows.append(action_row("resume", "Resume session", enabled=not current))
                    rows.append(
                        action_row(
                            "archive",
                            "Archive session",
                            enabled=not current and not active and not self.changes,
                            description="Content retained · available in Archive",
                        )
                    )
                    if current or active:
                        rows.append(
                            PanelRow(
                                "protected",
                                RowKind.INFO,
                                "Open another session before archiving this one"
                                if current
                                else "Active worker · archive after it finishes",
                            )
                        )
            rows.append(back("detail" if self.view == "confirm" else self.parent))
        elif self.view in {"preview", "query"}:
            crumbs += (
                self.parent.title(),
                "Recent turns" if self.view == "preview" else "Indexed text",
            )
            data = self.snapshot()
            if self.view == "preview":
                rows = [
                    PanelRow(
                        f"turn:{index}",
                        RowKind.INFO,
                        item["role"].title(),
                        description=item["text"],
                    )
                    for index, item in enumerate(data.get("turns", []))
                ]
            else:
                rows = [
                    PanelRow(f"hit:{index}", RowKind.INFO, item["source"], description=item["text"])
                    for index, item in enumerate(data.get("hits", []))
                ]
            if not rows:
                rows.append(
                    PanelRow(
                        "empty",
                        RowKind.INFO,
                        "Loading…"
                        if self.pending
                        else "Unavailable"
                        if self.error
                        else "No matching indexed text",
                    )
                )
            rows += [action_row("reload", "Reload"), back("detail")]
        else:
            crumbs += (self.view.title(),)
            rows = [
                PanelRow(
                    "pending",
                    RowKind.INFO,
                    "Not implemented yet",
                    description="Research reports are not available yet"
                    if self.view == "research"
                    else "Storage and import are not available yet",
                ),
                back("home"),
            ]
        cached = self.cache.get(self.key())
        subtitle = (
            f"Snapshot {max(0, int(time.monotonic() - cached[1]))}s old"
            if cached
            else "Stored ≠ indexed · Imported ≠ learned · Archived ≠ deleted"
        )
        # Detail page IDs include the store and exact record; state cannot leak
        # from another session/library with a similar display title.
        identity = self.view + (
            ":" + self.parent + ":" + self.target
            if self.view in {"detail", "confirm", "preview", "query"}
            else ""
        )
        return PanelPage(
            "library:" + identity,
            crumbs,
            tuple(rows),
            subtitle=subtitle,
            column_headers=("LIBRARY", "INDEX", "")
            if self.view == "knowledge"
            else ("SESSION", "TURNS", "UPDATED / ID")
            if self.view in {"sessions", "archive"}
            else None,
            table_section_id="inventory"
            if self.view in {"sessions", "archive", "knowledge"}
            else "",
            scrollable_body=self.view in {"preview", "query"},
        )

    def action(self, action: PanelAction) -> None:
        if action.kind.startswith("library-research-"):
            self.research.handle(action)
            return
        if action.kind.startswith("library-knowledge-"):
            self.knowledge.handle(action)
            return
        if action.kind.startswith("library-artifact-"):
            self.artifacts.handle(action)
            return
        kind = action.kind.removeprefix("library-")
        if kind == "view":
            self.leave()
            self.open(action.target)
        elif kind == "close":
            self.leave()
            self.host._cancel_choice()
        elif kind == "back":
            self.leave()
            previous = self.view
            self.feedback, self.error = None, ""
            focus = (
                "record:" + self.target
                if action.target == self.parent
                else previous
                if action.target == "home"
                else ""
            )
            self.show(action.target, focus)
            if action.target in {"sessions", "archive", "knowledge"}:
                self.load()
        elif kind == "reload":
            self.load(force=True)
        elif kind in {"search", "query"}:
            self.leave()
            self.host._begin_settings_input(
                "Search sessions" if kind == "search" else "Search indexed text",
                "Enter words · Enter searches · Escape returns",
                ("library", kind),
            )
        elif kind in {"clear-search", "next", "previous"}:
            self.leave()
            self.offset[self.view] = (
                max(0, self.offset[self.view] + (PAGE_SIZE if kind == "next" else -PAGE_SIZE))
                if kind != "clear-search"
                else 0
            )
            if kind == "clear-search":
                self.query[self.view] = ""
            self.show()
            self.load(force=True)
        elif kind == "record":
            self.detail = next(
                (item for item in self.snapshot()["items"] if item["id"] == action.target), {}
            )
            if not self.detail:
                raise ValueError("Record no longer available; reload the list")
            self.leave()
            self.parent, self.target = self.view, action.target
            self.feedback = None
            self.show("detail")
        elif kind == "preview":
            self.show("preview")
            self.load(force=True)
        elif kind == "confirm":
            self.show("confirm", "back")
        elif kind == "resume":
            self.leave()
            # Close through the common lifecycle to restore the composer draft.
            self.host._choice_kind, self.host._panel = None, None
            self.host._cancel_choice(resume_queue=False)
            self.host._resume_session(self.target)
        elif kind in {"archive", "restore", "delete"}:
            if self.changes:
                raise ValueError("Wait for the pending session change")
            identity = uuid.uuid4().hex
            change = LibrarySessionChange(self.host.session_id, identity, self.target, kind)
            if not self.host._session_actions.submit(change):
                raise ValueError("Session change was not queued; reload before retrying")
            self.changes[identity] = change
            self.feedback = ("Saving session change…", "neutral")
            self.show()

    def answer(self, kind: str, value: str | None) -> None:
        if kind.startswith("research-"):
            self.research.answer(kind.removeprefix("research-"), value)
            return
        if kind.startswith("knowledge-"):
            self.knowledge.answer(kind.removeprefix("knowledge-"), value)
            return
        if kind.startswith("artifact-"):
            self.artifacts.answer(kind.removeprefix("artifact-"), value)
            return
        if value is not None and not 1 <= len(value) <= 200:
            raise ValueError("Enter 1–200 characters")
        self.host._set_input("")
        if value is None:
            self.show()
            return
        if kind == "search":
            self.query[self.view], self.offset[self.view] = value, 0
            if self.host._panel is not None:
                self.host._panel.filter("")
                self.host._apply_picker_state()
            self.show()
        else:
            self.query["query"] = value
            self.show("query")
        self.load(force=True)

    def saved(self, change: LibrarySessionChange, error: str) -> None:
        if self.changes.pop(change.identity, None) != change:
            return
        self.cache.clear()
        if not self.visible or change.session_id != self.host.session_id:
            if error:
                self.host._append("\n[warning] " + error + ".\n")
            return
        if error:
            self.feedback = (error, "warning" if "unconfirmed" in error else "error")
            self.show()
        else:
            if self.view in {"detail", "confirm"} and self.target == change.target:
                self.show("sessions" if change.operation == "archive" else "archive")
            if self.view in {"sessions", "archive", "knowledge"}:
                self.load(force=True)
            self.feedback = (
                {
                    "archive": "Session archived · content retained",
                    "restore": "Session restored",
                    "delete": "Session deleted",
                }[change.operation],
                "success",
            )
            self.show()
