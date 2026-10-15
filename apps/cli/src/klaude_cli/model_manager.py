"""Model Manager workspace: native lifecycle, typed controls and owned progress."""

from __future__ import annotations

import os
import time
from typing import Any

from klaude_core.ollama_manager import PULL_TIMEOUT, model_name

from .dependency_panel import DependencyPanel
from .serving_panel import ServingPanel
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind
from .ssh_panel import SSHPanel

PREFIX = "model-manager-"
READ = "model-manager:read"
WORK = "model-manager:work"


def row(
    identity: str, label: str, value: str = "", *, target: str = "",
    kind: RowKind = RowKind.ACTION, **kwargs,
) -> PanelRow:
    return PanelRow(
        identity,
        kind,
        label,
        value,
        action=PanelAction(PREFIX + identity, target),
        **kwargs,
    )


def back(target: str) -> PanelRow:
    return row(
        "back",
        "Back" if target != "close" else "Close",
        target=target,
        control=RowControl.BACK if target != "close" else RowControl.CLOSE,
    )


def size(value: Any) -> str:
    if type(value) is not int:
        return "Unknown"
    for scale, unit in ((1024**3, "GiB"), (1024**2, "MiB"), (1024, "KiB")):
        if value >= scale:
            return f"{value / scale:.1f} {unit}"
    return f"{value} B"


def worker_request(cfg: Any, operation: str, **values: Any) -> dict:
    # Inherited credentials cross only the existing private worker request pipe.
    variable = values.pop("key_env", "")
    keys = {
        k: v
        for k in ("HUGGINGFACE_API_KEY", variable)
        if k and (v := os.environ.get(k)) is not None and len(v) <= 8192
    }
    return {
        "kind": "model_manager",
        "operation": operation,
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "environment_keys": keys,
        **values,
    }


