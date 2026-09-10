import json
import queue
from pathlib import Path

import pytest
from klaude_cli import main as cli_main
from klaude_core.codex_auth import (
    CODEX_DEVICE_URL,
    CodexAppServer,
    CodexAuthError,
    CodexAuthManager,
    CodexAuthStatus,
    CodexCredentials,
    CodexUsageStatus,
    _account_id,
)
from klaude_core.model_runtime import ModelInfo
from typer.testing import CliRunner


class FakeClient:
    def __init__(self, responses=None, *, login_error=None):
        self.responses = responses or {}
        self.login_error = login_error
        self.requests = []
        self.broker_version = "codex_app_server/0.153.4"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def request(self, method, params=None):
        self.requests.append((method, params))
        value = self.responses.get(method, {})
        return value() if callable(value) else value

    def wait_for_login(self, _login_id):
        if self.login_error:
            raise self.login_error


def _manager(client):
    return CodexAuthManager(client_factory=lambda: client)


def test_device_login_reports_code_and_waits_for_success():
    client = FakeClient(
        {
            "account/login/start": {
                "type": "chatgptDeviceCode",
                "loginId": "login-1",
                "verificationUrl": CODEX_DEVICE_URL,
                "userCode": "ABCD-EFGH",
            },
            "account/read": {"account": {"type": "chatgpt", "planType": "plus"}},
        }
    )
    shown = []

    status = _manager(client).login(lambda url, code: shown.append((url, code)))

    assert shown == [(CODEX_DEVICE_URL, "ABCD-EFGH")]
    assert status == CodexAuthStatus(True, "chatgpt", "plus")


@pytest.mark.parametrize("message", ["authorization expired", "access denied"])
def test_device_login_surfaces_expired_and_denied(message):
    client = FakeClient(
        {
            "account/login/start": {
                "loginId": "login-1",
                "verificationUrl": CODEX_DEVICE_URL,
                "userCode": "ABCD-EFGH",
            }
        },
        login_error=CodexAuthError(message),
    )

    with pytest.raises(CodexAuthError, match=message):
        _manager(client).login(lambda *_args: None)


def test_pending_notifications_do_not_hide_login_completion():
    client = CodexAppServer(executable="unused")
    client._messages = queue.Queue()
    client._messages.put({"method": "account/updated", "params": {"authMode": "chatgpt"}})
    client._messages.put(
        {
            "method": "account/login/completed",
            "params": {"loginId": "login-1", "success": True, "error": None},
        }
    )

    client.wait_for_login("login-1")

    assert client._deferred[0]["method"] == "account/updated"


def test_ctrl_c_cancels_device_login_before_reraising():
    client = FakeClient(
        {
            "account/login/start": {
                "loginId": "login-1",
                "verificationUrl": CODEX_DEVICE_URL,
                "userCode": "ABCD-EFGH",
            }
        },
        login_error=KeyboardInterrupt(),
    )

    with pytest.raises(KeyboardInterrupt):
        _manager(client).login(lambda *_args: None)

    assert ("account/login/cancel", {"loginId": "login-1"}) in client.requests


def test_logout_uses_official_account_rpc():
    client = FakeClient()

    _manager(client).logout()

    assert client.requests == [("account/logout", None)]


def test_rate_limits_parse_all_windows_and_cache_result():
    client = FakeClient(
        {
            "account/rateLimits/read": {
                "ordinaryUsageAllowed": True,
                "rateLimitsByLimitId": {
                    "codex": {
                        "limitId": "codex",
                        "planType": "plus",
                        "primary": {
                            "usedPercent": 5,
                            "windowDurationMins": 300,
                            "resetsAt": 2_000_000_000,
                        },
                        "secondary": {
                            "usedPercent": 31,
                            "windowDurationMins": 10_080,
                            "resetsAt": 2_000_100_000,
                        },
                    },
                    "reserve": {
                        "limitId": "base_model_inference",
                        "normalModelSlug": "gpt-5.6-luna",
                        "primary": {
                            "usedPercent": 0,
                            "windowDurationMins": 10_080,
                            "resetsAt": 2_000_200_000,
                        },
                    },
                },
            }
        }
    )
    manager = _manager(client)

    first = manager.rate_limits()
    second = manager.rate_limits()

    assert isinstance(first, CodexUsageStatus)
    assert first == second
    assert first.plan_type == "plus"
    assert [bucket.limit_id for bucket in first.buckets] == ["codex", "base_model_inference"]
    assert first.buckets[0].primary.used_percent == 5
    assert first.buckets[0].secondary.window_duration_minutes == 10_080
    assert client.requests == [
        (
            "account/rateLimits/read",
            {"supportsLunaReserve": True, "excludeResetCreditDetails": True},
        )
    ]


