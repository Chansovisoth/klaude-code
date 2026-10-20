"""Private fixed-operation worker for shared application domains.

Each request is a bounded JSON value on stdin. The worker never accepts an
arbitrary import, command or callable from its caller.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import stat
import sys
from dataclasses import asdict
from itertools import islice
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _skill_source_label(value: object) -> str:
    from klaude_core.skill_catalog import github_location

    source = str(value or "")
    try:
        parsed = urlsplit(source)
    except ValueError:
        return "Source unknown"
    if parsed.scheme in {"http", "https"} and parsed.hostname and not (
        parsed.username or parsed.password
    ):
        if parsed.hostname.casefold() == "github.com":
            location = github_location(source)
            if location is not None:
                return f"GitHub · {location[0]}"[:160]
        return f"Remote · {parsed.hostname}"[:160]
    if source.lower().endswith(".zip"):
        return "Local ZIP"
    if source:
        return "Local source"
    return "Source unknown"


def _skill_update_kind(data: dict[str, Any]) -> str:
    from klaude_core.skill_catalog import github_location

    source = data.get("source")
    revision = data.get("source_revision")
    if not isinstance(source, str) or not isinstance(revision, str):
        return ""
    location = github_location(source)
    return "github" if location and location[1] == revision and (
        location[2].endswith("SKILL.md")
    ) and re.fullmatch(r"[a-f0-9]{40}", revision) else ""


def _skill_description(manifest: Path, data: dict[str, Any]) -> str:
    from klaude_core.skill_catalog import _frontmatter_scalar, clean_text

    description = clean_text(data.get("description"), 240)
    if description:
        return description
    current = data.get("current_dir")
    if not isinstance(current, str):
        return ""
    candidate = Path(current) / "SKILL.md"
    try:
        root = manifest.parent.resolve(strict=True)
        if not candidate.resolve(strict=True).is_relative_to(root) or candidate.is_symlink():
            return ""
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 16_384:
                return ""
            content = stream.read(8_192).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""
    return clean_text(_frontmatter_scalar(content, "description"), 240)


def execute(request: dict[str, Any], progress=None) -> object:
    kind = request.get("kind")
    if kind == "library_management_operation":
        from .library_management import run_management_operation

        return run_management_operation(request)
    if kind == "model_default_candidates":
        for name, value in request.get("environment_keys", {}).items():
            if (
                re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name)
                and name not in {"HOME", "PATH", "PYTHONPATH", "PYTHONHOME"}
                and (not name.startswith("KLAUDE_") or name.startswith("KLAUDE_MODEL_"))
                and isinstance(value, str)
                and len(value) <= 8192
            ):
                os.environ[name] = value
        from .default_model_selection import read_default_candidates

        return read_default_candidates(request)
    if kind in {"fetch_settings_test", "search_settings_test"}:
        from .web_diagnostics import run_fetch_test, run_search_test

        return (
            run_fetch_test(request)
            if kind == "fetch_settings_test"
            else run_search_test(request)
        )
    if kind == "skill_update_all_check":
        batch_items = request.get("items")
        if not isinstance(batch_items, list) or not 1 <= len(batch_items) <= 10 or not all(
            isinstance(item, dict) and isinstance(item.get("name"), str)
            and isinstance(item.get("identity"), str)
            for item in batch_items
        ):
            raise ValueError("Invalid update batch")
        single_kind = "skill_update_check"
        batch_results = []
        for item in batch_items:
            result = execute({**request, **item, "kind": single_kind})
            if not isinstance(result, dict):
                raise ValueError("Invalid update result")
            batch_results.append(result)
        return {"items": batch_results}
    if kind == "skill_update_check":
        from klaude_core.skill_catalog import check_github_skill_update

        name, identity = request["name"], request["identity"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
            raise ValueError("Invalid skill name")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise ValueError("Invalid skill identity")
        manifest = Path(request["skills_dir"]) / name / "manifest.json"
        descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 256_000:
                raise ValueError("Unsafe skill manifest")
            raw = source.read(256_001)
        if len(raw) > 256_000 or hashlib.sha256(raw).hexdigest() != identity:
            return {"status": "changed", "name": name}
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("name") != name or not _skill_update_kind(data):
            return {"status": "unsupported", "name": name}
        result = check_github_skill_update(name, data["source"], data["source_revision"])
        return {"name": name, "identity": identity, **result}
    if kind == "skill_search":
        from klaude_core.skill_catalog import SearchRequest, search

        return search(SearchRequest(**request["request"])).payload()
    if kind == "skill_source":
        from klaude_core.skill_catalog import SkillRecord, resolve_source

        return resolve_source(SkillRecord.from_payload(request["record"]))
    if kind == "mcp_update_all_check":
        items = request.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 10 or not all(
            isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("fingerprint"), str)
            for item in items
        ):
            raise ValueError("Invalid update batch")
        return {"items": [
            execute({**request, **item, "kind": "mcp_update_check"}) for item in items
        ]}
    if kind == "utility":
        from .utility import UtilityCommand

        return UtilityCommand.from_worker(request).execute()
    if kind == "image_generation":
        from .image_generation import ImageGenerationCommand

        return ImageGenerationCommand.from_worker(request).execute()
    if kind == "vision":
        from .vision import VisionCommand

        return VisionCommand.from_worker(request).execute()
    if kind == "ssh_setup":
        from .ssh_operations import SSHSetupCommand

        return SSHSetupCommand.from_worker(request).execute()
    if kind == "ssh_servers":
        from .ssh_operations import SSHDiagnostic

        return SSHDiagnostic.from_worker(request).execute()
    if kind == "model_dependencies":
        from .model_dependencies import ModelDependencyCommand

        return ModelDependencyCommand.from_worker(request).execute(progress)
    if kind == "serving_read":
        from .serving_read import ServingRead

        return ServingRead.from_worker(request).execute()
    if kind == "model_manager":
        from .model_manager import ModelManagerCommand

        return ModelManagerCommand.from_worker(request).execute(progress)
    if kind == "mcp_review":
        from .mcp_inventory import read_mcp_review

        return read_mcp_review(Path(request["mcp_file"]), request["name"])
    if kind == "mcp_update_check":
        from klaude_core.mcp_catalog import MCPCatalogClient
        from klaude_core.mcp_client import MCPRegistry

        from .mcp_inventory import definition_digest
        from .mcp_updates import package_update_candidate, registry_package_source

        name, fingerprint = request["name"], request["fingerprint"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
            raise ValueError("Invalid MCP server name")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError("Invalid MCP definition identity")
        server = MCPRegistry(Path(request["mcp_file"])).load().get(name)
        if server is None or definition_digest(server) != fingerprint:
            return {"name": name, "fingerprint": fingerprint, "status": "changed"}
        if not registry_package_source(server):
            return {"name": name, "fingerprint": fingerprint, "status": "unsupported"}
        source_name = server.source["name"]
        latest, cached = MCPCatalogClient(Path(request["cache_file"])).search(
            source_name, limit=50, refresh=True
        )
        if cached:
            return {"name": name, "fingerprint": fingerprint, "status": "unavailable"}
        exact = next((item for item in latest if item.name == source_name), None)
        if exact is None:
            return {"name": name, "fingerprint": fingerprint, "status": "unavailable"}
        candidate = package_update_candidate(server, exact)
        if candidate is None:
            return {"name": name, "fingerprint": fingerprint, "status": "current" if (
                server.source.get("version") == exact.version
            ) else "unsupported"}
        return {"name": name, "fingerprint": fingerprint, "status": "available",
                "candidate": asdict(candidate)}
    if kind == "mcp_inventory":
        from .mcp_inventory import read_mcp_inventory

        return read_mcp_inventory(Path(request["mcp_file"]))
    if kind == "memory_inventory":
        from .memory_inventory import read_memory_inventory

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
            from .memory_inventory import read_memory_inventory

            try:
                inventory = read_memory_inventory(Path(request["sessions_db"]),
                                                  Path(request["memory_file"]))
                result["memory_count"] = inventory["count"]
            except (OSError, ValueError, TypeError, sqlite3.Error):
                result["memory_count"] = None
        return result
    if kind == "model_capabilities":
        from .model_capabilities import read_capabilities

        return read_capabilities(request)
    if kind in {"model_settings_inventory", "model_settings_test"}:
        from .model_catalog import read_inventory, test_catalog

        return (
            read_inventory(request)
            if kind == "model_settings_inventory"
            else test_catalog(request)
        )
    if kind == "library":
        from .library_inventory import execute_library

        return execute_library(request)
    if kind == "library_knowledge_operation":
        config_dir = request.get("config_dir")
        data_dir = request.get("data_dir")
        if not isinstance(config_dir, str) or not isinstance(data_dir, str):
            raise ValueError("Invalid knowledge operation roots")
        os.environ["KLAUDE_CONFIG_DIR"] = config_dir
        os.environ["KLAUDE_DATA_DIR"] = data_dir
        from .library_knowledge import run_operation

        return run_operation(request)
    if kind in {"research_control", "research_run"}:
        config_dir = request.get("config_dir")
        data_dir = request.get("data_dir")
        if not isinstance(config_dir, str) or not isinstance(data_dir, str):
            raise ValueError("Invalid research operation roots")
        os.environ["KLAUDE_CONFIG_DIR"] = config_dir
        os.environ["KLAUDE_DATA_DIR"] = data_dir
        environment_keys = request.get("environment_keys", {})
        if not isinstance(environment_keys, dict):
            raise ValueError("Invalid research credentials")
        for name, value in environment_keys.items():
            if (
                isinstance(name, str)
                and re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", name)
                and name not in {"HOME", "PATH", "PYTHONPATH", "PYTHONHOME"}
                and not name.startswith("KLAUDE_")
                and isinstance(value, str)
                and len(value) <= 8192
            ):
                os.environ[name] = value
        if kind == "research_control":
            from .research import ResearchService, research_control_from_worker

            return ResearchService().control(research_control_from_worker(request))
        if kind == "research_run":
            from .research import ResearchRun

            request = {**request, **ResearchRun.from_worker(request).worker_fields()}
        from klaude_core.research import execute_research_request

        return execute_research_request(request)
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
        from .model_activation import ModelActivation

        return ModelActivation.from_worker(request).verify()
    if kind == "connection_models":
        from klaude_core.model_discovery import probe_connection

        return probe_connection(request)
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
        import sqlite3

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
                    "enabled": True,
                    "source_label": _skill_source_label(data.get("source")),
                    "description": _skill_description(manifest, data),
                    "update_kind": _skill_update_kind(data),
                }
            )
        database = Path(request.get(
            "knowledge_dir", str(Path(request["skills_dir"]).parent / "knowledge.lance")
        )) / "fts.db"
        if database.is_symlink():
            raise ValueError("Unsafe knowledge database")
        if database.exists() and skills:
            with contextlib.closing(sqlite3.connect(
                database.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2
            )) as db:
                db.execute("PRAGMA query_only=ON")
                table = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='disabled_skills'"
                ).fetchone()
                if table:
                    names = [str(skill["name"]) for skill in skills]
                    disabled: set[str] = set()
                    for start in range(0, len(names), 500):
                        batch = names[start:start + 500]
                        placeholders = ",".join("?" for _ in batch)
                        disabled.update(row[0] for row in db.execute(
                            f"SELECT name FROM disabled_skills WHERE name IN ({placeholders})",
                            batch,
                        ))
                    for skill in skills:
                        skill["enabled"] = skill["name"] not in disabled
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

        client = MCPCatalogClient(Path(request["cache_file"]))
        results, cached = client.search(request["query"], limit=50)
        return {"servers": [asdict(server) for server in results], "cached": cached,
                "cache_age_seconds": client.last_cache_age_seconds}
    if kind == "mcp_repository_stars":
        from klaude_core.mcp_catalog import github_repository_stars

        url = request.get("repository_url")
        if not isinstance(url, str) or len(url) > 500:
            raise ValueError("Invalid repository URL")
        return {"repository_url": url, "stars": github_repository_stars(url)}
    raise ValueError("Unsupported application worker operation")


def main() -> None:
    def cancel(_signal: int, _frame: object) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, cancel)
    try:
        request = json.loads(sys.stdin.buffer.read(128_001))
        if not isinstance(request, dict):
            raise ValueError("Invalid worker request")
        public_output = sys.stdout

        def emit_progress(value: dict) -> None:
            line = json.dumps({"progress": value})
            if len(line.encode()) > 8192:
                raise ValueError("Progress event limit")
            public_output.write(line + "\n")
            public_output.flush()

        with open(os.devnull, "w") as discard, contextlib.redirect_stdout(discard):
            result = execute(request, emit_progress)
        response = json.dumps({"result": result})
        if len(response.encode()) > 2_000_000:
            raise ValueError("Worker response limit")
    except Exception:
        response = json.dumps({"error": "Background job unavailable; retry"})
    sys.stdout.write(response)


if __name__ == "__main__":
    main()