class ModelManager:
    def __init__(self, host: Any):
        self.host = host
        self.view = "home"
        self.parent = "close"
        self.connections: list[dict] = []
        self.endpoint = "default-ollama"
        self.snapshots: dict[str, dict] = {}
        self.read: tuple | None = None
        self.task: dict | None = None
        self.model = ""
        self.query = ""
        self.results: list[dict] = []
        self.hardware: dict = {}
        self.offset = 0
        self.filter = "all"
        self.sort = "name"
        self.feedback: tuple[str, str] | None = None
        self.review: dict = {}
        self.progress: dict = {}
        self.stopping = False
        self.last_task: dict = {}
        self.owner_return = False
        self.serving = ServingPanel(self)
        self.dependencies = DependencyPanel(self)
        self.ssh = SSHPanel(self)

    @property
    def active(self) -> bool:
        return str(self.host._choice_kind).startswith("model manager ")

    @property
    def busy(self) -> bool:
        return (self.task is not None or self.serving.busy
                or self.dependencies.busy or self.ssh.setup.busy)

    @property
    def cancelling(self) -> bool:
        return (self.stopping or self.dependencies.stopping or bool(self.serving.stopping)
                or self.ssh.setup.stopping)

    @property
    def scope(self) -> tuple:
        return self.host.session_id, str(self.host.cfg.data_dir)

    def current(self) -> str:
        info = getattr(self.host.agent, "model_info", None)
        return info.ref if info is not None else getattr(self.host.agent, "model", "")

    def open(self, parent: str = "close") -> None:
        self.parent = parent
        self.owner_return = False
        self.show("home")
        self.load("connections")

    def leave(self) -> None:
        self.ssh.leave()
        self.dependencies.leave()
        self.serving.leave()
        self.host._background_jobs.cancel(READ)
        self.read = None

    def show(self, view: str | None = None, focus: str = "", *, fresh: bool = False) -> None:
        if view is not None:
            self.view = view
        page = self.page()
        if fresh or (self.view == "review" and focus == "back"):
            state = getattr(self.host, "_panel_states", {}).get(page.id)
            if state is not None:
                state.filter("")
                state.search_active = False
        self.host._open_panel(page, "model manager " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def load(self, operation: str, *, preserve: bool = False) -> None:
        record = next((c for c in self.connections if c["id"] == self.endpoint), {})
        request = worker_request(
            self.host.cfg,
            operation,
            endpoint=self.endpoint,
            current=self.current(),
            query=self.query,
            key_env=record.get("key_env", ""),
        )
        identity = self.host._background_jobs.submit(READ, request, timeout=20)
        self.read = (
            identity,
            self.scope,
            self.endpoint,
            operation,
            self.feedback if preserve else None,
        )
        if not preserve:
            self.feedback = (
                "Checking…" if operation != "search" else "Searching GGUF models…",
                "neutral",
            )
        self.show()

    def snapshot(self) -> dict:
        return self.snapshots.get(self.endpoint, {})

    def page(self) -> PanelPage:
        snapshot = self.snapshot()
        endpoint = snapshot.get("endpoint") or next(
            (c for c in self.connections if c["id"] == self.endpoint), {}
        )
        title = endpoint.get("name", "Choose Ollama endpoint")
        models = snapshot.get("models")
        running = snapshot.get("running")
        loaded = {m["name"] for m in running or []}
        selected = next((m for m in models or [] if m["name"] == self.model), None)
        crumbs = ["Model Manager"]
        rows: list[PanelRow] = []
        if self.view == "home":
            rows = [
                row("endpoints", "Endpoint", title),
                row(
                    "installed",
                    "Installed models",
                    str(len(models)) if models is not None else "Not loaded",
                ),
                row("download", "Download model", enabled=bool(endpoint)),
                row(
                    "discover",
                    "Discover models",
                    description="Search Hugging Face GGUF repositories",
                ),
                row(
                    "service",
                    "Service status",
                    "Cached status"
                    if snapshot.get("stale")
                    else "Reachable"
                    if models is not None
                    else "Unknown",
                ),
                row("hardware", "Hardware", description="This machine; server hardware may differ"),
                row("serve", "Serve models", description="Manage installed local engines"),
                row("dependencies", "Dependencies",
                    description="Inspect tools or build a CPU engine"),
                row("ssh", "Servers", description="SSH configuration and remote diagnostics"),
            ]
            if self.task:
                rows.insert(1, row("progress", "Active operation", self.task["model"]))
            rows += [back(self.parent)]
        elif self.view == "endpoints":
            crumbs += ["Endpoints"]
            rows = [
                row(
                    "endpoint:" + c["id"],
                    c["name"],
                    c["base_url"],
                    target=c["id"],
                    status="Current" if c["id"] == self.endpoint else "",
                )
                for c in self.connections
            ]
            if not rows:
                rows = [
                    PanelRow(
                        "empty",
                        RowKind.INFO,
                        "No enabled native Ollama endpoint",
                        description="Add one in Settings → Models → Add Models",
                    )
                ]
            rows += [row("reload", "Reload endpoints", target="connections"), back("home")]
        elif self.view == "installed":
            crumbs += [title, "Installed models"]
            rows = [
                row("filter", "Filter", "Loaded" if self.filter == "loaded" else "All"),
                row("sort", "Sort", self.sort.title()),
                row("reload", "Reload models", target="inventory"),
                row("download", "Download model"),
            ]
            if snapshot.get("checked_at"):
                age = max(0, int(time.time() - snapshot["checked_at"]))
                rows += [
                    PanelRow(
                        "snapshot",
                        RowKind.INFO,
                        "Snapshot",
                        f"{age}s ago" + (" · stale" if snapshot.get("stale") else ""),
                    )
                ]
            if models is None:
                rows += [
                    PanelRow(
                        "empty", RowKind.INFO, "Installed inventory unavailable; Reload models"
                    )
                ]
            else:
                if running is None:
                    rows += [PanelRow(
                        "loaded-status", RowKind.INFO, "Loaded-model status", "Unknown",
                        "Reload models to check the server's loaded state.",
                    )]
                listed = [m for m in models if self.filter == "all" or m["name"] in loaded]
                listed.sort(
                    key=(lambda m: -(m.get("size") or 0))
                    if self.sort == "size"
                    else (lambda m: m.get("modified", ""))
                    if self.sort == "recent"
                    else (lambda m: m["name"].casefold()),
                    reverse=self.sort == "recent",
                )
                if self.offset:
                    rows += [row("previous", "Previous page")]
                if len(listed) > self.offset + 100:
                    rows += [row("next", "Next page")]
                rows += [PanelRow("columns", RowKind.TABLE_HEADER, "MODEL", "SIZE / STATE")]
                rows += [
                    row(
                        "model:" + m["name"],
                        m["name"],
                        size(m["size"]) + (" · Loaded" if m["name"] in loaded else ""),
                        target=m["name"],
                        kind=RowKind.NAVIGATION,
                        section_id="models",
                        description=" · ".join(
                            v for v in (m["parameters"], m["quantization"]) if v
                        ),
                    )
                    for m in listed[self.offset : self.offset + 100]
                ]
                if not listed:
                    rows += [PanelRow(
                        "empty", RowKind.INFO,
                        "Loaded-model inventory unavailable; Reload models"
                        if self.filter == "loaded" and running is None
                        else "No matching installed models",
                    )]
            rows += [back("home")]
        elif self.view == "detail":
            crumbs += [title, "Model"]
            if selected:
                blocked = snapshot.get("bindings", {}).get(self.model, [])
                rows = [
                    row("update", "Download / update", description="Review this installed tag"),
                    row(
                        "delete",
                        "Delete downloaded model",
                        enabled=not self.busy,
                        description="Review deletion on this server; keeps the endpoint",
                    ),
                    PanelRow("name", RowKind.INFO, "Model", selected["name"]),
                    PanelRow("size", RowKind.INFO, "Stored size", size(selected["size"])),
                    PanelRow(
                        "parameters",
                        RowKind.INFO,
                        "Parameters",
                        selected["parameters"] or "Unknown",
                    ),
                    PanelRow(
                        "quantization",
                        RowKind.INFO,
                        "Quantization",
                        selected["quantization"] or "Unknown",
                    ),
                    PanelRow(
                        "bindings",
                        RowKind.INFO,
                        "Selections",
                        ", ".join(blocked) or "None observed",
                    ),
                    PanelRow("digest", RowKind.INFO, "Digest", selected["digest"]),
                ]
            else:
                rows = [
                    PanelRow(
                        "empty", RowKind.INFO, "Model no longer in the inventory; Reload models"
                    )
                ]
            rows += [back("installed")]
        elif self.view in {"download", "discover"}:
            crumbs += ["Download" if self.view == "download" else "Discover"]
            if self.view == "download":
                rows = [
                    row("model-input", "Model", self.model or "Enter model:tag"),
                    PanelRow(
                        "server", RowKind.INFO, "Download to", title, endpoint.get("base_url", "")
                    ),
                    row(
                        "pull-review", "Review download", enabled=bool(self.model) and not self.busy
                    ),
                    PanelRow(
                        "purpose",
                        RowKind.INFO,
                        "Ollama downloads and stores the model",
                        description="No model is loaded or selected automatically. "
                        "Private Hugging Face pulls use the Ollama server's own account access.",
                    ),
                    back("home"),
                ]
            else:
                rows = [
                    row("query", "Search query", self.query or "Enter a model query"),
                    row("search", "Search Hugging Face", enabled=bool(self.query)),
                    row(
                        "hf-credentials",
                        "Hugging Face credentials",
                        description="Manage Hugging Face API key",
                    ),
                ]
                if self.results:
                    rows += [PanelRow("columns", RowKind.TABLE_HEADER, "REPOSITORY", "DOWNLOADS")]
                    rows += [
                        row(
                            "repo:" + r["id"],
                            r["id"],
                            str(r.get("downloads") or 0),
                            target=r["id"],
                            kind=RowKind.NAVIGATION,
                            section_id="results",
                            description=r.get("summary", ""),
                        )
                        for r in self.results
                    ]
                rows += [back("home")]
        elif self.view == "review":
            action = self.review.get("operation", "pull")
            crumbs += ["Review deletion" if action == "delete" else "Review download"]
            blockers = self.review.get("blockers", [])
            rows = [
                PanelRow("name", RowKind.INFO, "Model", self.review.get("model", "")),
                PanelRow("server", RowKind.INFO, "Server", title, endpoint.get("base_url", "")),
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Delete this downloaded model from the selected server"
                    if action == "delete"
                    else "Download this tag on the selected server",
                    description="Connections, role selections and session history are retained.",
                ),
                PanelRow("deadline", RowKind.INFO, "Request deadline", "30 minutes"),
                row(
                    "confirm",
                    "Delete model" if action == "delete" else "Start download",
                    enabled=not blockers and not self.busy,
                ),
            ]
            if blockers:
                rows.insert(
                    -1,
                    PanelRow(
                        "blocked",
                        RowKind.INFO,
                        "Cannot delete yet" if action == "delete" else "Cannot download yet",
                        ", ".join(blockers),
                        "Resolve the listed blockers, then reload status.",
                    ),
                )
            rows += [back("detail" if action == "delete" else "download")]
        elif self.view == "progress":
            crumbs += ["Operation"]
            task = self.task or self.last_task
            amount = ""
            if self.progress.get("completed") is not None:
                amount = size(self.progress["completed"]) + " / " + size(self.progress.get("total"))
            rows = [
                PanelRow("model", RowKind.INFO, "Model", task.get("model", self.model)),
                PanelRow("target", RowKind.INFO, "Server", task.get("name", title)),
                PanelRow(
                    "stage",
                    RowKind.INFO,
                    "Stage",
                    "Cancelling…"
                    if self.stopping
                    else self.progress.get("stage", "Checking operation"),
                ),
                PanelRow("bytes", RowKind.INFO, "Current file", amount or "Size not reported"),
                row("cancel", "Cancel request", enabled=self.busy and not self.stopping),
                PanelRow(
                    "retained",
                    RowKind.INFO,
                    "Ollama may retain partial download data",
                    description="Re-running the same download can reuse server data. "
                    "Cancelling does not delete models or stop Ollama.",
                ),
                back("home"),
            ]
        elif self.view == "service":
            crumbs += [title, "Service status"]
            rows = [
                row("reload", "Reload status", target="inventory"),
                PanelRow("endpoint", RowKind.INFO, "Endpoint", endpoint.get("base_url", "")),
                PanelRow(
                    "version", RowKind.INFO, "Ollama version", snapshot.get("version", "Unknown")
                ),
                PanelRow(
                    "loaded",
                    RowKind.INFO,
                    "Loaded models",
                    str(len(running)) if running is not None else "Unknown",
                ),
            ]
            rows += [
                PanelRow(
                    "running:" + m["name"],
                    RowKind.INFO,
                    m["name"],
                    "VRAM " + size(m["vram"]) + " · context " + str(m["context"] or "Unknown"),
                )
                for m in running or []
            ]
            rows += [
                PanelRow(
                    "control", RowKind.INFO, "Status checks do not stop or restart the service"
                ),
                back("home"),
            ]
        elif self.view == "hardware":
            crumbs += ["This machine", "Hardware"]
            rows = [
                row("reload", "Reload hardware", target="hardware"),
                PanelRow("ram", RowKind.INFO, "RAM", size(self.hardware.get("ram"))),
            ]
            rows += [
                PanelRow(
                    "cpu:" + str(i),
                    RowKind.INFO,
                    "CPU",
                    c.get("name") or "Unknown",
                    f"{c.get('logical_threads') or 'Unknown'} logical threads",
                )
                for i, c in enumerate(self.hardware.get("cpu", []))
            ]
            rows += [
                PanelRow(
                    "gpu:" + str(i),
                    RowKind.INFO,
                    "GPU",
                    g.get("name") or "Unknown",
                    "VRAM " + size(g.get("memory_bytes")),
                )
                for i, g in enumerate(self.hardware.get("gpu", []))
            ]
            if not self.hardware.get("gpu"):
                rows += [PanelRow("unknown", RowKind.INFO, "GPU information unavailable")]
            rows += [
                PanelRow(
                    "fit",
                    RowKind.INFO,
                    "Hardware information is not a model-fit or tool-quality benchmark",
                    description="This is the Klaude machine, not a remote endpoint's hardware.",
                ),
                back("home"),
            ]
        identity = "model-manager:" + self.view
        if self.view in {"installed", "detail", "review"}:
            identity += ":" + self.endpoint
        if self.view in {"detail", "review"}:
            identity += ":" + self.model
        if self.view == "review":
            identity += ":" + self.review.get("operation", "pull")
        return PanelPage(
            identity, tuple(crumbs), tuple(rows),
            column_headers=("MODEL", "SIZE / STATE", "DETAILS")
            if self.view == "installed" else ("REPOSITORY", "DOWNLOADS", "DESCRIPTION")
            if self.view == "discover" and self.results else None,
            table_section_id="models" if self.view == "installed" else "results",
        )

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix(PREFIX)
        if kind == "serve":
            self.serving.open()
        elif kind == "dependencies":
            self.dependencies.open()
        elif kind == "ssh":
            self.ssh.open()
        elif kind == "back":
            if action.target in {"close", "settings"}:
                self.leave()
                if action.target == "settings":
                    self.host._model_settings.open()
                else:
                    self.host._panel = None
                    self.host._cancel_choice()
            else:
                self.show(action.target)
        elif kind in {
            "home",
            "installed",
            "download",
            "discover",
            "hardware",
            "service",
            "endpoints",
            "progress",
        }:
            self.show(kind)
            if kind in {"installed", "service"}:
                snapshot = self.snapshot()
                if (
                    not snapshot
                    or snapshot.get("stale")
                    or time.time() - snapshot.get("checked_at", 0) >= 30
                ):
                    self.load("inventory")
            elif kind == "hardware":
                self.load("hardware")
        elif kind.startswith("endpoint:"):
            self.endpoint = action.target
            self.offset = 0
            self.show("home")
            self.load("inventory")
        elif kind.startswith("model:"):
            self.model = action.target
            self.show("detail")
        elif kind.startswith("repo:"):
            self.model = model_name("hf.co/" + action.target)
            self.show("download")
        elif kind == "reload":
            self.load(action.target)
        elif kind in {"model-input", "query"}:
            self.host._begin_settings_input(
                "Ollama model:tag" if kind == "model-input" else "Find GGUF models",
                "Private input · Escape returns",
                ("model-manager", kind),
            )
            self.host._set_input(self.model if kind == "model-input" else self.query)
        elif kind == "search":
            self.load("search")
        elif kind == "hf-credentials":
            self.owner_return = True
            self.host._open_settings_category("providers")
        elif kind in {"delete", "pull-review", "update"}:
            name = model_name(self.model)
            snapshot = self.snapshot()
            existing = next((m for m in snapshot.get("models") or [] if m["name"] == name), None)
            connection = snapshot.get("endpoint")
            if not connection:
                self.feedback = (
                    "Reload the installed inventory before reviewing an operation",
                    "warning",
                )
                self.load("inventory")
                return
            blockers = list(snapshot.get("bindings", {}).get(name, [])) if kind == "delete" else []
            if snapshot.get("running") is None:
                blockers.append("Loaded-model status unavailable; Reload status")
            elif any(
                m["name"] == name or existing and m["digest"] == existing["digest"]
                for m in snapshot["running"]
            ):
                blockers.append("Loaded by Ollama")
            self.review = {
                "operation": "delete" if kind == "delete" else "pull",
                "model": name,
                "digest": existing["digest"] if existing else "",
                "blockers": blockers,
                **{k: connection[k] for k in ("revision", "credential_revision")},
            }
            self.show("review", "back")
        elif kind == "confirm":
            self.start()
        elif kind == "cancel":
            self.stop()
        elif kind in {"next", "previous"}:
            self.offset = max(0, self.offset + (100 if kind == "next" else -100))
            self.show()
        elif kind == "filter":
            self.filter = "loaded" if self.filter == "all" else "all"
            self.offset = 0
            self.show()
        elif kind == "sort":
            order = ["name", "size", "recent"]
            self.sort = order[(order.index(self.sort) + 1) % len(order)]
            self.offset = 0
            self.show()

    def answer(self, field: str, value: str | None) -> None:
        if value is not None:
            if field == "model-input":
                self.model = model_name(value.strip())
            elif field == "query":
                if not value.strip() or len(value) > 200 or not value.isprintable():
                    raise ValueError("Enter a printable query of 1–200 characters")
                self.query = value.strip()
                self.results = []
        self.show()

    def start(self) -> None:
        if self.busy or self.review.get("blockers"):
            return
        if (
            self.host.running
            or getattr(self.host, "_watching_remote", False)
            or getattr(self.host, "_setup_job", None)
            or self.host._library.knowledge.busy
            or self.host._library.research.busy
            or getattr(getattr(self.host._library, "vision", None), "busy", False)
            or getattr(getattr(self.host._library, "generation", None), "busy", False)
            or self.host._ai_defaults.utility
            or getattr(self.host._ai_defaults, "preparing_utility", False)
            or getattr(self.host, "_skill_action_pending", False)
        ):
            self.feedback = (
                "Finish active model work before changing downloaded models",
                "warning",
            )
            self.show()
            return
        record = self.snapshot().get("endpoint", {})
        request = worker_request(
            self.host.cfg,
            self.review["operation"],
            endpoint=self.endpoint,
            current=self.current(),
            key_env=record.get("key_env", ""),
            **{k: v for k, v in self.review.items() if k != "blockers" and k != "operation"},
        )
        identity = self.host._background_jobs.submit(
            WORK, request, timeout=PULL_TIMEOUT, notify_cancel=True
        )
        self.task = {
            "id": identity,
            "scope": self.scope,
            "model": self.review["model"],
            "endpoint": self.endpoint,
            "name": record.get("name", "Ollama"),
        }
        self.last_task = dict(self.task)
        self.progress = {}
        self.stopping = False
        self.feedback = None
        self.show("progress", fresh=True)

    def stop(self) -> None:
        if self.ssh.setup.busy:
            self.ssh.setup.stop()
            return
        if self.dependencies.busy:
            self.dependencies.stop()
            return
        if self.task is None:
            self.serving.cancel_pending()
            return
        if self.task and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(WORK)
            if self.active:
                self.show()

    def stopped(self, identity: str) -> None:
        if self.task and self.task["id"] == identity:
            self.task = None
            self.stopping = False
            self.progress["stage"] = "Request cancelled"
            self.feedback = (
                "Request cancelled; reload models to check retained server data",
                "warning",
            )
            if self.active:
                self.show()
            self.host._start_next()

    def accept_progress(self, identity: str, progress: dict) -> None:
        if self.task and self.task["id"] == identity and self.task["scope"] == self.scope:
            self.progress = progress
            if self.active and self.view == "progress" and not self.host._settings_input_request:
                self.show()

    def accept(self, key: str, identity: str, result: Any, error: str) -> None:
        if key.startswith("model-manager:ssh-setup-"):
            self.ssh.setup.accept(key, identity, result, error)
            return
        if key == "model-manager:ssh-read":
            self.ssh.accept(identity, result, error)
            return
        if key.startswith("model-manager:dependencies-"):
            self.dependencies.accept(key, identity, result, error)
            return
        if key == WORK:
            if not self.task or self.task["id"] != identity:
                return
            task = self.task
            self.task = None
            self.stopping = False
            if task["scope"] != self.scope:
                self.host._start_next()
                return
            message = (
                "Outcome unknown; reload models before retrying"
                if error
                else (result or {}).get("message", "Operation failed")
            )
            success = not error and isinstance(result, dict) and result.get("status") == "ok"
            self.progress["stage"] = (
                "Complete" if success else "Outcome unknown" if error else "Failed"
            )
            self.feedback = (message, "success" if success else "warning" if error else "error")
            if success:
                self.snapshots.pop(task["endpoint"], None)
                if not result.get("cache_invalidated"):
                    self.feedback = (message + "; reload model choices", "warning")
            if self.active:
                self.show()
                if success and task["endpoint"] == self.endpoint:
                    self.load("inventory", preserve=True)
            self.host._start_next()
            return
        accepted = self.read
        if not accepted or accepted[0] != identity:
            return
        self.read = None
        _, scope, target, operation, previous_feedback = accepted
        if scope != self.scope or target != self.endpoint:
            return
        if error or not isinstance(result, dict) or result.get("status"):
            self.feedback = (
                (result or {}).get("message", "Model Manager unavailable; retry"),
                "error",
            )
        else:
            self.feedback = previous_feedback
            if operation == "connections":
                self.connections = result["connections"]
                valid = {c["id"]: c for c in self.connections}
                for identity, snapshot in list(self.snapshots.items()):
                    record = valid.get(identity)
                    saved = snapshot.get("endpoint", {})
                    if not record or any(
                        saved.get(k) != record.get(k) for k in ("revision", "credential_revision")
                    ):
                        self.snapshots.pop(identity, None)
                if self.endpoint not in valid:
                    self.endpoint = next(iter(valid), "")
                if self.connections:
                    self.load("inventory")
                    return
            elif operation == "inventory":
                if result.get("models") is not None:
                    self.snapshots[self.endpoint] = result
                else:
                    if self.endpoint in self.snapshots:
                        self.snapshots[self.endpoint]["stale"] = True
                    self.feedback = (
                        result.get(
                            "models_error", "Catalog unavailable; retained previous snapshot"
                        ),
                        "warning",
                    )
            elif operation == "search":
                self.results = result["results"]
                self.feedback = (f"{len(self.results)} GGUF repositories found", "neutral")
            elif operation == "hardware":
                self.hardware = result["hardware"]
        if self.active and not self.host._settings_input_request:
            self.show()
