"""Authentication broker for OpenAI Codex / ChatGPT account access.

Klaude never implements OpenAI's OAuth client or stores a second credential
copy.  The installed official Codex app-server owns login, persistence, and
refresh; this module only consumes its documented JSONL RPC surface.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CODEX_DEVICE_URL = "https://auth.openai.com/codex/device"
CODEX_RESPONSES_BASE_URL = "https://chatgpt.com/backend-api/codex"
_CLIENT_NAME = "klaude_code"
_CLIENT_TITLE = "Klaude"
_CLIENT_VERSION = "0.2.0a4"
_SENSITIVE_TEXT = re.compile(
    r"(?i)(bearer\s+)[^\s]+|\beyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]+){1,2}\b"
)


class CodexAuthError(RuntimeError):
    """A safe, user-displayable Codex authentication failure."""


@dataclass(frozen=True)
class CodexCredentials:
    access_token: str
    account_id: str
    broker_version: str = ""


@dataclass(frozen=True)
class CodexAuthStatus:
    authenticated: bool
    auth_method: str = ""
    plan_type: str = ""


@dataclass(frozen=True)
class CodexRateLimitWindow:
    used_percent: int
    window_duration_minutes: int | None = None
    resets_at: int | None = None


@dataclass(frozen=True)
class CodexRateLimitBucket:
    limit_id: str
    limit_name: str = ""
    model: str = ""
    primary: CodexRateLimitWindow | None = None
    secondary: CodexRateLimitWindow | None = None


@dataclass(frozen=True)
class CodexUsageStatus:
    ordinary_usage_allowed: bool | None
    plan_type: str = ""
    buckets: tuple[CodexRateLimitBucket, ...] = ()


def _safe_error(value: object) -> str:
    text = str(value or "Codex authentication failed.").strip()[:1000]
    return _SENSITIVE_TEXT.sub(lambda match: f"{match.group(1) or ''}[redacted]", text)


def _jwt_claims(token: str) -> dict[str, Any]:
    """Decode trusted broker token claims without treating them as verification."""
    try:
        encoded = token.split(".", 2)[1]
        encoded += "=" * (-len(encoded) % 4)
        value = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (IndexError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _account_id(token: str) -> str:
    claims = _jwt_claims(token)
    direct = claims.get("chatgpt_account_id")
    if isinstance(direct, str) and direct:
        return direct
    namespace = claims.get("https://api.openai.com/auth")
    if isinstance(namespace, dict):
        value = namespace.get("chatgpt_account_id")
        if isinstance(value, str) and value:
            return value
    dotted = claims.get("https://api.openai.com/auth.chatgpt_account_id")
    return dotted if isinstance(dotted, str) else ""


class CodexAppServer:
    """Small synchronous JSONL client for the official Codex app-server."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        timeout: float = 30.0,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ):
        self.executable = executable or os.environ.get("KLAUDE_CODEX_BIN") or shutil.which("codex")
        self.timeout = timeout
        self._process_factory = process_factory
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._deferred: deque[dict[str, Any]] = deque()
        self._request_id = 0
        self.broker_version = ""

    def __enter__(self) -> CodexAppServer:
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        if not self.executable:
            raise CodexAuthError(
                "Official Codex CLI was not found. Install it, then run "
                "`klaude auth login openai-codex`."
            )
        try:
            self._process = self._process_factory(
                [self.executable, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as exc:
            raise CodexAuthError(f"Could not start the official Codex app-server: {exc}") from exc
        threading.Thread(target=self._read_messages, daemon=True).start()
        try:
            initialized = self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": _CLIENT_NAME,
                        "title": _CLIENT_TITLE,
                        "version": _CLIENT_VERSION,
                    },
                    "capabilities": {"experimentalApi": False},
                },
            )
        except BaseException:
            self.close()
            raise
        self.broker_version = str(initialized.get("userAgent", ""))
        self.notify("initialized")

    def _read_messages(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._messages.put(None)
            return
        try:
            for line in process.stdout:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    self._messages.put(value)
        finally:
            self._messages.put(None)

    def _send(self, value: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise CodexAuthError("The official Codex app-server is not running.")
        try:
            process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexAuthError("The official Codex app-server stopped unexpectedly.") from exc

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        self._send({"id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        skipped: list[dict[str, Any]] = []
        try:
            while True:
                message = self._next_message(max(0.01, deadline - time.monotonic()))
                if message.get("id") != request_id:
                    skipped.append(message)
                    continue
                if "error" in message:
                    error = message.get("error")
                    detail = error.get("message") if isinstance(error, dict) else error
                    raise CodexAuthError(_safe_error(detail))
                result = message.get("result", {})
                if not isinstance(result, dict):
                    raise CodexAuthError(f"Invalid response from Codex app-server for {method}.")
                return result
        finally:
            self._deferred.extend(skipped)

    def _next_message(self, timeout: float) -> dict[str, Any]:
        if self._deferred:
            return self._deferred.popleft()
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise CodexAuthError("Timed out waiting for the official Codex app-server.") from exc
        if message is None:
            raise CodexAuthError("The official Codex app-server stopped unexpectedly.")
        # Klaude uses managed Codex auth, so server-to-client token refresh
        # requests are not expected. Fail closed instead of leaving Codex hung.
        if "id" in message and "method" in message:
            self._send(
                {
                    "id": message["id"],
                    "error": {"code": -32601, "message": "unsupported server request"},
                }
            )
            return self._next_message(timeout)
        return message

    def wait_for_login(self, login_id: str) -> None:
        skipped: list[dict[str, Any]] = []
        try:
            while True:
                message = self._next_message(900.0)
                if message.get("method") != "account/login/completed":
                    skipped.append(message)
                    continue
                params = message.get("params", {})
                if not isinstance(params, dict) or params.get("loginId") != login_id:
                    skipped.append(message)
                    continue
                if params.get("success") is True:
                    return
                raise CodexAuthError(
                    _safe_error(params.get("error") or "Login was denied or expired.")
                )
        finally:
            self._deferred.extend(skipped)

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


class CodexAuthManager:
    """High-level managed ChatGPT auth operations used by CLI and runtime."""

    def __init__(self, *, client_factory: Callable[[], CodexAppServer] = CodexAppServer):
        self._client_factory = client_factory
        self._rate_limit_cache: CodexUsageStatus | None = None
        self._rate_limit_cache_at = 0.0

    def status(self) -> CodexAuthStatus:
        with self._client_factory() as client:
            account = client.request("account/read", {"refreshToken": False})
            value = account.get("account")
            if not isinstance(value, dict) or value.get("type") != "chatgpt":
                method = str(value.get("type", "")) if isinstance(value, dict) else ""
                return CodexAuthStatus(False, method)
            return CodexAuthStatus(True, "chatgpt", str(value.get("planType") or ""))

    def login(self, display: Callable[[str, str], None]) -> CodexAuthStatus:
        with self._client_factory() as client:
            result = client.request("account/login/start", {"type": "chatgptDeviceCode"})
            login_id = str(result.get("loginId") or "")
            code = str(result.get("userCode") or "")
            url = str(result.get("verificationUrl") or CODEX_DEVICE_URL)
            if not login_id or not code:
                raise CodexAuthError("Codex did not return a device login code.")
            display(url, code)
            try:
                client.wait_for_login(login_id)
            except KeyboardInterrupt:
                try:
                    client.request("account/login/cancel", {"loginId": login_id})
                except CodexAuthError:
                    pass
                raise
            account = client.request("account/read", {"refreshToken": False}).get("account")
            plan = str(account.get("planType") or "") if isinstance(account, dict) else ""
            self._rate_limit_cache = None
            return CodexAuthStatus(True, "chatgpt", plan)

    def logout(self) -> None:
        with self._client_factory() as client:
            client.request("account/logout")
        self._rate_limit_cache = None

    def rate_limits(self, *, max_age_seconds: float = 30.0) -> CodexUsageStatus:
        """Read non-secret account usage windows from the official app-server."""
        if (
            self._rate_limit_cache is not None
            and max_age_seconds > 0
            and time.monotonic() - self._rate_limit_cache_at <= max_age_seconds
        ):
            return self._rate_limit_cache
        client_context = (
            CodexAppServer(timeout=3.0)
            if self._client_factory is CodexAppServer
            else self._client_factory()
        )
        with client_context as client:
            result = client.request(
                "account/rateLimits/read",
                {
                    "supportsLunaReserve": True,
                    "excludeResetCreditDetails": True,
                },
            )
        raw_buckets = result.get("rateLimitsByLimitId")
        values = tuple(raw_buckets.values()) if isinstance(raw_buckets, dict) else ()
        if not values and isinstance(result.get("rateLimits"), dict):
            values = (result["rateLimits"],)
        buckets: list[CodexRateLimitBucket] = []
        for raw in values:
            if not isinstance(raw, dict):
                continue

            def window(name: str, source: dict[str, Any] = raw) -> CodexRateLimitWindow | None:
                value = source.get(name)
                if not isinstance(value, dict) or not isinstance(value.get("usedPercent"), int):
                    return None
                duration = value.get("windowDurationMins")
                reset = value.get("resetsAt")
                return CodexRateLimitWindow(
                    used_percent=max(0, min(100, int(value["usedPercent"]))),
                    window_duration_minutes=int(duration) if isinstance(duration, int) else None,
                    resets_at=int(reset) if isinstance(reset, int) else None,
                )

            buckets.append(
                CodexRateLimitBucket(
                    limit_id=str(raw.get("limitId") or ""),
                    limit_name=str(raw.get("limitName") or ""),
                    model=str(raw.get("normalModelSlug") or ""),
                    primary=window("primary"),
                    secondary=window("secondary"),
                )
            )
        ordinary = result.get("ordinaryUsageAllowed")
        plan = next(
            (
                str(value.get("planType") or "")
                for value in values
                if isinstance(value, dict) and value.get("planType")
            ),
            "",
        )
        status = CodexUsageStatus(
            ordinary if isinstance(ordinary, bool) else None,
            plan,
            tuple(buckets),
        )
        self._rate_limit_cache = status
        self._rate_limit_cache_at = time.monotonic()
        return status

    def credentials(self, *, refresh: bool = False) -> CodexCredentials:
        with self._client_factory() as client:
            request_refresh = refresh
            for _attempt in range(2):
                result = client.request(
                    "getAuthStatus",
                    {"includeToken": True, "refreshToken": request_refresh},
                )
                method = str(result.get("authMethod") or "")
                token = result.get("authToken")
                if method != "chatgpt" or not isinstance(token, str) or not token:
                    raise CodexAuthError(
                        "OpenAI Codex is not signed in with ChatGPT. Run "
                        "`klaude auth login openai-codex`."
                    )
                claims = _jwt_claims(token)
                expires = claims.get("exp")
                expiring = (
                    isinstance(expires, (int, float)) and expires <= time.time() + 60
                )
                if expiring:
                    if not request_refresh:
                        request_refresh = True
                        continue
                    raise CodexAuthError("The Codex access token remained expired after refresh.")
                account_id = _account_id(token)
                if not account_id:
                    raise CodexAuthError(
                        "The Codex login is missing a ChatGPT account identifier."
                    )
                return CodexCredentials(token, account_id, client.broker_version)
            raise CodexAuthError("The Codex access token could not be refreshed.")

    def list_models(self) -> list[dict[str, Any]]:
        with self._client_factory() as client:
            account = client.request("account/read", {"refreshToken": False}).get("account")
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                return []
            models: list[dict[str, Any]] = []
            cursor: str | None = None
            while True:
                result = client.request(
                    "model/list", {"cursor": cursor, "limit": 100, "includeHidden": False}
                )
                models.extend(item for item in result.get("data", []) if isinstance(item, dict))
                next_cursor = result.get("nextCursor")
                if not isinstance(next_cursor, str) or not next_cursor:
                    return models
                cursor = next_cursor
