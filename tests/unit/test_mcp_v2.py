"""Migration contracts using Klaude storage and the actual SDK auth/client."""

import asyncio
import os
import sys
from types import SimpleNamespace

import httpx2
import pytest
from klaude_cli.main import _mcp_oauth_callback
from klaude_core.mcp_client import (
    MCPClient,
    MCPClientManager,
    MCPServerConfig,
    MCPTokenStorage,
    _list_tools,
    _oauth_provider,
    _tool_result,
    mcp_auth_file,
    safe_mcp_error,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from mcp.types import CallToolResult, ListToolsResult, Tool


def test_saved_expired_credentials_refresh_before_first_request(tmp_path):
    async def scenario():
        server = MCPServerConfig(
            name="fixture", transport="http", url="https://fixture.invalid/mcp", oauth=True
        )
        path = mcp_auth_file(tmp_path, server.name)
        storage = MCPTokenStorage(path, server_url=server.url)
        await storage.set_client_info(
            OAuthClientInformationFull(client_id="fixture", token_endpoint_auth_method="none")
        )
        await storage.set_tokens(
            OAuthToken(
                access_token="OLD-PRIVATE",
                refresh_token="REFRESH-PRIVATE",
                expires_in=0,
            )
        )
        storage.set_discovery(
            OAuthMetadata(
                issuer="https://fixture.invalid",
                authorization_endpoint="https://fixture.invalid/auth",
                token_endpoint="https://fixture.invalid/oauth/token",
            ),
            None,
            "https://fixture.invalid",
        )
        calls = []

        def handle(request):
            calls.append(request.url.path)
            if request.url.path == "/oauth/token":
                assert b"refresh_token=REFRESH-PRIVATE" in request.content
                return httpx2.Response(
                    200,
                    json={
                        "access_token": "NEW-PRIVATE",
                        "refresh_token": "ROTATED-PRIVATE",
                        "token_type": "Bearer",
                        "expires_in": 60,
                    },
                )
            assert request.headers["Authorization"] == "Bearer NEW-PRIVATE"
            return httpx2.Response(200)

        provider = _oauth_provider(server, tmp_path)
        async with httpx2.AsyncClient(
            auth=provider, transport=httpx2.MockTransport(handle)
        ) as client:
            await client.get(server.url)
        assert calls == ["/oauth/token", "/mcp"]
        # A fresh storage object proves rotation was persisted, not merely cached.
        saved = await MCPTokenStorage(path, server_url=server.url).get_tokens()
        assert saved.refresh_token == "ROTATED-PRIVATE"
        assert path.stat().st_mode & 0o777 == 0o600
        assert "PRIVATE" not in repr(storage.status())

    asyncio.run(scenario())


def test_changed_endpoint_never_receives_old_tokens_or_client_registration(tmp_path):
    async def scenario():
        path = mcp_auth_file(tmp_path, "fixture")
        original = MCPTokenStorage(path, server_url="https://original.invalid/mcp")
        await original.set_tokens(OAuthToken(access_token="PRIVATE", refresh_token="REFRESH"))
        await original.set_client_info(OAuthClientInformationFull(client_id="PRIVATE-CLIENT"))
        changed = MCPTokenStorage(path, server_url="https://changed.invalid/mcp")
        assert await changed.get_tokens() is None
        assert await changed.get_client_info() is None
        assert (await original.get_tokens()).access_token == "PRIVATE"

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["fifo", "directory", "symlink"])
def test_credential_read_rejects_non_regular_files(tmp_path, kind):
    path = tmp_path / "auth.json"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:
        private = tmp_path / "private"
        private.write_text('{"tokens":{"access_token":"PRIVATE"}}')
        path.symlink_to(private)
    assert not MCPTokenStorage(path).status().access_token_present


