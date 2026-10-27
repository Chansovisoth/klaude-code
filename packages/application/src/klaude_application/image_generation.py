"""Fixed private image-service operations for CLI and TUI workers."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast

from .image_settings import ImageSettingsUnconfirmed, save_image_settings
from .operation_journal import OperationConflict, OperationJournal

Operation = Literal[
    "read", "inspect", "save", "prepare", "run", "recovery_review", "recover",
    "history", "review_job", "refresh", "forget", "cancel", "status",
]
OPERATIONS = frozenset({"read", "inspect", "save", "prepare", "run", "recovery_review",
                        "recover", "history", "review_job", "refresh", "forget",
                        "cancel", "status"})
FIELDS = frozenset({"endpoint", "settings", "revision", "prompt", "options", "spec",
                    "id", "offset", "abandon", "request_id", "owner_id", "provider", "model"})


@dataclass(frozen=True)
class ImageGenerationCommand:
    operation: Operation
    config_dir: Path
    data_dir: Path
    values: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def for_client(cls, cfg: Any, operation: str, **values: Any) -> ImageGenerationCommand:
        return cls._validated(operation, Path(cfg.config_dir), Path(cfg.data_dir), values)

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ImageGenerationCommand:
        if request.get("kind") != "image_generation":
            raise ValueError("Invalid image generation request")
        config_dir, data_dir = request.get("config_dir"), request.get("data_dir")
        if not isinstance(config_dir, str) or not isinstance(data_dir, str):
            raise ValueError("Invalid image generation roots")
        values = {key: value for key, value in request.items() if key not in {
            "kind", "operation", "config_dir", "data_dir",
        }}
        return cls._validated(request.get("operation"), Path(config_dir), Path(data_dir), values)

    @classmethod
    def _validated(
        cls, operation: Any, config_dir: Path, data_dir: Path, values: dict[str, Any],
    ) -> ImageGenerationCommand:
        if (
            not isinstance(operation, str) or operation not in OPERATIONS
            or not config_dir.is_absolute() or not data_dir.is_absolute()
            or set(values) - FIELDS
            or operation in {"run", "recover", "forget"}
            and not isinstance(values.get("spec"), dict)
            or operation in {"cancel", "status", "recover", "forget", "refresh",
                             "review_job", "recovery_review"}
            and not isinstance(values.get("id"), str)
            or operation == "save" and (
                not isinstance(values.get("settings"), dict)
                or not isinstance(values.get("revision"), str)
                or not isinstance(values.get("request_id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", values["request_id"])
                or not isinstance(values.get("owner_id"), str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}",
                                    values["owner_id"])
            )
        ):
            raise ValueError("Invalid image generation request")
        return cls(cast(Operation, operation), config_dir, data_dir, values)

    def worker_request(self) -> dict[str, Any]:
        return {"kind": "image_generation", "operation": self.operation,
                "config_dir": str(self.config_dir), "data_dir": str(self.data_dir),
                **self.values}

    def execute(self) -> dict:
        if self.operation == "save":
            from klaude_core.image_generation import inspect_settings

            cfg = SimpleNamespace(config_dir=self.config_dir, data_dir=self.data_dir)
            try:
                candidate = self.values["settings"]
                if type(candidate.get("enabled")) is not bool:
                    raise ValueError("Invalid generation enable switch")
                if candidate["enabled"]:
                    evidence = inspect_settings(candidate)
                    if evidence["model"] != candidate["model"]:
                        raise ValueError("Loaded model changed; Test again")
                journal = OperationJournal(self.data_dir / "operations.db")
                result = save_image_settings(
                    cfg, candidate, self.values["revision"], journal,
                    self.values["request_id"], self.values["owner_id"],
                )
                return {"settings": result}
            except (ValueError, OSError, sqlite3.Error, KeyError, TypeError,
                    OperationConflict, ImageSettingsUnconfirmed) as exc:
                return {
                    "status": "error",
                    "message": str(exc) if isinstance(exc, (ValueError, OperationConflict,
                                                      ImageSettingsUnconfirmed)) else
                    "Image-service settings unavailable; check journal before retrying",
                }
        from klaude_core.image_generation import execute

        return execute(self.worker_request())
