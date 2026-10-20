"""Fixed local engine setup commands for CLI and TUI owned workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

Operation = Literal["inspect", "prepare", "build", "inventory", "logs", "prepare_remove", "remove"]
OPERATIONS = frozenset({"inspect", "prepare", "build", "inventory", "logs",
                        "prepare_remove", "remove"})
FIELDS = frozenset({"current", "engine", "executable", "source", "jobs", "profile",
                    "architectures", "host_compiler", "python", "owner", "id", "evidence"})


@dataclass(frozen=True)
class ModelDependencyCommand:
    operation: Operation
    config_dir: Path
    data_dir: Path
    values: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def for_client(cls, cfg: Any, operation: str, **values: Any) -> ModelDependencyCommand:
        return cls._validated(operation, Path(cfg.config_dir), Path(cfg.data_dir), values)

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ModelDependencyCommand:
        if request.get("kind") != "model_dependencies":
            raise ValueError("Invalid model dependency request")
        data_dir = request.get("data_dir")
        config_dir = request.get("config_dir", data_dir)
        if not isinstance(config_dir, str) or not isinstance(data_dir, str):
            raise ValueError("Invalid model dependency roots")
        if request.get("operation") in {"prepare_remove", "remove"} and "config_dir" not in request:
            raise ValueError("Invalid model dependency roots")
        values = {key: value for key, value in request.items() if key not in {
            "kind", "operation", "config_dir", "data_dir",
        }}
        return cls._validated(request.get("operation"), Path(config_dir), Path(data_dir), values)

    @classmethod
    def _validated(
        cls, operation: Any, config_dir: Path, data_dir: Path, values: dict[str, Any],
    ) -> ModelDependencyCommand:
        if (
            not isinstance(operation, str) or operation not in OPERATIONS
            or not config_dir.is_absolute() or not data_dir.is_absolute()
            or set(values) - FIELDS
        ):
            raise ValueError("Invalid model dependency request")
        return cls(cast(Operation, operation), config_dir, data_dir, values)

    def worker_request(self) -> dict[str, Any]:
        return {
            "kind": "model_dependencies", "operation": self.operation,
            "config_dir": str(self.config_dir), "data_dir": str(self.data_dir),
            **self.values,
        }

    def execute(self, progress: Callable[[dict], None] | None = None) -> dict:
        if self.operation in {"prepare_remove", "remove"}:
            import os

            os.environ["KLAUDE_CONFIG_DIR"] = str(self.config_dir)
            os.environ["KLAUDE_DATA_DIR"] = str(self.data_dir)
        from klaude_core.model_dependencies import execute as dependency_execute

        return dependency_execute(self.worker_request(), progress or (lambda _: None))
