"""Shared private Library artifact reads and reviewed changes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from klaude_core.library_artifacts import ArtifactStore, execute_artifact_change

Operation = Literal["import", "export", "open", "tags", "archive", "restore",
                    "delete", "clear_ai_tags"]
OPERATIONS = frozenset({"import", "export", "open", "tags", "archive", "restore",
                        "delete", "clear_ai_tags"})


@dataclass(frozen=True)
class ArtifactChange:
    root: Path
    operation: Operation
    target: str = ""
    revision: int = 0
    value: str = field(default="", repr=False)
    kind: str = "document"
    session: str = ""
    workspace: Path | None = None

    @classmethod
    def reviewed(
        cls, root: Path, operation: str, *, target: str = "", revision: int = 0,
        value: str = "", kind: str = "document", session: str = "",
        workspace: Path | None = None,
    ) -> ArtifactChange:
        if (
            not isinstance(operation, str) or operation not in OPERATIONS
            or not Path(root).is_absolute()
            or not isinstance(target, str) or len(target) > 256
            or type(revision) is not int or revision < 0
            or not isinstance(value, str)
            or not isinstance(kind, str) or not isinstance(session, str)
            or workspace is not None and not Path(workspace).is_absolute()
        ):
            raise ValueError("Invalid artifact change")
        return cls(Path(root), cast(Operation, operation), target, revision,
                   value, kind, session, Path(workspace) if workspace else None)

    def apply(self) -> dict[str, Any]:
        return execute_artifact_change(
            self.root, self.operation, target=self.target, revision=self.revision,
            value=self.value, kind=self.kind, session=self.session, workspace=self.workspace,
        )


class ArtifactService:
    def __init__(self, root: Path) -> None:
        self.store = ArtifactStore(root)

    @property
    def root(self) -> Path:
        return self.store.root

    def get(self, identity: str) -> dict[str, Any]:
        return self.store.get(identity)

    def attachment(self, identity: str, revision: int) -> tuple[str, bytes]:
        """Capture exact current bytes under the store transaction, with no opener."""
        if type(revision) is not int or revision < 1:
            raise ValueError("Invalid file revision")
        with self.store.database() as db:
            row = db.execute(
                "SELECT filename,content,sha256,revision,archived,size FROM artifacts WHERE id=?",
                (identity,),
            ).fetchone()
            if row is None or row["revision"] != revision or row["archived"]:
                raise ValueError("File changed or was archived; choose it again")
            if row["size"] > 32 * 1024 * 1024:
                raise ValueError("Choose a file up to 32 MiB")
            data = bytes(row["content"])
            if len(data) != row["size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("Stored file checksum failed")
            return str(row["filename"]), data

    def change(self, action: ArtifactChange) -> dict[str, Any]:
        if action.root != self.root:
            raise ValueError("Artifact root changed; reload before saving")
        return action.apply()
