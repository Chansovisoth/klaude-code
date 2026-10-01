import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import klaude_cli.main as cli_main
import pytest
from klaude_cli.main import _configured_mcp_tools, _select_tool_names
from klaude_core.mcp_client import (
    MCPClientManager,
    MCPRegistry,
    MCPServerConfig,
    MCPTokenStorage,
    _oauth_provider,
    _stdio_environment,
    mcp_auth_file,
    namespaced_tool_name,
    safe_mcp_error,
)
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from pydantic import AnyUrl


class FakeConfig:
    def __init__(self, path: Path):
        self.mcp_servers_file = path


def test_registry_round_trip_is_private_and_preserves_secret_references(tmp_path):
    path = tmp_path / "mcp-servers.json"
    registry = MCPRegistry(path)
    server = MCPServerConfig(
        name="context7",
        transport="http",
        url="https://mcp.context7.com/mcp",
        headers={"Authorization": "${env:CONTEXT7_API_KEY}"},
        tools=[
            {
                "name": "query-docs",
                "description": "Fetch current library documentation.",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ],
    )

    registry.save({server.name: server})

    assert path.stat().st_mode & 0o777 == 0o600
    assert registry.load()["context7"] == server
    assert "CONTEXT7_API_KEY" in path.read_text()
    assert os.environ.get("CONTEXT7_API_KEY", "not-a-secret") not in path.read_text()


def test_bearer_header_uses_environment_without_persisting_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_MCP_TOKEN", "secret-value")
    server = MCPServerConfig(
        name="remote",
        transport="http",
        url="https://example.com/mcp",
        headers={"Authorization": "Bearer ${env:PRIVATE_MCP_TOKEN}"},
    )

    server.validate()
    path = tmp_path / "mcp-servers.json"
    MCPRegistry(path).save({server.name: server})

    assert "secret-value" not in path.read_text()


def test_stdio_environment_keeps_safe_runtime_vars_without_leaking_ambient_secrets(
    monkeypatch,
):
    monkeypatch.setenv("PATH", "/safe/bin")
    monkeypatch.setenv("UNRELATED_PRIVATE_TOKEN", "do-not-inherit")
    monkeypatch.setenv("DECLARED_MCP_TOKEN", "explicit-secret")

    environment = _stdio_environment(
        {"MCP_TOKEN": "${env:DECLARED_MCP_TOKEN}", "LOG_LEVEL": "warn"}
    )

    assert environment["PATH"] == "/safe/bin"
    assert environment["MCP_TOKEN"] == "explicit-secret"
    assert environment["LOG_LEVEL"] == "warn"
    assert "UNRELATED_PRIVATE_TOKEN" not in environment


def test_mcp_secret_uses_masked_prompt_and_never_prints_value(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("TEST_MCP_API_KEY", raising=False)
    monkeypatch.setattr(
        cli_main,
        "load_config",
        lambda: SimpleNamespace(config_dir=tmp_path),
    )
    prompt_options = {}

    def fake_prompt(_label, **options):
        prompt_options.update(options)
        return "super-secret-value"

    monkeypatch.setattr(cli_main.typer, "prompt", fake_prompt)

    cli_main.mcp_secret("TEST_MCP_API_KEY", remove=False, yes=False)

    assert prompt_options["hide_input"] is True
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert "super-secret-value" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "server",
    [
        MCPServerConfig(name="remote", transport="http", url="http://example.com/mcp"),
        MCPServerConfig(
            name="remote",
            transport="http",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer literal-secret"},
        ),
        MCPServerConfig(name="local", transport="stdio"),
    ],
)
def test_server_validation_rejects_unsafe_or_incomplete_configuration(server):
    with pytest.raises(ValueError):
        server.validate()


def test_import_accepts_vscode_shape_but_does_not_execute(tmp_path):
    source = tmp_path / "vscode.json"
    source.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "playwright": {
                        "command": "npx",
                        "args": ["-y", "@playwright/mcp@latest"],
                    }
                }
            }
        )
    )

    imported = MCPRegistry(tmp_path / "saved.json").import_file(source)

    assert imported["playwright"].transport == "stdio"
    assert imported["playwright"].tools == []


