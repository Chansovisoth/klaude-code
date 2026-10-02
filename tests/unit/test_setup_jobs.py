import asyncio
import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from klaude_cli.main import _mcp_oauth_callback
from klaude_cli.setup_jobs import oauth_loopback


@pytest.mark.parametrize("outcome", ["success", "pending", "denied"])
def test_oauth_loopback_owns_listener_and_connection_cleanup(monkeypatch, outcome):
    async def scenario():
        handler = None

        class Server:
            closed = False

            def close(self):
                self.closed = True

            async def wait_closed(self):
                pass

        class Writer:
            closed = False
            output = b""

            def write(self, value):
                self.output += value

            async def drain(self):
                pass

            def close(self):
                self.closed = True

        server = Server()

        async def start(callback, host, port, *, limit):
            nonlocal handler
            handler = callback
            assert (host, port, limit) == ("127.0.0.1", 8765, 8_192)
            return server

        monkeypatch.setattr(asyncio, "start_server", start)
        reader = asyncio.StreamReader()
        writer = Writer()
        async with oauth_loopback("http://127.0.0.1:8765/callback", _mcp_oauth_callback) as answer:
            connection = asyncio.create_task(handler(reader, writer))
            await asyncio.sleep(0)
            if outcome != "pending":
                if outcome == "denied":
                    reader.feed_data(b"GET /callback?error=access_denied HTTP/1.1\r\n")
                    with pytest.raises(RuntimeError, match="denied"):
                        await asyncio.wait_for(answer, 1)
                else:
                    reader.feed_data(b"GET /callback?code=PRIVATE&state=STATE HTTP/1.1\r\n")
                    result = await asyncio.wait_for(answer, 1)
                    assert (result.code, result.state) == ("PRIVATE", "STATE")
                await connection
        assert server.closed
        assert writer.closed
        assert connection.done()
        if outcome == "pending":
            assert answer.cancelled()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "invalid-state", "cancelled"])
