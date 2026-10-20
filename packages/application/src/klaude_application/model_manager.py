"""Private fixed Model Manager operations shared by embedded clients."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

Operation = Literal["connections", "hardware", "search", "inventory", "pull", "delete"]
OPERATIONS = frozenset({"connections", "hardware", "search", "inventory", "pull", "delete"})
FIELDS = frozenset({"endpoint", "current", "query", "model", "digest",
                    "revision", "credential_revision"})


def _environment_name(name: str) -> bool:
    return bool(
        re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name)
        and name not in {"HOME", "PATH", "PYTHONPATH", "PYTHONHOME"}
        and (not name.startswith("KLAUDE_") or name.startswith("KLAUDE_MODEL_"))
    )


@dataclass(frozen=True)
class ModelManagerCommand:
    operation: Operation
    config_dir: Path
    data_dir: Path
    values: dict[str, Any] = field(default_factory=dict)
    environment_keys: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def for_client(
        cls, cfg: Any, operation: str, **values: Any,
    ) -> ModelManagerCommand:
        key_env = values.pop("key_env", "")
        if not isinstance(key_env, str):
            raise ValueError("Invalid model credential variable")
        environment_keys = {
            name: value
            for name in ("HUGGINGFACE_API_KEY", key_env)
            if name and _environment_name(name)
            and (value := os.environ.get(name)) is not None and len(value) <= 8192
        }
        return cls._validated(
            operation, Path(cfg.config_dir), Path(cfg.data_dir), values, environment_keys
        )

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ModelManagerCommand:
        values = {key: value for key, value in request.items() if key not in {
            "kind", "operation", "config_dir", "data_dir", "environment_keys",
        }}
        if request.get("kind") != "model_manager":
            raise ValueError("Invalid Model Manager request")
        config_dir, data_dir = request.get("config_dir"), request.get("data_dir")
        environment_keys = request.get("environment_keys", {})
        if not isinstance(config_dir, str) or not isinstance(data_dir, str):
            raise ValueError("Invalid Model Manager roots")
        return cls._validated(
            request.get("operation"), Path(config_dir), Path(data_dir),
            values, environment_keys,
        )

    @classmethod
    def _validated(
        cls, operation: Any, config_dir: Path, data_dir: Path,
        values: dict[str, Any], environment_keys: Any,
    ) -> ModelManagerCommand:
        if (
            not isinstance(operation, str) or operation not in OPERATIONS
            or not config_dir.is_absolute() or not data_dir.is_absolute()
            or set(values) - FIELDS
            or not isinstance(environment_keys, dict)
            or any(not isinstance(name, str) or not _environment_name(name)
                   or not isinstance(value, str) or len(value) > 8192
                   for name, value in environment_keys.items())
        ):
            raise ValueError("Invalid Model Manager request")
        return cls(cast(Operation, operation), config_dir, data_dir,
                   values, environment_keys)

    def worker_request(self) -> dict[str, Any]:
        return {
            "kind": "model_manager", "operation": self.operation,
            "config_dir": str(self.config_dir), "data_dir": str(self.data_dir),
            "environment_keys": self.environment_keys, **self.values,
        }

    def execute(self, progress: Callable[[dict], None] | None = None) -> dict:
        os.environ["KLAUDE_CONFIG_DIR"] = str(self.config_dir)
        os.environ["KLAUDE_DATA_DIR"] = str(self.data_dir)
        os.environ.update(self.environment_keys)
        from klaude_core.config import load_config
        from klaude_core.ollama_manager import execute_manager

        return execute_manager(load_config(), self.worker_request(), progress or (lambda _: None))