@pytest.mark.parametrize("unsafe", ["symlink", "fifo", "oversized", "directory"])
def test_import_rejects_unsafe_source_without_blocking(tmp_path, unsafe):
    from klaude_core.mcp_client import MAX_MCP_IMPORT_FILE_BYTES

    source = tmp_path / "source"
    if unsafe == "symlink":
        target = tmp_path / "target"
        target.write_text('{}')
        source.symlink_to(target)
    elif unsafe == "fifo":
        os.mkfifo(source)
    elif unsafe == "directory":
        source.mkdir()
    else:
        with source.open("wb") as stream:
            stream.truncate(MAX_MCP_IMPORT_FILE_BYTES + 1)
    with pytest.raises((ValueError, OSError)):
        MCPRegistry(tmp_path / "saved.json").import_file(source)


def test_import_normalizes_current_opencode_local_and_remote_shapes(tmp_path):
    source = tmp_path / "opencode.json"
    source.write_text(
        json.dumps(
            {
                "mcp": {
                    "playwright": {
                        "type": "local",
                        "command": ["npx", "-y", "@playwright/mcp@latest"],
                        "environment": {"LOG_LEVEL": "warn"},
                    },
                    "context7": {
                        "type": "remote",
                        "url": "https://mcp.context7.com/mcp",
                    },
                }
            }
        )
    )

    imported = MCPRegistry(tmp_path / "saved.json").import_file(source)

    assert imported["playwright"].command == "npx"
    assert imported["playwright"].args == ["-y", "@playwright/mcp@latest"]
    assert imported["playwright"].env == {"LOG_LEVEL": "warn"}
    assert imported["context7"].transport == "http"


def test_import_preserves_opencode_oauth_without_tokens(tmp_path):
    source = tmp_path / "opencode.json"
    source.write_text(
        json.dumps(
            {
                "mcp": {
                    "github": {
                        "type": "remote",
                        "url": "https://example.com/mcp",
                        "oauth": {"scope": "repo"},
                    }
                }
            }
        )
    )

    imported = MCPRegistry(tmp_path / "saved.json").import_file(source)

    assert imported["github"].oauth is True
    assert imported["github"].oauth_scope == "repo"
    assert imported["github"].tools == []


def test_oauth_config_round_trip_never_embeds_tokens(tmp_path):
    path = tmp_path / "mcp-servers.json"
    server = MCPServerConfig(
        name="github",
        transport="http",
        url="https://mcp.example.com/mcp",
        oauth=True,
        oauth_scope="repo read:user",
    )

    MCPRegistry(path).save({server.name: server})

    restored = MCPRegistry(path).load()["github"]
    assert restored.oauth is True
    assert restored.oauth_scope == "repo read:user"
    assert "access_token" not in path.read_text()


def test_oauth_callback_requires_exact_loopback_code_and_state():
    callback = "http://127.0.0.1:8765/callback"

    assert cli_main._mcp_oauth_callback(
        callback + "?code=short-lived-code&state=expected", callback
    ) == AuthorizationCodeResult(code="short-lived-code", state="expected")
    with pytest.raises(ValueError, match="did not match"):
        cli_main._mcp_oauth_callback(
            "http://evil.example/callback?code=x&state=y", callback
        )
    with pytest.raises(ValueError, match="denied"):
        cli_main._mcp_oauth_callback(callback + "?error=access_denied&state=y", callback)


def test_mcp_errors_redact_oauth_and_bearer_credentials():
    rendered = safe_mcp_error(
        RuntimeError(
            "failed https://example/callback?code=secret-code&state=secret-state "
            "access_token=secret-access Authorization: Bearer secret-bearer"
        )
    )

    assert "secret-code" not in rendered
    assert "secret-state" not in rendered
    assert "secret-access" not in rendered
    assert "secret-bearer" not in rendered