def test_callback_keeps_issuer_for_sdk_validation_and_rejects_ambiguous_parameters():
    redirect = "http://127.0.0.1:8765/callback"
    result = _mcp_oauth_callback(redirect + "?code=C&state=S&iss=https://issuer.invalid", redirect)
    assert result.iss == "https://issuer.invalid"
    for duplicate in ("code=X", "state=X", "iss=https://other.invalid"):
        with pytest.raises(ValueError):
            _mcp_oauth_callback(
                redirect + "?code=C&state=S&iss=https://issuer.invalid&" + duplicate, redirect
            )


@pytest.mark.parametrize("repeated", [False, True])
def test_tools_pagination_follows_pages_and_rejects_repeated_cursor(repeated):
    calls = []

    async def list_tools(*, cursor):
        calls.append(cursor)
        index = len(calls)
        return ListToolsResult(
            tools=[Tool(name=f"tool{index}", input_schema={"type": "object"})],
            next_cursor="next" if index == 1 or repeated else None,
        )

    async def scenario():
        client = SimpleNamespace(list_tools=list_tools)
        if repeated:
            with pytest.raises(RuntimeError, match="pagination cursor"):
                await _list_tools(client)
        else:
            assert len((await _list_tools(client)).tools) == 2
        assert calls == [None, "next"]

    asyncio.run(scenario())


@pytest.mark.parametrize("manager", [False, True])
def test_disabled_production_tool_call_never_starts_a_process(manager, monkeypatch):
    server = MCPServerConfig(
        name="fixture", transport="stdio", enabled=False, command=sys.executable
    )
    client = MCPClientManager() if manager else MCPClient()
    with pytest.raises(RuntimeError, match="disabled"):
        client.call(server, "anything", {})
    if manager:
        assert not client._actors
        client.close()


@pytest.mark.parametrize("outcome", ["revoked", "issuer-mismatch", "cancel"])
def test_oauth_failures_do_not_send_expired_tokens_or_continue_authorization(tmp_path, outcome):
    async def scenario():
        server = MCPServerConfig(
            name="fixture", transport="http", url="https://fixture.invalid/mcp", oauth=True
        )
        storage = MCPTokenStorage(mcp_auth_file(tmp_path, server.name), server_url=server.url)
        await storage.set_client_info(
            OAuthClientInformationFull(client_id="fixture", token_endpoint_auth_method="none")
        )
        await storage.set_tokens(
            OAuthToken(access_token="OLD-PRIVATE", refresh_token="REFRESH-PRIVATE", expires_in=0)
        )
        calls = []

        def handle(request):
            calls.append(request.url.path)
            if request.url.path == "/token":
                if outcome == "cancel":
                    raise asyncio.CancelledError
                return httpx2.Response(400, json={"error": "invalid_grant"})
            assert "OLD-PRIVATE" not in request.headers.get("authorization", "")
            if request.url.path == "/mcp":
                return httpx2.Response(401)
            if outcome == "issuer-mismatch" and "oauth-authorization-server" in request.url.path:
                return httpx2.Response(
                    200,
                    json={
                        "issuer": "https://wrong.invalid",
                        "authorization_endpoint": "https://wrong.invalid/auth",
                        "token_endpoint": "https://wrong.invalid/token",
                    },
                )
            return httpx2.Response(404)

        async def redirect(_url):
            raise RuntimeError("interactive sign-in required")

        provider = _oauth_provider(server, tmp_path, redirect_handler=redirect)
        async with httpx2.AsyncClient(
            auth=provider, transport=httpx2.MockTransport(handle)
        ) as client:
            expected = asyncio.CancelledError if outcome == "cancel" else Exception
            with pytest.raises(expected) as failure:
                await client.get(server.url)
            if outcome == "issuer-mismatch":
                assert "issuer" in str(failure.value).lower()
        assert calls.count("/token") == 1

    asyncio.run(scenario())


def test_grouped_transport_error_keeps_useful_message_without_token():
    error = ExceptionGroup("transport", [RuntimeError("access_token=PRIVATE connection failed")])
    assert safe_mcp_error(error) == "access_token=[REDACTED] connection failed"


