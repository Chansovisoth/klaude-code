"""Opt-in, isolated MCP reuse experiment; never imported by Klaude production.

Run each backend in its own uv --no-project environment (see docs/mcp-reuse.md).
Only synthetic local fixture servers are contacted. No user config is loaded.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import resource
import socket
import subprocess
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path


class Adapter:
    """Identical minimal contract; trust and permission remain host decisions."""

    def __init__(self, backend: str, *, url: str = "", enabled: bool = True, mode: str = "auto"):
        self.backend, self.url, self.enabled = backend, url, enabled
        self.mode = mode
        self.client = None

    async def __aenter__(self):
        if not self.enabled:
            raise PermissionError("server disabled")
        start = time.perf_counter()
        args = [str(Path(__file__).resolve()), "--serve", "stdio"]
        # Neither implementation is given model keys or ambient credentials.
        env = {"PATH": os.defpath, "HOME": "/nonexistent", "NO_COLOR": "1"}
        if self.backend == "sdk":
            from mcp import StdioServerParameters
            from mcp.client import Client

            target = self.url or StdioServerParameters(command=sys.executable, args=args, env=env)
            self.client = Client(target, mode=self.mode, read_timeout_seconds=5)
        else:
            from fastmcp import Client
            from fastmcp.client.transports import StdioTransport

            target = self.url or StdioTransport(sys.executable, args, env=env, keep_alive=False)
            self.client = Client(target, mode=self.mode, timeout=5)
        self.construction_seconds = time.perf_counter() - start
        await self.client.__aenter__()
        self.connection_seconds = time.perf_counter() - start - self.construction_seconds
        return self

    async def __aexit__(self, *exc):
        return await self.client.__aexit__(*exc)

    async def tools(self):
        result = await self.client.list_tools()
        return [tool.name for tool in getattr(result, "tools", result)]

    async def call(self, name: str, arguments: dict, *, permitted: bool = True):
        if not permitted:
            raise PermissionError("host policy denied")
        result = await self.client.call_tool(name, arguments)
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            raise RuntimeError("tool failed")
        return "".join(getattr(block, "text", "") for block in result.content)


def serve(transport: str, port: int):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("klaude-reuse-fixture", log_level="ERROR")

    @server.tool()
    def echo(value: str) -> str:
        return value

    @server.tool()
    async def slow() -> str:
        await asyncio.sleep(30)
        return "finished"

    @server.tool()
    def environment_clean() -> bool:
        return "KLAUDE_REUSE_SENTINEL_TOKEN" not in os.environ

    if transport == "stdio":
        server.run()
    else:
        server.run(transport="streamable-http", host="127.0.0.1", port=port)


async def oauth_refresh():
    """Real shared SDK auth flow over synthetic HTTP; no browser/account login.

    Both candidates use this SDK. This does NOT test FastMCP's convenience OAuth
    storage or Klaude's persistent storage adapter, which require separate parity.
    """
    import httpx2
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

    class Storage:
        tokens = OAuthToken(
            access_token="synthetic-old",
            refresh_token="synthetic-refresh",
            token_type="Bearer",
            expires_in=3600,
        )
        client = OAuthClientInformationFull(client_id="fixture", token_endpoint_auth_method="none")

        async def get_tokens(self):
            return self.tokens

        async def set_tokens(self, tokens):
            self.tokens = tokens

        async def get_client_info(self):
            return self.client

        async def set_client_info(self, client_info):
            self.client = client_info

    storage = Storage()
    auth = OAuthClientProvider(
        "https://fixture.invalid/mcp",
        OAuthClientMetadata(redirect_uris=["http://127.0.0.1/callback"]),
        storage,
    )
    seen = []

    def handle(request):
        seen.append(request.url.path)
        if request.url.path == "/token":
            assert b"grant_type=refresh_token" in request.content
            return httpx2.Response(
                200,
                json={
                    "access_token": "synthetic-new",
                    "refresh_token": "synthetic-rotated",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        assert request.headers["Authorization"] == "Bearer synthetic-new"
        return httpx2.Response(200, json={"ok": True})

    # Explicit test-only clock expiry. No private auth context used in production.
    await auth._initialize()
    auth.context.token_expiry_time = time.time() - 1
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle), auth=auth) as client:
        response = await client.get("https://fixture.invalid/mcp")
    assert response.status_code == 200 and seen == ["/token", "/mcp"]
    assert storage.tokens.refresh_token == "synthetic-rotated"


async def compare(backend: str, port: int, mode: str = "auto") -> dict:
    checks = []
    connections = []

    async def record(name, operation):
        start = time.perf_counter()
        try:
            await asyncio.wait_for(operation(), timeout=15)
        except Exception as exc:
            checks.append({"name": name, "passed": False, "error_type": type(exc).__name__})
        else:
            checks.append(
                {"name": name, "passed": True, "seconds": round(time.perf_counter() - start, 4)}
            )

    async def disabled():
        adapter = Adapter(backend, enabled=False, mode=mode)
        try:
            async with adapter:
                raise AssertionError("disabled connected")
        except PermissionError:
            assert adapter.client is None

    async def connection(url=""):
        async with Adapter(backend, url=url, mode=mode) as adapter:
            connections.append(
                {
                    "transport": "http" if url else "stdio",
                    "protocol_version": adapter.client.protocol_version,
                    "construction_seconds": round(adapter.construction_seconds, 4),
                    "connection_seconds": round(adapter.connection_seconds, 4),
                }
            )
            assert "echo" in await adapter.tools()
            assert "fixture-value" in await adapter.call("echo", {"value": "fixture-value"})
            if not url:
                assert "true" in (await adapter.call("environment_clean", {})).lower()
            try:
                await adapter.call("echo", {"value": "denied"}, permitted=False)
            except PermissionError:
                pass
            else:
                raise AssertionError("permission bypass")
            task = asyncio.create_task(adapter.call("slow", {}))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await asyncio.wait_for(task, 2)
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("slow call completed instead of being cancelled")
            assert "after-cancel" in await adapter.call("echo", {"value": "after-cancel"})
            try:
                await adapter.call("missing_tool", {})
            except Exception:
                pass
            else:
                raise AssertionError("unknown tool appeared successful")
            assert "after-error" in await adapter.call("echo", {"value": "after-error"})

    async def multiple():
        async with AsyncExitStack() as stack:
            clients = [
                await stack.enter_async_context(Adapter(backend, mode=mode)) for _ in range(2)
            ]
            results = await asyncio.gather(
                *(
                    client.call("echo", {"value": str(index)})
                    for index, client in enumerate(clients)
                )
            )
            assert all(str(index) in value for index, value in enumerate(results))

    async def http():
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve", "http", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath, "HOME": "/nonexistent"},
        )
        try:
            for _ in range(100):
                if child.poll() is not None:
                    raise RuntimeError("HTTP fixture exited")
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                except OSError:
                    await asyncio.sleep(0.05)
                else:
                    writer.close()
                    await writer.wait_closed()
                    break
            else:
                raise TimeoutError("fixture readiness")
            await connection(f"http://127.0.0.1:{port}/mcp")
            # Explicit reconnect, not an automatic retry of a potentially mutating tool.
            await connection(f"http://127.0.0.1:{port}/mcp")
        finally:
            child.terminate()
            try:
                await asyncio.to_thread(child.wait, timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                await asyncio.to_thread(child.wait)

    await record("disabled-never-connects", disabled)
    await record("stdio-discovery-call-deny-env-cancel-recovery", connection)
    await record("stdio-reconnect", connection)
    await record("independent-multiple-servers", multiple)
    await record("http-discovery-cancel-error-recovery-reconnect", http)
    await record("shared-sdk-oauth-refresh-rotation", oauth_refresh)
    distributions = sorted({dist.metadata["Name"] for dist in importlib.metadata.distributions()})
    return {
        "backend": backend,
        "mode": mode,
        "checks": checks,
        "connections": connections,
        "installed_distributions": distributions,
        "distribution_count": len(distributions),
        "peak_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "mcp_version": importlib.metadata.version("mcp"),
        "fastmcp_version": importlib.metadata.version("fastmcp") if backend == "fastmcp" else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["sdk", "fastmcp"], default="sdk")
    parser.add_argument("--mode", choices=["auto", "legacy"], default="auto")
    parser.add_argument("--serve", choices=["stdio", "http"])
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve, args.port)
        return
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    os.environ["KLAUDE_REUSE_SENTINEL_TOKEN"] = "synthetic-never-inherit"
    start = time.perf_counter()
    report = asyncio.run(compare(args.backend, port, args.mode))
    report["total_seconds"] = round(time.perf_counter() - start, 4)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(check["passed"] for check in report["checks"]) else 1)


if __name__ == "__main__":
    main()