def test_oauth_storage_is_private_expiry_aware_and_clearable(tmp_path, monkeypatch):
    import anyio

    path = mcp_auth_file(tmp_path / "auth", "github")
    storage = MCPTokenStorage(path)
    monkeypatch.setattr(time, "time", lambda: 1_000.0)
    anyio.run(
        storage.set_client_info,
        OAuthClientInformationFull(
            client_id="public-client-id",
            redirect_uris=[AnyUrl("http://127.0.0.1:8765/callback")],
        )
    )
    anyio.run(
        storage.set_tokens,
        OAuthToken(
            access_token="secret-access",
            refresh_token="secret-refresh",
            expires_in=120,
            scope="repo",
        )
    )
    monkeypatch.setattr(time, "time", lambda: 1_030.0)

    restored = anyio.run(storage.get_tokens)
    status = storage.status()

    assert restored is not None and restored.expires_in == 90
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert status.access_token_present is True
    assert status.refresh_token_present is True
    assert status.client_registered is True
    assert status.expires_at == 1_120.0
    assert "secret-access" not in repr(status)
    assert storage.clear() is True
    assert not path.exists()


def test_oauth_discovery_metadata_survives_restart_for_refresh(tmp_path):
    storage = MCPTokenStorage(mcp_auth_file(tmp_path / "auth", "github"))
    storage.set_discovery(
        OAuthMetadata(
            issuer="https://auth.example.com",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/oauth/token",
        ),
        ProtectedResourceMetadata(
            resource="https://mcp.example.com/mcp",
            authorization_servers=["https://auth.example.com"],
        ),
        "https://auth.example.com",
    )
    server = MCPServerConfig(
        name="github",
        transport="http",
        url="https://mcp.example.com/mcp",
        oauth=True,
    )

    provider = _oauth_provider(server, tmp_path / "auth")

    assert str(provider.context.oauth_metadata.token_endpoint) == (
        "https://auth.example.com/oauth/token"
    )
    assert provider.context.auth_server_url == "https://auth.example.com"


def test_mcp_oauth_status_and_logout_never_print_tokens(tmp_path, monkeypatch, capsys):
    import anyio

    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    server = MCPServerConfig(
        name="github",
        transport="http",
        url="https://mcp.example.com/mcp",
        oauth=True,
        enabled=True,
    )
    registry.save({server.name: server})
    cfg = SimpleNamespace(mcp_auth_dir=tmp_path / "auth")
    storage = MCPTokenStorage(mcp_auth_file(cfg.mcp_auth_dir, "github"))
    anyio.run(
        storage.set_tokens,
        OAuthToken(access_token="never-print-me", refresh_token="nor-me", expires_in=60),
    )
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)
    monkeypatch.setattr(cli_main, "load_config", lambda: cfg)

    cli_main.mcp_auth_status("github")
    cli_main.mcp_auth_logout("github", yes=True)

    output = capsys.readouterr().out
    assert "never-print-me" not in output
    assert "nor-me" not in output
    assert not mcp_auth_file(cfg.mcp_auth_dir, "github").exists()
    assert registry.load()["github"].enabled is False


def test_mcp_enable_checks_oauth_login_before_trust_prompt(tmp_path, monkeypatch):
    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    server = MCPServerConfig(
        name="github",
        transport="http",
        url="https://mcp.example.com/mcp",
        oauth=True,
        enabled=False,
    )
    registry.save({server.name: server})
    cfg = SimpleNamespace(mcp_auth_dir=tmp_path / "auth")
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)
    monkeypatch.setattr(cli_main, "load_config", lambda: cfg)
    monkeypatch.setattr(
        cli_main.typer,
        "confirm",
        lambda *_args, **_kwargs: pytest.fail("trust prompt must not run before OAuth preflight"),
    )

    with pytest.raises(cli_main.typer.Exit):
        cli_main.mcp_enable("github", yes=False)


