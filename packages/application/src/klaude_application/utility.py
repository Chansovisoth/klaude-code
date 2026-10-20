"""Private bounded Utility requests shared by terminal clients."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from klaude_core.ai_defaults import AIDefaults, read_defaults
from klaude_core.model_management import reference_parts

Task = Literal["recap", "name"]
TASKS = frozenset({"recap", "name"})


def utility_request(
    cfg: Any,
    session_id: str,
    chat_ref: str,
    connections: Any = None,
    defaults: AIDefaults | None = None,
    native_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture the reviewed model scope and only required private credentials."""
    from klaude_core.model_connections import connection_registry, legacy_connections

    if connections is None:
        registry = connection_registry(cfg)
        connections = (
            registry.load().values() if registry.path.exists() else legacy_connections(cfg)
        )
    if defaults is None:
        defaults = read_defaults(cfg)
    references = (defaults.utility or chat_ref, *defaults.fallbacks)
    identities = {reference_parts(ref)[1] for ref in references}
    names = {item.key_env for item in connections if item.id in identities and item.key_env}
    return {
        "kind": "utility",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "roles": dict(cfg.models),
        "ollama_url": cfg.ollama_url,
        "session_id": session_id,
        "chat_ref": chat_ref,
        "defaults": defaults.public(),
        "native_options": {
            name: value
            for name, value in (native_options or {}).items()
            if name in {"num_gpu", "num_thread"} and type(value) is int
        },
        "environment_keys": {
            name: value for name in names if (value := os.environ.get(name)) and len(value) <= 8192
        },
    }


@dataclass(frozen=True)
class UtilityCommand:
    task: Task
    request: dict[str, Any] = field(repr=False)

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> UtilityCommand:
        task = request.get("task")
        roots = (request.get("config_dir"), request.get("data_dir"))
        keys = request.get("environment_keys", {})
        if (
            request.get("kind") != "utility"
            or not isinstance(task, str) or task not in TASKS
            or any(not isinstance(root, str) or not Path(root).is_absolute() for root in roots)
            or not isinstance(request.get("session_id"), str)
            or not isinstance(request.get("chat_ref"), str)
            or not isinstance(request.get("roles"), dict)
            or not isinstance(request.get("ollama_url"), str)
            or not isinstance(keys, dict)
            or any(not isinstance(name, str)
                   or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name)
                   or not isinstance(value, str) or len(value) > 8192
                   for name, value in keys.items())
        ):
            raise ValueError("Invalid Utility request")
        return cls(cast(Task, task), request)

    def execute(self) -> dict[str, Any]:
        from klaude_core.utility import run_utility

        return run_utility(self.request)
