"""Deep Research forms, defaults and owned execution inside Library."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from klaude_core.research import LIMITS, ResearchDefaults, question
from klaude_core.search_settings import KEYS, PROVIDERS

from .library_inventory import public_text
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

KEY = "library:research"


def action(key: str, label: str, target: str = "", **kwargs: Any) -> PanelRow:
    return PanelRow(
        key, RowKind.ACTION, label, action=PanelAction("library-research-" + key, target), **kwargs
    )


def back(target: str) -> PanelRow:
    return action("back", "Back", target, control=RowControl.BACK)


class ResearchPanel:
    def __init__(self, library: Any):
        self.library = library
        self.defaults = ResearchDefaults().public()
        self.saved_defaults = dict(self.defaults)
        self.draft: dict[str, Any] = {"question": "", "format": "report", "model": None}
        self.item: dict[str, Any] = {}
        self.task: tuple[str, str, str] | None = None
        self.started = 0.0
        self.stopping = False
        self.offset = 0
        self.parent = "research"
        self.settings_parent = "search"
        self.control: tuple[str, str, str] | None = None
        self.last_poll = 0.0

    @property
    def host(self) -> Any:
        return self.library.host

    @property
    def active(self) -> bool:
        return self.library.view == "research" or self.library.view.startswith("research-")

    @property
    def busy(self) -> bool:
        return self.task is not None or self.control is not None

    def open(self) -> None:
        self.library.leave()
        self.library.show("research")
        self.library.load(force=True)

    def key(self) -> tuple[str, str, int]:
        return self.library.view, self.item.get("id", ""), self.offset

    def request(self) -> dict:
        return {
            "operation": "research-detail"
            if self.library.view == "research-job" and self.item
            else "research-list",
            "target": self.item.get("id", ""),
            "offset": self.offset,
        }

    def snapshot(self, result: dict) -> None:
        self.saved_defaults = result.get("defaults", self.saved_defaults)
        if self.library.view not in {"research-form", "research-review"}:
            self.defaults = dict(self.saved_defaults)
        if self.library.view == "research-job" and isinstance(result.get("item"), dict):
            self.item = result["item"]

    def effective_model(self) -> str:
        defaults = self.host._ai_defaults.defaults
        return (
            self.draft["model"]
            or (defaults.research if defaults else None)
            or self.host._ai_defaults.chat_ref()
            or ""
        )

    def page(self) -> PanelPage:
        view = self.library.view
        crumbs: tuple[str, ...] = ("Library", "Research")
        rows: list[PanelRow] = []
        if view == "research":
            rows = [
                action("new", "New research…", enabled=self.control is None),
                action("reports", "Saved reports"),
                action("defaults", "Research defaults"),
                action("reload", "Reload jobs"),
                PanelRow("jobs", RowKind.SECTION, "RESEARCH JOBS"),
                PanelRow("columns", RowKind.TABLE_HEADER, "", section_id="jobs"),
            ]
            items = self.library.snapshot().get("items", [])
            for item in items:
                rows.append(
                    PanelRow(
                        "job:" + item["id"],
                        RowKind.NAVIGATION,
                        public_text(item["question"], 160),
                        item["status"].title(),
                        description=public_text(item["phase"], 180),
                        section_id="jobs",
                        action=PanelAction("library-research-job", item["id"]),
                    )
                )
            if not items:
                rows.append(
                    PanelRow(
                        "empty",
                        RowKind.INFO,
                        "Loading…"
                        if self.library.pending
                        else "No research jobs yet · New research starts with a review",
                    )
                )
            if self.offset:
                rows.append(action("previous", "Previous 100 jobs"))
            if self.library.snapshot().get("more"):
                rows.append(action("next", "Next 100 jobs"))
            rows.append(back("home"))
        elif view == "research-form":
            crumbs += ("New research",)
            rows = [
                action("question", "Question", value=self.draft["question"] or "Required"),
                action("format", "Format", value=self.draft["format"].title()),
                action(
                    "model",
                    "Endpoint / model",
                    value=self.host._ai_defaults.label(self.effective_model())
                    if self.effective_model()
                    else "Required",
                    description="Job override; no changes to the current session model",
                ),
                action("provider", "Search", value=self.defaults["provider"]),
                action("rounds", "Rounds", value=str(self.defaults["rounds"])),
                action(
                    "queue", "Queue", enabled=bool(self.draft["question"]) and self.control is None
                ),
                action("start", "Start", enabled=bool(self.draft["question"]) and not self.busy),
                PanelRow(
                    "budget",
                    RowKind.INFO,
                    "Budgets",
                    f"{self.defaults['queries']} queries · {self.defaults['sources']} sources · "
                    f"{self.defaults['timeout']}s",
                    description=f"{self.defaults['output_tokens']} report tokens · "
                    f"{self.defaults['parallel']} extractions · "
                    "web/model requests may incur provider charges",
                ),
                back("research"),
            ]
        elif view == "research-job":
            crumbs += ("Job",)
            item = self.item
            status = item.get("status", "")
            running = bool(self.task) and item.get("id") == getattr(self, "running_id", "")
            rows = [
                PanelRow("question", RowKind.INFO, item.get("question", "Research job")),
                PanelRow(
                    "status",
                    RowKind.INFO,
                    "State",
                    status.title(),
                    description=item.get("phase", ""),
                ),
                PanelRow(
                    "progress",
                    RowKind.INFO,
                    "Progress",
                    f"Round {item.get('round', 0)} · "
                    f"{len(item.get('queries', []))} queries · "
                    f"{len(item.get('sources', []))} sources",
                ),
            ]
            if item.get("report"):
                rows.append(action("report", "View saved report"))
            if running:
                rows.append(action("stop", "Cancel job", enabled=not self.stopping))
            elif status in {"queued", "cancelled", "interrupted", "error", "partial"}:
                rows.append(
                    action(
                        "resume",
                        "Start queued job" if status == "queued" else "Resume with fresh evidence",
                        enabled=not self.busy,
                    )
                )
                if status == "queued":
                    rows.append(action("cancel-queued", "Cancel queued job", enabled=not self.busy))
            rows += [
                action("reload", "Reload progress"),
                PanelRow("sources", RowKind.SECTION, "FETCHED SOURCE RECEIPTS"),
            ]
            for index, source in enumerate(item.get("sources", [])):
                rows.append(
                    PanelRow(
                        "source:" + str(index),
                        RowKind.INFO,
                        source["url"],
                        description="Metadata only; resuming re-fetches evidence",
                    )
                )
            rows.append(back("research"))
        elif view == "research-defaults":
            crumbs = ("Settings", "Search", "Deep Research")
            rows = [
                action(
                    "provider",
                    "Search provider",
                    value=self.defaults["provider"],
                    description="Auto follows Web Search",
                ),
                action(
                    "role",
                    "Research model",
                    value=self.host._ai_defaults.label(self.host._ai_defaults.defaults.research)
                    if self.host._ai_defaults.defaults and self.host._ai_defaults.defaults.research
                    else "Same as chat · AI Defaults",
                ),
            ]
            labels = {
                "output_tokens": "Max report tokens",
                "extract_timeout": "Extraction timeout (s)",
                "parallel": "Extraction parallelism",
                "timeout": "Run deadline (s)",
                "rounds": "Rounds",
                "queries": "Max queries",
                "sources": "Max sources",
                "context_tokens": "Context budget",
            }
            rows += [
                action(field, labels[field], value=str(self.defaults[field])) for field in LIMITS
            ]
            rows += [
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Saved for new jobs",
                    description="Accepted jobs keep their captured settings. "
                    "No silent model fallback.",
                ),
                back(self.settings_parent),
            ]
        elif view in {"research-provider", "research-format"}:
            crumbs += ("Search provider" if view == "research-provider" else "Format",)
            choices = (
                {"auto": "Same as Web Search", **PROVIDERS}
                if view == "research-provider"
                else {"report": "Report", "brief": "Brief", "comparison": "Comparison"}
            )
            rows = [action("choose:" + value, label, value) for value, label in choices.items()]
            rows.append(back(self.parent))
        else:
            crumbs += ("Review",)
            rows = [
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Run bounded web research?",
                    description="Searches public pages, uses the selected model, "
                    "saves a sourced report. "
                    "No workspace writes, MCP tools or implicit learning.",
                ),
                PanelRow("question", RowKind.INFO, self.draft["question"]),
                PanelRow(
                    "model",
                    RowKind.INFO,
                    "Model",
                    self.host._ai_defaults.label(self.effective_model()),
                ),
                PanelRow(
                    "budget",
                    RowKind.INFO,
                    "Limits",
                    f"{self.defaults['rounds']} rounds · "
                    f"{self.defaults['sources']} sources · {self.defaults['timeout']}s",
                ),
                action(
                    "confirm",
                    "Queue job" if self.draft.get("queued") else "Start job",
                    enabled=self.control is None and (not self.task or self.draft.get("queued")),
                ),
                back("research-form"),
            ]
        if self.task and (view != "research-job" or self.item.get("id") != self.running_id):
            rows.insert(0, action("current", "Current research job"))
        return PanelPage(
            "library:research:" + view + ":" + self.item.get("id", ""),
            crumbs,
            tuple(rows),
            column_headers=("QUESTION", "STATE", "PROGRESS") if view == "research" else None,
            table_section_id="jobs" if view == "research" else "",
            scrollable_body=view == "research-job",
        )

    def handle(self, command: PanelAction) -> None:
        kind = command.kind.removeprefix("library-research-")
        view = self.library.view
        if kind == "settings":
            self.library.leave()
            self.library.scope = str(self.host.cfg.data_dir / "sessions.db")
            self.settings_parent = command.target
            self.library.show("research-defaults")
            self.library.load(force=True)
        elif kind == "back":
            self.library.leave()
            if command.target == "search":
                self.host._search_settings.show("home")
            elif command.target == "ai-defaults":
                self.host._ai_defaults.show("home")
            elif command.target == "research":
                self.open()
            else:
                self.library.show(command.target)
        elif kind == "new":
            self.draft = {"question": "", "format": "report", "model": None}
            self.host._ai_defaults.refresh(show=False)
            self.library.show("research-form")
        elif kind == "question" or kind in LIMITS:
            self.host._begin_settings_input(
                "Research " + kind.replace("_", " "),
                "Enter value · Escape returns",
                ("library", "research-" + kind),
            )
            self.host._set_input(
                str(self.draft["question"] if kind == "question" else self.defaults[kind])
            )
        elif kind in {"provider", "format"}:
            self.parent = view
            self.library.show("research-" + kind)
        elif kind.startswith("choose:"):
            if view == "research-format":
                self.draft["format"] = command.target
            else:
                self.defaults["provider"] = command.target
                if self.parent == "research-defaults":
                    self.submit_control("defaults", values=self.defaults)
            self.library.show(self.parent)
        elif kind == "model":
            self.host._ai_defaults.choose_for_research()
        elif kind == "role":
            self.host._ai_defaults.open()
            self.host._ai_defaults.role = "research"
            self.host._ai_defaults.show("endpoints")
        elif kind == "defaults":
            self.settings_parent = "research"
            self.library.show("research-defaults")
        elif kind in {"queue", "start"}:
            self.draft["queued"] = kind == "queue"
            self.library.show("research-review", "back")
        elif kind == "confirm":
            self.submit_control(
                "create",
                draft={**self.draft, "model": self.effective_model()},
                settings=self.defaults,
            )
        elif kind in {"resume", "cancel-queued"}:
            self.submit_control(
                "load" if kind == "resume" else "stop",
                target=self.item["id"],
                queued_only=kind == "cancel-queued",
            )
        elif kind == "stop":
            self.stop()
        elif kind in {"job", "current"}:
            identity = command.target if kind == "job" else getattr(self, "running_id", "")
            self.item = {"id": identity}
            self.library.leave()
            self.library.show("research-job")
            self.library.load(force=True)
        elif kind == "report":
            self.library.artifacts.open("research-reports")
            self.library.artifacts.detail = {"id": self.item["report"]}
            self.library.show("artifact-detail")
            self.library.load(force=True)
        elif kind == "reports":
            self.library.artifacts.open("research-reports")
        elif kind in {"reload", "next", "previous"}:
            if kind != "reload":
                self.offset = max(0, self.offset + (100 if kind == "next" else -100))
            self.library.load(force=True)

    def answer(self, kind: str, value: str | None) -> None:
        if kind == "report-action":
            if value is not None:
                self.submit_control(
                    "report-action",
                    target=self.report_target["id"],
                    revision=self.report_target["revision"],
                    action=self.report_kind,
                    value=value,
                )
            self.host._set_input("")
            self.library.show()
            return
        if value is not None:
            if kind == "question":
                self.draft["question"] = question(value)
            else:
                from klaude_core.research import research_defaults

                candidate = {**self.defaults, kind: int(value)}
                self.defaults = research_defaults(candidate).public()
                if self.library.view == "research-defaults":
                    self.submit_control("defaults", values=self.defaults)
        self.host._set_input("")
        self.library.show()

    def set_model(self, reference: str | None) -> None:
        self.draft["model"] = reference
        self.library.show("research-form", "model")

    def request_base(self) -> dict:
        cfg = self.host.cfg
        keys = {name: os.environ.get(name, getattr(cfg, attr, "")) for name, attr in KEYS.values()}
        keys.update(self.host._model_settings.environment_keys())
        keys["CRAWL4AI_API_KEY"] = os.environ.get("CRAWL4AI_API_KEY", cfg.crawl4ai_api_key)
        return {
            "kind": "research_control",
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "session": self.host.session_id,
            "environment_keys": keys,
            "native_options": getattr(self.host.agent, "ollama_options", {}),
        }

    def submit_control(self, operation: str, **values: Any) -> None:
        if self.control is not None or self.task is not None and operation == "load":
            raise ValueError("Finish or cancel the current research action")
        identity = self.host._background_jobs.submit(
            "research:control",
            {
                **self.request_base(),
                "operation": operation,
                "expected": self.saved_defaults,
                **values,
            },
            timeout=8,
        )
        self.control_context = (self.library.view, self.item.get("id", ""), self.library.scope)
        self.control_queued = bool(self.draft.get("queued"))
        self.control = (identity, self.host.session_id, operation)
        self.library.feedback = ("Saving research action…", "neutral")
        self.library.show()

    def accept_control(self, identity: str, result: Any, error: str) -> None:
        if not self.control or self.control[0] != identity:
            return
        session = self.control[1]
        operation = self.control[2]
        context = getattr(self, "control_context", (self.library.view, "", self.library.scope))
        follows = (
            self.library.visible
            and self.library.view == context[0]
            and self.library.scope == context[2]
        )
        self.control = None
        if session != self.host.session_id or self.library.scope != context[2]:
            self.host._start_next()
            return
        if error or not isinstance(result, dict) or result.get("error"):
            self.library.feedback = (
                (result or {}).get("error")
                if isinstance(result, dict)
                else "Research action unconfirmed; Reload",
                "error",
            )
            if not self.library.feedback[0]:
                self.library.feedback = ("Research action unconfirmed; Reload", "warning")
        elif operation == "report-action":
            if self.report_kind == "discuss":
                self.library.leave()
                self.host._panel = None
                self.host._cancel_choice(resume_queue=False)
                from klaude_core.capabilities import TurnScope

                from .main import PendingChatTurn

                self.host.pending.append(
                    PendingChatTurn(
                        result["public_message"],
                        model_message=result["prompt"],
                        scope=TurnScope.RESEARCH,
                    )
                )
                self.host._start_next()
                return
            knowledge = self.library.knowledge
            knowledge.name = result["library"]
            knowledge.parent = "artifact-detail"
            knowledge.draft = {
                "operation": "learn-report",
                "library": result["library"],
                "artifact": result["artifact"],
                "revision": result["revision"],
                "source": "Stored research report",
            }
            self.library.show("knowledge-review", "back")
            return
        elif operation == "defaults":
            self.defaults = result["defaults"]
            self.saved_defaults = dict(self.defaults)
            self.library.feedback = ("Research defaults saved", "success")
        else:
            item = result["item"]
            if follows:
                self.item = item
            if operation == "load" or operation == "create" and not self.control_queued:
                self.start(item, follow=follows)
                return
            self.library.feedback = (
                "Research job queued" if operation == "create" else "Job stopped",
                "success",
            )
            if follows:
                self.library.cache.clear()
                self.library.show("research-job")
                return
        if self.library.visible:
            self.library.show()
        self.host._start_next()

    def start(self, item: dict | None = None, *, follow: bool = True) -> None:
        item = item or self.item
        if (
            self.host.running
            or self.host._watching_remote
            or self.library.knowledge.busy
            or self.host._setup_job is not None
            or self.host._skill_action_pending
            or self.host._ai_defaults.utility
            or self.host._ai_defaults.preparing_utility
        ):
            self.library.feedback = (
                "Job queued; start after the active turn or setup finishes",
                "warning",
            )
            self.library.show("research-job")
            return
        request = {
            **self.request_base(),
            "kind": "research_run",
            "target": item["id"],
            "owner": uuid.uuid4().hex,
        }
        self.run_request = request
        identity = self.host._background_jobs.submit(
            KEY, request, timeout=item["spec"]["settings"]["timeout"] + 5, notify_cancel=True
        )
        self.task_scope = self.library.scope
        self.task = (identity, self.host.session_id, self.library.scope)
        self.running_id = item["id"]
        self.started = time.monotonic()
        self.stopping = False
        self.library.feedback = None
        if self.library.visible and follow:
            self.library.show("research-job", "stop")
            self.library.load(force=True)

    def poll(self) -> None:
        if (
            self.task
            and self.library.visible
            and self.library.view == "research-job"
            and not self.library.pending
            and time.monotonic() - self.last_poll >= 2
        ):
            self.last_poll = time.monotonic()
            self.library.load(force=True)

    def stop(self) -> None:
        if self.task and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(KEY)
            self.library.feedback = ("Stopping research; saved reports are retained", "warning")
            if self.library.visible:
                self.library.show()

    def stopped(self, identity: str) -> None:
        if not self.task or self.task[0] != identity:
            return
        self.task = None
        self.stopping = False
        request = {**self.run_request, "kind": "research_control", "operation": "stop"}
        control_id = self.host._background_jobs.submit("research:control", request, timeout=8)
        self.control_context = (self.library.view, self.item.get("id", ""), self.task_scope)
        self.control_queued = False
        self.control = (control_id, self.run_request["session"], "stop")

    def accept(self, identity: str, result: Any, error: str) -> None:
        if not self.task or self.task[0] != identity:
            return
        accepted = self.task
        self.task = None
        if accepted[1:] != (self.host.session_id, self.library.scope):
            self.host._start_next()
            return
        if isinstance(result, dict) and not error and not result.get("error"):
            if self.item.get("id") == self.running_id:
                self.item = result
            status = result.get("status")
            self.library.feedback = (
                "Research report saved"
                if status == "completed"
                else "Partial report saved; review limits"
                if status == "partial"
                else result.get("phase", "Research failed"),
                "success"
                if status == "completed"
                else "warning"
                if status == "partial"
                else "error",
            )
        else:
            self.library.feedback = (
                "Research request rejected; Reload the current job"
                if isinstance(result, dict) and result.get("error")
                else "Research interrupted; Reload and resume with fresh evidence",
                "error" if isinstance(result, dict) and result.get("error") else "warning",
            )
        self.library.cache.clear()
        if self.library.visible and self.library.view == "research-job":
            self.library.show()
        self.host._start_next()

    def report_action(self, kind: str, item: dict) -> None:
        self.report_target = dict(item)
        self.report_kind = kind
        self.host._begin_settings_input(
            "Discuss saved report" if kind == "discuss" else "Destination knowledge library",
            "Explicit action · stored report is not fresh source evidence · Escape returns",
            ("library", "research-report-action"),
        )
