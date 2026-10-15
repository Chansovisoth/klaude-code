"""One reviewed local image-service consumer, owned by Library Media."""

from __future__ import annotations

import time
import uuid
from typing import Any

from klaude_core.image_generation import DEADLINE, DEFAULTS, cancellation_notice, endpoint, text

from .session_actions import ImageGenerationUpdate
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

KEY = "library:generation"


def row(identity: str, label: str, **kwargs: Any) -> PanelRow:
    return PanelRow(
        identity,
        RowKind.ACTION,
        label,
        action=PanelAction("library-generation-" + identity),
        **kwargs,
    )


class GenerationPanel:
    def __init__(self, library: Any):
        self.library = library
        self.settings: dict[str, Any] = dict(DEFAULTS)
        self.draft: dict[str, Any] = dict(DEFAULTS)
        self.evidence: dict = {}
        self.prompt = ""
        self.width, self.height, self.steps, self.seed = 512, 512, 20, -1
        self.spec: dict = {}
        self.result: dict = {}
        self.task: tuple[str, str, str, str] | None = None
        self.saving = ""
        self.started = self.last_poll = 0.0
        self.stopping = False
        self.return_settings = False
        self.failure = ""
        self.roots = ("", "")
        self.inventory: dict = {}
        self.offset = 0
        self.receipt_view = False
        self.abandon = False

    @property
    def host(self) -> Any:
        return self.library.host

    @property
    def busy(self) -> bool:
        return bool(self.task or self.saving)

    @property
    def active(self) -> bool:
        return self.library.view.startswith("generation-")

    def open(self, *, settings: bool = False) -> None:
        if self.busy:
            self.library.show("generation-task")
            return
        self.return_settings = settings
        self.receipt_view = False
        self.library.leave()
        self.start("read")

    def page(self) -> PanelPage:
        view = self.library.view
        crumbs: tuple[str, ...] = (
            ("Settings", "Model Defaults", "Image generation")
            if self.return_settings
            else ("Library", "Media", "Generate image")
        )
        rows: list[PanelRow] = []
        if view == "generation-history":
            crumbs = ("Library", "Media", "Image jobs")
            rows = [row("history", "Reload"),
                    PanelRow("privacy", RowKind.INFO, "Saved job receipts",
                             description="Local metadata only. Server checks and recovery "
                             "are explicit.")]
            if self.inventory.get("invalid"):
                rows.append(PanelRow("invalid", RowKind.INFO, "Unreadable receipts omitted",
                                     str(self.inventory["invalid"]), value_tone="warning"))
            for item in self.inventory.get("items", []):
                rows.append(row("job:" + item["job"], item["job"],
                                value=item["status"], description=item["model"] + " · "
                                + time.strftime("%Y-%m-%d %H:%M", time.localtime(item["created"]))))
            if not self.inventory.get("items"):
                rows.append(PanelRow("empty", RowKind.INFO, "No image job receipts"))
            if self.offset:
                rows.append(row("previous-jobs", "Previous 100 jobs"))
            if self.inventory.get("more"):
                rows.append(row("next-jobs", "Next 100 jobs"))
            rows.append(row("back", "Back", control=RowControl.BACK))
        elif view in {"generation-receipt", "generation-cancel-review", "generation-forget-review"}:
            crumbs = ("Library", "Media", "Image jobs", "Job")
            rows = [PanelRow("id", RowKind.INFO, "Job", self.spec["id"]),
                    PanelRow("state", RowKind.INFO, "Saved state",
                             self.spec.get("status", "unknown")),
                    PanelRow("endpoint", RowKind.INFO, "Endpoint",
                             self.spec["settings"]["endpoint"]),
                    PanelRow("model", RowKind.INFO, "Model", self.spec["settings"]["model"]),
                    PanelRow("prompt", RowKind.INFO, "Prompt", self.spec["prompt"])]
            if view == "generation-cancel-review":
                rows += [PanelRow("effect", RowKind.INFO, "Cancel this exact server job",
                                  description=cancellation_notice(self.spec["evidence"])),
                         row("cancel-saved", "Send job cancellation")]
            elif view == "generation-forget-review":
                rows += [PanelRow("effect", RowKind.INFO, "Remove private job receipt",
                                  description="Removes its prompt and recovery reference. Media "
                                  "images remain. No server cancellation is sent.")]
                uncertain = self.spec.get("status") not in {
                    "complete", "completed_remote", "cancelled", "failed"
                }
                if uncertain:
                    rows += [PanelRow("warning", RowKind.INFO, "Unconfirmed outcome",
                                      "Server work may continue", value_tone="warning",
                                      description="An active client may recreate its receipt."),
                             PanelRow("abandon", RowKind.TOGGLE, "Abandon local tracking",
                                      checked=self.abandon,
                                      action=PanelAction("library-generation-abandon"))]
                rows.append(row("forget-saved", "Remove job receipt",
                                enabled=not uncertain or self.abandon))
            else:
                rows += [row("refresh-job", "Check server status"),
                         row("review-cancel", "Review job cancellation")]
                if self.spec.get("remote_id") and self.spec.get("status") not in {
                    "cancelled", "failed", "complete"
                }:
                    rows.append(row("recovery-review", "Review output recovery"))
                rows.append(row("review-forget", "Review receipt removal"))
                if self.spec.get("artifact"):
                    rows.append(PanelRow("artifact", RowKind.INFO, "Saved artifact",
                                         self.spec["artifact"]))
            rows.append(row("back", "Back", control=RowControl.BACK))
        elif view == "generation-settings":
            rows = [
                PanelRow(
                    "adapter",
                    RowKind.INFO,
                    "Service",
                    "stable-diffusion.cpp native API",
                    description="Existing local/LAN server · no authentication or installation",
                ),
                row("toggle", "Image generation", value="ON" if self.draft["enabled"] else "OFF"),
                row("endpoint", "Endpoint URL", value=self.draft["endpoint"] or "Not configured"),
                row("test", "Test connection", description="Capabilities only · no generation"),
                PanelRow(
                    "model",
                    RowKind.INFO,
                    "Loaded model",
                    self.draft["model"] or "Test to inspect",
                    description="Save pins this model; Klaude never loads a different model",
                ),
                row("save", "Save", enabled=not self.saving),
                row("reload", "Reload saved settings"),
                row("back", "Back", control=RowControl.BACK),
            ]
        elif view == "generation-form":
            rows = [
                row(
                    "settings",
                    "Image generation settings",
                    value="ON" if self.settings["enabled"] else "OFF",
                ),
                PanelRow(
                    "model", RowKind.INFO, "Model", self.settings["model"] or "Not configured"
                ),
                row("prompt", "Prompt", value=self.prompt or "Enter a description"),
            ]
            for field in ("width", "height", "steps", "seed"):
                rows.append(row(field, field.title(), value=str(getattr(self, field))))
            rows += [
                row("review", "Review generation"),
                PanelRow(
                    "effects",
                    RowKind.INFO,
                    "One PNG image",
                    description="Saved privately in Media with provenance. "
                    "No chat changes, tools, indexing or tags.",
                ),
                row("back", "Back", control=RowControl.BACK),
            ]
        elif view in {"generation-review", "generation-recovery-review"}:
            recovering = view == "generation-recovery-review"
            automatic = all(
                self.spec["evidence"][key] == "default" for key in ("sampler", "scheduler")
            )
            rows = [
                PanelRow("endpoint", RowKind.INFO, "Endpoint", self.spec["settings"]["endpoint"]),
                PanelRow("model", RowKind.INFO, "Loaded model", self.spec["settings"]["model"]),
                PanelRow("prompt", RowKind.INFO, "Prompt", self.spec["prompt"]),
                PanelRow(
                    "size", RowKind.INFO, "Size", f"{self.spec['width']} × {self.spec['height']}"
                ),
                PanelRow(
                    "sampling",
                    RowKind.INFO,
                    "Sampling",
                    f"{self.spec['steps']} steps · seed {self.spec['seed']}"
                    + (" · Server defaults" if automatic else ""),
                    description="" if automatic else self.spec["evidence"]["sampler"]
                    + " · "
                    + self.spec["evidence"]["scheduler"],
                ),
                PanelRow(
                    "limit",
                    RowKind.INFO,
                    "Recovery" if recovering else "Request limit",
                    "Retrieve completed PNG · no generation submitted" if recovering
                    else "One PNG · 5 minutes · no automatic retry",
                    description="Only this saved job is checked; current settings/model must match."
                    if recovering else "",
                ),
                row("recover", "Recover and save image") if recovering
                else row("start", "Generate and save image"),
                row("back", "Back", control=RowControl.BACK),
            ]
            if not recovering:
                rows.insert(-2, PanelRow(
                    "cancellation", RowKind.INFO, "Cancellation",
                    "Queued and running jobs" if self.spec["evidence"]["cancel_generating"]
                    else "Queued jobs only",
                    description=cancellation_notice(self.spec["evidence"]),
                    value_tone="neutral" if self.spec["evidence"]["cancel_generating"]
                    else "warning",
                ))
        elif view == "generation-task":
            rows = [
                PanelRow(
                    "work",
                    RowKind.INFO,
                    "Saving settings"
                    if self.saving
                    else "Checking server cleanup"
                    if self.stopping
                    else "Generating image"
                    if self.task and self.task[3] == "run"
                    else "Recovering completed image"
                    if self.task and self.task[3] == "recover"
                    else "Checking image service",
                    f"{int(time.monotonic() - self.started)}s",
                ),
                PanelRow("job", RowKind.INFO, "Job", self.spec.get("id", "")),
                row(
                    "cancel",
                    "Cancel",
                    enabled=bool(self.task) and not self.stopping,
                    control=RowControl.CANCEL,
                ),
                row("back", "Back to Media", control=RowControl.BACK),
            ]
        else:
            rows = [
                PanelRow(
                    "result",
                    RowKind.INFO,
                    "Generation result",
                    self.result.get("message", "Image saved in Media"),
                ),
                PanelRow("artifact", RowKind.INFO, "Artifact", self.result.get("artifact", "")),
                PanelRow(
                    "job", RowKind.INFO, "Job", self.result.get("job", self.spec.get("id", ""))
                ),
                row("media", "Open Media"),
                row("again", "Generate another image"),
                row("back", "Back", control=RowControl.BACK),
            ]
            if (
                self.spec.get("id") and not self.result.get("artifact")
                and (self.result.get("recoverable") or self.spec.get("remote_id"))
            ):
                rows.insert(-3, row("recovery-review", "Review output recovery"))
        return PanelPage(
            "library:" + view,
            crumbs,
            tuple(rows),
            scrollable_body=True,
            scroll_wrapped_rows=True,
            align_info_values=True,
        )

    def handle(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("library-generation-")
        if kind == "back":
            if self.library.view in {"generation-cancel-review", "generation-forget-review"}:
                self.library.show("generation-receipt", "back")
            elif self.library.view == "generation-receipt":
                self.start("history")
            elif self.library.view == "generation-review":
                self.library.show("generation-form")
            elif self.library.view == "generation-recovery-review":
                self.library.show("generation-receipt" if self.receipt_view
                                  else "generation-result", "back")
            elif self.library.view == "generation-settings" and not self.return_settings:
                self.library.show("generation-form")
            elif self.return_settings and not self.busy:
                self.host._ai_defaults.show("home")
            else:
                self.library.artifacts.open("media")
        elif kind in {"media", "again"}:
            if kind == "media":
                self.library.artifacts.open("media")
            else:
                self.result = {}
                self.library.show("generation-form", "prompt")
        elif kind in {"history", "next-jobs", "previous-jobs"}:
            if kind != "history":
                self.offset = max(0, self.offset + (100 if kind == "next-jobs" else -100))
            self.return_settings = False
            self.start("history")
        elif kind.startswith("job:"):
            self.spec = {"id": kind.split(":", 1)[1]}
            self.abandon = False
            self.receipt_view = True
            self.start("review_job")
        elif kind in {"review-cancel", "review-forget"}:
            self.abandon = False
            self.library.show("generation-cancel-review" if kind == "review-cancel"
                              else "generation-forget-review", "back")
        elif kind == "abandon":
            self.abandon = not self.abandon
            self.library.show()
        elif kind in {"refresh-job", "cancel-saved", "forget-saved"}:
            self.start({"refresh-job": "refresh", "cancel-saved": "cancel",
                        "forget-saved": "forget"}[kind])
        elif kind == "settings":
            self.library.show("generation-settings")
        elif kind == "toggle":
            self.draft["enabled"] = not self.draft["enabled"]
            self.library.show()
        elif kind in {"endpoint", "prompt", "width", "height", "steps", "seed"}:
            self.host._begin_settings_input(
                kind.title(), "Enter a value; Escape returns", ("library", "generation-" + kind)
            )
            self.host._set_input(
                str(self.draft["endpoint"] if kind == "endpoint" else getattr(self, kind))
            )
        elif kind == "save":
            if self.busy:
                raise ValueError("Wait for image-service work to finish")
            if self.draft["enabled"] and (
                self.evidence.get("endpoint"),
                self.evidence.get("model"),
            ) != (self.draft["endpoint"], self.draft["model"]):
                raise ValueError(
                    "Test this endpoint and review the loaded model before enabling it"
                )
            identity = uuid.uuid4().hex
            update = ImageGenerationUpdate(
                self.host.session_id,
                identity,
                self.host.cfg,
                dict(self.draft),
                self.settings["revision"],
            )
            if not self.host._session_actions.submit(update):
                raise ValueError("Image settings could not be queued; Reload")
            self.saving, self.started = identity, time.monotonic()
            self.library.show("generation-task")
        elif kind == "cancel":
            self.stop()
        else:
            self.start(
                {"test": "inspect", "reload": "read", "review": "prepare", "start": "run",
                 "recovery-review": "recovery_review", "recover": "recover"}[kind]
            )

    def answer(self, value: str | None, field: str) -> None:
        if value is not None:
            if field == "endpoint":
                self.draft["endpoint"] = endpoint(value)
                self.draft["model"], self.evidence = "", {}
            elif field == "prompt":
                self.prompt = text(value, 2000)
            else:
                number = int(value)
                if (
                    field in {"width", "height"}
                    and (number % 64 or not 256 <= number <= 1024)
                    or field == "steps"
                    and not 1 <= number <= 50
                    or field == "seed"
                    and not -1 <= number <= 2**32 - 1
                ):
                    raise ValueError(
                        "Use size 256–1024 in multiples of 64; steps 1–50; seed -1 or 0–4294967295"
                    )
                setattr(self, field, number)
            self.spec = {}
        self.host._set_input("")
        self.library.show(
            "generation-settings" if field == "endpoint" else "generation-form", field
        )

    def start(self, operation: str) -> None:
        host = self.host
        if self.busy:
            raise ValueError("Wait for the current image-service operation")
        if operation in {"prepare", "run", "recovery_review", "recover"} and (
            host.running
            or host._watching_remote
            or host._setup_job is not None
            or host._skill_action_pending
            or self.library.knowledge.busy
            or self.library.research.busy
            or self.library.vision.busy
            or host._model_manager.busy
            or host._ai_defaults.utility
            or host._ai_defaults.preparing_utility
        ):
            raise ValueError("Finish the running model/setup task before generating an image")
        cfg = host.cfg
        self.roots = (str(cfg.config_dir), str(cfg.data_dir))
        request = {
            "kind": "image_generation",
            "operation": operation,
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "endpoint": self.draft["endpoint"],
            "prompt": self.prompt,
            "options": {
                "width": self.width,
                "height": self.height,
                "steps": self.steps,
                "seed": self.seed,
                "session": host.session_id,
            },
            "spec": self.spec,
            "id": self.spec.get("id", ""),
            "offset": self.offset,
            "abandon": self.abandon,
        }
        self.library.leave()
        identity = host._background_jobs.submit(
            KEY, request, timeout=DEADLINE + 30 if operation == "run" else 20, notify_cancel=True
        )
        self.task = (identity, host.session_id, self.library.scope, operation)
        self.started, self.stopping = time.monotonic(), False
        if operation == "cancel":
            self.stopping = True
        self.library.feedback = None
        self.library.show("generation-task", "cancel")

    def stop(self) -> None:
        if self.task and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(KEY)
            self.library.show()

    def cleanup(self, previous: tuple[str, str, str, str]) -> None:
        request = {
            "kind": "image_generation",
            "operation": "cancel",
            "id": self.spec["id"],
            "config_dir": self.roots[0],
            "data_dir": self.roots[1],
        }
        identity = self.host._background_jobs.submit(KEY, request, timeout=16, notify_cancel=True)
        self.task = (identity, previous[1], previous[2], "cancel")
        self.stopping = True
        if self.library.visible and self.active:
            self.library.show("generation-task")

    def stopped(self, identity: str) -> None:
        self.accept(
            identity, {"status": "cancelled", "message": "Image request cancelled locally"}, ""
        )

    def accept(self, identity: str, result: object, error: str) -> None:
        task = self.task
        if not task or task[0] != identity:
            return
        self.task, self.stopping = None, False
        data: dict[str, Any] = (
            result
            if not error and isinstance(result, dict)
            else {
                "status": "error",
                "message": "Image worker unavailable; check job status before retrying",
            }
        )
        if task[3] == "run" and data.get("status") != "complete":
            self.failure = (
                ""
                if data.get("status") == "cancelled"
                else data.get("message", "Image generation failed")
            )
            self.cleanup(task)
            return
        if task[1:3] != (self.host.session_id, self.library.scope):
            self.host._start_next()
            return
        visible = self.library.visible and self.active
        if data.get("status") == "error" and task[3] in {"review_job", "history"}:
            self.library.feedback = (data.get("message", "Job metadata unavailable"), "error")
            if visible:
                self.library.show("generation-history", "back")
        elif "items" in data:
            self.inventory = data
            if visible:
                self.library.show("generation-history", "back")
        elif "record" in data:
            self.spec = data["record"]
            if visible:
                self.library.show("generation-receipt", "back")
        elif task[3] in {"refresh", "forget"} or task[3] == "cancel" and self.receipt_view:
            self.result = data
            self.library.feedback = (data.get("message", "Job updated"),
                                     "error" if data.get("status") == "error" else "neutral")
            if data.get("status") != "error" and visible:
                if task[3] == "forget":
                    self.offset = 0
                    # A removed receipt must not leave its old ID filter hiding
                    # the now-empty inventory or other remaining jobs.
                    self.host._panel_states.pop("library:generation-history", None)
                self.start("history" if task[3] == "forget" else "review_job")
                return
            if visible:
                self.library.show("generation-receipt", "back")
        elif "settings" in data:
            self.settings = self.draft = data["settings"]
            self.draft = dict(self.settings)
            if visible:
                self.library.show(
                    "generation-settings" if self.return_settings else "generation-form"
                )
        elif "evidence" in data:
            self.evidence = data["evidence"]
            self.draft["model"] = self.evidence["model"]
            if visible:
                self.library.feedback = ("Connection reached; loaded model verified", "success")
                self.library.show("generation-settings", "save")
        elif "spec" in data:
            self.spec = data["spec"]
            if visible:
                self.library.show(
                    "generation-recovery-review" if task[3] == "recovery_review"
                    else "generation-review", "back"
                )
        elif (
            data.get("status") == "complete"
            or task[3] in {"cancel", "recover", "recovery_review"}
        ):
            self.result = data
            failed = bool(self.failure) or data.get("status") == "error"
            if self.failure:
                self.result["message"] = (
                    self.failure + ". " + data.get("message", "Server cleanup unconfirmed")
                )
                self.failure = ""
            self.library.feedback = (
                ("Image generation failed", "error")
                if failed
                else ("Image saved in Media", "success")
                if data.get("artifact")
                else ("Server cleanup unconfirmed", "warning")
                if data.get("status") in {"unknown", "running_remote"}
                else (data.get("message", "Image request stopped"), "neutral")
            )
            if visible:
                self.library.show("generation-result", "back")
            else:
                self.host._append(
                    "\n[image] Generation finished; inspect its job and Media output.\n"
                )
        elif visible:
            self.library.feedback = (
                data.get("message", "Image service unavailable"),
                "neutral" if data.get("status") == "cancelled" else "error",
            )
            self.library.show("generation-settings" if self.return_settings else "generation-form")
        self.host._start_next()

    def saved(self, update: ImageGenerationUpdate, result: object, error: str) -> None:
        if update.identity != self.saving:
            return
        self.saving = ""
        if update.session_id != self.host.session_id:
            self.host._start_next()
            return
        if isinstance(result, dict) and not error:
            self.settings, self.draft = result, dict(result)
            self.library.feedback = ("Image generation settings saved", "success")
        else:
            self.library.feedback = (error or "Image settings save unconfirmed; Reload", "error")
        if self.library.visible and self.active:
            self.library.show("generation-settings", "back")
        self.host._start_next()

    def poll(self) -> None:
        now = time.monotonic()
        if (
            self.busy
            and self.library.visible
            and self.library.view == "generation-task"
            and now - self.last_poll > 0.5
        ):
            self.last_poll = now
            self.library.show()

    def finish_shutdown(self) -> str:
        """Called after local workers are reaped; cleanup never uses a new session's root."""
        if not self.task or self.task[3] not in {"run", "cancel"}:
            return ""
        from pathlib import Path
        from types import SimpleNamespace

        from .generation_commands import work

        cfg = SimpleNamespace(config_dir=Path(self.roots[0]), data_dir=Path(self.roots[1]))
        result = work(cfg, "cancel", id=self.spec["id"])
        self.task = None
        return result.get("message", "Image service cleanup unconfirmed; inspect job status")
