import hashlib
import io
import json
import queue
import sqlite3
import subprocess
import threading
import time

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.background_worker import execute
from klaude_core.config import provider_secret_revision, save_provider_secret
from klaude_core.model_runtime import (
    ModelInfo,
    load_model_cache,
    model_cache_generation,
    save_model_cache,
)


def test_real_owned_worker_reads_only_bounded_skill_metadata(tmp_path):
    skills = tmp_path / "skills"
    (skills / "test").mkdir(parents=True)
    (skills / "test" / "manifest.json").write_text(
        json.dumps(
            {
                "name": "test",
                "library": "docs",
                "indexed_files": ["a", "b"],
                "private": "not-for-ipc",
            }
        )
    )
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put((kind, value)))
    start = time.monotonic()
    identity = jobs.submit("skills", {"kind": "skills", "skills_dir": str(skills)})
    assert time.monotonic() - start < 0.25
    try:
        kind, (key, returned, result, error) = events.get(timeout=5)
        assert (kind, key, returned, error) == ("background_result", "skills", identity, "")
        assert result == {
            "skills": [{"name": "test", "library": "docs", "indexed_file_count": 2,
                        "enabled": True,
                        "source_label": "Source unknown", "description": "",
                        "update_kind": "",
                        "identity": hashlib.sha256(
                            (skills / "test" / "manifest.json").read_bytes()
                        ).hexdigest()}],
            "truncated": False,
        }
        assert "not-for-ipc" not in json.dumps(result)
    finally:
        jobs.close(wait=True)
    assert not jobs._active


def test_skill_inventory_reads_persisted_disabled_state_without_importing_packages(tmp_path):
    skills = tmp_path / "skills"
    (skills / "test").mkdir(parents=True)
    (skills / "test" / "manifest.json").write_text(json.dumps({
        "name": "test", "library": "docs", "indexed_files": ["SKILL.md"],
    }))
    knowledge = tmp_path / "knowledge.lance"
    knowledge.mkdir()
    with sqlite3.connect(knowledge / "fts.db") as db:
        db.execute("CREATE TABLE disabled_skills (name TEXT PRIMARY KEY NOT NULL)")
        db.execute("INSERT INTO disabled_skills (name) VALUES ('test')")
    result = execute({"kind": "skills", "skills_dir": str(skills),
                      "knowledge_dir": str(knowledge)})
    assert result["skills"][0]["enabled"] is False


def test_skill_manage_metadata_is_bounded_and_does_not_expose_source_path(tmp_path):
    root = tmp_path / "skills" / "example"
    current = root / "versions" / "v1"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text(
        '---\ndescription: "Helpful \x1b[31mprivate\x1b[0m guidance"\n---\n'
    )
    (root / "manifest.json").write_text(json.dumps({
        "name": "example", "library": "example", "source": str(tmp_path / "secret.zip"),
        "current_dir": str(current), "indexed_files": ["SKILL.md"],
    }))
    result = execute({"kind": "skills", "skills_dir": str(tmp_path / "skills")})
    item = result["skills"][0]
    assert item["source_label"] == "Local ZIP"
    assert "secret" not in json.dumps(item)
    assert "\x1b" not in item["description"]
    assert len(item["description"]) <= 240


def test_skill_update_worker_rechecks_manifest_identity_before_network(tmp_path, monkeypatch):
    from klaude_core import skill_catalog

    root = tmp_path / "skills" / "demo"
    root.mkdir(parents=True)
    revision = "a" * 40
    source = f"https://github.com/org/repo/blob/{revision}/demo/SKILL.md"
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({
        "name": "demo", "library": "demo", "source": source,
        "source_revision": revision,
    }))
    identity = hashlib.sha256(manifest.read_bytes()).hexdigest()
    calls = []
    monkeypatch.setattr(skill_catalog, "check_github_skill_update",
                        lambda *args: calls.append(args) or {"status": "current"})
    request = {"kind": "skill_update_check", "skills_dir": str(tmp_path / "skills"),
               "name": "demo", "identity": identity}
    assert execute(request) == {"name": "demo", "identity": identity,
                                "status": "current"}
    assert calls == [("demo", source, revision)]
    assert execute({**request, "identity": "b" * 64}) == {
        "name": "demo", "status": "changed"
    }
    assert len(calls) == 1


