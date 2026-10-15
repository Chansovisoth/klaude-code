"""Model Manager's local serving forms and client-owned process controls."""

from __future__ import annotations

import os
import uuid
from dataclasses import asdict, replace
from typing import Any

from klaude_core.managed_serving import ENGINES, LaunchSpec
from klaude_core.ssh_serving import preflight_timeout

from .serving_jobs import ServingJobs
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

READ = "serving:read"


def action(identity: str, label: str, value: str = "", **kwargs) -> PanelRow:
    return PanelRow(
        identity, RowKind.ACTION, label, value, action=PanelAction("serving-" + identity), **kwargs
    )


def back(target: str) -> PanelRow:
    return PanelRow(
        "back",
        RowKind.NAVIGATION,
        "Back",
        control=RowControl.BACK,
        action=PanelAction("serving-back", target),
    )


class ServingPanel:
    def __init__(self, manager: Any):
        self.manager = manager
        self.host = manager.host
        self.jobs = ServingJobs(getattr(self.host, "_emit", lambda *_: None))
        self.view = "home"
        self.spec = LaunchSpec("llama_cpp", "llama-server", "")
        self.evidence: dict = {}
        self.revision = 0
        self.read: tuple | None = None
        self.items: dict[str, dict] = {}
        self.target = ""
        self.starting: set[str] = set()
        self.stopping: set[str] = set()
        self.feedback: tuple[str, str] | None = None
        self.logs = ""
        self.adopting = False
        self.ssh_revision = ""
        self.remote_name = ""

    @property
    def busy(self) -> bool:
        return bool(self.starting or self.stopping)

    @property
    def active(self) -> bool:
        return str(self.host._choice_kind).startswith("model manager serving")

    def open(self) -> None:
        self.show("home")
        self.load("inventory")

    def new_draft(
        self,
        *,
        adopt: bool = False,
        executable: str = "llama-server",
        focus: str = "",
        engine: str = "llama_cpp",
    ) -> None:
        self.revision += 1
        self.evidence = {}
        self.feedback = None
        self.adopting = adopt
        self.ssh_revision = ""
        self.remote_name = ""
        self.spec = LaunchSpec(engine, executable, "")
        self.show("form", focus, fresh=True)

    def new_remote_draft(
        self, identity: str, revision: str, name: str, *, adopt: bool = False
    ) -> None:
        self.revision += 1
        self.evidence = {}
        self.feedback = None
        self.adopting = adopt
        self.ssh_revision = revision
        self.remote_name = name
        self.spec = LaunchSpec(
            "llama_cpp",
            "/usr/local/bin/llama-server",
            "",
            name="Adopted remote model" if adopt else "Remote model",
            ssh_server=identity,
        )
        self.show("form", "field:executable", fresh=True)

    def leave(self) -> None:
        self.host._background_jobs.cancel(READ)
        self.read = None

    def show(self, view: str | None = None, focus: str = "", *, fresh: bool = False) -> None:
        if view:
            self.view = view
        page = self.page()
        state = self.host._panel_states.get(page.id)
        if fresh and state:
            state.filter("")
            state.search_active = False
        self.host._open_panel(page, "model manager serving " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def page(self) -> PanelPage:
        remote = bool(self.spec.ssh_server) and self.view in {"form", "review"}
        crumbs: tuple[str, ...] = (
            ("Model Manager", "Servers", self.remote_name, "Serve")
            if remote
            else ("Model Manager", "Serve")
        )
        rows: list[PanelRow] = []
        item = self.items.get(self.target, {})
        if self.view == "home":
            rows = [
                action("new", "Launch server"),
                action("reload", "Reload servers"),
                action("adopt", "Adopt existing server"),
                PanelRow(
                    "scope",
                    RowKind.INFO,
                    "Client-owned servers",
                    description="Servers stop when their owning Klaude client exits.",
                ),
                PanelRow("columns", RowKind.TABLE_HEADER, "SERVER"),
            ]
            rows += [
                PanelRow(
                    "server:" + key,
                    RowKind.NAVIGATION,
                    value["spec"]["name"],
                    value["state"].title(),
                    value["spec"]["engine"],
                    section_id="servers",
                    action=PanelAction("serving-detail", key),
                )
                for key, value in self.items.items()
            ]
            if not self.items:
                rows += [PanelRow("empty", RowKind.INFO, "No managed servers")]
            rows += [back("manager")]
        elif self.view == "form":
            crumbs += ("Adopt" if self.adopting else "Launch",)
            fields = [
                ("name", "Name"),
                ("engine", "Engine"),
                ("executable", "Executable"),
                ("model", "Local model path"),
                ("port", "Port"),
                ("context", "Context"),
            ]
            if remote:
                fields = [
                    ("name", "Name"),
                    ("engine", "Engine"),
                    ("executable", "Remote executable"),
                    (
                        "model",
                        "Remote model directory"
                        if self.spec.engine == "vllm"
                        else "Remote GGUF path",
                    ),
                    ("port", "Remote port"),
                    ("local_port", "Tunnel port"),
                    ("context", "Context"),
                ]
            fields += (
                [("threads", "CPU threads"), ("gpu_layers", "GPU layers")]
                if self.spec.engine == "llama_cpp"
                else [
                    ("memory", "GPU memory fraction"),
                    ("dtype", "Precision"),
                    ("enforce_eager", "Eager execution"),
                ]
            )
            if self.spec.engine == "vllm" or self.spec.gpu_layers:
                fields += [("gpu", "GPU IDs")]
            if self.adopting:
                fields = [
                    ("name", "Name"),
                    ("engine", "Engine"),
                    ("executable", "Remote executable" if remote else "Executable"),
                    ("adopt_pid", "Server PID"),
                    ("model_id", "Model ID"),
                    ("port", "Remote loopback port" if remote else "Port"),
                ]
                if remote:
                    fields += [("local_port", "Tunnel port")]
            rows = [
                action(
                    "field:" + key,
                    label,
                    ("ON" if self.spec.enforce_eager else "OFF")
                    if key == "enforce_eager"
                    else str(getattr(self.spec, key)) or "Enter value",
                )
                for key, label in fields
            ]
            rows += [
                action(
                    "test",
                    "Inspect server" if remote and self.adopting else "Test engine",
                    "Verified" if self.evidence else "Not tested",
                    enabled=not (remote and self.adopting)
                    or bool(self.spec.adopt_pid and self.spec.model_id),
                ),
                action(
                    "review",
                    "Review adoption" if self.adopting else "Review launch",
                    enabled=bool(
                        self.evidence
                        and (
                            self.spec.adopt_pid and self.spec.model_id
                            if self.adopting
                            else self.spec.model
                        )
                    ),
                ),
                PanelRow(
                    "bind",
                    RowKind.INFO,
                    "Bind address",
                    "127.0.0.1",
                    "Inspects the exact existing PID and model; "
                    "leaves the server running until reviewed adoption."
                    if remote and self.adopting
                    else "Installed vLLM and local safetensors over verified SSH; "
                    "NVIDIA CUDA required."
                    if remote and self.spec.engine == "vllm"
                    else "Remote llama.cpp through a verified SSH tunnel; GPU layers 0 selects CPU."
                    if remote
                    else "Uses installed engines and local weights; no automatic downloads.",
                ),
                back("ssh" if remote else "home"),
            ]
            if self.evidence and not self.adopting and (self.spec.engine == "llama_cpp" or remote):
                devices = self.evidence.get("devices")
                labels = ", ".join(f"{i}: {name}" for i, name in enumerate(devices or []))
                position = (
                    next(
                        (
                            i
                            for i, row in enumerate(rows)
                            if row.id in {"field:gpu", "field:gpu_layers"}
                        ),
                        len(rows) - 1,
                    )
                    if remote
                    else -1
                )
                rows.insert(
                    position,
                    PanelRow(
                        "devices",
                        RowKind.INFO,
                        "Remote GPU devices" if remote else "GPU devices",
                        labels or ("Unknown" if devices is None else "Unavailable"),
                    ),
                )
        elif self.view == "review":
            crumbs += ("Review adoption" if self.adopting else "Review launch",)
            rows = [
                PanelRow("name", RowKind.INFO, "Server", self.spec.name),
                PanelRow("engine", RowKind.INFO, "Engine", self.spec.engine),
                PanelRow(
                    "model",
                    RowKind.INFO,
                    "Model ID" if self.adopting else "Model",
                    self.spec.model_id if self.adopting else self.spec.model,
                ),
                PanelRow(
                    "url",
                    RowKind.INFO,
                    "Endpoint",
                    f"127.0.0.1:{self.spec.local_port if remote else self.spec.port}",
                ),
            ]
            if remote:
                rows += [
                    PanelRow("ssh", RowKind.INFO, "SSH server", self.remote_name),
                    PanelRow(
                        "remote-port", RowKind.INFO, "Remote loopback port", str(self.spec.port)
                    ),
                    PanelRow("executable", RowKind.INFO, "Remote executable", self.spec.executable),
                ]
                if not self.adopting and (self.spec.gpu_layers or self.spec.engine == "vllm"):
                    rows += [
                        PanelRow(
                            "devices",
                            RowKind.INFO,
                            "Verified devices",
                            ", ".join(self.evidence.get("selected_devices", [])),
                        ),
                    ]
            if remote and self.spec.gpu_layers:
                rows += [PanelRow("layers", RowKind.INFO, "GPU layers", str(self.spec.gpu_layers))]
            if self.spec.engine == "vllm" and not self.adopting:
                rows += [
                    PanelRow("memory", RowKind.INFO, "GPU memory fraction", str(self.spec.memory)),
                    PanelRow("precision", RowKind.INFO, "Precision", self.spec.dtype),
                    PanelRow(
                        "eager",
                        RowKind.INFO,
                        "Eager execution",
                        "ON" if self.spec.enforce_eager else "OFF",
                    ),
                    PanelRow("parallel", RowKind.INFO, "Concurrency", "1 sequence"),
                ]
                if remote:
                    runtime = self.evidence.get("runtime", {})
                    rows += [
                        PanelRow(
                            "runtime",
                            RowKind.INFO,
                            "Verified runtime",
                            "vLLM "
                            + runtime.get("vllm", "Unknown")
                            + " · CUDA "
                            + runtime.get("cuda", "Unknown"),
                        )
                    ]
            if not self.adopting:
                rows += [
                    PanelRow("context", RowKind.INFO, "Context", str(self.spec.context)),
                    PanelRow(
                        "device",
                        RowKind.INFO,
                        "Device",
                        "CPU"
                        if self.spec.engine == "llama_cpp" and not self.spec.gpu_layers
                        else "GPU " + self.spec.gpu,
                    ),
                ]
            elif remote:
                rows += [
                    PanelRow("resources", RowKind.INFO, "Engine settings", "Retained unchanged"),
                    PanelRow("logs", RowKind.INFO, "Logs", "Original destination; not attached"),
                    PanelRow(
                        "ownership",
                        RowKind.INFO,
                        "Verified ownership",
                        "Same account; isolated process/session",
                    ),
                    PanelRow(
                        "lease",
                        RowKind.INFO,
                        "Connection loss",
                        "Stops after the owner lease expires",
                    ),
                ]
            rows += [
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Takes control of an existing server"
                    if self.spec.adopt_pid
                    else "Loads a remote GPU model"
                    if remote and (self.spec.gpu_layers or self.spec.engine == "vllm")
                    else "Loads a remote CPU model"
                    if remote
                    else "Loads a model on this machine",
                    description="Registers a new endpoint after health checks. "
                    "Stops on client exit; current model choices stay unchanged.",
                ),
                PanelRow("pid", RowKind.INFO, "Adopted PID", str(self.spec.adopt_pid))
                if self.spec.adopt_pid
                else PanelRow("lifecycle", RowKind.INFO, "Client-owned process lifetime"),
                action(
                    "launch",
                    "Adopt server" if self.adopting else "Launch server",
                    enabled=not self.busy,
                ),
                back("form"),
            ]
        elif self.view in {"detail", "stop"}:
            crumbs += (item.get("spec", {}).get("name", "Server"),)
            if self.view == "stop":
                rows = [
                    PanelRow(
                        "effect",
                        RowKind.INFO,
                        "Stop this owned server?",
                        description="Disconnects its clients and disables its endpoint. "
                        "Model files and defaults are retained.",
                    ),
                    action("confirm-stop", "Stop server", enabled=self.jobs.owns(self.target)),
                    back("detail"),
                ]
            else:
                rows = [
                    action(
                        "cancel-load",
                        "Cancel loading",
                        enabled=self.jobs.owns(self.target) and self.target not in self.stopping,
                    )
                    if self.target in self.starting
                    else action("stop", "Stop server", enabled=self.jobs.owns(self.target)),
                    action(
                        "logs",
                        "Logs",
                        enabled=not item.get("adopted", False),
                        description="Existing server keeps its original log destination"
                        if item.get("adopted")
                        else "",
                    ),
                    action("reload", "Reload servers"),
                    PanelRow("state", RowKind.INFO, "Status", item.get("state", "Unknown")),
                    PanelRow(
                        "url",
                        RowKind.INFO,
                        "Endpoint",
                        item.get("endpoint", {}).get("base_url", "Not registered"),
                    ),
                    PanelRow("model", RowKind.INFO, "Model ID", item.get("model", "Pending")),
                    PanelRow(
                        "owner",
                        RowKind.INFO,
                        "Owner",
                        "This client"
                        if self.jobs.owns(self.target)
                        else "Another client or finished",
                    ),
                    back("home"),
                ]
                if item.get("ssh"):
                    if (
                        item.get("spec", {}).get("gpu_layers")
                        or item.get("spec", {}).get("engine") == "vllm"
                    ):
                        rows.insert(
                            -1,
                            PanelRow(
                                "gpu-request",
                                RowKind.INFO,
                                "GPU request",
                                ", ".join(item.get("selected_devices", [])),
                                str(item["spec"]["gpu_layers"]) + " requested offload layers"
                                if item["spec"]["engine"] == "llama_cpp"
                                else "NVIDIA CUDA · "
                                + str(item["spec"]["memory"])
                                + " memory fraction",
                            ),
                        )
                    rows.insert(
                        -1, PanelRow("remote", RowKind.INFO, "SSH server", item["ssh"]["name"])
                    )
                    rows.insert(
                        -1,
                        PanelRow(
                            "cleanup",
                            RowKind.INFO,
                            "Remote cleanup",
                            "Active owner lease"
                            if item.get("state") in {"ready", "starting"}
                            and self.jobs.owns(self.target)
                            else item.get("remote_cleanup", "Unknown"),
                        ),
                    )
        elif self.view == "logs":
            crumbs += ("Logs",)
            rows = [
                action("logs", "Reload logs"),
                PanelRow(
                    "log",
                    RowKind.INFO,
                    "Latest engine output",
                    description=self.logs or "No log output available",
                ),
                back("detail"),
            ]
        return PanelPage(
            "serving:"
            + self.view
            + (":" + self.target if self.view in {"detail", "stop", "logs"} else ""),
            crumbs,
            tuple(rows),
            column_headers=("SERVER", "STATE", "ENGINE") if self.view == "home" else None,
            table_section_id="servers",
            scroll_wrapped_rows=self.view in {"form", "logs", "review"},
            scrollable_body=self.view in {"form", "logs", "review"},
            align_info_values=self.view == "review",
        )

    def load(self, operation: str) -> None:
        if operation == "probe":
            self.evidence = {}
        identity = self.host._background_jobs.submit(
            READ,
            {
                "kind": "serving_read",
                "operation": operation,
                "data_dir": str(self.host.cfg.data_dir),
                "engine": self.spec.engine,
                "executable": self.spec.executable,
                "spec": asdict(self.spec),
                "evidence": self.evidence,
                "id": self.target,
                "config_dir": str(self.host.cfg.config_dir),
                "server_revision": self.ssh_revision,
                "agent_socket": os.environ.get("SSH_AUTH_SOCK", ""),
            },
            timeout=preflight_timeout(self.spec),
        )
        self.read = (
            identity,
            self.manager.scope,
            self.revision,
            operation,
            str(self.host.cfg.config_dir),
        )
        self.feedback = ("Checking…", "neutral")
        self.show()

    def accept(self, identity: str, result: Any, error: str) -> None:
        accepted = self.read
        if not accepted or accepted[0] != identity:
            return
        self.read = None
        _, scope, revision, operation, root = accepted
        if (
            scope != self.manager.scope
            or revision != self.revision
            or root != str(self.host.cfg.config_dir)
        ):
            return
        if error or not isinstance(result, dict) or result.get("error"):
            self.feedback = (
                result.get("error", "Inspection failed; check installation or paths")
                if isinstance(result, dict)
                else "Inspection failed; retry",
                "error",
            )
        else:
            self.feedback = None
            if operation == "inventory":
                self.items = {item["id"]: item for item in result["servers"]}
            elif operation == "probe":
                self.evidence = result
                self.spec = replace(self.spec, executable=result["executable"])
                self.feedback = (
                    "Existing process verified; server retained"
                    if self.spec.ssh_server and self.adopting
                    else "Engine flags verified; no model loaded",
                    "success",
                )
            elif operation == "prepare":
                self.evidence = result["evidence"]
                if self.spec.ssh_server:
                    self.spec = replace(
                        self.spec,
                        executable=self.evidence["executable"],
                        model=self.evidence.get("model", ""),
                    )
                self.show("review", "back", fresh=True)
                return
            elif operation == "logs":
                self.logs = result["logs"]
        if self.active and not self.host._settings_input_request:
            self.show()

    def action(self, event: PanelAction) -> None:
        kind = event.kind.removeprefix("serving-")
        if kind == "back":
            if event.target == "ssh":
                self.manager.ssh.target = self.spec.ssh_server
                self.manager.ssh.show("detail")
            elif event.target == "manager":
                self.manager.show("home", "serve")
            else:
                self.show(event.target)
        elif kind in {"new", "adopt"}:
            self.new_draft(adopt=kind == "adopt")
        elif kind.startswith("field:"):
            field = kind.removeprefix("field:")
            if field == "engine":
                engine = "vllm" if self.spec.engine == "llama_cpp" else "llama_cpp"
                self.spec = replace(
                    self.spec,
                    engine=engine,
                    executable=("/usr/local/bin/" if self.spec.ssh_server else "")
                    + ENGINES[engine],
                    model="",
                    gpu_layers=0,
                    dtype="auto",
                    enforce_eager=bool(self.spec.ssh_server and engine == "vllm"),
                )
                self.evidence = {}
                self.revision += 1
                self.show()
            elif field in {"dtype", "enforce_eager"}:
                value: Any = (
                    not self.spec.enforce_eager
                    if field == "enforce_eager"
                    else (
                        {
                            "auto": "half",
                            "half": "bfloat16",
                            "bfloat16": "float32",
                            "float32": "auto",
                        }[self.spec.dtype]
                    )
                )
                self.spec = replace(self.spec, **{field: value})
                self.revision += 1
                self.show()
            else:
                self.host._begin_settings_input(
                    field.replace("_", " ").title(),
                    "Enter a value; Escape returns",
                    ("serving-field", field),
                )
                self.host._set_input(str(getattr(self.spec, field)))
        elif kind == "test":
            self.load("probe")
        elif kind == "review":
            self.load("prepare")
        elif kind == "reload":
            self.load("inventory")
        elif kind == "detail":
            self.target = event.target
            self.show("detail")
        elif kind == "logs":
            self.show("logs")
            self.load("logs")
        elif kind == "launch":
            if not self.busy and not self.host._session_action_is_busy():
                identity = uuid.uuid4().hex
                self.target = identity
                self.starting.add(identity)
                self.items[identity] = {
                    "id": identity,
                    "spec": asdict(self.spec),
                    "state": "starting",
                }
                try:
                    self.jobs.start(
                        {
                            "id": identity,
                            "spec": asdict(self.spec),
                            "evidence": self.evidence,
                            "owner": self.host.client_id,
                            "config_dir": str(self.host.cfg.config_dir),
                            "data_dir": str(self.host.cfg.data_dir),
                            "agent_socket": os.environ.get("SSH_AUTH_SOCK", ""),
                        }
                    )
                except ValueError:
                    self.starting.discard(identity)
                    raise
                self.show("detail")
            else:
                self.feedback = ("Finish active model work before launching a server", "warning")
                self.show()
        elif kind == "stop":
            self.show("stop", "back", fresh=True)
        elif kind == "cancel-load":
            if self.target in self.starting and self.jobs.owns(self.target):
                self.stopping.add(self.target)
                self.jobs.stop(self.target)
                self.feedback = ("Cancelling loading…", "neutral")
                self.show("detail")
        elif kind == "confirm-stop":
            if self.host._session_action_is_busy() and self.target not in self.starting:
                self.feedback = ("Finish active model work before stopping this server", "warning")
                self.show()
            elif self.jobs.owns(self.target):
                self.stopping.add(self.target)
                self.jobs.stop(self.target)
                self.show("detail")

    def answer(self, field: str, value: str | None) -> None:
        if value is not None:
            parsed: Any = value.strip()
            if field in {"port", "local_port", "context", "threads", "gpu_layers", "adopt_pid"}:
                parsed = int(parsed)
            elif field == "memory":
                parsed = float(parsed)
            self.spec = replace(self.spec, **{field: parsed})
            self.revision += 1
            if field in {"executable", "adopt_pid"}:
                self.evidence = {}
        self.show("form", "field:" + field)

    def event(self, identity: str, value: dict) -> None:
        if value.get("state") == "ready":
            self.starting.discard(identity)
        prior = self.items.get(identity, {})
        prior.update(value)
        self.items[identity] = prior
        self.feedback = (
            value.get("message", "Server updated"),
            "success"
            if value["state"] == "ready"
            else "error"
            if value["state"] == "failed"
            else "warning"
            if value["state"] == "warning"
            else "neutral",
        )
        if self.active and not self.host._settings_input_request:
            self.show()
        self.host._start_next()

    def stopped(self, identity: str, failed: bool) -> None:
        self.starting.discard(identity)
        self.stopping.discard(identity)
        if identity in self.items:
            self.items[identity]["state"] = "failed" if failed else "stopped"
        if self.active:
            self.show()
        self.host._start_next()

    def cancel_pending(self) -> None:
        for identity in self.starting:
            self.stopping.add(identity)
            self.jobs.stop(identity)
