"""Model Manager dependency diagnostics and explicit local CPU build reviews."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

from klaude_core.model_dependencies import BUILD_TIMEOUT
from klaude_core.model_setup_removal import REMOVE_TIMEOUT

from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

READ = "model-manager:dependencies-read"
WORK = "model-manager:dependencies-work"


def action(key: str, label: str, value: str = "", **kwargs) -> PanelRow:
    return PanelRow(
        key, RowKind.ACTION, label, value, action=PanelAction("dependency-" + key), **kwargs
    )


def back(target: str) -> PanelRow:
    return PanelRow(
        "back",
        RowKind.NAVIGATION,
        "Back",
        control=RowControl.BACK,
        action=PanelAction("dependency-back", target),
    )


class DependencyPanel:
    def __init__(self, manager: Any):
        self.manager = manager
        self.host = manager.host
        self.view = "home"
        self.engine = "llama_cpp"
        self.executable = "llama-server"
        self.source = ""
        self.jobs = 2
        self.profile = "cpu"
        self.sources: dict[str, str] = {}
        self.architectures = ""
        self.host_compiler = ""
        self.python = str(Path(sys.executable).resolve())
        self.revision = 0
        self.read: tuple | None = None
        self.evidence: dict = {}
        self.removal: dict = {}
        self.report: dict = {}
        self.items: list[dict] = []
        self.task: dict | None = None
        self.result: dict = {}
        self.stage = ""
        self.logs = ""
        self.stopping = False
        self.feedback: tuple[str, str] | None = None

    @property
    def busy(self) -> bool:
        return self.task is not None

    @property
    def active(self) -> bool:
        return str(self.host._choice_kind).startswith("model manager dependencies")

    @property
    def title(self) -> str:
        return {"cpu": "CPU build", "cuda": "CUDA build", "vllm_cuda": "vLLM installation"}[
            self.profile
        ]

    def show(self, view: str | None = None, focus: str = "", *, fresh: bool = False) -> None:
        if view:
            self.view = view
        page = self.page()
        if fresh and (state := self.host._panel_states.get(page.id)):
            state.filter("")
            state.search_active = False
        self.host._open_panel(page, "model manager dependencies " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def page(self) -> PanelPage:
        crumbs: tuple[str, ...] = ("Model Manager", "This machine", "Dependencies")
        if self.view == "home":
            rows = [
                action("inspect", "Inspect dependencies"),
                action("engine", "Engine", self.engine),
                action("executable", "Executable", self.executable),
                action("form", "Build llama.cpp CPU engine", enabled=not self.manager.busy),
                action("cuda", "Build llama.cpp CUDA engine", enabled=not self.manager.busy),
                action("vllm", "Install vLLM from wheels", enabled=not self.manager.busy),
                action("inventory", "Built/installed engines"),
                PanelRow(
                    "scope",
                    RowKind.INFO,
                    "Local diagnostics and separate engine environments",
                    description="Builds and removals are reviewed; "
                    "originals and defaults are retained.",
                ),
            ]
            if self.report:
                tested = self.report["engine"]
                rows += [
                    PanelRow(
                        "engine-status",
                        RowKind.INFO,
                        "Engine test",
                        tested["status"],
                        tested.get("message", tested.get("executable", "")),
                    ),
                    PanelRow("columns", RowKind.TABLE_HEADER, "TOOL"),
                ]
                rows += [
                    PanelRow(
                        "tool:" + t["name"],
                        RowKind.INFO,
                        t["name"],
                        t["status"],
                        t.get("version", ""),
                        section_id="tools",
                    )
                    for t in self.report["tools"]
                ]
            if self.task:
                rows.insert(0, action("progress", "Active build", self.stage))
            rows += [back("manager")]
        elif self.view == "form":
            crumbs += (self.title,)
            rows = [
                action(
                    "source",
                    "Wheel folder" if self.profile == "vllm_cuda" else "Local source checkout",
                    self.source or "Enter absolute path",
                ),
            ]
            if self.profile == "vllm_cuda":
                rows += [action("python", "Python interpreter", self.python)]
            else:
                rows += [action("jobs", "Build jobs", str(self.jobs))]
            if self.profile == "cuda":
                rows += [
                    action(
                        "architectures", "CUDA architectures", self.architectures or "Auto detect"
                    ),
                    action(
                        "host_compiler",
                        "CUDA host compiler",
                        self.host_compiler or "Default C++ compiler",
                    ),
                ]
            rows += [
                action(
                    "review",
                    "Review installation" if self.profile == "vllm_cuda" else "Review build",
                    enabled=bool(self.source) and not self.busy,
                ),
                PanelRow(
                    "snapshot",
                    RowKind.INFO,
                    "Uses trusted local wheels"
                    if self.profile == "vllm_cuda"
                    else "Builds the committed HEAD snapshot",
                    description="Installs one version per package, including CUDA PyTorch, "
                    "into a new environment without downloads. Package checks execute code."
                    if self.profile == "vllm_cuda"
                    else "Uncommitted edits are excluded. Build instructions execute "
                    "code from that commit; choose a source you trust.",
                ),
                back("home"),
            ]
        elif self.view == "review":
            crumbs += (self.title, "Review")
            rows = [
                PanelRow("source", RowKind.INFO, "Source", self.evidence.get("source", "")),
                PanelRow(
                    "commit", RowKind.INFO, "Source revision", self.evidence.get("commit", "")
                ),
            ]
            if self.profile == "vllm_cuda":
                rows += [
                    PanelRow(
                        "version", RowKind.INFO, "vLLM version", self.evidence.get("version", "")
                    ),
                    PanelRow("python", RowKind.INFO, "Python interpreter", self.python),
                    PanelRow(
                        "count",
                        RowKind.INFO,
                        "Reviewed wheels",
                        str(len(self.evidence.get("wheels", []))),
                    ),
                ]
            else:
                rows += [PanelRow("jobs", RowKind.INFO, "Build jobs", str(self.jobs))]
            if self.profile == "cuda":
                settings = self.evidence.get("cuda", {})
                rows += [
                    PanelRow(
                        "targets",
                        RowKind.INFO,
                        "CUDA architectures",
                        settings.get("architectures", "Unknown"),
                    ),
                    PanelRow(
                        "host",
                        RowKind.INFO,
                        "CUDA host compiler",
                        settings.get("host_compiler", "Unknown"),
                    ),
                ]
            rows += [
                PanelRow(
                    "profile",
                    RowKind.INFO,
                    "New private vLLM environment"
                    if self.profile == "vllm_cuda"
                    else self.profile.upper() + " server with static llama/ggml libraries",
                    description="Installs hash-checked local wheels and runs package checks. "
                    "Retains existing environments and partial installs. "
                    "Engine help verification does not certify GPU inference."
                    if self.profile == "vllm_cuda"
                    else "Runs the selected commit's CMake/compiler instructions "
                    "inside a new private build directory. Retains failed/partial builds. "
                    "Selecting and serving the executable are separate actions."
                    + (" GPU inference remains untested." if self.profile == "cuda" else ""),
                ),
                action(
                    "build",
                    "Install vLLM"
                    if self.profile == "vllm_cuda"
                    else "Build " + self.profile.upper() + " engine",
                    enabled=not self.manager.busy,
                ),
                back("form"),
            ]
        elif self.view == "progress":
            removing = (self.task or self.result).get("operation") == "remove"
            installing = (self.task or self.result).get("profile", self.profile) == "vllm_cuda"
            crumbs += ("Removal" if removing else "Installation" if installing else "Build",)
            rows = (
                [
                    action(
                        "cancel",
                        "Cancel removal"
                        if removing
                        else "Cancel installation"
                        if installing
                        else "Cancel build",
                        enabled=not self.stopping,
                    )
                ]
                if self.busy
                else []
            )
            if self.result.get("state") == "ready":
                rows += [action("serve", "Use in Serve models")]
            if self.result.get("id") and not self.busy and self.result.get("state") != "removed":
                rows += [action("remove-review", "Review removal", enabled=not self.manager.busy)]
            rows += [
                action(
                    "logs",
                    "Setup logs",
                    enabled=bool(self.task or self.result)
                    and self.result.get("state") != "removed",
                ),
                PanelRow(
                    "stage",
                    RowKind.INFO,
                    "Status",
                    "Waiting for cleanup" if self.stopping else self.stage or "No active setup",
                ),
                PanelRow(
                    "directory",
                    RowKind.INFO,
                    "Setup directory",
                    str(
                        self.host.cfg.data_dir
                        / "model-builds"
                        / (self.task or self.result).get("id", "")
                    ),
                ),
                PanelRow(
                    "exe",
                    RowKind.INFO,
                    "Verified executable",
                    self.result.get("executable", "Not available")
                    if self.result.get("state") == "ready"
                    else "Not available",
                ),
                PanelRow(
                    "retain",
                    RowKind.INFO,
                    "Setup has been removed"
                    if self.result.get("state") == "removed"
                    else "Removal may leave partial files"
                    if removing
                    else "Cancellation retains partial setup files",
                    description="Original sources, wheel folders and models are independent."
                    if self.result.get("state") == "removed"
                    else "Owned setup and checks stop before new model work starts.",
                ),
                back("home"),
            ]
        elif self.view == "remove-review":
            from .model_manager import size

            crumbs += ("Built/installed engines", "Remove setup")
            rows = [
                PanelRow("identity", RowKind.INFO, "Setup ID", self.removal.get("id", "")),
                PanelRow("path", RowKind.INFO, "Directory", self.removal.get("directory", "")),
                PanelRow("profile", RowKind.INFO, "Recipe", self.removal.get("profile", "")),
                PanelRow(
                    "size",
                    RowKind.INFO,
                    "Estimated storage",
                    size(self.removal.get("bytes", 0)),
                ),
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Permanent removal",
                    description="Deletes all files in this setup directory. Original source/wheel "
                    "folders, external model weights, defaults and server history are retained.",
                ),
            ]
            rows += [
                PanelRow("blocked:" + str(i), RowKind.INFO, "Cannot remove yet", description=reason)
                for i, reason in enumerate(self.removal.get("blockers", []))
            ]
            rows += [
                PanelRow(
                    "warning:" + str(i), RowKind.INFO, "Process inspection", description=warning
                )
                for i, warning in enumerate(self.removal.get("warnings", []))
            ]
            rows += [
                action(
                    "remove",
                    "Remove setup",
                    enabled=bool(self.removal)
                    and not self.removal.get("blockers")
                    and not self.manager.busy,
                ),
                back("progress"),
            ]
        elif self.view == "logs":
            crumbs += ("Setup logs",)
            rows = [
                action("logs", "Reload logs"),
                PanelRow(
                    "log",
                    RowKind.INFO,
                    "Latest setup output",
                    description=self.logs or "No output available",
                ),
                back("progress"),
            ]
        else:
            crumbs += ("Built/installed engines",)
            rows = [
                action("inventory", "Reload setups"),
                PanelRow("columns", RowKind.TABLE_HEADER, "COMMIT"),
            ]
            rows += [
                PanelRow(
                    "built:" + b["id"],
                    RowKind.ACTION,
                    b["commit"][:12],
                    b["state"].title(),
                    b.get("profile", "cpu") + " · " + b.get("executable", b["source"]),
                    section_id="builds",
                    action=PanelAction("dependency-select", b["id"]),
                    enabled=not self.busy,
                )
                for b in self.items
            ]
            if not self.items:
                rows += [PanelRow("empty", RowKind.INFO, "No retained setups")]
            rows += [back("home")]
        if self.read:
            rows.insert(0, action("cancel-check", "Cancel check"))
        return PanelPage(
            "dependencies:"
            + self.view
            + (":" + self.profile if self.view in {"form", "review"} else ""),
            crumbs,
            tuple(rows),
            column_headers=("TOOL", "STATUS", "VERSION")
            if self.view == "home" and self.report
            else ("REVISION", "STATE", "RECIPE / PATH")
            if self.view == "inventory"
            else None,
            table_section_id="tools" if self.view == "home" else "builds",
            scroll_wrapped_rows=self.view in {"logs", "review", "remove-review"},
            scrollable_body=self.view in {"logs", "review", "remove-review"},
        )

    def open(self) -> None:
        self.show("home")
        self.load("inspect")

    def leave(self) -> None:
        self.host._background_jobs.cancel(READ)
        self.read = None

    def request(self, operation: str, **values) -> dict:
        return {
            "kind": "model_dependencies",
            "operation": operation,
            "data_dir": str(self.host.cfg.data_dir),
            "config_dir": str(self.host.cfg.config_dir),
            "current": self.manager.current(),
            "engine": self.engine,
            "executable": self.executable,
            "source": self.source,
            "jobs": self.jobs,
            "profile": self.profile,
            "architectures": self.architectures,
            "host_compiler": self.host_compiler,
            "python": self.python,
            "owner": os.getpid(),
            "id": (self.task or self.result).get("id", ""),
            **values,
        }

    def load(self, operation: str) -> None:
        identity = self.host._background_jobs.submit(READ, self.request(operation), timeout=40)
        self.read = identity, self.manager.scope, self.revision, operation
        self.feedback = ("Checking local dependencies…", "neutral")
        self.show()

    def accept(self, key: str, identity: str, result: Any, error: str) -> None:
        if key == WORK:
            if not self.task or self.task["worker"] != identity:
                return
            task = self.task
            self.task = None
            self.stopping = False
            success = not error and isinstance(result, dict) and result.get("status") == "ok"
            if task["scope"] == self.manager.scope:
                removing = task.get("operation") == "remove"
                self.result = (
                    {"id": task["id"], "state": "removed", "operation": "remove"}
                    if removing and success
                    else result["build"]
                    if success
                    else {"id": task["id"]}
                )
                if removing and success:
                    self.items = [b for b in self.items if b["id"] != task["id"]]
                self.stage = "Complete" if success else "Outcome unconfirmed" if error else "Failed"
                if task["revision"] == self.revision and not self.host._settings_input_request:
                    self.feedback = (
                        (result if isinstance(result, dict) else {}).get(
                            "message",
                            "Removal outcome unconfirmed; reload built/installed engines"
                            if removing
                            else "Setup outcome unconfirmed; reload builds",
                        ),
                        "success" if success else "warning" if error else "error",
                    )
                if self.active and not self.host._settings_input_request:
                    self.show()
            self.host._start_next()
            return
        if not self.read or self.read[0] != identity:
            return
        _, scope, revision, operation = self.read
        self.read = None
        if scope != self.manager.scope or revision != self.revision:
            return
        if error or not isinstance(result, dict) or result.get("status") == "error":
            self.feedback = (
                (result if isinstance(result, dict) else {}).get(
                    "message", "Inspection failed; retry"
                ),
                "error",
            )
        elif operation == "inspect":
            self.report = result
            self.feedback = ("Local dependencies inspected; no installation performed", "neutral")
        elif operation == "prepare":
            self.evidence = result["evidence"]
            self.feedback = None
            if self.active and not self.host._settings_input_request:
                self.show("review", "back", fresh=True)
            return
        elif operation == "prepare_remove":
            self.removal = result["evidence"]
            self.feedback = (
                ("Setup is still in use", "warning") if self.removal["blockers"] else None
            )
            if not self.feedback and self.removal.get("warnings"):
                self.feedback = ("Partial checks", "warning")
            if self.active and not self.host._settings_input_request:
                self.show("remove-review", "back", fresh=True)
            return
        elif operation == "inventory":
            self.items = result["builds"]
            self.feedback = None
        elif operation == "logs":
            self.logs = result["logs"]
            self.feedback = None
        if self.active and not self.host._settings_input_request:
            self.show()

    def action(self, event: PanelAction) -> None:
        kind = event.kind.removeprefix("dependency-")
        if kind == "back":
            self.leave()
            self.revision += 1
            if event.target == "manager":
                self.manager.show("home", "dependencies")
            else:
                self.show(event.target)
        elif kind == "engine":
            self.engine = "vllm" if self.engine == "llama_cpp" else "llama_cpp"
            self.executable = "vllm" if self.engine == "vllm" else "llama-server"
            self.report = {}
            self.revision += 1
            self.show()
        elif kind in {"source", "jobs", "executable", "architectures", "host_compiler", "python"}:
            self.host._begin_settings_input(
                kind.replace("_", " ").title(),
                "Private input · Escape returns",
                ("dependency-field", kind),
            )
            self.host._set_input(str(getattr(self, kind)))
        elif kind in {"form", "cuda", "vllm"}:
            if self.manager.busy:
                raise ValueError("Finish active setup before opening another recipe")
            self.sources[self.profile] = self.source
            self.profile = {"form": "cpu", "cuda": "cuda", "vllm": "vllm_cuda"}[kind]
            self.source = self.sources.get(self.profile, "")
            self.revision += 1
            self.evidence = {}
            self.feedback = None
            self.show("form", fresh=True)
        elif kind == "progress":
            self.feedback = None
            self.show(kind)
        elif kind == "review":
            self.load("prepare")
        elif kind == "remove-review":
            self.removal = {}
            self.load("prepare_remove")
        elif kind in {"inspect", "inventory"}:
            if kind == "inventory":
                self.show("inventory")
            self.load(kind)
        elif kind == "logs":
            self.show("logs")
            self.load("logs")
        elif kind == "cancel":
            self.stop()
        elif kind == "cancel-check":
            self.leave()
            self.revision += 1
            self.feedback = ("Dependency check cancelled", "neutral")
            self.show()
        elif kind in {"build", "remove"}:
            if self.host._session_action_is_busy() or self.manager.busy:
                self.feedback = ("Finish active model/setup work first", "warning")
                self.show()
                return
            if kind == "remove" and (not self.removal or self.removal.get("blockers")):
                raise ValueError("Review an unused setup before removal")
            identity = self.removal["id"] if kind == "remove" else uuid.uuid4().hex
            self.revision += 1
            worker = self.host._background_jobs.submit(
                WORK,
                self.request(
                    kind, id=identity, evidence=self.removal if kind == "remove" else self.evidence
                ),
                timeout=REMOVE_TIMEOUT if kind == "remove" else BUILD_TIMEOUT,
                notify_cancel=True,
            )
            self.task = {
                "worker": worker,
                "id": identity,
                "scope": self.manager.scope,
                "revision": self.revision,
                "profile": self.profile,
                "operation": kind,
            }
            self.result = {}
            self.stage = "Removing setup" if kind == "remove" else "Starting " + self.title.lower()
            self.feedback = None
            self.show("progress", fresh=True)
        elif kind == "select":
            self.revision += 1
            self.result = next(b for b in self.items if b["id"] == event.target)
            self.stage = self.result["state"].title()
            self.show("progress")
        elif kind == "serve":
            if self.result.get("state") != "ready":
                raise ValueError("Choose a verified build before opening Serve models")
            self.manager.serving.new_draft(
                executable=self.result["executable"],
                focus="field:model",
                engine=self.result.get("engine", "llama_cpp"),
            )

    def answer(self, field: str, value: str | None) -> None:
        if value is not None:
            parsed: Any = int(value) if field == "jobs" else value.strip()
            if field == "jobs" and not 1 <= parsed <= 8:
                raise ValueError("Build jobs must be 1–8")
            if field != "jobs" and (
                len(parsed) > 4096
                or parsed
                and not parsed.isprintable()
                or not parsed
                and field not in {"architectures", "host_compiler"}
            ):
                raise ValueError("Enter a printable path")
            setattr(self, field, parsed)
            self.revision += 1
            self.evidence = {}
            if field == "executable":
                self.report = {}
        self.show()

    def stop(self) -> None:
        if self.task and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(WORK)
            if self.active and not self.host._settings_input_request:
                self.show()

    def stopped(self, identity: str) -> None:
        if self.task and self.task["worker"] == identity:
            task = self.task
            self.task = None
            self.stopping = False
            if task["scope"] == self.manager.scope:
                self.result = {"id": task["id"]}
                self.stage = "Cancelled"
                if task["revision"] == self.revision and not self.host._settings_input_request:
                    self.feedback = (
                        "Removal cancelled; some files may have been removed; reload builds"
                        if task.get("operation") == "remove"
                        else "Setup cancelled; partial files retained",
                        "warning",
                    )
                if self.active and not self.host._settings_input_request:
                    self.show()
            self.host._start_next()

    def progress(self, identity: str, value: dict) -> None:
        if (
            self.task
            and self.task["worker"] == identity
            and self.task["scope"] == self.manager.scope
        ):
            self.stage = value["stage"]
            if self.active and not self.host._settings_input_request:
                self.show()
