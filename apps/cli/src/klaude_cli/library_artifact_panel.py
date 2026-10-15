"""Documents/Media panels using Library's owned reads and ordered action lane."""

from __future__ import annotations

import shlex
import uuid
from pathlib import Path
from typing import Any

from klaude_core.library_artifacts import manual_tags

from .session_actions import LibraryArtifactChange
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind


def action(identity: str, label: str, target: str = "", **kwargs: Any) -> PanelRow:
    return PanelRow(
        identity,
        RowKind.ACTION,
        label,
        action=PanelAction("library-artifact-" + identity, target),
        **kwargs,
    )


class ArtifactPanel:
    def __init__(self, library: Any):
        self.library = library
        self.list_view = "documents"
        self.kind = "document"
        self.filters = {
            "documents": "",
            "media": "",
            "research-reports": "",
            "artifact-archive": "",
        }
        self.formats = dict.fromkeys(self.filters, "")
        self.sorts = dict.fromkeys(self.filters, "newest")
        self.offsets = dict.fromkeys(self.filters, 0)
        self.detail: dict[str, Any] = {}
        self.changes: dict[str, LibraryArtifactChange] = {}

    @property
    def host(self) -> Any:
        return self.library.host

    @property
    def active(self) -> bool:
        return self.library.view in {
            "documents",
            "media",
            "research-reports",
        } or self.library.view.startswith("artifact-")

    @property
    def archived(self) -> bool:
        return self.list_view == "artifact-archive"

    def open(self, view: str) -> None:
        self.library.leave()
        self.list_view = view
        self.kind = {"documents": "document", "media": "media", "research-reports": "research"}.get(
            view, "all"
        )
        self.library.feedback, self.library.error = None, ""
        self.library.show(view)
        self.library.load()

    def key(self) -> tuple[str, str, int]:
        view = self.library.view
        query = "\0".join(
            (
                self.kind,
                self.filters[self.list_view],
                self.sorts[self.list_view],
                self.formats[self.list_view],
            )
        )
        if view in {"artifact-detail", "artifact-preview", "artifact-confirm"}:
            query += "\0" + str(self.detail.get("id", ""))
        return view, query, self.offsets[self.list_view]

    def request(self) -> dict[str, Any]:
        return {
            "operation": {
                "artifact-preview": "artifact-preview",
                "artifact-detail": "artifact-detail",
            }.get(self.library.view, "artifact-list"),
            "artifact_kind": self.kind,
            "archived": self.archived,
            "query": self.filters[self.list_view],
            "offset": self.offsets[self.list_view],
            "sort": self.sorts[self.list_view],
            "format": self.formats[self.list_view],
            "target": self.detail.get("id", ""),
        }

    def page(self) -> PanelPage:
        view = self.library.view
        crumbs: tuple[str, ...] = (
            ("Library", "Archive", "Artifacts")
            if self.archived
            else ("Library", "Research", "Saved reports")
            if self.list_view == "research-reports"
            else ("Library", self.list_view.title())
        )
        rows: list[PanelRow] = []
        listing = view in {"documents", "media", "research-reports", "artifact-archive"}
        if not listing and not self.detail.get("kind"):
            return PanelPage(
                "library:artifact-loading:" + str(self.detail.get("id", "")),
                crumbs + ("Detail",),
                (
                    PanelRow("loading", RowKind.INFO, "Loading report metadata…"),
                    action("reload", "Reload metadata"),
                    action("back", "Back", self.list_view, control=RowControl.BACK),
                ),
            )
        if listing:
            if self.kind == "media" and not self.archived:
                rows.append(action("generate", "Generate image",
                                   description="Explicit local service · review first"))
                rows.append(action("generation-history", "Image jobs",
                                   description="Saved receipts · status, recovery and cleanup"))
                if self.library.generation.busy:
                    rows.append(action("generation-task", "Current image generation"))
            if not self.archived and self.kind != "research":
                rows.append(
                    action(
                        "import",
                        "Import " + ("image" if self.kind == "media" else "document"),
                        description="Managed copy · original retained · no indexing or model calls",
                        enabled=not bool(self.changes),
                    )
                )
            rows += [
                action(
                    "search",
                    "Search metadata",
                    description=self.filters[self.list_view]
                    or "Names, tags, file types and source paths",
                ),
                action(
                    "filter",
                    "Filter",
                    value=self.kind.title()
                    if self.archived
                    else self.formats[self.list_view] or "All types",
                ),
                action("sort", "Sort", value=self.sorts[self.list_view].title()),
                action("reload", "Reload"),
            ]
            if self.filters[self.list_view]:
                rows.append(action("clear", "Clear search"))
            rows += [
                PanelRow("inventory", RowKind.SECTION, "ARTIFACTS"),
                PanelRow(
                    "columns",
                    RowKind.TABLE_HEADER,
                    "ARTIFACT / SIZE / TYPE, DATE, TAGS",
                    section_id="inventory",
                ),
            ]
            data = self.library.snapshot()
            for item in data["items"]:
                tags = ", ".join(item["tags"])
                if item.get("ai_tags"):
                    tags += (" · " if tags else "") + "AI: " + ", ".join(item["ai_tags"])
                tags = tags or "No tags"
                rows.append(
                    PanelRow(
                        "artifact:" + item["id"],
                        RowKind.NAVIGATION,
                        item["name"],
                        f"{item['size']:,} B",
                        description=f"{item['mime']} · {item['date']} · {tags}",
                        section_id="inventory",
                        search_terms=item["origin"],
                        action=PanelAction("library-artifact-record", item["id"]),
                    )
                )
            if not data["items"]:
                rows.append(
                    PanelRow(
                        "empty",
                        RowKind.INFO,
                        "Loading…"
                        if self.library.pending
                        else "Unavailable · Reload to retry"
                        if self.library.error
                        else "No matching artifacts"
                        if self.filters[self.list_view]
                        else "No artifacts on this page",
                    )
                )
            start = self.offsets[self.list_view]
            if start:
                rows.append(action("previous", "Previous 100 artifacts"))
            if data["more"]:
                rows.append(action("next", "Next 100 artifacts"))
            rows.append(
                action(
                    "back",
                    "Back",
                    "archive"
                    if self.archived
                    else "research"
                    if self.kind == "research"
                    else "home",
                    control=RowControl.BACK,
                )
            )
        else:
            item = self.detail
            crumbs += (
                "Preview"
                if view == "artifact-preview"
                else "Confirm deletion"
                if view == "artifact-confirm"
                else "Detail",
            )
            rows.append(PanelRow("name", RowKind.INFO, item.get("name", "Artifact")))
            if view == "artifact-preview":
                rows += [
                    action("reload", "Reload preview"),
                    action("export", "Export copy…", enabled=not self.changes),
                ]
                data = self.library.snapshot()
                lines = data.get("lines", [])
                rows += [
                    PanelRow(f"line:{index}", RowKind.INFO, line or " ")
                    for index, line in enumerate(lines)
                ]
                if data.get("truncated"):
                    rows.append(
                        PanelRow(
                            "bounded",
                            RowKind.INFO,
                            "Preview limited to 100 lines / 16 KiB / 500 characters per line · "
                            "export the full file",
                        )
                    )
                if not lines:
                    dimensions = (
                        f"{item['width']} × {item['height']}"
                        if item.get("width") and item.get("height")
                        else "Dimensions unknown"
                    )
                    rows.append(
                        PanelRow(
                            "fallback",
                            RowKind.INFO,
                            "Loading…"
                            if self.library.pending
                            else "Preview unavailable · Reload to retry"
                            if self.library.error
                            else data.get("fallback", "No text content"),
                            description=dimensions + " · original bytes retained",
                        )
                    )
                rows += [
                    action("back", "Back", "artifact-detail", control=RowControl.BACK),
                ]
            elif view == "artifact-confirm":
                rows += [
                    PanelRow(
                        "effect",
                        RowKind.INFO,
                        "Permanently delete this archived artifact?",
                        description="Removes the managed copy and metadata. Original files, "
                        "exported or opened copies and learned knowledge are retained.",
                    ),
                    action("delete", "Permanently delete artifact", enabled=not self.changes),
                    action("back", "Back", "artifact-detail", control=RowControl.BACK),
                ]
            else:
                summary = f"{item['mime']} · {item['size']:,} B"
                if item.get("width") and item.get("height"):
                    summary += f" · {item['width']} × {item['height']}"
                rows.append(PanelRow("type", RowKind.INFO, summary))
                rows += [
                    action(
                        "preview",
                        "Preview",
                        description="Bounded text or image metadata · no model calls",
                    ),
                    action("tags", "Edit tags…", enabled=not self.changes),
                    action(
                        "open",
                        "Open externally",
                        enabled=not self.changes,
                        description="Desktop opener · retained private copy · "
                        "Export for headless use",
                    ),
                    action(
                        "export",
                        "Export copy…",
                        enabled=not self.changes,
                        description="New file inside the current workspace · never overwrite",
                    ),
                ]
                if provenance := item.get("generation"):
                    rows += [
                        PanelRow("generation-model", RowKind.INFO, "Generated by", item["model"],
                                 description=provenance["settings"]["endpoint"]),
                        PanelRow("generation-prompt", RowKind.INFO, "Prompt",
                                 description=provenance["prompt"]),
                        PanelRow("generation-seed", RowKind.INFO, "Seed",
                                 str(provenance["seed"])),
                    ]
                if item["kind"] == "media" and not item["archived"]:
                    rows.append(action("analyze", "Analyze image", enabled=not self.changes,
                                       description="Explicit Vision request · review first"))
                    rows.append(action("suggest-tags", "Suggest AI tags", enabled=not self.changes,
                                       description="Review Vision request · select tags "
                                       "before saving"))
                if item.get("ai_tags"):
                    rows.append(action("clear-ai-tags", "Clear AI tags", enabled=not self.changes,
                                       description="Manual tags are retained · no model calls"))
                if item["kind"] == "document":
                    rows.append(
                        PanelRow(
                            "learn",
                            RowKind.INFO,
                            "Learn explicitly",
                            description="Export, then: klaude learn PATH -l "
                            + shlex.quote("your-library"),
                        )
                    )
                if item["archived"]:
                    rows += [
                        action("restore", "Restore artifact", enabled=not self.changes),
                        action("confirm", "Delete permanently…", enabled=not self.changes),
                    ]
                else:
                    rows.append(
                        action(
                            "archive",
                            "Archive artifact",
                            enabled=not self.changes,
                            description="Content retained · available in Archive → Artifacts",
                        )
                    )
                if item.get("kind") == "research":
                    rows += [
                        action(
                            "discuss",
                            "Discuss report…",
                            description="Read-only chat with a stored report excerpt",
                        ),
                        action(
                            "learn-report",
                            "Learn report…",
                            description="Explicit indexing; stored report remains independent",
                        ),
                    ]
                rows += [
                    action("reload", "Reload metadata"),
                    PanelRow("metadata", RowKind.SECTION, "METADATA"),
                ]
                for key, label in (
                    ("id", "ID"),
                    ("date", "Imported"),
                    ("origin", "Origin"),
                    ("session", "Session"),
                    ("job", "Job"),
                    ("model", "Model"),
                ):
                    if item.get(key):
                        rows.append(PanelRow(key, RowKind.INFO, label, str(item[key])))
                rows.append(
                    PanelRow(
                        "manual-tags",
                        RowKind.INFO,
                        "Manual tags",
                        ", ".join(item["tags"]) or "None",
                    )
                )
                if item["kind"] == "media":
                    rows.append(PanelRow("ai-tags", RowKind.INFO, "AI tags",
                                         ", ".join(item.get("ai_tags", [])) or "None"))
                if not item.get("model"):
                    rows.append(PanelRow("unknown-model", RowKind.INFO, "Model provenance unknown"))
                rows.append(action("back", "Back", self.list_view, control=RowControl.BACK))
        return PanelPage(
            "library:"
            + ":".join((view, self.list_view, "" if listing else str(self.detail.get("id", "")))),
            crumbs,
            tuple(rows),
            subtitle="Stored ≠ indexed · Imported ≠ learned · Archived ≠ deleted",
            column_headers=("ARTIFACT", "SIZE", "TYPE / DATE / TAGS") if listing else None,
            table_section_id="inventory" if listing else "",
            scrollable_body=view in {"artifact-preview", "artifact-detail"},
            scroll_wrapped_rows=view == "artifact-detail" and bool(self.detail.get("generation")),
        )

    def handle(self, command: PanelAction) -> None:
        kind = command.kind.removeprefix("library-artifact-")
        library = self.library
        if kind in {"discuss", "learn-report"}:
            library.research.report_action(kind, self.detail)
        elif kind == "archive-list":
            self.open("artifact-archive")
        elif kind == "back":
            library.leave()
            library.feedback, library.error = None, ""
            if command.target in {"home", "archive"}:
                library.show(
                    command.target, "artifact-archive" if self.archived else self.list_view
                )
                if command.target == "archive":
                    library.load()
            else:
                library.show(command.target, "artifact:" + str(self.detail.get("id", "")))
                if command.target != "artifact-detail":
                    library.load()
        elif kind == "record":
            self.detail = next(
                (item for item in library.snapshot()["items"] if item["id"] == command.target), {}
            )
            if not self.detail:
                raise ValueError("Artifact no longer available; reload the list")
            library.leave()
            library.feedback = None
            library.show("artifact-detail")
            if self.detail.get("job") and self.detail.get("kind") == "media":
                library.load(force=True)
        elif kind == "generate":
            library.generation.open()
        elif kind == "generation-task":
            library.show("generation-task")
        elif kind == "generation-history":
            library.generation.handle(PanelAction("library-generation-history"))
        elif kind == "analyze":
            library.vision.open(self.detail)
        elif kind == "suggest-tags":
            library.vision.open(self.detail, tagging=True)
        elif kind == "clear-ai-tags":
            self.queue("clear_ai_tags", "")
        elif kind == "preview":
            library.show("artifact-preview")
            library.load(force=True)
        elif kind == "reload":
            library.load(force=True)
        elif kind in {"search", "import", "tags", "export"}:
            if self.changes and kind != "search":
                raise ValueError("Wait for the pending artifact change")
            library.leave()
            hint = {
                "search": "Names, tags, type or source · Enter searches",
                "import": "File path · managed copy · at most 32 MiB",
                "tags": "Comma-separated tags · blank removes all tags",
                "export": "New file path inside current workspace · never overwrite",
            }[kind]
            self.host._begin_settings_input(
                {
                    "search": "Search artifact metadata",
                    "import": "Import image" if self.kind == "media" else "Import document",
                    "tags": "Edit manual tags",
                    "export": "Export artifact copy",
                }[kind],
                hint + " · Escape returns",
                ("library", "artifact-" + kind),
            )
            if kind == "tags":
                self.host._set_input(", ".join(self.detail["tags"]))
        elif kind in {"clear", "next", "previous", "filter", "sort"}:
            choices: tuple[str, ...]
            library.leave()
            if kind in {"next", "previous"}:
                self.offsets[self.list_view] = max(
                    0, self.offsets[self.list_view] + (100 if kind == "next" else -100)
                )
            else:
                self.offsets[self.list_view] = 0
                if kind == "clear":
                    self.filters[self.list_view] = ""
                elif kind == "sort":
                    choices = ("newest", "oldest", "name")
                    self.sorts[self.list_view] = choices[
                        (choices.index(self.sorts[self.list_view]) + 1) % len(choices)
                    ]
                elif self.archived:
                    choices = ("all", "document", "media", "research")
                    self.kind = choices[(choices.index(self.kind) + 1) % len(choices)]
                else:
                    choices = (
                        ("", "image/png", "image/jpeg", "image/gif", "image/webp")
                        if self.kind == "media"
                        else ("", "text/", "application/pdf")
                    )
                    self.formats[self.list_view] = choices[
                        (choices.index(self.formats[self.list_view]) + 1) % len(choices)
                    ]
            library.show()
            library.load(force=True)
        elif kind == "confirm":
            library.show("artifact-confirm", "back")
        elif kind in {"archive", "restore", "delete", "open"}:
            self.queue(kind)

    def answer(self, kind: str, value: str | None) -> None:
        if value is None:
            self.host._set_input("")
            self.library.show()
            return
        if kind == "tags":
            manual_tags(value)
        elif not 1 <= len(value.strip()) <= (200 if kind == "search" else 4096):
            raise ValueError(
                "Enter 1–200 characters"
                if kind == "search"
                else "Enter a file path of 1–4096 characters"
            )
        if kind == "search":
            self.filters[self.list_view], self.offsets[self.list_view] = value.strip(), 0
            if self.host._panel is not None:
                self.host._panel.filter("")
                self.host._apply_picker_state()
            self.host._set_input("")
            self.library.show()
            self.library.load(force=True)
        else:
            self.queue(kind, value if kind == "tags" else value.strip())
            self.host._set_input("")

    def queue(self, operation: str, value: str = "") -> None:
        if self.changes:
            raise ValueError("Wait for the pending artifact change")
        change = LibraryArtifactChange(
            self.host.session_id,
            uuid.uuid4().hex,
            str(Path(self.library.scope).parent / "library"),
            operation,
            self.detail.get("id", ""),
            self.detail.get("revision", 0),
            value,
            self.kind,
            str(getattr(self.host.agent, "workdir", Path.cwd())),
        )
        if not self.host._session_actions.submit(change):
            raise ValueError("Artifact change was not queued; reload before retrying")
        self.changes[change.identity] = change
        self.library.feedback = (
            "Importing copy…" if operation == "import" else "Saving artifact change…",
            "neutral",
        )
        self.library.show()

    def saved(self, change: LibraryArtifactChange, result: object, error: str) -> None:
        if self.changes.pop(change.identity, None) != change:
            return
        library = self.library
        if not error:
            library.cache.clear()
        if (
            change.session_id != self.host.session_id
            or not library.visible
            or change.root != str(Path(library.scope).parent / "library")
        ):
            if error:
                self.host._append("\n[warning] " + error + ".\n")
            return
        if error:
            library.feedback = (
                error,
                "warning" if "unconfirmed" in error or change.operation == "open" else "error",
            )
        else:
            if self.active and change.target == self.detail.get("id"):
                if change.operation in {"tags", "clear_ai_tags"} and isinstance(result, dict):
                    self.detail = result
                if change.operation in {"archive", "restore", "delete"}:
                    library.show(self.list_view)
            if library.view in {"documents", "media", "artifact-archive"}:
                library.load(force=True)
            message = {
                "import": "Imported managed copy · original retained · not indexed",
                "tags": "Tags saved",
                "archive": "Artifact archived · content retained",
                "restore": "Artifact restored",
                "delete": "Artifact deleted",
                "export": "Exported copy",
                "open": "Desktop open requested",
            }[change.operation]
            if change.operation == "export" and isinstance(result, dict):
                message += " · " + str(result.get("path", ""))
            library.feedback = (message, "success")
        library.show()