def test_structured_only_tool_result_is_preserved_and_bounded():
    server = MCPServerConfig(name="fixture", transport="stdio", command="unused")
    result = CallToolResult(content=[], structured_content={"answer": 42})
    assert _tool_result(server, "query", result)["structured_content"] == {"answer": 42}
    result.structured_content = {"oversized": "x" * 50_001}
    payload = _tool_result(server, "query", result)
    assert payload["truncated"] and "structured_content" not in payload


@pytest.mark.parametrize("package", ["web", "knowledge"])
def test_builtin_servers_register_and_run_with_sdk_v2(package, monkeypatch):
    import importlib

    from mcp.client import Client
    from mcp.server.mcpserver import MCPServer

    module = importlib.import_module(f"klaude_{package}.mcp_server")
    captured = []
    monkeypatch.setattr(MCPServer, "run", lambda self, **kwargs: captured.append(self))
    monkeypatch.setattr(module, "load_config", lambda: SimpleNamespace())
    if package == "web":
        monkeypatch.setattr(
            module,
            "Web",
            lambda cfg: SimpleNamespace(
                probe_detailed=lambda url, method: {"status": 200, "method": method}
            ),
        )
    else:
        monkeypatch.delenv("KLAUDE_MCP_ALLOW_WRITES", raising=False)
        monkeypatch.setattr(module, "Knowledge", lambda cfg: None)
    module.main()

    async def scenario():
        async with Client(captured[0]) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            if package == "web":
                assert {"web_search", "fetch_url", "http_probe"} <= tools
                result = await client.call_tool("http_probe", {"url": "https://fixture.invalid"})
                assert '"status": 200' in result.content[0].text
            else:
                assert {"learn_file", "query_knowledge", "list_libraries"} <= tools
                result = await client.call_tool("learn_file", {"path": "no-read.txt"})
                assert "mutations are disabled" in result.content[0].text

    asyncio.run(scenario())


def test_production_http_connection_and_explicit_reconnect():
    import socket

    import uvicorn
    from mcp.server.mcpserver import MCPServer

    async def scenario():
        fixture = MCPServer("fixture", log_level="ERROR")

        @fixture.tool()
        def echo(value: str) -> str:
            return value

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            server = uvicorn.Server(
                uvicorn.Config(
                    fixture.streamable_http_app(),
                    log_level="error",
                    access_log=False,
                )
            )
            running = asyncio.create_task(server.serve(sockets=[sock]))
            try:
                for _ in range(100):
                    if server.started:
                        break
                    await asyncio.sleep(0.01)
                assert server.started
                config = MCPServerConfig(
                    name="fixture",
                    transport="http",
                    url=f"http://127.0.0.1:{sock.getsockname()[1]}/mcp",
                )
                for _ in range(2):
                    client = MCPClient(timeout_seconds=3)
                    assert [tool["name"] for tool in await client.discover_async(config)] == [
                        "echo"
                    ]
                    result = await asyncio.to_thread(client.call, config, "echo", {"value": "ok"})
                    assert result["content"][0]["text"] == "ok"
            finally:
                server.should_exit = True
                await asyncio.wait_for(running, 5)

    asyncio.run(scenario())


def test_server_death_fails_once_then_next_call_reconnects(tmp_path):
    fixture = tmp_path / "server.py"
    fixture.write_text("""import os
from mcp.server.mcpserver import MCPServer
server = MCPServer("fixture", log_level="ERROR")
@server.tool()
def crash() -> str:
    os._exit(0)
@server.tool()
def echo() -> str:
    return "new connection"
server.run()
""")
    server = MCPServerConfig(
        name="fixture", transport="stdio", command=sys.executable, args=[str(fixture)]
    )
    manager = MCPClientManager(timeout_seconds=3)
    try:
        with pytest.raises(RuntimeError, match="Connection closed"):
            manager.call(server, "crash", {})
        assert manager.call(server, "echo", {})["content"][0]["text"] == "new connection"
    finally:
        manager.close()