def test_status_rejects_api_key_as_codex_account_auth():
    client = FakeClient({"account/read": {"account": {"type": "apiKey"}}})

    assert _manager(client).status() == CodexAuthStatus(False, "apiKey", "")


def test_credentials_request_refresh_without_logging_token():
    payload = {"chatgpt_account_id": "acct-123", "exp": 4_000_000_000}
    encoded = json.dumps(payload).encode()
    import base64

    body = base64.urlsafe_b64encode(encoded).decode().rstrip("=")
    token = f"header.{body}.signature"
    client = FakeClient(
        {"getAuthStatus": {"authMethod": "chatgpt", "authToken": token}}
    )

    credentials = _manager(client).credentials(refresh=True)

    assert credentials == CodexCredentials(token, "acct-123", "codex_app_server/0.153.4")
    assert client.requests == [
        ("getAuthStatus", {"includeToken": True, "refreshToken": True})
    ]


def test_expiring_credentials_are_refreshed_automatically():
    import base64

    def token(exp):
        body = base64.urlsafe_b64encode(
            json.dumps({"chatgpt_account_id": "acct-123", "exp": exp}).encode()
        ).decode().rstrip("=")
        return f"header.{body}.signature"

    expired = token(1)
    fresh = token(4_000_000_000)

    class RefreshClient(FakeClient):
        def request(self, method, params=None):
            self.requests.append((method, params))
            return {
                "authMethod": "chatgpt",
                "authToken": fresh if params["refreshToken"] else expired,
            }

    client = RefreshClient()

    assert _manager(client).credentials().access_token == fresh
    assert [params["refreshToken"] for _method, params in client.requests] == [False, True]


def test_account_id_supports_namespaced_official_claim():
    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct-nested"}}
    import base64

    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    assert _account_id(f"header.{body}.signature") == "acct-nested"


def test_auth_login_cli_uses_device_ux_and_refreshes_catalog(monkeypatch):
    refreshed = []

    class Auth:
        def login(self, display):
            display(CODEX_DEVICE_URL, "ABCD-EFGH")
            return CodexAuthStatus(True, "chatgpt", "plus")

    monkeypatch.setattr(cli_main, "CodexAuthManager", Auth)
    monkeypatch.setattr(cli_main, "_refresh_cloud_model_cache", refreshed.append)
    monkeypatch.setattr(cli_main, "load_config", lambda: object())

    result = CliRunner().invoke(cli_main.app, ["auth", "login", "openai-codex"])

    assert result.exit_code == 0, result.output
    assert CODEX_DEVICE_URL in result.output
    assert "ABCD-EFGH" in result.output
    assert "Waiting for authorization" in result.output
    assert "Signed in" in result.output
    assert len(refreshed) == 1


def test_auth_status_cli_keeps_api_key_auth_separate(monkeypatch):
    class Auth:
        def status(self):
            return CodexAuthStatus(False, "apiKey", "")

    monkeypatch.setattr(cli_main, "CodexAuthManager", Auth)

    result = CliRunner().invoke(cli_main.app, ["auth", "status", "openai-codex"])

    assert result.exit_code == 0, result.output
    assert "not signed in with ChatGPT" in result.output
    assert "API-key" in result.output and "auth remains separate" in result.output


def test_auth_logout_cli_removes_only_codex_catalog(monkeypatch):
    calls = []

    class Auth:
        def logout(self):
            calls.append("logout")

    cfg = type("Config", (), {"data_dir": Path("/tmp/test")})()
    cached = [
        ModelInfo("openai_codex", "codex", "codex"),
        ModelInfo("openai_api", "api", "api"),
    ]
    saved = []
    monkeypatch.setattr(cli_main, "CodexAuthManager", Auth)
    monkeypatch.setattr(cli_main, "load_config", lambda: cfg)
    monkeypatch.setattr(cli_main, "load_model_cache", lambda _path: cached)
    monkeypatch.setattr(cli_main, "save_model_cache", lambda _path, models: saved.extend(models))

    result = CliRunner().invoke(cli_main.app, ["auth", "logout", "openai-codex"])

    assert result.exit_code == 0, result.output
    assert calls == ["logout"]
    assert [item.backend for item in saved] == ["openai_api"]