def test_mcp_update_worker_checks_exact_definition_before_registry(tmp_path, monkeypatch):
    from klaude_cli.mcp_inventory import definition_digest, read_mcp_inventory
    from klaude_core import mcp_catalog
    from klaude_core.mcp_client import MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "mcp.json")
    server = MCPServerConfig(
        "docs", "stdio", False, command="npx",
        args=["--yes", "@example/docs@1.2.3"],
        source={"registry": "official", "name": "io.github.example/docs",
                "version": "1.2.3"},
    )
    registry.save({"docs": server})
    assert read_mcp_inventory(registry.path)["servers"][0]["source_label"] == (
        "MCP Registry · io.github.example/docs"
    )
    calls = []

    def search(_self, query, **kwargs):
        calls.append((query, kwargs))
        return ([mcp_catalog.MCPCatalogServer(
            "io.github.example/docs", "Docs", "Example", "1.2.4", "active",
            raw={"packages": [{"registryType": "npm", "identifier": "@example/docs",
                               "version": "1.2.4", "runtimeHint": "npx",
                               "transport": {"type": "stdio"}}]},
        )], False)

    monkeypatch.setattr(mcp_catalog.MCPCatalogClient, "search", search)
    request = {"kind": "mcp_update_check", "mcp_file": str(registry.path),
               "cache_file": str(tmp_path / "cache.json"), "name": "docs",
               "fingerprint": definition_digest(server)}
    result = execute(request)
    assert result["status"] == "available"
    assert result["candidate"]["new_arg"] == "@example/docs@1.2.4"
    assert calls == [("io.github.example/docs", {"limit": 50, "refresh": True})]
    assert execute({**request, "fingerprint": "a" * 64}) == {
        "name": "docs", "fingerprint": "a" * 64, "status": "changed"
    }
    assert len(calls) == 1


def test_real_owned_worker_reads_memory_inventory_without_mutations(tmp_path):
    from klaude_core.memory import Memory

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.remember("Prefer concise answers")
    memory.db.close()
    before = memory.memory_file.read_bytes()
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    identity = jobs.submit("memory-inventory", {
        "kind": "memory_inventory", "sessions_db": str(memory.sessions_db),
        "memory_file": str(memory.memory_file),
    }, timeout=8)
    try:
        kind, (key, returned, result, error) = events.get(timeout=8)
        assert (kind, key, returned, error) == (
            "background_result", "memory-inventory", identity, ""
        )
        assert result == {
            "enabled": True, "count": 1, "facts": ["Prefer concise answers"], "hidden": 0,
            "entries": [{"id": "ab6b90a5511c", "fact": "Prefer concise answers"}],
        }
        assert memory.memory_file.read_bytes() == before
    finally:
        jobs.close(wait=True)


def test_real_owned_worker_reads_mcp_public_metadata_only(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"browser": {
        "command": "never-execute", "enabled": False,
        "args": ["private-argument"], "env": {"TOKEN": "${env:PRIVATE_TOKEN}"},
    }}}))
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    identity = jobs.submit("mcp-inventory", {"kind": "mcp_inventory", "mcp_file": str(path)},
                           timeout=8)
    try:
        kind, (key, returned, result, error) = events.get(timeout=8)
        assert (kind, key, returned, error) == (
            "background_result", "mcp-inventory", identity, ""
        )
        fingerprint = result["servers"][0].pop("fingerprint")
        assert isinstance(fingerprint, str) and len(fingerprint) == 64
        assert result == {"servers": [{
            "name": "browser", "enabled": False, "transport": "stdio",
            "oauth": False, "tool_count": 0,
            "source_label": "Local configuration", "description": "",
            "update_kind": "",
        }], "truncated": False}
        assert "private" not in json.dumps(result).lower()
    finally:
        jobs.close(wait=True)


def test_mcp_manage_description_strips_terminal_controls(tmp_path):
    from klaude_cli.mcp_inventory import read_mcp_inventory

    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"docs": {
        "transport": "http", "url": "https://example.org/mcp", "enabled": False,
        "source": {"registry": "official", "description": "Docs \x1b[31mred\x1b[0m search"},
    }}}))
    item = read_mcp_inventory(path)["servers"][0]
    assert item["source_label"] == "MCP Registry"
    assert item["description"] == "Docs red search"
    assert "https://example.org" not in json.dumps(item)


