"""Fixed serving inspection commands for embedded CLI and TUI clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

Operation = Literal["probe", "prepare", "logs", "inventory"]
OPERATIONS = frozenset({"probe", "prepare", "logs", "inventory"})
FIELDS = frozenset({"engine", "executable", "spec", "evidence", "id",
                    "server_revision", "agent_socket"})


@dataclass(frozen=True)
class ServingRead:
    operation: Operation
    data_dir: Path | None = None
    config_dir: Path | None = None
    values: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def for_client(cls, cfg: Any, operation: str, **values: Any) -> ServingRead:
        return cls._validated(operation, Path(cfg.data_dir), Path(cfg.config_dir), values)

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ServingRead:
        if request.get("kind") != "serving_read":
            raise ValueError("Invalid serving read request")
        data_dir, config_dir = request.get("data_dir"), request.get("config_dir")
        if data_dir is not None and not isinstance(data_dir, str) or (
            config_dir is not None and not isinstance(config_dir, str)
        ):
            raise ValueError("Invalid serving read roots")
        values = {key: value for key, value in request.items() if key not in {
            "kind", "operation", "data_dir", "config_dir",
        }}
        return cls._validated(
            request.get("operation"), Path(data_dir) if data_dir else None,
            Path(config_dir) if config_dir else None, values,
        )

    @classmethod
    def _validated(
        cls, operation: Any, data_dir: Path | None, config_dir: Path | None,
        values: dict[str, Any],
    ) -> ServingRead:
        if (
            not isinstance(operation, str) or operation not in OPERATIONS
            or set(values) - FIELDS
            or data_dir is not None and not data_dir.is_absolute()
            or config_dir is not None and not config_dir.is_absolute()
            or operation in {"logs", "inventory"} and data_dir is None
            or operation == "prepare" and not isinstance(values.get("spec"), dict)
        ):
            raise ValueError("Invalid serving read request")
        return cls(cast(Operation, operation), data_dir, config_dir, values)

    def worker_request(self) -> dict[str, Any]:
        request = {"kind": "serving_read", "operation": self.operation, **self.values}
        if self.data_dir is not None:
            request["data_dir"] = str(self.data_dir)
        if self.config_dir is not None:
            request["config_dir"] = str(self.config_dir)
        return request

    def execute(self) -> dict:
        from klaude_core.managed_serving import (
            LaunchSpec,
            inventory,
            prepare,
            probe_engine,
            read_log,
        )

        request = self.worker_request()
        if request.get("spec", {}).get("ssh_server") and self.operation in {"probe", "prepare"}:
            from klaude_core.ssh_serving import inspect as inspect_remote

            return inspect_remote(request)
        if self.operation == "probe":
            try:
                return probe_engine(request["engine"], request["executable"], owned_group=True)
            except ValueError as exc:
                return {"error": str(exc)}
        if self.operation == "prepare":
            try:
                return {"evidence": prepare(LaunchSpec(**request["spec"]), request["evidence"])}
            except ValueError as exc:
                return {"error": str(exc)}
        assert self.data_dir is not None
        if self.operation == "logs":
            return {"logs": read_log(self.data_dir, request["id"])}
        return {"servers": inventory(self.data_dir)}
