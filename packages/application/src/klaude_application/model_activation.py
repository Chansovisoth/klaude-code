"""Private, fixed model SDK activation check shared with terminal clients."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

Backend = Literal["gemini_api", "openai_api", "openrouter", "openai_codex"]
BACKENDS = frozenset({"gemini_api", "openai_api", "openrouter", "openai_codex"})


@dataclass(frozen=True)
class ModelActivation:
    backend: Backend
    key: str = field(repr=False)
    config_dir: str = ""
    env_name: str = ""
    revision: str = ""

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ModelActivation:
        backend = request.get("backend")
        key = request.get("key")
        config_dir = request.get("config_dir", "")
        env_name = request.get("env_name", "")
        revision = request.get("revision", "")
        if (
            request.get("kind") != "model_activation"
            or not isinstance(backend, str) or backend not in BACKENDS
            or not isinstance(key, str) or len(key) > 8192
            or not isinstance(config_dir, str)
            or not isinstance(env_name, str)
            or not isinstance(revision, str)
            or (env_name and (
                not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", env_name)
                or not config_dir or not Path(config_dir).is_absolute()
                or len(revision) > 256
            ))
        ):
            raise ValueError("Invalid model activation request")
        return cls(cast(Backend, backend), key, config_dir, env_name, revision)

    def worker_request(self) -> dict[str, str]:
        return {
            "kind": "model_activation", "backend": self.backend, "key": self.key,
            "config_dir": self.config_dir, "env_name": self.env_name,
            "revision": self.revision,
        }

    def verify(self) -> dict[str, bool]:
        from klaude_core.model_runtime import (
            CodexRuntime,
            GeminiRuntime,
            OpenAIRuntime,
            OpenRouterRuntime,
        )

        if self.backend == "gemini_api":
            GeminiRuntime(self.key)._sdk()
        else:
            runtime: Any = (
                CodexRuntime() if self.backend == "openai_codex"
                else {"openai_api": OpenAIRuntime, "openrouter": OpenRouterRuntime}[
                    self.backend
                ](self.key)
            )
            client = runtime._client()
            client.close()
        if self.env_name:
            from klaude_core.config import provider_credential_current
            from klaude_core.settings_store import settings_lock

            directory = Path(self.config_dir)
            with settings_lock(directory / ".env"):
                if not provider_credential_current(
                    directory, self.env_name, self.key, self.revision
                ):
                    return {"ready": False}
        # The live model runtime is constructed lazily in the parent process.
        return {"ready": True}
