"""Owned async setup resources, separate from chat turns and persisted output."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypeVar
from urllib.parse import parse_qs, urlparse

CallbackResult = TypeVar("CallbackResult")


@asynccontextmanager
async def oauth_loopback(
    redirect_uri: str,
    validate: Callable[[str, str], CallbackResult],
) -> AsyncIterator[asyncio.Future[CallbackResult]]:
    """Receive one bounded OAuth callback without blocking or logging its URL."""
    target = urlparse(redirect_uri)
    result: asyncio.Future[CallbackResult] = asyncio.get_running_loop().create_future()
    connections: set[asyncio.Task[None]] = set()

    async def receive(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            connections.add(task)
        try:
            line = await asyncio.wait_for(reader.readline(), 5.0)
            if len(line) > 8_192:
                return
            parts = line.decode("ascii").split()
            if len(parts) != 3 or parts[0] != "GET":
                return
            try:
                answer = validate(f"http://127.0.0.1:{target.port}{parts[1]}", redirect_uri)
            except ValueError:
                request = urlparse(parts[1])
                if (
                    request.path == target.path
                    and parse_qs(request.query).get("error")
                    and not result.done()
                ):
                    result.set_exception(
                        RuntimeError("MCP OAuth authorization denied or cancelled")
                    )
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            else:
                if not result.done():
                    result.set_result(answer)
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        except (TimeoutError, OSError, ValueError, UnicodeError):
            pass
        finally:
            writer.close()
            if task is not None:
                connections.discard(task)

    server = await asyncio.start_server(receive, "127.0.0.1", target.port, limit=8_192)
    try:
        yield result
    finally:
        server.close()
        await server.wait_closed()
        pending = list(connections)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if result.done() and not result.cancelled():
            result.exception()  # consume an unawaited denial if discovery failed first
        else:
            result.cancel()
