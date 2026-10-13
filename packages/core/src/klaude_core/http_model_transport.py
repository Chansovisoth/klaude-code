"""Shared cancellable HTTP transport, including requests waiting for headers."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from typing import Any

import httpx


class CancellableHTTPTransport:
    def __init__(
        self,
        base_url: str,
        timeout: float = 600.0,
        *,
        headers: dict[str, str] | None = None,
        trust_env: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=headers, trust_env=trust_env
        )
        self._chat_client_factory = lambda: httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=headers,
            trust_env=trust_env,
        )
        self.last_chat_metadata: dict[str, Any] = {}
        self._active_client: httpx.Client | None = None
        self._active_response: httpx.Response | None = None
        self._active_socket: Any = None
        self._active_response_lock = threading.Lock()

    def _cancel_error(self) -> RuntimeError:
        return RuntimeError("Model request cancelled")

    def _track_request(
        self,
        client: httpx.Client | None,
        response: httpx.Response | None = None,
    ) -> None:
        with self._active_response_lock:
            self._active_client = client
            self._active_response = response
            self._active_socket = None

    def _request_trace(self, client: httpx.Client) -> Callable[[str, dict[str, Any]], None]:
        """Track the connection before response headers (including model loading)."""

        def trace(event: str, info: dict[str, Any]) -> None:
            if event in {"http11.response_closed.started", "http2.response_closed.started"}:
                return
            connection = None
            if event in {
                "connection.connect_tcp.complete",
                "connection.connect_unix_socket.complete",
                "connection.start_tls.complete",
            }:
                stream = info.get("return_value")
                if stream is not None:
                    connection = stream.get_extra_info("socket")
            if connection is None and not event.endswith(".started"):
                return
            with self._active_response_lock:
                cancelled = self._active_client is not client
                if not cancelled and connection is not None:
                    self._active_socket = connection
            if cancelled:
                if connection is not None:
                    try:
                        connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                raise self._cancel_error()

        return trace

    def _attach_response(self, client: httpx.Client, response: httpx.Response) -> None:
        with self._active_response_lock:
            if self._active_client is not client:
                raise self._cancel_error()
            self._active_response = response

    def _finish_request(self, client: httpx.Client) -> None:
        with self._active_response_lock:
            if self._active_client is client:
                self._active_client = None
                self._active_response = None
                self._active_socket = None

    def cancel_active(self) -> bool:
        """Close the active response stream so a steering turn can proceed."""
        with self._active_response_lock:
            client = self._active_client
            response = self._active_response
            connection = self._active_socket
            # Detach first so repeated cancellation is idempotent and a close
            # callback cannot race a later request into being cleared.
            self._active_client = None
            self._active_response = None
            self._active_socket = None
        if client is None and response is None:
            return False
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if response is not None:
            # close() alone need not wake a recv blocked in another thread.
            stream = response.extensions.get("network_stream")
            if stream is not None:
                try:
                    connection = stream.get_extra_info("socket")
                    if connection is not None:
                        connection.shutdown(socket.SHUT_RDWR)
                except (AttributeError, OSError):
                    pass
            try:
                response.close()
            except Exception:
                # Closing is only a best-effort wake-up mechanism. The owning
                # worker still observes its cancellation flag at a safe event
                # boundary, and terminal input must remain usable if an HTTP
                # transport raises while being torn down.
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        return True

    def close(self) -> None:
        """Release idle and active HTTP transports owned by this client."""
        self.cancel_active()
        try:
            self._client.close()
        except Exception:
            # Cleanup is best effort during child teardown and process exit.
            pass
