"""Explicit host fingerprint verification and reviewed public-key enrollment."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from klaude_application.ssh_operations import SSHSetupCommand
from klaude_core.ssh_setup import TIMEOUT

from .session_actions import SSHServerChange
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

READ = "model-manager:ssh-setup-read"
WORK = "model-manager:ssh-setup-work"


def action(key: str, label: str, value: str = "", **kwargs) -> PanelRow:
    return PanelRow(
        key, RowKind.ACTION, label, value, action=PanelAction("ssh-setup-" + key), **kwargs
    )


def back(target: str) -> PanelRow:
    return PanelRow(
        "back",
        RowKind.NAVIGATION,
        "Back",
        control=RowControl.BACK,
        action=PanelAction("ssh-setup-back", target),
    )


class SSHSetupPanel:
    def __init__(self, parent: Any):
        self.parent = parent
        self.manager = parent.manager
        self.host = parent.host
        self.view = "home"
        self.target = ""
        self.revision = 0
        self.scan: dict = {}
        self.selected: dict = {}
        self.expected = ""
        self.public_path = ""
        self.review: dict = {}
        self.read: tuple | None = None
        self.task: dict | None = None
        self.write: dict | None = None
        self.stopping = False
        self.feedback: tuple[str, str] | None = None

    @property
    def active(self) -> bool:
        return str(self.host._choice_kind).startswith("model manager ssh setup")

    @property
    def busy(self) -> bool:
        return bool(self.task or self.write)

    @property
    def scope(self) -> tuple:
        return self.manager.scope, str(self.host.cfg.config_dir)

    def record(self) -> dict:
        return self.parent.inventory.get("servers", {}).get(self.target, {})

    def open(self) -> None:
        self.parent.leave()
        self.target = self.parent.target
        self.revision += 1
        self.scan = {}
        self.selected = {}
        self.review = {}
        self.expected = ""
        self.public_path = ""
        self.feedback = None
        self.show("home", fresh=True)

    def leave(self) -> None:
        self.host._background_jobs.cancel(READ)
        self.read = None

    def page(self) -> PanelPage:
        definition = self.record().get("definition", {})
        crumbs: tuple[str, ...] = (
            "Model Manager",
            "Servers",
            definition.get("name", "SSH server"),
            "Key setup",
        )
        rows: list[PanelRow] = []
        if self.view == "home":
            rows = [
                action("scan", "Verify host key", enabled=not self.busy),
                action("public", "Enroll public key", enabled=not self.busy),
                PanelRow(
                    "scope",
                    RowKind.INFO,
                    "Explicit trust and account access",
                    description="Verify the host fingerprint from its server/admin. "
                    "Enrollment uses existing verified SSH authentication.",
                ),
                PanelRow(
                    "identity",
                    RowKind.INFO,
                    "Current identity",
                    definition.get("identity_file") or "SSH agent",
                ),
                PanelRow("hosts", RowKind.INFO, "Known hosts", definition.get("known_hosts", "")),
                back("server"),
            ]
        elif self.view == "host":
            crumbs += ("Host fingerprints",)
            rows = [
                action("scan", "Reload fingerprints", enabled=not self.busy),
                PanelRow(
                    "warning",
                    RowKind.INFO,
                    "Discovery is not verification",
                    description="Compare with the fingerprint from the server/admin.",
                    value_tone="warning",
                ),
                PanelRow("columns", RowKind.TABLE_HEADER, "TYPE"),
            ]
            rows += [
                PanelRow(
                    "key:" + item["fingerprint"],
                    RowKind.NAVIGATION,
                    "Ed25519",
                    item["fingerprint"],
                    section_id="keys",
                    action=PanelAction("ssh-setup-select", item["fingerprint"]),
                )
                for item in self.scan.get("keys", [])
            ]
            if not self.scan:
                rows += [PanelRow("empty", RowKind.INFO, "Scan to discover candidate keys")]
            rows += [back("home")]
        elif self.view in {"verify", "trust-review"}:
            crumbs += ("Verify host",)
            rows = [
                PanelRow(
                    "observed",
                    RowKind.INFO,
                    "Observed fingerprint",
                    self.selected.get("fingerprint", "Unavailable"),
                )
            ]
            if self.view == "verify":
                rows += [
                    action("expected", "Verified fingerprint", self.expected or "Enter value"),
                    PanelRow(
                        "source",
                        RowKind.INFO,
                        "Use the server/admin's fingerprint",
                        description="A scan alone cannot establish host identity.",
                    ),
                    action("trust-review", "Review host trust", enabled=bool(self.expected)),
                    back("host"),
                ]
            else:
                crumbs += ("Review",)
                rows += [
                    PanelRow("expected", RowKind.INFO, "Verified fingerprint", self.expected),
                    PanelRow(
                        "address",
                        RowKind.INFO,
                        "Host",
                        f"{self.scan.get('host')}:{self.scan.get('port')}",
                    ),
                    PanelRow(
                        "effect",
                        RowKind.INFO,
                        "Save a private host pin",
                        description="Updates this definition's trust-file reference. "
                        "Existing known-hosts files and identity remain intact.",
                    ),
                    action("trust-save", "Save verified host", enabled=not self.busy),
                    back("verify"),
                ]
        elif self.view in {"public", "enroll-review"}:
            crumbs += ("Enroll public key",)
            if self.view == "public":
                rows = [
                    action("public-file", "Public key file", self.public_path or "Enter .pub path"),
                    action(
                        "enroll-review",
                        "Review enrollment",
                        enabled=bool(self.public_path) and not self.busy,
                    ),
                    PanelRow(
                        "scope",
                        RowKind.INFO,
                        "Existing Ed25519 public key",
                        description="Uses your current identity/agent. Private key contents "
                        "and passwords are not requested.",
                    ),
                    back("home"),
                ]
            else:
                crumbs += ("Review",)
                rows = [
                    PanelRow(
                        "account",
                        RowKind.INFO,
                        "SSH account",
                        f"{definition.get('user')}@{definition.get('host')}",
                    ),
                    PanelRow(
                        "key",
                        RowKind.INFO,
                        "Public fingerprint",
                        self.review.get("fingerprint", "Unavailable"),
                    ),
                    PanelRow("target", RowKind.INFO, "Remote file", self.review.get("target", "")),
                    PanelRow(
                        "presence",
                        RowKind.INFO,
                        "Key status",
                        "Already present" if self.review.get("present") else "New key",
                    ),
                    PanelRow(
                        "effect",
                        RowKind.INFO,
                        "Grants SSH access to this account",
                        description="Appends one public key. Existing entries/restrictions "
                        "are retained; current identity selection stays the same.",
                    ),
                    action("enroll", "Enroll public key", enabled=not self.busy),
                    back("public"),
                ]
        elif self.view == "progress":
            crumbs += ("Enrollment",)
            rows = [
                action(
                    "cancel", "Cancel enrollment", enabled=bool(self.task) and not self.stopping
                ),
                PanelRow(
                    "scope",
                    RowKind.INFO,
                    "Reviewed append in progress",
                    description="Cancellation waits for local worker cleanup; "
                    "a completed append may remain.",
                ),
                back("home"),
            ]
        if self.read:
            rows.insert(0, action("cancel-check", "Cancel check"))
        return PanelPage(
            "ssh-setup:" + self.view + ":" + self.target,
            crumbs,
            tuple(rows),
            column_headers=("TYPE", "FINGERPRINT", "") if self.view == "host" else None,
            table_section_id="keys",
            scrollable_body=self.view in {"trust-review", "enroll-review"},
            scroll_wrapped_rows=self.view in {"trust-review", "enroll-review"},
        )

    def show(self, view: str | None = None, focus: str = "", *, fresh: bool = False) -> None:
        if view:
            self.view = view
        page = self.page()
        if fresh and (state := self.host._panel_states.get(page.id)):
            state.filter("")
            state.search_active = False
        self.host._open_panel(page, "model manager ssh setup " + self.view, focus)
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def request(self, operation: str) -> dict:
        return SSHSetupCommand.for_client(
            self.host.cfg, operation, target=self.target,
            revision=self.record().get("revision", ""),
            public_file=self.public_path, review=self.review,
            agent_socket=os.environ.get("SSH_AUTH_SOCK", ""),
        ).worker_request()

    def load(self, operation: str) -> None:
        identity = self.host._background_jobs.submit(READ, self.request(operation), timeout=TIMEOUT)
        self.read = identity, self.scope, self.revision, self.target, operation
        self.feedback = (
            "Discovering host key…" if operation == "scan" else "Reviewing remote keys…",
            "neutral",
        )
        self.show()

    def matches(self, captured: dict) -> bool:
        return (
            captured["scope"] == self.scope
            and captured["target"] == self.target
            and captured["revision"] == self.revision
        )

    def accept(self, key: str, identity: str, result: Any, error: str) -> None:
        if key == WORK:
            if not self.task or self.task["id"] != identity:
                return
            task, self.task = self.task, None
            self.stopping = False
            feedback = (
                ("Enrollment unconfirmed; review remote keys before retrying", "warning")
                if error or not isinstance(result, dict)
                else (
                    result.get("message", "Enrollment failed"),
                    "success"
                    if result.get("status") == "ok"
                    else "warning"
                    if result.get("status") == "unknown"
                    else "error",
                )
            )
            if self.matches(task) and self.active and not self.host._settings_input_request:
                self.feedback = feedback
                self.show("home" if self.view == "progress" else None)
            self.host._start_next()
            return
        captured = self.read
        if not captured or captured[0] != identity:
            return
        self.read = None
        _, scope, revision, target, operation = captured
        if scope != self.scope or revision != self.revision or target != self.target:
            return
        if error or not isinstance(result, dict) or result.get("status") != "ok":
            self.feedback = (
                (result if isinstance(result, dict) else {}).get(
                    "message", "SSH setup check unavailable; retry"
                ),
                "error",
            )
        elif operation == "scan":
            self.scan = result
            self.feedback = ("Verify the fingerprint from the server/admin", "warning")
        else:
            self.review = result["review"]
            self.feedback = None
            if self.active and not self.host._settings_input_request:
                self.show("enroll-review", "back", fresh=True)
                return
        if self.active and not self.host._settings_input_request:
            self.show()

    def saved(self, update: SSHServerChange, result: dict | None, error: str) -> None:
        if not self.write or self.write["id"] != update.identity:
            return
        captured, self.write = self.write, None
        if result is not None and update.root == str(self.host.cfg.config_dir):
            self.parent.adopt_inventory(result)
        feedback = (
            error or "Verified host pin saved",
            "warning" if "unconfirmed" in error else "error" if error else "success",
        )
        if self.matches(captured) and self.active and not self.host._settings_input_request:
            self.feedback = feedback
            self.show("home" if self.view == "trust-review" else None)
        self.host._start_next()

    def action(self, event: PanelAction) -> None:
        kind = event.kind.removeprefix("ssh-setup-")
        if kind in {"back", "scan", "select", "public", "cancel-check"}:
            self.leave()
            self.revision += 1
        if kind == "back":
            if event.target == "server":
                self.parent.target = self.target
                self.parent.show("detail")
            else:
                self.show(event.target)
        elif kind == "scan":
            self.scan = {}
            self.show("host", fresh=True)
            self.load("scan")
        elif kind == "select":
            self.selected = next(
                item for item in self.scan["keys"] if item["fingerprint"] == event.target
            )
            self.expected = ""
            self.show("verify", "expected", fresh=True)
        elif kind == "public":
            self.review = {}
            self.feedback = None
            self.show("public", fresh=True)
        elif kind in {"expected", "public-file"}:
            self.host._begin_settings_input(
                "Verified fingerprint" if kind == "expected" else "Public key file",
                "Private single-line input · Escape returns",
                ("ssh-setup-field", kind),
            )
            self.host._set_input(self.expected if kind == "expected" else self.public_path)
        elif kind == "trust-review":
            if self.expected != self.selected.get("fingerprint"):
                raise ValueError("Verified fingerprint does not match the discovered host")
            self.feedback = None
            self.show("trust-review", "back", fresh=True)
        elif kind == "enroll-review":
            self.load("review")
        elif kind in {"trust-save", "enroll"}:
            if self.busy or self.host._session_action_is_busy():
                self.feedback = ("Finish active work before changing SSH access", "warning")
                self.show()
                return
            identity = uuid.uuid4().hex
            if kind == "trust-save":
                receipt = {
                    **self.selected,
                    "expected_fingerprint": self.expected,
                    "host": self.scan["host"],
                    "port": self.scan["port"],
                    "observed_at": self.scan["observed_at"],
                }
                update = SSHServerChange(
                    self.host.session_id,
                    identity,
                    str(self.host.cfg.config_dir),
                    "trust",
                    receipt,
                    self.target,
                    self.scan["server_revision"],
                )
                if not self.host._session_actions.submit(update):
                    raise ValueError("Settings writer busy; retry")
                self.write = {
                    "id": identity,
                    "scope": self.scope,
                    "target": self.target,
                    "revision": self.revision,
                }
                self.feedback = ("Saving verified host pin…", "neutral")
                self.show()
            else:
                worker = self.host._background_jobs.submit(
                    WORK, self.request("enroll"), timeout=TIMEOUT, notify_cancel=True
                )
                self.task = {
                    "id": worker,
                    "scope": self.scope,
                    "target": self.target,
                    "revision": self.revision,
                }
                self.feedback = ("Enrolling public key…", "neutral")
                self.show("progress", fresh=True)
        elif kind == "cancel":
            self.stop()
        elif kind == "cancel-check":
            self.feedback = ("SSH setup check cancelled", "neutral")
            self.show()

    def answer(self, field: str, value: str | None) -> None:
        if value is not None:
            if field == "expected":
                self.expected = value.strip()
            else:
                self.public_path = str(Path(value.strip()).expanduser().absolute())
                self.review = {}
            self.revision += 1
            self.feedback = None
        self.show()

    def stop(self) -> None:
        if self.task and not self.stopping:
            self.stopping = True
            self.host._background_jobs.cancel(WORK)
            self.feedback = ("Cancelling enrollment…", "neutral")
            if self.active and not self.host._settings_input_request:
                self.show()

    def stopped(self, identity: str) -> None:
        if self.task and self.task["id"] == identity:
            task, self.task = self.task, None
            self.stopping = False
            if self.matches(task) and self.active and not self.host._settings_input_request:
                self.feedback = (
                    "Enrollment cancelled; completed append may remain; review before retrying",
                    "warning",
                )
                self.show("home" if self.view == "progress" else None)
            self.host._start_next()
