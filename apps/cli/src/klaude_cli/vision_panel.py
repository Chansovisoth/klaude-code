"""Explicit Media analysis with private input/results and an owned request."""

from __future__ import annotations

import os
import time
from typing import Any

from klaude_core.vision import ANALYSIS_TIMEOUT, PREPARE_TIMEOUT

from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

KEY = "library:vision"


def row(identity: str, label: str, **kwargs: Any) -> PanelRow:
    return PanelRow(
        identity, RowKind.ACTION, label, action=PanelAction("library-vision-" + identity), **kwargs
    )


class VisionPanel:
    def __init__(self, library: Any):
        self.library = library
        self.item: dict = {}
        self.question = "Describe this image and any visible text."
        self.spec: dict = {}
        self.result: dict = {}
        self.task: tuple[str, str, str, str] | None = None
        self.started = 0.0
        self.stopping = False
        self.context, self.output_tokens = 4096, 512
        self.last_poll = 0.0
        self.tagging = False
        self.selected: set[str] = set()

    @property
    def host(self) -> Any:
        return self.library.host

    @property
    def busy(self) -> bool:
        return self.task is not None

    @property
    def active(self) -> bool:
        return self.library.view.startswith("vision-")

    def open(self, item: dict, *, tagging: bool = False) -> None:
        if self.busy:
            self.library.show("vision-task")
            return
        self.library.leave()
        if (self.item.get("id"), self.item.get("revision"), self.tagging) != (
            item["id"], item["revision"], tagging
        ):
            self.question = "Describe this image and any visible text."
            self.spec, self.result = {}, {}
            self.selected = set()
        self.tagging = tagging
        self.item = dict(item)
        self.library.feedback = None
        self.library.show(
            "vision-result" if self.result else "vision-form", "back" if self.result else ""
        )

    def page(self) -> PanelPage:
        view, defaults = self.library.view, self.host._ai_defaults.defaults
        crumbs: tuple[str, ...] = (
            "Library", "Media", "Suggest AI tags" if self.tagging else "Analyze image"
        )
        rows = [PanelRow("image", RowKind.INFO, "Image", self.item.get("name", "Image"))]
        if view == "vision-form":
            rows += [
                row(
                    "settings",
                    "Vision settings",
                    value="ON" if defaults and defaults.vision_enabled else "OFF",
                    description=self.host._ai_defaults.label(defaults.vision if defaults else None),
                ),
                PanelRow("purpose", RowKind.INFO, "Task", "Suggest objects, colors and style tags")
                if self.tagging else row("question", "Question", value=self.question),
                row("context", "Context", value=str(self.context),
                    description="Ollama allocation; HTTP servers use a local input estimate"),
                row("output_tokens", "Output tokens", value=str(self.output_tokens)),
                row("review", "Review tag request" if self.tagging else "Review analysis",
                    enabled=not self.busy),
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Optional AI tag suggestions" if self.tagging else "Explicit image analysis",
                    description="Sends the stored image to the reviewed Vision endpoint. "
                    "Select suggestions to save separately from manual tags; no automatic changes."
                    if self.tagging else "Sends the stored PNG/JPEG and question "
                    "to the reviewed endpoint. "
                    "No tools, indexing, tags or chat changes. Result stays private to this panel.",
                ),
                row("back", "Back", control=RowControl.BACK),
            ]
        elif view == "vision-review":
            crumbs += ("Review",)
            rows += [
                PanelRow("question", RowKind.INFO, "Task" if self.tagging else "Question",
                         "Suggest visible objects, colors and style tags"
                         if self.tagging else self.spec["question"]),
                PanelRow(
                    "budget",
                    RowKind.INFO,
                    "Budget",
                    f"{self.spec['context']} context · {self.spec['output_tokens']} output tokens",
                    description="HTTP server allocation stays unchanged"
                    if any(m.get("backend") != "ollama" for m in self.spec["models"]) else "",
                ),
                PanelRow(
                    "bytes",
                    RowKind.INFO,
                    "Stored image",
                    f"{self.item['size']:,} B · checksum verified",
                ),
            ]
            for index, model in enumerate(self.spec["models"]):
                rows.append(
                    PanelRow(
                        "model:" + str(index),
                        RowKind.INFO,
                        "Model" if not index else f"Fallback {index}",
                        model["reference"],
                        description=model["name"]
                        + " · "
                        + model["endpoint"]
                        + (" · documented image support · metadata verified"
                           if model.get("profile_source") else " · declared vision support"),
                    )
                )
            rows += [
                PanelRow(
                    "policy",
                    RowKind.INFO,
                    "Request limit",
                    "90 seconds per model",
                    description="Only listed fallbacks for network/timeouts "
                    "or temporary service errors. "
                    + ("No tags saved until you select and save suggestions." if self.tagging
                       else "No saved analysis, chat changes or indexing."),
                ),
                row("start", "Suggest tags" if self.tagging else "Analyze image"),
                row("back", "Back", control=RowControl.BACK),
            ]
        elif view == "vision-task":
            rows += [
                PanelRow(
                    "progress",
                    RowKind.INFO,
                    "Checking image and model"
                    if self.task and self.task[3].endswith("prepare")
                    else "Saving selected AI tags"
                    if self.task and self.task[3] == "tags_apply"
                    else "Suggesting image tags" if self.tagging
                    else "Analyzing image",
                    f"{int(time.monotonic() - self.started)}s",
                ),
                row("cancel", "Cancel", enabled=not self.stopping
                    and not (self.task and self.task[3] == "tags_apply"),
                    control=RowControl.CANCEL),
                row("back", "Back to Media", control=RowControl.BACK),
            ]
        else:
            crumbs += ("Result",)
            if self.tagging:
                rows += [
                    PanelRow("model", RowKind.INFO, "Used model", self.result.get("model", "")),
                    PanelRow("manual", RowKind.INFO, "Manual tags",
                             ", ".join(self.item["tags"]) or "None"),
                    PanelRow("choose", RowKind.INFO, "Select suggestions to save",
                             description="AI tags are separate. Manual tags are retained."),
                ]
                manual = {tag.casefold() for tag in self.item["tags"]}
                for index, tag in enumerate(self.result.get("tags", [])):
                    existing = tag.casefold() in manual
                    rows.append(PanelRow(
                        "select:" + str(index), RowKind.TOGGLE, tag,
                        checked=tag in self.selected, enabled=not existing,
                        description="Already a manual tag" if existing else "",
                        action=PanelAction("library-vision-select:" + str(index)),
                    ))
                rows += [row("apply", "Save selected AI tags", enabled=bool(self.selected)),
                         row("again", "Suggest again"),
                         row("back", "Back", control=RowControl.BACK)]
            else:
                rows += [
                    PanelRow("model", RowKind.INFO, "Used model", self.result.get("model", "")),
                    PanelRow(
                        "answer", RowKind.INFO, "Analysis", description=self.result.get("text", "")
                    ),
                    PanelRow(
                        "private", RowKind.INFO, "Private result",
                        "Not saved, indexed or added to chat"
                    ),
                    row("again", "Ask another question"),
                    row("back", "Back", control=RowControl.BACK),
                ]
        return PanelPage(
            "library:" + view + ":" + self.item.get("id", ""),
            crumbs,
            tuple(rows),
            scrollable_body=True,
            scroll_wrapped_rows=True,
            align_info_values=True,
        )

    def handle(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("library-vision-")
        if kind == "back":
            self.library.show(
                "vision-form" if self.library.view == "vision-review" else "artifact-detail"
            )
        elif kind == "settings":
            self.host._ai_defaults.vision_return = self
            self.host._ai_defaults.show("vision")
            self.host._ai_defaults.refresh()
        elif kind in {"question", "context", "output_tokens"}:
            self.host._begin_settings_input(
                kind.replace("_", " ").title(),
                "Enter a value; Escape returns",
                ("library", "vision-" + kind),
            )
            self.host._set_input(str(getattr(self, kind)))
        elif kind in {"review", "start"}:
            self.start("prepare" if kind == "review" else "analyze")
        elif kind == "cancel":
            self.stop()
        elif kind == "again":
            self.result = {}
            self.selected = set()
            self.library.show("vision-form", "question")
        elif kind.startswith("select:"):
            tag = self.result["tags"][int(kind.split(":")[1])]
            if tag.casefold() not in {t.casefold() for t in self.item["tags"]}:
                self.selected.symmetric_difference_update({tag})
                self.library.show()
        elif kind == "apply":
            self.start("tags_apply")

    def answer(self, value: str | None, field: str = "question") -> None:
        if value is not None:
            if field != "question":
                from klaude_core.vision import budget

                parsed = int(value)
                budget(
                    parsed if field == "context" else self.context,
                    parsed if field == "output_tokens" else self.output_tokens,
                )
                setattr(self, field, parsed)
                self.spec = {}
                self.host._set_input("")
                self.library.show("vision-form", field)
                return
            if not 1 <= len(value.strip()) <= 1000:
                raise ValueError("Enter an image question of 1–1000 characters")
            self.question, self.spec = value.strip(), {}
        self.host._set_input("")
        self.library.show("vision-form", "question")

    def start(self, operation: str) -> None:
        if self.tagging:
            operation = {"prepare": "tags_prepare", "analyze": "tags_suggest"}.get(
                operation, operation
            )
        host = self.host
        if (
            self.busy
            or getattr(getattr(self.library, "generation", None), "busy", False)
            or host.running
            or host._watching_remote
            or host._setup_job is not None
            or host._skill_action_pending
            or self.library.knowledge.busy
            or self.library.research.busy
            or host._model_manager.busy
            or host._ai_defaults.utility
            or host._ai_defaults.preparing_utility
        ):
            raise ValueError("Finish the running model/setup task before analyzing an image")
        cfg = host.cfg
        environment = host._model_settings.environment_keys()
        for connection in host._ai_defaults.connections.values():
            if (
                connection.key_env
                and (value := os.environ.get(connection.key_env))
                and len(value) <= 8192
            ):
                environment[connection.key_env] = value
        request = {
            "kind": "vision",
            "operation": operation,
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "ollama_url": cfg.ollama_url,
            "roles": dict(cfg.models),
            "artifact": self.item["id"],
            "revision": self.item["revision"],
            "question": self.question,
            "context": self.context,
            "output_tokens": self.output_tokens,
            "spec": self.spec,
            "proposal": self.result if self.tagging else {},
            "selected": [tag for tag in self.result.get("tags", []) if tag in self.selected],
            "environment_keys": environment,
        }
        self.library.leave()
        identity = host._background_jobs.submit(
            KEY,
            request,
            timeout=PREPARE_TIMEOUT if operation.endswith("prepare")
            else 20 if operation == "tags_apply"
            else ANALYSIS_TIMEOUT * len(self.spec["models"]),
            notify_cancel=True,
        )
        self.task = (identity, host.session_id, self.library.scope, operation)
        self.started, self.stopping = time.monotonic(), False
        self.library.feedback = None
        self.library.show("vision-task", "cancel")

    def stop(self) -> None:
        if self.task and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(KEY)
            self.library.feedback = ("Cancelling image analysis…", "neutral")
            if self.library.visible:
                self.library.show()

    def poll(self) -> None:
        now = time.monotonic()
        if (
            self.busy
            and self.library.visible
            and self.library.view == "vision-task"
            and now - self.last_poll > 0.5
        ):
            self.last_poll = now
            self.library.show()

    def stopped(self, identity: str) -> None:
        saving = bool(self.task and self.task[3] == "tags_apply")
        self.accept(
            identity,
            {"status": "cancelled", "message": "Tag save interrupted; reload image metadata"
             if saving else "Image analysis cancelled; no result saved"},
            "",
        )

    def accept(self, identity: str, result: object, error: str) -> None:
        task = self.task
        if task is None or task[0] != identity:
            return
        self.task, self.stopping = None, False
        if task[1:3] != (self.host.session_id, self.library.scope):
            self.host._start_next()
            return
        data: dict[str, Any] = (
            result
            if not error and isinstance(result, dict)
            else {
                "status": "error",
                "message": "Vision worker failed or timed out; retry explicitly",
            }
        )
        status = data.get("status")
        if self.library.visible and self.library.view == "vision-task":
            if isinstance(spec := data.get("spec"), dict):
                self.spec = spec
                self.library.show("vision-review", "back")
            elif status == "complete":
                if task[3] == "tags_apply":
                    self.library.cache.clear()
                    self.item = self.library.artifacts.detail = data["item"]
                    self.result, self.spec, self.selected = {}, {}, set()
                    self.library.feedback = ("AI tags saved; manual tags retained", "success")
                    self.library.show("artifact-detail", "back")
                else:
                    self.result, self.selected = data, set()
                    self.library.show("vision-result", "back")
            else:
                self.library.feedback = (
                    data.get("message", "Image analysis failed"),
                    "neutral" if status == "cancelled" else "error",
                )
                self.library.show("vision-form")
        elif status == "complete":
            if task[3] == "tags_apply":
                self.library.cache.clear()
            else:
                self.result = data
            self.host._append(
                "\n[media] AI tag save finished; reload image metadata.\n"
                if task[3] == "tags_apply"
                else "\n[vision] Image analysis finished; reopen its Media detail to inspect.\n"
            )
        self.host._start_next()