def test_manual_mcp_oauth_login_uses_masked_callback_and_enables_server(
    tmp_path, monkeypatch, capsys
):
    import anyio
    import klaude_core.mcp_client as mcp_client

    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    server = MCPServerConfig(
        name="github",
        transport="http",
        url="https://mcp.example.com/mcp",
        enabled=False,
    )
    registry.save({server.name: server})
    cfg = SimpleNamespace(mcp_auth_dir=tmp_path / "auth")
    prompt_options = {}

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def discover(self, selected):
            async def authorize():
                await self.kwargs["oauth_redirect_handler"](
                    "https://auth.example/authorize?state=expected"
                )
                assert await self.kwargs["oauth_callback_handler"]() == AuthorizationCodeResult(
                    code="short-lived-code", state="expected",
                )

            anyio.run(authorize)
            return [
                {
                    "name": "issues",
                    "description": "List issues",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]

    def prompt(_label, **options):
        prompt_options.update(options)
        return "http://127.0.0.1:8765/callback?code=short-lived-code&state=expected"

    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)
    monkeypatch.setattr(cli_main, "load_config", lambda: cfg)
    monkeypatch.setattr(cli_main.typer, "prompt", prompt)
    monkeypatch.setattr(mcp_client, "MCPClient", FakeClient)

    cli_main.mcp_auth_login(
        "github",
        manual=True,
        open_browser=False,
        scope="repo",
        client_metadata_url="",
    )

    configured = registry.load()["github"]
    assert configured.oauth is True
    assert configured.oauth_scope == "repo"
    assert configured.enabled is True
    assert [tool["name"] for tool in configured.tools] == ["issues"]
    assert prompt_options["hide_input"] is True
    assert "short-lived-code" not in capsys.readouterr().out


def test_cached_mcp_tools_are_namespaced_routed_and_permission_gated(tmp_path, monkeypatch):
    path = tmp_path / "mcp-servers.json"
    server = MCPServerConfig(
        name="context7",
        transport="http",
        url="https://mcp.context7.com/mcp",
        tools=[
            {
                "name": "query-docs",
                "description": "Get up-to-date code documentation for a library.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ],
    )
    MCPRegistry(path).save({server.name: server})
    monkeypatch.setattr(
        MCPClientManager,
        "call",
        lambda _self, selected, name, arguments: {
            "server": selected.name,
            "tool": name,
            "content": arguments,
        },
    )

    cfg = FakeConfig(path)
    tools = _configured_mcp_tools(cfg)
    by_name = {tool.name: tool for tool in tools}
    tool_name = namespaced_tool_name("context7", "query-docs")

    assert set(by_name) == {tool_name}
    assert _select_tool_names("use Context7 for current React docs", by_name) == [tool_name]
    assert json.loads(by_name[tool_name].fn(query="hooks"))["content"] == {"query": "hooks"}
    cfg._mcp_client_manager.close()


def test_persistent_manager_preserves_stdio_server_state(tmp_path):
    server_script = tmp_path / "stateful_server.py"
    server_script.write_text(
        """import json
import sys

counter = 0
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if "id" not in message:
        continue
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "stateful-test", "version": "1"},
        }
    elif method == "tools/list":
        result = {
            "tools": [{
                "name": "increment",
                "description": "Increment a process-local counter.",
                "inputSchema": {"type": "object", "properties": {}},
            }]
        }
    elif method == "tools/call":
        counter += 1
        result = {
            "content": [{"type": "text", "text": str(counter)}],
            "isError": False,
        }
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""
    )
    server = MCPServerConfig(
        name="stateful",
        transport="stdio",
        command=sys.executable,
        args=[str(server_script)],
    )
    manager = MCPClientManager(timeout_seconds=10)
    try:
        assert [tool["name"] for tool in manager.discover(server)] == ["increment"]
        first = manager.call(server, "increment", {})
        second = manager.call(server, "increment", {})
    finally:
        manager.close()

    assert first["content"][0]["text"] == "1"
    assert second["content"][0]["text"] == "2"
