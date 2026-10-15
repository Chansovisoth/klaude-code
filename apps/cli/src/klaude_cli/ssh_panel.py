"""Model Manager server definitions and read-only SSH diagnostics."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from klaude_core.ssh_servers import TIMEOUT, SSHServer

from .session_actions import SSHServerChange
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind
from .ssh_setup_panel import SSHSetupPanel

READ = "model-manager:ssh-read"


def row(key: str, label: str, value: str = "", **kwargs) -> PanelRow:
    return PanelRow(key, RowKind.ACTION, label, value, action=PanelAction("ssh-" + key), **kwargs)


def back(target: str) -> PanelRow:
    return PanelRow(
        "back",
        RowKind.NAVIGATION,
        "Back",
        control=RowControl.BACK,
        action=PanelAction("ssh-back", target),
    )


def amount(value: Any) -> str:
    if type(value) is not int:
        return "Unknown"
    for scale, unit in ((1024**3, "GiB"), (1024**2, "MiB"), (1024, "KiB")):
        if value >= scale:
            return f"{value / scale:.1f} {unit}"
    return f"{value} B"


class SSHPanel:
    def __init__(self, manager: Any):
        self.manager = manager
        self.host = manager.host
        self.view = "home"
        self.inventory: dict = {}
        self.reports: dict[str, dict] = {}
        self.target = "local"
        self.draft = SSHServer(
            "ssh-" + uuid.uuid4().hex[:12],
            "SSH server",
            "",
            "",
            known_hosts=str(Path.home() / ".ssh/known_hosts"),
        )
        self.edit_revision = ""
        self.revision = 0
        self.read: tuple | None = None
        self.pending: dict | None = None
        self.feedback: tuple[str, str] | None = None
        self.setup = SSHSetupPanel(self)

    @property
    def active(self) -> bool:
        kind = str(self.host._choice_kind)
        return kind.startswith("model manager ssh") and not kind.startswith(
            "model manager ssh setup"
        )

    @property
    def checking(self) -> bool:
        return bool(self.read and self.read[3] != "list")

    def record(self) -> dict:
        return self.inventory.get("servers", {}).get(self.target, {})

    def report(self) -> dict:
        value = self.reports.get(self.target, {})
        return value if value.get("revision") == self.record().get("revision") else {}

    def page(self) -> PanelPage:
        crumbs: tuple[str, ...] = ("Model Manager", "Servers")
        rows: list[PanelRow] = []
        if self.view == "home":
            default = self.inventory.get("default", "local")
            rows = [
                row("new", "Add SSH server"),
                row("reload", "Reload servers"),
                row("inspect-default", "Inspect default server", enabled=bool(self.inventory)),
                PanelRow(
                    "default",
                    RowKind.INFO,
                    "Default server",
                    "This machine"
                    if default == "local"
                    else self.inventory["servers"][default]["definition"]["name"],
                    "Used by Inspect default server; model choices are independent.",
                ),
                PanelRow("columns", RowKind.TABLE_HEADER, "SERVER"),
                PanelRow(
                    "server:local",
                    RowKind.NAVIGATION,
                    "This machine",
                    "Local",
                    "",
                    section_id="servers",
                    status="Default" if default == "local" else "",
                    action=PanelAction("ssh-select", "local"),
                ),
            ]
            for identity, record in self.inventory.get("servers", {}).items():
                server = SSHServer(**record["definition"])
                report = self.reports.get(identity, {})
                message = (
                    report.get("message", "Not tested")
                    if report.get("revision") == record["revision"]
                    else "Not tested"
                )
                rows.append(
                    PanelRow(
                        "server:" + identity,
                        RowKind.NAVIGATION,
                        server.name,
                        f"{server.host}:{server.port}",
                        message,
                        section_id="servers",
                        status="Default" if default == identity else "",
                        action=PanelAction("ssh-select", identity),
                    )
                )
            rows += [back("manager")]
        elif self.view in {"form", "review"}:
            crumbs += ("Edit SSH server" if self.edit_revision else "Add SSH server",)
            if self.view == "form":
                rows = [
                    row("field:" + key, label, str(getattr(self.draft, key)) or "Enter value")
                    for key, label in (
                        ("name", "Name"),
                        ("host", "Host"),
                        ("port", "SSH port"),
                        ("user", "User"),
                        ("identity_file", "Identity file"),
                        ("known_hosts", "Known hosts"),
                        ("models_dir", "Models directory"),
                    )
                ]
                rows += [
                    PanelRow(
                        "agent",
                        RowKind.TOGGLE,
                        "Use SSH agent",
                        "ON" if self.draft.use_agent else "OFF",
                        checked=self.draft.use_agent,
                        action=PanelAction("ssh-agent"),
                    ),
                    row("review", "Review settings", enabled=not self.pending),
                    PanelRow(
                        "scope",
                        RowKind.INFO,
                        "Use existing keys and verified known hosts",
                        description="No password prompts or automatic host-key trust.",
                    ),
                    back("home"),
                ]
            else:
                crumbs += ("Review",)
                rows = [
                    PanelRow("destination", RowKind.INFO, "SSH server", self.draft.name),
                    PanelRow(
                        "address",
                        RowKind.INFO,
                        "Address",
                        f"{self.draft.user}@{self.draft.host}:{self.draft.port}",
                    ),
                    PanelRow("directory", RowKind.INFO, "Models directory", self.draft.models_dir),
                    PanelRow(
                        "scope",
                        RowKind.INFO,
                        "Save connection settings",
                        description="Stores paths and server metadata. Connect after saving. "
                        "Key contents stay in your existing files/agent.",
                    ),
                    row("save", "Save server", enabled=not self.pending),
                    back("form"),
                ]
        elif self.view == "remove":
            crumbs += ("Remove server",)
            rows = [
                PanelRow(
                    "effect",
                    RowKind.INFO,
                    "Remove this SSH definition?",
                    description="Retains remote files/processes and local keys. "
                    "If default, diagnostics return to This machine.",
                ),
                row("remove-confirm", "Remove server", enabled=not self.pending),
                back("detail"),
            ]
        elif self.target == "local":
            crumbs += ("This machine",)
            rows = [
                row("local-hardware", "Hardware"),
                row(
                    "default",
                    "Use as default",
                    enabled=self.inventory.get("default") != "local" and not self.pending,
                ),
                back("home"),
            ]
        else:
            record = self.record()
            server = SSHServer(**record["definition"])
            report = self.report()
            data = report.get("data", {})
            crumbs += (server.name,)
            if self.view in {"models", "processes"}:
                models = self.view == "models"
                crumbs += ("Models" if models else "Processes",)
                rows = [
                    row("inspect", "Reload diagnostics"),
                    PanelRow(
                        "scope",
                        RowKind.INFO,
                        "Read-only snapshot",
                        description="No files loaded or processes controlled.",
                    ),
                    PanelRow("columns", RowKind.TABLE_HEADER, "NAME" if models else "PID"),
                ]
                rows += [
                    PanelRow(
                        "item:" + str(i),
                        RowKind.INFO,
                        item["name"] if models else str(item["pid"]),
                        item["kind"] if models else item["name"],
                        amount(item.get("size")) if models else "Observed name",
                        section_id="items",
                    )
                    for i, item in enumerate(data.get(self.view, []))
                ]
                if not data.get(self.view):
                    rows += [
                        PanelRow(
                            "empty",
                            RowKind.INFO,
                            "Inventory unavailable; inspect or edit this server"
                            if data.get("directory_status" if models else "process_status")
                            != "Available"
                            else "No matching records in this snapshot",
                        )
                    ]
                if data.get("truncated" if models else "process_truncated"):
                    rows += [
                        PanelRow("limited", RowKind.INFO, "Bounded listing; more records may exist")
                    ]
                rows += [back("detail")]
            else:
                rows = [
                    row("setup", "Key setup", enabled=not self.pending),
                    row("serve", "Serve model", enabled=not self.pending),
                    row("adopt", "Adopt existing server", enabled=not self.pending),
                    row("test", "Test connection", enabled=not self.pending),
                    row("inspect", "Inspect server", enabled=not self.pending),
                    row(
                        "models",
                        "Models",
                        str(len(data.get("models", [])))
                        if data.get("directory_status") == "Available"
                        else "Unavailable",
                        enabled=bool(data.get("directory_status")),
                    ),
                    row(
                        "processes",
                        "Processes",
                        str(len(data.get("processes", [])))
                        if data.get("process_status") == "Available"
                        else "Unavailable",
                        enabled=bool(data.get("directory_status")),
                    ),
                    row("edit", "Edit server", enabled=not self.pending),
                    row(
                        "default",
                        "Use as default",
                        enabled=not self.pending and self.inventory.get("default") != self.target,
                    ),
                    row("remove", "Remove server", enabled=not self.pending),
                    PanelRow(
                        "address",
                        RowKind.INFO,
                        "Address",
                        f"{server.user}@{server.host}:{server.port}",
                    ),
                    PanelRow(
                        "connection",
                        RowKind.INFO,
                        "Connection",
                        report.get("message", "Not tested"),
                    ),
                    PanelRow("directory", RowKind.INFO, "Models directory", server.models_dir),
                    PanelRow(
                        "directory-status",
                        RowKind.INFO,
                        "Directory status",
                        data.get("directory_status", "Not checked"),
                    ),
                    PanelRow("ram", RowKind.INFO, "RAM", amount(data.get("ram"))),
                    PanelRow(
                        "cpu",
                        RowKind.INFO,
                        "CPU threads",
                        str(data.get("cpu_threads") or "Unknown"),
                    ),
                    PanelRow("disk", RowKind.INFO, "Free disk", amount(data.get("disk_free"))),
                    PanelRow(
                        "architecture",
                        RowKind.INFO,
                        "Architecture",
                        data.get("architecture", "Unknown"),
                    ),
                    PanelRow(
                        "gpu",
                        RowKind.INFO,
                        "System GPU inventory",
                        "Not checked",
                        description="Serve model checks the selected engine's devices.",
                    ),
                    PanelRow(
                        "scope",
                        RowKind.INFO,
                        "Diagnostics do not launch models or certify ownership",
                        description="Serve model verifies engine GPU devices and explicitly "
                        "loads remote weights through SSH. "
                        "Dependency builds remain local.",
                    ),
                    back("home"),
                ]
                if self.checking:
                    rows.insert(2, row("cancel", "Cancel check"))
                if report.get("checked_at"):
                    rows.insert(
                        -1,
                        PanelRow(
                            "age",
                            RowKind.INFO,
                            "Checked",
                            f"{max(0, int(time.time() - report['checked_at']))}s ago",
                        ),
                    )
                if report.get("inspected_at"):
                    rows.insert(
                        -1,
                        PanelRow(
                            "inspected",
                            RowKind.INFO,
                            "Inspected",
                            f"{max(0, int(time.time() - report['inspected_at']))}s ago",
                        ),
                    )
        return PanelPage(
            "ssh:" + self.view + ":" + self.target,
            crumbs,
            tuple(rows),
            column_headers=("SERVER", "ADDRESS", "CONNECTION")
            if self.view == "home"
            else ("NAME", "TYPE", "SIZE")
            if self.view == "models"
            else ("PID", "NAME", "STATE")
            if self.view == "processes"
            else None,
            table_section_id="servers" if self.view == "home" else "items",
        )

    def show(self, view: str | None = None, focus: str = "", *, fresh: bool = False) -> None:
        if view:
            self.view = view
        page = self.page()
        if fresh and (state := self.host._panel_states.get(page.id)):
            state.filter("")
            state.search_active = False
        self.host._open_panel(page, "model manager ssh " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def open(self) -> None:
        self.show("home")
        self.load("list")

    def adopt_inventory(self, value: dict) -> None:
        self.inventory = value
        self.reports = {
            key: report
            for key, report in self.reports.items()
            if key in value["servers"]
            and report.get("revision") == value["servers"][key]["revision"]
        }
        if self.target not in {"local", *value["servers"]} and self.view != "review":
            self.target = value["default"]
            self.view = "home"

    def leave(self) -> None:
        self.setup.leave()
        self.host._background_jobs.cancel(READ)
        self.read = None

    def load(self, operation: str) -> None:
        request = {
            "kind": "ssh_servers",
            "config_dir": str(self.host.cfg.config_dir),
            "operation": operation,
            "target": self.target,
            "revision": self.record().get("revision", ""),
            "agent_socket": os.environ.get("SSH_AUTH_SOCK", ""),
        }
        identity = self.host._background_jobs.submit(READ, request, timeout=TIMEOUT)
        self.read = (
            identity,
            self.manager.scope,
            self.revision,
            operation,
            self.target,
            str(self.host.cfg.config_dir),
        )
        self.feedback = ("Loading servers…" if operation == "list" else "Checking SSH…", "neutral")
        self.show()

    def accept(self, identity: str, result: Any, error: str) -> None:
        if not self.read or self.read[0] != identity:
            return
        _, scope, revision, operation, target, root = self.read
        self.read = None
        if (
            scope != self.manager.scope
            or revision != self.revision
            or target != self.target
            or root != str(self.host.cfg.config_dir)
        ):
            return
        success = not error and isinstance(result, dict) and result.get("status") == "ok"
        if success and operation == "list":
            self.adopt_inventory(result["inventory"])
            self.feedback = None
            if self.target not in {"local", *self.inventory["servers"]}:
                self.target = "local"
                self.view = "home"
        else:
            if operation != "list":
                previous = self.report()
                report = {
                    **(result or {}),
                    "revision": self.record().get("revision", ""),
                }
                if success and operation == "inspect":
                    report["inspected_at"] = report["checked_at"]
                elif success and previous.get("inspected_at"):
                    report["data"] = previous["data"]
                    report["inspected_at"] = previous["inspected_at"]
                self.reports[target] = report
            self.feedback = (
                (result or {}).get("message", "SSH check interrupted or unavailable; retry"),
                "success" if success else "error",
            )
            if (
                success
                and operation == "inspect"
                and result["data"]["directory_status"] != "Available"
            ):
                self.feedback = ("Connected; model directory unavailable", "warning")
        if self.active and not self.host._settings_input_request:
            self.show()

    def write(self, operation: str) -> None:
        if self.pending:
            return
        identity = uuid.uuid4().hex
        update = SSHServerChange(
            self.host.session_id,
            identity,
            str(self.host.cfg.config_dir),
            operation,
            asdict(self.draft) if operation in {"add", "edit"} else None,
            self.target,
            self.edit_revision if operation == "edit" else self.record().get("revision", ""),
            self.inventory.get("default_revision", "0"),
        )
        if not self.host._session_actions.submit(update):
            raise ValueError("Settings writer busy; retry")
        self.pending = {
            "id": identity,
            "revision": self.revision,
            "operation": operation,
            "target": self.draft.id if operation in {"add", "edit"} else self.target,
        }
        self.feedback = ("Saving…", "neutral")
        self.show()

    def saved(self, update: SSHServerChange, result: dict | None, error: str) -> None:
        if not self.pending or update.identity != self.pending["id"]:
            return
        pending, self.pending = self.pending, None
        if update.root != str(self.host.cfg.config_dir):
            return
        if result is not None:
            self.adopt_inventory(result)
            if self.target not in {"local", *result["servers"]} and self.view != "review":
                self.target = result["default"]
                self.view = "home"
        self.feedback = (error or "SSH settings saved", "error" if error else "success")
        if self.active and not self.host._settings_input_request:
            if (
                not error
                and self.revision == pending["revision"]
                and update.session_id == self.host.session_id
            ):
                if self.view == "review" and pending["operation"] in {"add", "edit"}:
                    self.target = pending["target"]
                    self.view = "detail"
                elif self.view == "remove" and pending["operation"] == "remove":
                    self.target = self.inventory["default"]
                    self.view = "home"
            self.show()

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("ssh-")
        if kind == "back":
            if action.target == "manager":
                self.manager.show("home", "ssh")
            else:
                self.show(action.target)
        elif kind == "select":
            self.target = action.target
            self.revision += 1
            self.feedback = None
            self.show("detail")
        elif kind in {"new", "edit"}:
            if kind == "new":
                self.draft = SSHServer(
                    "ssh-" + uuid.uuid4().hex[:12],
                    "SSH server",
                    "",
                    "",
                    known_hosts=str(Path.home() / ".ssh/known_hosts"),
                )
                self.edit_revision = ""
            else:
                self.draft = SSHServer(**self.record()["definition"])
                self.edit_revision = self.record()["revision"]
            self.revision += 1
            self.feedback = None
            self.show("form", fresh=True)
        elif kind.startswith("field:"):
            field = kind.removeprefix("field:")
            self.host._begin_settings_input(
                field.replace("_", " ").title(),
                "Private input · Escape returns",
                ("ssh-field", field),
            )
            self.host._set_input(str(getattr(self.draft, field)))
        elif kind == "agent":
            self.draft = replace(self.draft, use_agent=not self.draft.use_agent)
            self.revision += 1
            self.show()
        elif kind == "review":
            self.draft = self.draft.validate()
            self.show("review", "back", fresh=True)
        elif kind == "save":
            self.write("edit" if self.edit_revision else "add")
        elif kind == "remove":
            self.show("remove", "back", fresh=True)
        elif kind == "remove-confirm":
            self.write("remove")
        elif kind == "default":
            self.write("default")
        elif kind in {"test", "inspect", "reload"}:
            self.load("list" if kind == "reload" else kind)
        elif kind == "inspect-default":
            self.target = self.inventory.get("default", "local")
            self.revision += 1
            if self.target == "local":
                self.manager.show("hardware")
                self.manager.load("hardware")
            else:
                self.show("detail")
                self.load("inspect")
        elif kind == "cancel":
            self.stop()
        elif kind in {"serve", "adopt"}:
            record = self.record()
            self.manager.serving.new_remote_draft(
                self.target, record["revision"], record["definition"]["name"], adopt=kind == "adopt"
            )
        elif kind == "setup":
            self.setup.open()
        elif kind in {"models", "processes"}:
            self.show(kind)
        elif kind == "local-hardware":
            self.manager.show("hardware")
            self.manager.load("hardware")

    def answer(self, field: str, value: str | None) -> None:
        if value is not None:
            parsed: Any = int(value) if field == "port" else value.strip()
            if field == "port" and not 1 <= parsed <= 65535:
                raise ValueError("SSH port must be 1–65535")
            if field in {"identity_file", "known_hosts"} and parsed:
                parsed = str(Path(parsed).expanduser())
            self.draft = replace(self.draft, **{field: parsed})
            self.revision += 1
            self.feedback = None
        self.show("form")

    def stop(self) -> None:
        self.leave()
        self.feedback = ("SSH check cancelled", "warning")
        if self.active:
            self.show()