def test_real_owned_worker_reviews_exact_mcp_definition_without_private_values(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"docs": {
        "command": "never-execute", "args": ["private-argument"], "enabled": False,
    }}}))
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    identity = jobs.submit("mcp-review", {
        "kind": "mcp_review", "mcp_file": str(path), "name": "docs",
    }, timeout=8)
    try:
        kind, (key, returned, result, error) = events.get(timeout=8)
        assert (kind, key, returned, error) == ("background_result", "mcp-review", identity, "")
        assert result["name"] == "docs" and len(result["fingerprint"]) == 64
        assert result["enabled"] is False and result["tool_count"] == 0
        assert "private-argument" not in json.dumps(result)
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("action", ["cancel", "close", "timeout", "supersede"])
def test_owned_jobs_cancel_reap_and_never_publish_obsolete_results(monkeypatch, action):
    import klaude_cli.background_jobs as module

    entered = threading.Event()
    killed = []
    processes = []

    class Process:
        pid = 999999
        returncode = None
        stdin = None
        stdout = None

        def __init__(self, args, **kwargs):
            assert all("private-key" not in str(arg) for arg in args)
            assert "OPENAI_API_KEY" not in kwargs["env"]
            self.stdin, self.stdout = io.BytesIO(), io.BytesIO()
            processes.append(self)

        def communicate(self, payload, *, timeout):
            entered.set()
            time.sleep(0.005)
            raise subprocess.TimeoutExpired("worker", timeout)

        def wait(self, *, timeout):
            self.returncode = -15
            return self.returncode

    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")
    monkeypatch.setattr(module.subprocess, "Popen", Process)
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put(value))
    old = jobs.submit(
        "models:test", {"key": "private-key"}, timeout=0.03 if action == "timeout" else 5
    )
    assert entered.wait(1)
    if action == "cancel":
        jobs.cancel("models:test")
    elif action == "close":
        jobs.close()
    elif action == "supersede":
        newer = jobs.submit("models:test", {"key": "new-private-key"}, timeout=0.03)
        assert newer != old
    try:
        if action in {"timeout", "supersede"}:
            key, identity, result, error = events.get(timeout=1)
            assert "timed out" in error
            assert identity == (newer if action == "supersede" else old)
            assert result is None
        jobs.close(wait=True)
        assert not jobs._active
        assert killed
        assert all(proc.stdin.closed and proc.stdout.closed for proc in processes)
        assert events.empty()
    finally:
        jobs.close(wait=True)


def test_model_cache_scoped_updates_merge_and_reject_invalidated_refresh(tmp_path):
    path = tmp_path / "cache.json"
    old = model_cache_generation(path, "openrouter")
    assert save_model_cache(
        path, [ModelInfo("openai_api", "gpt-test", "GPT")], backend="openai_api"
    )
    assert save_model_cache(
        path, [ModelInfo("openrouter", "openrouter/free", "Free")], backend="openrouter"
    )
    assert {model.backend for model in load_model_cache(path)} == {"openai_api", "openrouter"}
    assert save_model_cache(path, [], backend="openrouter", invalidate=True)
    assert not save_model_cache(
        path,
        [ModelInfo("openrouter", "openrouter/free", "Free")],
        backend="openrouter",
        expected_generation=old,
    )
    assert [model.backend for model in load_model_cache(path)] == ["openai_api"]
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("change", ["remove", "replace", "same_key_again"])
def test_worker_never_publishes_catalog_after_credential_revision_changed(
    tmp_path, monkeypatch, change
):
    import klaude_core.model_runtime as runtime

    directory = tmp_path / "config"
    path = tmp_path / "cache.json"
    save_provider_secret(directory, "OPENROUTER_API_KEY", "old-private-key")
    revision = provider_secret_revision(directory, "OPENROUTER_API_KEY")

    def discover(key):
        assert key == "old-private-key"
        save_provider_secret(
            directory, "OPENROUTER_API_KEY", "" if change == "remove" else "new-private-key"
        )
        if change == "same_key_again":
            save_provider_secret(directory, "OPENROUTER_API_KEY", "old-private-key")
        return [ModelInfo("openrouter", "openrouter/free", "Free")]

    monkeypatch.setattr(runtime, "discover_openrouter_models", discover)
    result = execute(
        {
            "kind": "models",
            "backend": "openrouter",
            "key": "old-private-key",
            "config_dir": str(directory),
            "env_name": "OPENROUTER_API_KEY",
            "revision": revision,
            "generation": "",
            "cache_file": str(path),
        }
    )
    assert result == {"updated": False, "reason": "stale"}
    assert not load_model_cache(path)
    assert "private-key" not in (directory / ".env.revisions.json").read_text()


