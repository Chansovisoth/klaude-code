import asyncio

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
        async with oauth_loopback(
            "http://127.0.0.1:8765/callback", _mcp_oauth_callback
        ) as answer:
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
