"""Fixed SSH diagnostics and reviewed key-setup commands for embedded clients."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from klaude_core.settings_store import settings_lock

from .operation_journal import (
    OperationConflict,
    OperationFenceLost,
    OperationJournal,
    OperationReceipt,
)

DiagnosticOperation = Literal["list", "test", "inspect"]
SetupOperation = Literal["scan", "review", "enroll"]
DefinitionOperation = Literal["add", "edit", "remove", "default", "trust"]
DIAGNOSTICS = frozenset({"list", "test", "inspect"})
SETUP = frozenset({"scan", "review", "enroll"})
DEFINITIONS = frozenset({"add", "edit", "remove", "default", "trust"})
TARGET = re.compile(r"[A-Za-z0-9_.-]{1,128}")


class SSHChangeUnconfirmed(RuntimeError):
    """The definition effect or its durable acknowledgement is uncertain."""


def ssh_resource(root: Path) -> str:
    """Stable private journal resource for one SSH definition file."""
    path = Path(root).resolve() / "model-servers.json"
    return "ssh:" + hashlib.sha256(str(path).encode()).hexdigest()


def recover_ssh_definition(
    root: Path, journal: OperationJournal, request_id: str, owner_id: str,
) -> OperationReceipt:
    """Reconcile an unknown definition write by exact locked state, without replay."""
    from klaude_core.ssh_servers import load

    fenced = journal.fenced_operation(ssh_resource(root))
    if (
        fenced is None or fenced.owner_id != owner_id
        or fenced.receipt.request_id != request_id
        or fenced.receipt.state != "unknown"
    ):
        raise OperationConflict("Matching uncertain SSH definition change unavailable")
    with settings_lock(Path(root) / "model-servers.json", timeout=2):
        return journal.reconcile_witness(
            request_id, owner_id, current=load(root)
        )


@dataclass(frozen=True)
class SSHDiagnostic:
    operation: DiagnosticOperation
    config_dir: Path
    target: str = ""
    revision: str = ""
    agent_socket: str = field(default="", repr=False)

    @classmethod
    def for_client(
        cls, cfg: Any, operation: str, *, target: str = "", revision: str = "",
        agent_socket: str = "",
    ) -> SSHDiagnostic:
        return cls._validated(operation, Path(cfg.config_dir), target, revision, agent_socket)

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> SSHDiagnostic:
        if request.get("kind") != "ssh_servers" or set(request) - {
            "kind", "operation", "config_dir", "target", "revision", "agent_socket",
        }:
            raise ValueError("Invalid SSH diagnostic request")
        root = request.get("config_dir")
        if not isinstance(root, str):
            raise ValueError("Invalid SSH diagnostic root")
        return cls._validated(
            request.get("operation"), Path(root), request.get("target", ""),
            request.get("revision", ""), request.get("agent_socket", ""),
        )

    @classmethod
    def _validated(
        cls, operation: Any, root: Path, target: Any, revision: Any, agent_socket: Any,
    ) -> SSHDiagnostic:
        if (
            not isinstance(operation, str) or operation not in DIAGNOSTICS
            or not root.is_absolute()
            or not isinstance(target, str) or target and not TARGET.fullmatch(target)
            or operation != "list" and not target
            or not isinstance(revision, str) or len(revision) > 256
            or not isinstance(agent_socket, str) or len(agent_socket) > 4096
        ):
            raise ValueError("Invalid SSH diagnostic request")
        return cls(cast(DiagnosticOperation, operation), root, target, revision, agent_socket)

    def worker_request(self) -> dict[str, str]:
        return {"kind": "ssh_servers", "operation": self.operation,
                "config_dir": str(self.config_dir), "target": self.target,
                "revision": self.revision, "agent_socket": self.agent_socket}

    def execute(self) -> dict:
        from klaude_core.ssh_servers import execute

        return execute(self.worker_request())


@dataclass(frozen=True)
class SSHSetupCommand:
    operation: SetupOperation
    config_dir: Path
    target: str
    revision: str
    public_file: str = ""
    review: dict[str, Any] = field(default_factory=dict, repr=False)
    agent_socket: str = field(default="", repr=False)

    @classmethod
    def for_client(cls, cfg: Any, operation: str, **values: Any) -> SSHSetupCommand:
        return cls._validated(operation, Path(cfg.config_dir), values)

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> SSHSetupCommand:
        if request.get("kind") != "ssh_setup" or set(request) - {
            "kind", "operation", "config_dir", "target", "revision", "public_file",
            "review", "agent_socket",
        }:
            raise ValueError("Invalid SSH setup request")
        root = request.get("config_dir")
        if not isinstance(root, str):
            raise ValueError("Invalid SSH setup root")
        values = {key: value for key, value in request.items() if key not in {
            "kind", "operation", "config_dir",
        }}
        return cls._validated(request.get("operation"), Path(root), values)

    @classmethod
    def _validated(
        cls, operation: Any, root: Path, values: dict[str, Any],
    ) -> SSHSetupCommand:
        target, revision = values.get("target"), values.get("revision")
        public_file = values.get("public_file", "")
        review = values.get("review", {})
        agent_socket = values.get("agent_socket", "")
        if (
            not isinstance(operation, str) or operation not in SETUP
            or not root.is_absolute() or set(values) - {
                "target", "revision", "public_file", "review", "agent_socket",
            }
            or not isinstance(target, str) or not TARGET.fullmatch(target)
            or not isinstance(revision, str) or len(revision) > 256
            or not isinstance(public_file, str) or len(public_file) > 4096
            or operation != "scan" and not public_file
            or not isinstance(review, dict)
            or not isinstance(agent_socket, str) or len(agent_socket) > 4096
        ):
            raise ValueError("Invalid SSH setup request")
        return cls(cast(SetupOperation, operation), root, target, revision,
                   public_file, review, agent_socket)

    def worker_request(self) -> dict[str, Any]:
        return {"kind": "ssh_setup", "operation": self.operation,
                "config_dir": str(self.config_dir), "target": self.target,
                "revision": self.revision, "public_file": self.public_file,
                "review": self.review, "agent_socket": self.agent_socket}

    def execute(self) -> dict:
        from klaude_core.ssh_setup import execute

        return execute(self.worker_request())


@dataclass(frozen=True)
class SSHDefinitionChange:
    root: Path
    operation: DefinitionOperation
    target: str = ""
    revision: str = ""
    default_revision: str = ""
    definition: dict[str, Any] | None = field(default=None, repr=False)

    @classmethod
    def reviewed(
        cls, root: Path, operation: str, *, target: str = "", revision: str = "",
        default_revision: str = "", definition: dict[str, Any] | None = None,
    ) -> SSHDefinitionChange:
        if (
            not isinstance(operation, str) or operation not in DEFINITIONS
            or not Path(root).is_absolute()
            or not isinstance(target, str) or target and not TARGET.fullmatch(target)
            or operation in {"edit", "remove", "default", "trust"} and not target
            or not isinstance(revision, str) or len(revision) > 256
            or not isinstance(default_revision, str) or len(default_revision) > 256
            or definition is not None and not isinstance(definition, dict)
        ):
            raise ValueError("Invalid SSH definition change")
        return cls(Path(root), cast(DefinitionOperation, operation), target,
                   revision, default_revision, definition)

    def apply(self) -> dict:
        from klaude_core.ssh_servers import change

        return change(self.root, self.operation, definition=self.definition,
                      target=self.target, revision=self.revision,
                      default_revision=self.default_revision)

    def apply_journaled(
        self, journal: OperationJournal, request_id: str, owner_id: str,
    ) -> dict:
        """Fence one local definition write; trust/pin has a separate effect path."""
        from klaude_core.ssh_servers import change

        if self.operation == "trust":
            raise ValueError("SSH host trust requires its separate reviewed path")
        intent = json.dumps({
            "operation": self.operation, "target": self.target,
            "revision": self.revision, "default_revision": self.default_revision,
            "definition": self.definition,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        if len(intent) > 262_144:
            raise ValueError("SSH definition intent exceeds safety limit")
        receipt = journal.admit(
            request_id=request_id, owner_id=owner_id, kind="SSHDefinitionChange",
            resource=ssh_resource(self.root),
            payload={"sha256": hashlib.sha256(intent).hexdigest()},
            lease_seconds=60,
        )
        if not receipt.created:
            raise OperationConflict("SSH definition request was already submitted")
        started = False

        def before_publish(before: dict, after: dict) -> None:
            nonlocal started
            journal.record_witness(
                request_id, owner_id, receipt.fence, before=before, after=after,
            )
            # The start transaction may commit even if its acknowledgement fails.
            # Treat that boundary as uncertain; recovery can compare the witness.
            started = True
            journal.start(request_id, owner_id, receipt.fence)
            journal.check_effect(request_id, owner_id, receipt.fence)

        try:
            result = change(
                self.root, self.operation, definition=self.definition,
                target=self.target, revision=self.revision,
                default_revision=self.default_revision,
                before_publish=before_publish,
            )
        except Exception as exc:
            if started:
                try:
                    journal.mark_unknown(request_id, owner_id, receipt.fence)
                except (OSError, sqlite3.Error, OperationFenceLost):
                    pass  # An expired running receipt stays unknown and fenced.
                raise SSHChangeUnconfirmed(
                    "SSH definition outcome uncertain; run `klaude model-manager ssh recover`"
                ) from exc
            try:
                current = journal.status(request_id, owner_id)
                if current is not None and current.state == "accepted":
                    journal.finish(request_id, owner_id, receipt.fence, state="failed",
                                   outcome="failed")
            except (OSError, sqlite3.Error, OperationFenceLost):
                raise SSHChangeUnconfirmed(
                    "SSH definition admission uncertain; inspect journal before retrying"
                ) from exc
            raise
        try:
            journal.finish(request_id, owner_id, receipt.fence, state="completed",
                           outcome="ok")
        except (OSError, sqlite3.Error, OperationFenceLost) as exc:
            try:
                journal.mark_unknown(request_id, owner_id, receipt.fence)
            except (OSError, sqlite3.Error, OperationFenceLost):
                pass  # Expiry also leaves a running write unknown and fenced.
            raise SSHChangeUnconfirmed(
                "SSH definition saved but acknowledgement uncertain; "
                "run `klaude model-manager ssh recover`"
            ) from exc
        return result