def test_worker_empty_discovery_preserves_existing_provider_catalog(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    model = ModelInfo("openrouter", "openrouter/free", "Free")
    save_model_cache(path, [model], backend="openrouter")
    monkeypatch.setattr("klaude_core.model_runtime.discover_openrouter_models", lambda key: [])
    assert execute({"kind": "models", "backend": "openrouter", "key": "test"}) == {
        "updated": False,
        "reason": "empty",
    }
    assert load_model_cache(path) == [model]


def test_registry_cache_keeps_another_clients_query(tmp_path):
    from klaude_core.mcp_catalog import MCPCatalogClient

    path = tmp_path / "registry.json"
    first, second = MCPCatalogClient(path), MCPCatalogClient(path)
    one, two = first._load_cache(), second._load_cache()
    one["entries"]["one"] = {"saved_at": time.time(), "payload": {"servers": []}}
    two["entries"]["two"] = {"saved_at": time.time(), "payload": {"servers": []}}
    first._save_cache(one, "one")
    second._save_cache(two, "two")
    assert set(first._load_cache()["entries"]) == {"one", "two"}


def test_local_catalog_worker_reads_tags_only_and_sanitizes_inventory(monkeypatch):
    import httpx

    requests = []

    def tags(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"models": [
            {"name": "gemma4:e4b"}, {"name": "gemma4:e4b"},
            {"name": "unsafe\x1b[31m"}, {"name": ""}, {"other": "value"},
        ]})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real(
        transport=httpx.MockTransport(tags), **kwargs
    ))
    assert execute({"kind": "local_models", "base_url": "http://localhost:11434"}) == {
        "names": ["gemma4:e4b"], "truncated": False,
    }
    assert requests == ["/api/tags"]


def test_codex_usage_worker_returns_only_public_account_limits(monkeypatch):
    from klaude_core.codex_auth import (
        CodexAuthManager,
        CodexRateLimitBucket,
        CodexRateLimitWindow,
        CodexUsageStatus,
    )

    monkeypatch.setattr(CodexAuthManager, "rate_limits", lambda self: CodexUsageStatus(
        True, "plus", (CodexRateLimitBucket("codex", primary=CodexRateLimitWindow(30, 300)),)
    ))
    result = execute({"kind": "codex_usage"})
    assert result["buckets"][0]["primary"]["used_percent"] == 30
    assert set(result) == {"ordinary_usage_allowed", "plan_type", "buckets"}


@pytest.mark.parametrize("backend", ["openai_api", "openrouter", "openai_codex", "gemini_api"])
def test_activation_worker_validates_without_returning_credentials(monkeypatch, backend):
    from types import SimpleNamespace

    import klaude_core.model_runtime as runtime

    closed = []
    client = SimpleNamespace(api_key="secret-token", close=lambda: closed.append(True))
    for cls in (runtime.OpenAIRuntime, runtime.OpenRouterRuntime, runtime.CodexRuntime):
        monkeypatch.setattr(cls, "_client", lambda self: client)
    monkeypatch.setattr(runtime.GeminiRuntime, "_sdk", lambda self: (None, None))
    result = execute({"kind": "model_activation", "backend": backend, "key": "private-key"})
    assert result == {"ready": True}
    assert closed == ([] if backend == "gemini_api" else [True])
    assert "secret" not in json.dumps(result)
    assert "private-key" not in json.dumps(result)


def test_activation_worker_rejects_key_removed_during_preparation(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from klaude_core.model_runtime import OpenRouterRuntime

    directory = tmp_path / "config"
    save_provider_secret(directory, "OPENROUTER_API_KEY", "private-key")
    revision = provider_secret_revision(directory, "OPENROUTER_API_KEY")

    def prepare(self):
        save_provider_secret(directory, "OPENROUTER_API_KEY", "")
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(OpenRouterRuntime, "_client", prepare)
    assert execute({
        "kind": "model_activation", "backend": "openrouter", "key": "private-key",
        "env_name": "OPENROUTER_API_KEY", "revision": revision, "config_dir": str(directory),
    }) == {"ready": False}


def test_status_metadata_worker_reads_only_bounded_public_fields(tmp_path):
    from klaude_core.memory import Memory

    db = tmp_path / "sessions.db"
    memory = Memory(tmp_path / "memory.md", db)
    memory.rename_session("session-1", "Saved title")
    memory.set_auto_memory(False)
    memory.log_turn("session-1", "user", "Private conversation not requested by status")
    before = db.read_bytes()
    result = execute({"kind": "status_metadata", "sessions_db": str(db), "session_id": "session-1"})
    assert result == {"assigned_title": "Saved title", "memory_enabled": False}
    assert db.read_bytes() == before
    assert "Private conversation" not in json.dumps(result)


def test_status_metadata_worker_never_creates_a_missing_database(tmp_path):
    import sqlite3

    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        execute({"kind": "status_metadata", "sessions_db": str(path), "session_id": "test"})
    assert not path.exists()
