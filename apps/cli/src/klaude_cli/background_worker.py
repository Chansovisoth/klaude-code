"""Private fixed-operation worker. No shell, tools, model turns, or arbitrary imports."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import sys
from dataclasses import asdict
from itertools import islice
from pathlib import Path
from typing import Any


def execute(request: dict[str, Any]) -> object:
    kind = request.get("kind")
    if kind == "mcp_review":
        from klaude_cli.mcp_inventory import read_mcp_review

        return read_mcp_review(Path(request["mcp_file"]), request["name"])
    if kind == "mcp_inventory":
        from klaude_cli.mcp_inventory import read_mcp_inventory

        return read_mcp_inventory(Path(request["mcp_file"]))
    if kind == "memory_inventory":
        from klaude_cli.memory_inventory import read_memory_inventory

        return read_memory_inventory(Path(request["sessions_db"]), Path(request["memory_file"]))
    if kind == "settings_overview":
        import sqlite3

        from klaude_core.mcp_client import MCPRegistry

        memory_enabled = None
        enabled = total = None
        try:
            path = Path(request["sessions_db"])
            if path.is_symlink():
                raise ValueError("Unsafe session database")
            with contextlib.closing(sqlite3.connect(
                path.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2
            )) as db:
                db.execute("PRAGMA query_only=ON")
                memory = db.execute(
                    "SELECT value FROM settings WHERE key='auto_memory_enabled'"
                ).fetchone()
            memory_enabled = not memory or memory[0] == "1"
        except (OSError, ValueError, TypeError, sqlite3.Error):
            pass
        try:
            servers = MCPRegistry(Path(request["mcp_file"])).load()
            total = len(servers)
            enabled = sum(server.enabled for server in servers.values())
        except (OSError, ValueError, TypeError):
            pass
        # Definitions, arguments, env values, tools, names and conversation text
        # stay in this private worker. Never initialize/migrate session storage.
        result = {"memory_enabled": memory_enabled, "mcp_enabled": enabled, "mcp_total": total}
        if request.get("memory_file"):
            from klaude_cli.memory_inventory import read_memory_inventory

            try:
                inventory = read_memory_inventory(Path(request["sessions_db"]),
                                                  Path(request["memory_file"]))
                result["memory_count"] = inventory["count"]
            except (OSError, ValueError, TypeError, sqlite3.Error):
                result["memory_count"] = None
        return result
    if kind == "runtime_calibration":
        from klaude_core.runtime_calibration import calibrate_runtime_options

        return calibrate_runtime_options()
    if kind == "status_metadata":
        import sqlite3

        path = Path(request["sessions_db"])
        if path.is_symlink():
            raise ValueError("Unsafe session database")
        # Do not instantiate Memory: a status read must never initialize/migrate
        # storage, create files, or change journal mode.
        with contextlib.closing(sqlite3.connect(
            path.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2
        )) as db:
            db.execute("PRAGMA query_only=ON")
            named = db.execute(
                "SELECT substr(name, 1, 160) FROM session_names WHERE session_id=?",
                (request["session_id"],),
            ).fetchone()
            memory = db.execute(
                "SELECT value FROM settings WHERE key='auto_memory_enabled'"
            ).fetchone()
        title = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(named[0])) if named else ""
        return {"assigned_title": title, "memory_enabled": not memory or memory[0] == "1"}
    if kind == "model_activation":
        from klaude_core.model_runtime import (
            CodexRuntime,
            GeminiRuntime,
            OpenAIRuntime,
            OpenRouterRuntime,
        )

        backend = request["backend"]
        if backend == "gemini_api":
            GeminiRuntime(request["key"])._sdk()
        else:
            runtime: Any = (
                CodexRuntime() if backend == "openai_codex"
                else {"openai_api": OpenAIRuntime, "openrouter": OpenRouterRuntime}[backend](
                    request["key"]
                )
            )
            client = runtime._client()
            client.close()
        if request.get("env_name"):
            from klaude_core.config import provider_credential_current
            from klaude_core.settings_store import settings_lock

            directory = Path(request["config_dir"])
            with settings_lock(directory / ".env"):
                if not provider_credential_current(
                    directory, request["env_name"], request["key"], request["revision"]
                ):
                    return {"ready": False}
        # Tokens/runtime objects never cross IPC. The live runtime is constructed
        # lazily in the parent; its first actual request owns SDK/network work.
        return {"ready": True}
    if kind == "local_models":
        import httpx

        # Catalog inspection only: never loads or runs a local model.
        with httpx.Client(timeout=3.0) as client:
            response = client.get(str(request["base_url"]).rstrip("/") + "/api/tags")
            response.raise_for_status()
            entries = response.json().get("models", [])
        names = []
        for entry in entries[:1000]:
            name = entry.get("name") if isinstance(entry, dict) else None
            if (
                isinstance(name, str) and 0 < len(name) <= 256
                and not re.search(r"[\x00-\x1f\x7f-\x9f]", name)
            ):
                names.append(name)
        return {"names": sorted(set(names)), "truncated": len(entries) > 1000}
    if kind == "codex_usage":
        from klaude_core.codex_auth import CodexAuthManager

        return asdict(CodexAuthManager().rate_limits())
    if kind == "skills":
        skills = []
        manifests = list(islice(Path(request["skills_dir"]).glob("*/manifest.json"), 1001))
        for manifest in manifests[:1000]:
            if manifest.is_symlink() or manifest.parent.is_symlink():
                continue
            try:
                if manifest.stat().st_size > 256_000:
                    continue
                with manifest.open("rb") as stream:
                    raw = stream.read(256_001)
                if len(raw) > 256_000:
                    continue
                data = json.loads(raw)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("name") != manifest.parent.name:
                continue
            files = data.get("indexed_files", [])
            skills.append(
                {
                    "identity": hashlib.sha256(raw).hexdigest(),
                    "name": re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(data.get("name", "?")))[:200],
                    "library": re.sub(
                        r"[\x00-\x1f\x7f-\x9f]",
                        "",
                        str(data.get("library") or data.get("collection") or "?"),
                    )[:200],
                    "indexed_file_count": len(files) if isinstance(files, list) else 0,
                }
            )
        return {
            "skills": sorted(skills, key=lambda item: str(item["name"])),
            "truncated": len(manifests) > 1000,
        }
    if kind == "codex_status":
        from klaude_core.codex_auth import CodexAuthManager

        return CodexAuthManager().status().authenticated
    if kind == "models":
        from klaude_core.config import provider_credential_current
        from klaude_core.model_runtime import (
            discover_codex_models,
            discover_gemini_models,
            discover_openai_models,
            discover_openrouter_models,
            save_model_cache,
        )
        from klaude_core.settings_store import settings_lock

        backend = request["backend"]
        discover = {
            "openai_api": discover_openai_models,
            "openrouter": discover_openrouter_models,
            "gemini_api": discover_gemini_models,
        }
        models = (
            discover_codex_models()
            if backend == "openai_codex"
            else discover[backend](request["key"])
        )
        if not models:
            return {"updated": False, "reason": "empty"}
        from functools import partial

        publish = partial(
            save_model_cache,
            Path(request["cache_file"]),
            models[:3000],
            backend=backend,
            expected_generation=request["generation"],
        )
        if request.get("env_name"):
            directory = Path(request["config_dir"])
            with settings_lock(directory / ".env"):
                if not provider_credential_current(
                    directory, request["env_name"], request["key"], request["revision"]
                ):
                    return {"updated": False, "reason": "stale"}
                updated = publish()
        else:
            updated = publish()
        return {"updated": updated, "reason": "" if updated else "stale"}
    if kind == "mcp_search":
        from klaude_core.mcp_catalog import MCPCatalogClient

        results, cached = MCPCatalogClient(Path(request["cache_file"])).search(request["query"])
        return {"servers": [asdict(server) for server in results], "cached": cached}
    raise ValueError("Unsupported worker operation")


def main() -> None:
    def cancel(_signal: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, cancel)
    try:
        request = json.loads(sys.stdin.buffer.read(128_001))
        if not isinstance(request, dict):
            raise ValueError
        # Optional SDK imports/logging must never corrupt IPC or print keys.
        with open(os.devnull, "w") as discard, contextlib.redirect_stdout(discard):
            result = execute(request)
        response = json.dumps({"result": result})
        if len(response.encode()) > 2_000_000:
            raise ValueError
    except Exception:
        response = json.dumps({"error": "Background job unavailable; retry"})
    sys.stdout.write(response)


if __name__ == "__main__":
    main()
