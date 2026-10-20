"""Private fixed Vision analysis/tagging requests for owned workers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

Operation = Literal["inspect", "prepare", "analyze", "tags_prepare", "tags_suggest", "tags_apply"]
OPERATIONS = frozenset({"inspect", "prepare", "analyze", "tags_prepare",
                        "tags_suggest", "tags_apply"})
FIELDS = frozenset({"artifact", "revision", "question", "context", "output_tokens",
                    "spec", "proposal", "selected", "reference", "expected"})


def _allowed_key(name: Any, value: Any) -> bool:
    return bool(
        isinstance(name, str)
        and re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name)
        and name not in {"HOME", "PATH", "PYTHONPATH", "PYTHONHOME"}
        and not name.startswith("KLAUDE_")
        and isinstance(value, str) and len(value) <= 8192
    )


@dataclass(frozen=True)
class VisionCommand:
    operation: Operation
    config_dir: Path
    data_dir: Path
    ollama_url: str
    roles: dict[str, str] = field(repr=False)
    environment_keys: dict[str, str] = field(default_factory=dict, repr=False)
    values: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def for_client(
        cls, cfg: Any, operation: str, *, environment_keys: dict[str, str] | None = None,
        **values: Any,
    ) -> VisionCommand:
        return cls._validated(
            operation, Path(cfg.config_dir), Path(cfg.data_dir), cfg.ollama_url,
            dict(cfg.models), {name: value for name, value in (environment_keys or {}).items()
                               if _allowed_key(name, value)}, values,
        )

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> VisionCommand:
        if request.get("kind") != "vision":
            raise ValueError("Invalid Vision request")
        config_dir, data_dir = request.get("config_dir"), request.get("data_dir")
        if not isinstance(config_dir, str) or not isinstance(data_dir, str):
            raise ValueError("Invalid Vision roots")
        values = {key: value for key, value in request.items() if key not in {
            "kind", "operation", "config_dir", "data_dir", "ollama_url", "roles",
            "environment_keys",
        }}
        return cls._validated(
            request.get("operation"), Path(config_dir), Path(data_dir),
            request.get("ollama_url"), request.get("roles"),
            {name: value for name, value in request.get("environment_keys", {}).items()
             if _allowed_key(name, value)}
            if isinstance(request.get("environment_keys", {}), dict)
            else request.get("environment_keys"), values,
        )

    @classmethod
    def _validated(
        cls, operation: Any, config_dir: Path, data_dir: Path, ollama_url: Any,
        roles: Any, environment_keys: Any, values: dict[str, Any],
    ) -> VisionCommand:
        if (
            not isinstance(operation, str) or operation not in OPERATIONS
            or not config_dir.is_absolute() or not data_dir.is_absolute()
            or not isinstance(ollama_url, str) or not isinstance(roles, dict)
            or not isinstance(environment_keys, dict)
            or set(values) - FIELDS
            or operation in {"analyze", "tags_suggest"} and not isinstance(values.get("spec"), dict)
        ):
            raise ValueError("Invalid Vision request")
        return cls(cast(Operation, operation), config_dir, data_dir,
                   ollama_url, roles, environment_keys, values)

    def worker_request(self) -> dict[str, Any]:
        return {"kind": "vision", "operation": self.operation,
                "config_dir": str(self.config_dir), "data_dir": str(self.data_dir),
                "ollama_url": self.ollama_url, "roles": self.roles,
                "environment_keys": self.environment_keys, **self.values}

    def execute(self) -> dict:
        os.environ.update(self.environment_keys)
        from klaude_core.vision import execute

        return execute(self.worker_request())