def test_mcp_sdk_oauth_discovery_pkce_and_private_token_restart(tmp_path, outcome):
    """Drive the actual SDK auth flow with deterministic HTTP responses, no account."""
    import httpx2
    from klaude_core.mcp_client import (
        MCPServerConfig,
        _oauth_provider,
        _persist_oauth_discovery,
    )
    from mcp.client.auth.exceptions import OAuthFlowError
    from mcp.shared.auth import AuthorizationCodeResult

    async def scenario():
        authorization = {}
        exchanges = []
        server = MCPServerConfig(
            name="oauth-test", transport="http", url="https://mcp.example.com/mcp", oauth=True
        )

        async def redirect(url):
            authorization.update(parse_qs(urlsplit(url).query))
            assert authorization["code_challenge_method"] == ["S256"]

        async def callback():
            if outcome == "cancelled":
                raise asyncio.CancelledError
            return AuthorizationCodeResult(
                code="synthetic-code",
                state="incorrect" if outcome == "invalid-state" else authorization["state"][0],
            )

        def respond(request):
            path = request.url.path
            if path == "/mcp":
                if request.headers.get("authorization") == "Bearer synthetic-token":
                    return httpx2.Response(200, json={"ok": True})
                return httpx2.Response(
                    401,
                    headers={
                        "WWW-Authenticate": 'Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"'
                    },
                )
            if path == "/.well-known/oauth-protected-resource":
                return httpx2.Response(
                    200,
                    json={
                        "resource": server.url,
                        "authorization_servers": ["https://auth.example.com"],
                        "scopes_supported": ["docs"],
                    },
                )
            if path == "/.well-known/oauth-authorization-server":
                return httpx2.Response(
                    200,
                    json={
                        "issuer": "https://auth.example.com",
                        "authorization_endpoint": "https://auth.example.com/authorize",
                        "token_endpoint": "https://auth.example.com/token",
                        "registration_endpoint": "https://auth.example.com/register",
                        "response_types_supported": ["code"],
                        "code_challenge_methods_supported": ["S256"],
                    },
                )
            if path == "/register":
                metadata = json.loads(request.content)
                return httpx2.Response(201, json={**metadata, "client_id": "synthetic-client"})
            if path == "/token":
                form = parse_qs(request.content.decode())
                exchanges.append(form)
                if form["grant_type"] == ["refresh_token"]:
                    assert form["refresh_token"] == ["synthetic-refresh"]
                else:
                    assert form["grant_type"] == ["authorization_code"]
                    assert form["code"] == ["synthetic-code"]
                    challenge = (
                        base64.urlsafe_b64encode(
                            hashlib.sha256(form["code_verifier"][0].encode()).digest()
                        )
                        .decode()
                        .rstrip("=")
                    )
                    assert challenge == authorization["code_challenge"][0]
                return httpx2.Response(
                    200,
                    json={
                        "access_token": "synthetic-token",
                        "refresh_token": "synthetic-refresh",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
            raise AssertionError(f"Unexpected OAuth endpoint: {path}")

        provider = _oauth_provider(server, tmp_path, redirect, callback)
        async with httpx2.AsyncClient(
            auth=provider, transport=httpx2.MockTransport(respond)
        ) as client:
            if outcome == "invalid-state":
                with pytest.raises(OAuthFlowError, match="State parameter mismatch"):
                    await client.get(server.url)
            elif outcome == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await client.get(server.url)
            else:
                assert (await client.get(server.url)).status_code == 200
        tokens = await provider.context.storage.get_tokens()
        if outcome != "success":
            assert tokens is None
            assert exchanges == []
            return
        assert tokens.access_token == "synthetic-token"
        _persist_oauth_discovery(provider)
        files = list(tmp_path.glob("*.json"))
        assert files and all(path.stat().st_mode & 0o777 == 0o600 for path in files)
        restarted = _oauth_provider(server, tmp_path)
        async with httpx2.AsyncClient(
            auth=restarted, transport=httpx2.MockTransport(respond)
        ) as client:
            assert (await client.get(server.url)).status_code == 200
            assert len(exchanges) == 1  # restart reused private tokens without a new sign-in
            restarted.context.token_expiry_time = 1
            assert (await client.get(server.url)).status_code == 200
        assert len(exchanges) == 2
        assert exchanges[-1]["grant_type"] == ["refresh_token"]

    asyncio.run(scenario())


def test_async_mcp_discovery_propagates_cancellation_and_unwinds(monkeypatch):
    from klaude_core.mcp_client import MCPClient, MCPServerConfig

    async def scenario():
        client = MCPClient()
        entered = asyncio.Event()
        cleaned = asyncio.Event()

        async def run(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        monkeypatch.setattr(client, "_run", run)
        server = MCPServerConfig(name="test", transport="http", url="https://example.com/mcp")
        task = asyncio.create_task(client.discover_async(server))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "denied", "cancelled"])
def test_oauth_loopback_real_socket_roundtrip_and_cancel_cleanup(monkeypatch, outcome):
    """Exercise actual streams and port release rather than fake listener methods."""

    async def scenario():
        original_start = asyncio.start_server
        listeners = []
        connected = asyncio.Event()

        async def start(callback, *args, **kwargs):
            async def receive(reader, writer):
                connected.set()
                await callback(reader, writer)

            listener = await original_start(receive, *args, **kwargs)
            listeners.append(listener)
            return listener

        monkeypatch.setattr(asyncio, "start_server", start)
        ready = asyncio.Event()

        async def operation():
            async with oauth_loopback(
                "http://127.0.0.1:0/callback",
                _mcp_oauth_callback,
            ) as answer:
                ready.set()
                return await answer

        task = asyncio.create_task(operation())
        await asyncio.wait_for(ready.wait(), 2)
        port = listeners[0].sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            await asyncio.wait_for(connected.wait(), 2)
            if outcome == "cancelled":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert await asyncio.wait_for(reader.read(), 2) == b""
            else:
                query = (
                    "error=access_denied&state=STATE"
                    if outcome == "denied"
                    else ("code=PRIVATE&state=STATE")
                )
                writer.write(f"GET /callback?{query} HTTP/1.1\r\n\r\n".encode())
                await writer.drain()
                if outcome == "denied":
                    with pytest.raises(RuntimeError, match="denied"):
                        await asyncio.wait_for(task, 2)
                else:
                    result = await asyncio.wait_for(task, 2)
                    assert (result.code, result.state) == ("PRIVATE", "STATE")
            assert not listeners[0].is_serving()
            with pytest.raises(OSError):
                await asyncio.open_connection("127.0.0.1", port)
        finally:
            writer.close()
            await writer.wait_closed()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
