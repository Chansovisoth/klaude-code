"""Explicit Knowledge actions with private inputs and scoped owned tasks."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .library_inventory import public_text
from .library_knowledge import KnowledgeAction, knowledge_worker_request, library_name
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

TASK_KEY = "library:knowledge"


def row(identity: str, label: str, target: str = "", **kwargs: Any) -> PanelRow:
    return PanelRow(
        identity,
        RowKind.ACTION,
        label,
        action=PanelAction("library-knowledge-" + identity, target),
        **kwargs,
    )


def back(target: str) -> PanelRow:
    return row("back", "Back", target, control=RowControl.BACK)


class KnowledgePanel:
    def __init__(self, library: Any):
        self.library = library
        self.name = ""
        self.parent = "knowledge"
        self.sources_parent = "knowledge"
        self.draft: dict[str, Any] = {}
        self.source: dict[str, Any] = {}
        self.offset = 0
        self.task: tuple[str, str, str, str] | None = None  # job/session/store/operation
        self.task_started = 0.0
        self.stopping = False
        self.result: dict[str, Any] = {}
        self.task_context: dict[str, Any] = {}

    @property
    def host(self) -> Any:
        return self.library.host

    @property
    def active(self) -> bool:
        return self.library.view.startswith("knowledge-")

    @property
    def busy(self) -> bool:
        return self.task is not None

    def key(self) -> tuple[str, str, int]:
        return self.library.view, self.name, self.offset

    def request(self) -> dict[str, Any]:
        return {"operation": "knowledge-sources", "target": self.name, "offset": self.offset}

    def page(self) -> PanelPage:
        view = self.library.view
        crumbs: tuple[str, ...] = ("Library", "Knowledge")
        rows: list[PanelRow] = []
        if view == "knowledge-sources":
            crumbs += ("Managed sources",)
            data = self.library.snapshot()
            rows = [
                row("reload", "Reload sources"),
                PanelRow("inventory", RowKind.SECTION, "MANAGED SOURCES"),
                PanelRow(
                    "columns",
                    RowKind.TABLE_HEADER,
                    "SOURCE / FILES / LIBRARY, TYPE",
                    section_id="inventory",
                ),
            ]
            for item in data["items"]:
                rows.append(
                    PanelRow(
                        "source:" + item["id"],
                        RowKind.NAVIGATION,
                        item["id"],
                        str(item["files"]) + " files",
                        section_id="inventory",
                        description=f"{item['library']} · {item['kind']}",
                        action=PanelAction("library-knowledge-source", item["id"]),
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
                        else "No managed sources for this library"
                        if self.name
                        else "No managed sources installed",
                        description="Use klaude docs add or klaude crawl "
                        "to install a managed source",
                    )
                )
            if self.offset:
                rows.append(row("previous", "Previous 100 sources"))
            if data["more"]:
                rows.append(row("next", "Next 100 sources"))
            if data.get("bounded"):
                rows.append(
                    PanelRow(
                        "bounded", RowKind.INFO, "Inventory limited to 1000 source directories"
                    )
                )
            if data.get("unavailable"):
                rows.append(
                    PanelRow(
                        "unavailable",
                        RowKind.STATUS,
                        f"{data['unavailable']} source records unavailable",
                        status_tone="warning",
                    )
                )
            rows.append(back(self.sources_parent))
        elif view == "knowledge-source-detail":
            crumbs += ("Managed sources", self.source["id"])
            rows = [
                row(
                    "refresh",
                    "Refresh source…",
                    enabled=not self.busy,
                    description="Fetch fresh pages and replace this source's indexed snapshot",
                ),
                PanelRow("library", RowKind.INFO, "Library", self.source["library"]),
                PanelRow("url", RowKind.INFO, "Source", self.source["url"]),
                PanelRow("kind", RowKind.INFO, "Type", self.source["kind"]),
                PanelRow("files", RowKind.INFO, "Files", str(self.source["files"])),
                PanelRow(
                    "checked", RowKind.INFO, "Last checked", self.source["checked"] or "Unknown"
                ),
                back("knowledge-sources"),
            ]
        elif view == "knowledge-review":
            operation = self.draft["operation"]
            crumbs += ("Review learning" if operation != "refresh" else "Review refresh",)
            rows = [
                row(
                    "start",
                    "Learn source" if operation != "refresh" else "Refresh source",
                    enabled=not self.busy,
                ),
                PanelRow("destination", RowKind.INFO, "Library", self.draft["library"]),
                PanelRow("source", RowKind.INFO, "Source", public_text(self.draft["source"], 500)),
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Creates or replaces learned knowledge",
                    description="Uses the configured local embedding model; "
                    "originals and stored artifacts are retained.",
                ),
                PanelRow(
                    "model",
                    RowKind.INFO,
                    "Embedding model",
                    str(self.host.cfg.models.get("embed") or "Not configured"),
                ),
                PanelRow(
                    "budget",
                    RowKind.INFO,
                    "Limits",
                    "2 MiB text · 1000 chunks · 5 minutes"
                    if operation != "refresh"
                    else "8 MiB text · 1000 chunks · 5 minutes",
                    description=(
                        "Refresh keeps existing page/crawl settings. "
                        "Oversized or failed downloads retain the previous indexed snapshot."
                    )
                    if operation == "refresh"
                    else "Indexes this single source; unchanged content skips embeddings.",
                ),
                back(self.parent),
            ]
        elif view == "knowledge-task":
            crumbs += ("Task",)
            label = {
                "learn": "Learning source",
                "refresh": "Refreshing source",
                "query": "Querying indexed knowledge",
            }.get(self.task[3] if self.task else "", "Knowledge task")
            rows = [
                PanelRow(
                    "progress",
                    RowKind.INFO,
                    "Stopping…" if self.stopping else label,
                    description="5-minute deadline · no chat generation",
                ),
                row("stop", "Cancel task", enabled=self.busy and not self.stopping),
                back(self.parent),
            ]
        else:
            crumbs += ("Hybrid query",)
            rows = [
                row(
                    "hybrid",
                    "New hybrid query…",
                    enabled=not self.busy,
                    description="Uses embeddings and hybrid retrieval · no chat generation",
                )
            ]
            for index, hit in enumerate(self.result.get("hits", [])):
                rows.append(
                    PanelRow(
                        "hit:" + str(index), RowKind.INFO, hit["source"], description=hit["text"]
                    )
                )
            if not self.result.get("hits"):
                rows.append(PanelRow("empty", RowKind.INFO, "No matching indexed knowledge"))
            rows.append(back(self.parent))
        if self.busy and view != "knowledge-task":
            rows.insert(
                0, row("task", "Current Knowledge task", description="Open progress or cancel")
            )
        return PanelPage(
            "library:" + ":".join((view, self.name, self.source.get("id", ""))),
            crumbs,
            tuple(rows),
            subtitle="Learning is explicit · Browsing stays local",
            column_headers=("SOURCE", "FILES", "LIBRARY / TYPE")
            if view == "knowledge-sources"
            else None,
            table_section_id="inventory" if view == "knowledge-sources" else "",
            scrollable_body=view == "knowledge-hybrid",
        )

    def handle(self, command: PanelAction) -> None:
        kind = command.kind.removeprefix("library-knowledge-")
        library = self.library
        if kind in {"learn", "hybrid", "sources"}:
            if self.busy and kind != "sources":
                raise ValueError("Finish or cancel the current Knowledge task")
            if library.view != "knowledge-hybrid":
                self.parent = library.view
                self.name = library.target if library.view == "detail" else ""
            library.leave()
            library.feedback, library.error = None, ""
            if kind == "sources":
                self.sources_parent = self.parent
                self.offset = 0
                library.show("knowledge-sources")
                library.load()
            elif kind == "hybrid":
                self.editor(
                    "hybrid", "Hybrid query", "Question · uses embeddings · no chat generation"
                )
            elif not self.name:
                self.editor("name", "Destination knowledge library", "Existing or new library name")
            else:
                self.editor("source", "Learn one source", "UTF-8 file path or public HTTP(S) URL")
        elif kind == "back":
            library.leave()
            library.feedback, library.error = None, ""
            if command.target == "knowledge-sources":
                library.show(command.target, "source:" + self.source.get("id", ""))
                library.load()
            else:
                library.show(
                    command.target, "record:" + self.name if command.target == "detail" else ""
                )
                if command.target == "knowledge":
                    library.load()
        elif kind == "source":
            self.source = next(
                (item for item in library.snapshot()["items"] if item["id"] == command.target), {}
            )
            if not self.source:
                raise ValueError("Source no longer available; reload the list")
            library.leave()
            library.show("knowledge-source-detail")
        elif kind == "refresh":
            self.parent = "knowledge-source-detail"
            self.draft = {
                "operation": "refresh",
                "library": self.source["library"],
                "source": self.source["id"],
                "source_identity": self.source["identity"],
            }
            library.show("knowledge-review", "back")
        elif kind == "start":
            self.start(dict(self.draft))
        elif kind == "task":
            self.restore_context()
            library.show("knowledge-task")
        elif kind == "stop":
            self.stop()
        elif kind in {"reload", "next", "previous"}:
            library.leave()
            if kind != "reload":
                self.offset = max(0, self.offset + (100 if kind == "next" else -100))
            library.show()
            library.load(force=True)

    def editor(self, kind: str, label: str, hint: str) -> None:
        self.host._begin_settings_input(
            label, hint + " · Enter continues · Escape returns", ("library", "knowledge-" + kind)
        )

    def answer(self, kind: str, value: str | None) -> None:
        if value is None:
            self.host._set_input("")
            self.library.show()
            return
        value = value.strip()
        if kind == "name":
            self.name = library_name(value)
            self.host._set_input("")
            self.editor("source", "Learn one source", "UTF-8 file path or public HTTP(S) URL")
            return
        if kind == "source":
            if not 1 <= len(value) <= 4096 or public_text(value, 4096) != value:
                raise ValueError("Enter a printable file path or public URL of 1–4096 characters")
            if value.startswith(("http://", "https://")):
                from klaude_web.fetch import canonicalize_public_url

                canonicalize_public_url(value)
            self.draft = {"operation": "learn", "library": self.name, "source": value}
            self.host._set_input("")
            self.library.show("knowledge-review", "back")
        else:
            if not 1 <= len(value) <= 200:
                raise ValueError("Enter a question of 1–200 characters")
            if not self.name:
                raise ValueError("Open a named knowledge library before running a hybrid query")
            self.start({"operation": "query", "library": self.name, "query": value})
            self.host._set_input("")

    def start(self, draft: dict[str, Any]) -> None:
        action = KnowledgeAction.from_draft(draft)
        if getattr(getattr(self.host, "_model_manager", None), "busy", False):
            raise ValueError("Finish the Model Manager operation before starting a Knowledge task")
        if (
            self.busy
            or getattr(getattr(self.library, "vision", None), "busy", False)
            or getattr(getattr(self.library, "generation", None), "busy", False)
            or self.host.running
            or self.host._watching_remote
            or self.host._setup_job is not None
            or self.host._skill_action_pending
            or self.library.research.task
            or self.host._ai_defaults.utility
            or self.host._ai_defaults.preparing_utility
        ):
            raise ValueError("Finish the running turn or setup before starting a Knowledge task")
        cfg = self.host.cfg
        if not cfg.models.get("embed"):
            raise ValueError("Configure a local embedding model before starting this task")
        request = knowledge_worker_request(
            action, cfg, data_dir=Path(self.library.scope).parent,
            workspace=Path(getattr(self.host.agent, "workdir", Path.cwd())),
        )
        self.library.leave()
        # An action chosen through page filtering must not conceal its results.
        for view in (self.library.view, "knowledge-hybrid"):
            page_id = "library:" + ":".join((view, self.name, self.source.get("id", "")))
            state = self.host._panel_states.get(page_id)
            if state is not None:
                state.filter("")
        self.task_context = {
            "name": self.name,
            "parent": self.parent,
            "sources_parent": self.sources_parent,
            "source": dict(self.source),
            "library_parent": self.library.parent,
            "library_target": self.library.target,
            "library_detail": dict(self.library.detail),
        }
        identity = self.host._background_jobs.submit(
            TASK_KEY, request, timeout=300, notify_cancel=True
        )
        self.task = (identity, self.host.session_id, self.library.scope, draft["operation"])
        self.task_started, self.stopping = time.monotonic(), False
        self.library.feedback, self.library.error = None, ""
        self.library.show("knowledge-task", "stop")

    def restore_context(self) -> None:
        if (
            not self.task_context
            or self.task
            and self.task[1:3] != (self.host.session_id, self.library.scope)
        ):
            return
        self.name = self.task_context["name"]
        self.parent = self.task_context["parent"]
        self.sources_parent = self.task_context["sources_parent"]
        self.source = dict(self.task_context["source"])
        self.library.parent = self.task_context["library_parent"]
        self.library.target = self.task_context["library_target"]
        self.library.detail = dict(self.task_context["library_detail"])

    def stop(self) -> None:
        if self.busy and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(TASK_KEY)
            self.library.feedback = ("Stopping task; completed indexing may remain", "warning")
            if self.library.visible:
                self.library.show()

    def stopped(self, identity: str) -> None:
        if self.task and self.task[0] == identity:
            self.finish(
                {
                    "status": "unconfirmed",
                    "message": "Task stopped; Reload to verify indexing status",
                }
            )

    def accept(self, identity: str, result: object, error: str) -> None:
        if self.task is None or self.task[0] != identity:
            return
        self.finish(
            result
            if not error and isinstance(result, dict)
            else {
                "status": "unconfirmed",
                "message": "Task failed or timed out; Reload to verify indexing status",
            }
        )

    def finish(self, result: dict[str, Any]) -> None:
        task, self.task = self.task, None
        if task is None:
            return
        self.stopping = False
        self.library.cache.clear()
        current = task[1:3] == (self.host.session_id, self.library.scope)
        status = result.get("status", "unconfirmed")
        if current:
            self.result = result
        if self.library.visible and current:
            if self.library.view == "knowledge-task":
                self.restore_context()
                self.library.show("knowledge-hybrid" if status == "queried" else self.parent)
            if self.library.view in {"knowledge", "knowledge-sources"}:
                self.library.load(force=True)
            if status in {"unconfirmed", "rejected"}:
                self.library.feedback = (
                    str(result.get("message", "Operation unconfirmed")),
                    "warning" if status == "unconfirmed" else "error",
                )
            else:
                self.library.feedback = (
                    {
                        "queried": f"{len(result.get('hits', []))} hybrid results",
                        "unchanged": "Source unchanged · indexing skipped",
                        "learned": f"Learned {result.get('chunks', 0)} chunks",
                        "refreshed": f"Refreshed {result.get('files', 0)} files · "
                        f"{result.get('chunks', 0)} new chunks",
                    }.get(status, "Knowledge updated"),
                    "neutral" if status in {"queried", "unchanged"} else "success",
                )
            self.library.show()
        elif current:
            self.host._append(
                "\n[knowledge] "
                + (
                    "Task finished · reopen Library to inspect results"
                    if status not in {"unconfirmed", "rejected"}
                    else public_text(result.get("message"))
                )
                + ".\n"
            )
        self.host._start_next()
