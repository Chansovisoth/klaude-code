"""Loopback host contract tests with a deterministic shared Agent."""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import io
import json
import os
import select
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import pytest
from klaude_application import HeadlessApplication, compose_agent
from klaude_core import AgentEvent, PermissionGate
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelInfo
from klaude_webhost.host import LocalWebHost
from klaude_webhost.hosting import HostingStatus, ManagedControl, WebHostController
from klaude_webhost.lan import lan_ipv4_addresses, private_lan_ip
from klaude_webhost.transfers import BrowserTransfers


class _Runtime:
    def chat(self, *_args, **_kwargs):
        return {"role": "assistant", "content": "Ready."}

    def close(self):
        pass


def _app(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    agent = compose_agent(
        _Runtime(),
        "fixture",
        [],
        PermissionGate({}, lambda *_args: "n"),
        "Fixture instructions.",
        tool_selector=lambda _message, tools: list(tools),
        model_info=ModelInfo("ollama", "fixture", "fixture"),
    )
    return HeadlessApplication(agent, memory, allow_user_input_tool=False, allow_approvals=False)


def test_lan_reachability_requires_recent_remote_request(tmp_path, monkeypatch):
    controller = WebHostController(tmp_path / "config", tmp_path / "data")
    monkeypatch.setattr("klaude_webhost.hosting.WEBUI_PORT", 50000)
    monkeypatch.setattr(controller, "_probe", lambda *_args, **_kwargs: "reachable")
    base = HostingStatus(
        True,
        True,
        "http://127.0.0.1:50000",
        "",
        True,
        "192.168.1.5",
        "http://192.168.1.5:50000",
        "a" * 64,
        "192.168.1.6",
        time.time() - 3600,
    )
    monkeypatch.setattr(controller, "status", lambda: base)
    assert controller.diagnose().device.startswith("previously reached")
    recent = HostingStatus(
        True,
        True,
        base.origin,
        "",
        True,
        base.lan_ip,
        base.lan_origin,
        base.lan_fingerprint,
        base.lan_remote_peer,
        time.time(),
    )
    monkeypatch.setattr(controller, "status", lambda: recent)
    assert controller.diagnose().device == "confirmed by a recent LAN request"


def test_webhost_local_fonts_keep_security_headers_and_fixed_asset_boundary(tmp_path):
    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        for name in ("Roboto", "JetBrainsMono"):
            conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
            conn.request("GET", f"/fonts/{name}.ttf")
            response = conn.getresponse()
            assert response.status == 200
            assert response.getheader("Content-Type") == "font/ttf"
            assert "font-src 'self'" in response.getheader("Content-Security-Policy")
            assert response.getheader("X-Content-Type-Options") == "nosniff"
            assert response.read().startswith(b"\x00\x01\x00\x00")
            conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", "/fonts/../../host.py")
        assert conn.getresponse().status == 401
        conn.close()
    finally:
        host.stop()
        thread.join(3)


def test_browser_transfer_store_is_private_bounded_and_owner_scoped(tmp_path):
    root = tmp_path / "staging"
    store = BrowserTransfers(root)
    try:
        record = store.upload("owner-a", io.BytesIO(b"private"), 7, "../../note.svg")
        assert record.filename == "note.svg"
        assert root.stat().st_mode & 0o077 == 0
        assert (root / record.id).stat().st_mode & 0o077 == 0
        with pytest.raises(FileNotFoundError):
            store.open_download("owner-b", record.id)
        reviewed, source = store.open_download("owner-a", record.id)
        with source:
            assert reviewed.sha256 == hashlib.sha256(source.read()).hexdigest()
        (root / record.id).write_bytes(b"changed")
        with pytest.raises(ValueError, match="changed"):
            store.open_download("owner-a", record.id)
        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("private outside")
        (root / record.id).unlink()
        (root / record.id).symlink_to(outside_file)
        with pytest.raises(OSError):
            store.open_download("owner-a", record.id)
        assert outside_file.read_text() == "private outside"
        store.revoke("owner-a")
        assert not (root / record.id).exists()
        with pytest.raises(ValueError, match="early"):
            store.upload("owner-a", io.BytesIO(b"short"), 6, "short.txt")
        assert list(root.iterdir()) == []
        for _ in range(8):
            store.upload("owner-a", io.BytesIO(b"x"), 1, "x.txt")
        with pytest.raises(ValueError, match="quota"):
            store.upload("owner-a", io.BytesIO(b"x"), 1, "x.txt")
    finally:
        store.close()
    restarted = BrowserTransfers(root)
    try:
        assert list(root.iterdir()) == []
    finally:
        restarted.close()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError, match="Unsafe"):
        BrowserTransfers(tmp_path / "link")


def test_browser_upload_download_requires_session_and_forces_attachment(tmp_path):
    host = LocalWebHost(_app(tmp_path), staging_dir=tmp_path / "staging")
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, login = _request(
            host,
            "POST",
            "/api/v1/auth/exchange",
            body={"code": code},
            origin=host.origin,
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        payload = b"<svg><script>alert(1)</script></svg>"
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request(
            "POST",
            "/api/v1/uploads",
            body=payload,
            headers={
                "Host": host.authority,
                "Origin": host.origin,
                "Cookie": cookie,
                "X-Klaude-CSRF": login["csrf"],
                "Content-Type": "application/octet-stream",
                "X-Klaude-Filename": "../../unsafe.svg",
            },
        )
        response = conn.getresponse()
        assert response.status == 201
        uploaded = json.loads(response.read())
        conn.close()
        assert uploaded["filename"] == "unsafe.svg"
        assert uploaded["sha256"] == hashlib.sha256(payload).hexdigest()
        path = f"/api/v1/uploads/{uploaded['id']}/download"
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request(
            "POST",
            "/api/v1/uploads",
            body=b"",
            headers={
                "Host": host.authority,
                "Origin": host.origin,
                "Cookie": cookie,
                "X-Klaude-CSRF": login["csrf"],
                "Content-Type": "application/octet-stream",
                "Content-Length": str(32 * 1024 * 1024 + 1),
            },
        )
        assert conn.getresponse().status == 413
        conn.close()
        assert _request(host, "GET", path)[0] == 401
        other = host.new_bootstrap_url().partition("#")[2]
        _, other_headers, _ = _request(
            host,
            "POST",
            "/api/v1/auth/exchange",
            body={"code": other},
            origin=host.origin,
        )
        other_cookie = other_headers["Set-Cookie"].split(";", 1)[0]
        assert _request(host, "GET", path, cookie=other_cookie)[0] == 404
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", path, headers={"Host": host.authority, "Cookie": cookie})
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/octet-stream"
        assert response.getheader("Content-Disposition") == ('attachment; filename="unsafe.svg"')
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        assert response.getheader("Cache-Control") == "no-store"
        assert response.read() == payload
        conn.close()
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/logout",
                body={},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        assert not (tmp_path / "staging" / uploaded["id"]).exists()
    finally:
        host.stop()
        thread.join(3)


def test_host_shutdown_revokes_browser_session_and_bootstrap(tmp_path):
    host = LocalWebHost(_app(tmp_path))
    code = host.bootstrap_url.partition("#")[2]
    session = host.exchange(code)
    assert session is not None
    identity = hashlib.sha256(session[0].encode()).hexdigest()
    assert host.session_active(identity)
    host.begin_shutdown()
    assert not host.session_active(identity)
    assert host.exchange(code) is None
    with pytest.raises(RuntimeError, match="stopping"):
        host.new_bootstrap_url()
    host.http.server_close()
    asyncio.run(host.application.close())


def test_host_stop_drains_accepted_turn_after_revoking_browser(tmp_path):
    app = _app(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def events(_message, scope=None):
        started.set()
        assert release.wait(5)
        yield AgentEvent("text", {"content": "Finished after disconnect."})

    app.agent.run = events
    host = LocalWebHost(app)
    serving = threading.Thread(target=host.serve_forever, daemon=True)
    serving.start()
    controller = WebHostController(tmp_path / "config", tmp_path / "data")
    control = ManagedControl(controller.directory, host, tmp_path)
    code = host.bootstrap_url.partition("#")[2]
    _, headers, login = _request(
        host,
        "POST",
        "/api/v1/auth/exchange",
        body={"code": code},
        origin=host.origin,
    )
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    identity = hashlib.sha256(cookie.partition("=")[2].encode()).hexdigest()
    try:
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "drain-turn", "text": "Finish this"},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 202 and started.wait(3)
        handle = app._active
        assert handle is not None
        stopping = threading.Thread(target=host.stop, daemon=True)
        stopping.start()
        deadline = time.monotonic() + 3
        while not host._stopping and time.monotonic() < deadline:
            time.sleep(0.01)
        assert host._stopping and not host.session_active(identity)
        assert controller.status().stopping
        with pytest.raises(RuntimeError, match="still draining"):
            controller.enable(tmp_path)
        assert stopping.is_alive() and not handle.cancelled.is_set()
        release.set()
        stopping.join(5)
        assert not stopping.is_alive()
        assert handle.finished.is_set() and handle.state == "completed"
    finally:
        release.set()
        if not host._stopping:
            host.stop()
        serving.join(3)
        control.close()


def test_managed_host_toggle_and_one_use_browser_link(tmp_path, monkeypatch):
    controller = WebHostController(tmp_path / "config", tmp_path / "data")
    assert controller.status().enabled is False
    assert controller.ensure_started(tmp_path) is None
    app = _app(tmp_path)
    host = LocalWebHost(app)
    monkeypatch.setattr("klaude_webhost.hosting.WEBUI_PORT", host.http.server_port)
    server = threading.Thread(target=host.serve_forever, daemon=True)
    server.start()
    control = ManagedControl(controller.directory, host, tmp_path)
    try:
        with pytest.raises(BlockingIOError):
            ManagedControl(controller.directory, host, tmp_path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(control.path))
            client.sendall(b'{"version":999,"command":"bootstrap"}\n')
            rejected = json.loads(client.recv(4096))
        assert rejected["error"] == "Unsupported control protocol"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(control.path))
            client.sendall(b'{"version":1,"command":"runtime_snapshot","root":"/"}\n')
            rejected = json.loads(client.recv(4096))
        assert rejected["error"] == "Invalid control command fields"
        first = controller.enable(tmp_path)
        assert first.startswith(host.origin + "/#")
        assert controller.status().enabled and controller.status().running
        assert controller.status().runtime_instance == f"{control.pid}:{control.start_ticks}"
        assert controller.status().session_id == app.session_id
        assert not controller.decide_hosted_approval("unknown", "allow_once")
        assert not controller.cancel_hosted_turn("unknown")
        initial = controller.runtime_snapshot()
        accepted = controller.submit_hosted_turn("terminal-ipc-turn", "Hello from terminal")
        assert accepted["session_id"] == initial["session_id"]
        deadline = time.monotonic() + 3
        while controller.runtime_snapshot()["state"] != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert controller.runtime_snapshot()["messages"][-1]["content"] == "Ready."
        duplicate = controller.submit_hosted_turn("terminal-ipc-turn", "Hello from terminal")
        assert duplicate["turn_id"] == accepted["turn_id"]
        assert duplicate["state"] == "completed"
        epoch = str(controller.runtime_snapshot()["cursor"]).split(":", 1)[0]
        assert any(
            item["kind"] == "turn.completed"
            for item in controller.runtime_events(
                f"{epoch}:0",
            )
        )
        profile = control.profile
        control.profile = "wrong-profile"
        with pytest.raises(RuntimeError, match="owner identity mismatch"):
            controller.status()
        control.profile = profile
        with pytest.raises(RuntimeError, match="another workspace"):
            controller.enable(tmp_path / "different")
        assert controller.desired()
        second = controller.bootstrap_url()
        assert second != first
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/auth/exchange",
            body={"code": first.partition("#")[2]},
            origin=host.origin,
        )
        assert status == 401
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/auth/exchange",
            body={"code": second.partition("#")[2]},
            origin=host.origin,
        )
        assert status == 200
        controller.disable()
        server.join(timeout=3)
        assert not server.is_alive()
        assert controller.desired() is False
    finally:
        control.close()
        host.stop()


def test_legacy_control_permits_only_verified_status_and_shutdown(tmp_path, monkeypatch):
    controller = WebHostController(tmp_path / "config", tmp_path / "data")
    controller.directory.mkdir(parents=True, mode=0o700)
    verified = []
    monkeypatch.setattr(controller, "_verify_legacy_owner", verified.append)
    commands = []
    done = threading.Event()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(controller.socket_path))
    listener.listen(4)
    listener.settimeout(0.1)

    def serve():
        while not done.is_set():
            try:
                client, _ = listener.accept()
            except TimeoutError:
                continue
            with client:
                request = json.loads(client.recv(4096))
                command = request["command"]
                commands.append(command)
                if command == "stop":
                    # Owner verification must happen before a mutation is sent.
                    assert len(verified) >= 3
                    response = {"stopping": True}
                elif command == "status":
                    response = {
                        "running": True,
                        "origin": "http://127.0.0.1:50000",
                        "workspace": str(tmp_path),
                    }
                else:
                    response = {"url": "http://127.0.0.1:50000/#legacy-link"}
                client.sendall(json.dumps(response).encode())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        state = controller.status()
        assert state.running and state.restart_required
        with pytest.raises(RuntimeError, match="needs an update"):
            controller.enable(tmp_path)
        with pytest.raises(RuntimeError, match="needs an update"):
            controller.bootstrap_url()
        controller.disable()
        assert not controller.desired()
        assert commands[-1] == "stop"
    finally:
        done.set()
        thread.join(3)
        listener.close()


def test_legacy_control_rejects_process_without_managed_host_identity(tmp_path):
    controller = WebHostController(tmp_path / "config", tmp_path / "data")
    with pytest.raises(RuntimeError, match="legacy owner identity mismatch"):
        controller._verify_legacy_owner(os.getpid())


def test_account_login_password_change_and_session_revocation(tmp_path):
    from klaude_webhost.accounts import AccountStore

    accounts = AccountStore(tmp_path / "config")
    accounts.initialize()
    password = accounts.initial_password()
    host = LocalWebHost(_app(tmp_path), accounts=accounts)
    serving = threading.Thread(target=host.serve_forever, daemon=True)
    serving.start()
    control = ManagedControl(tmp_path / "data" / "webhost", host, tmp_path)
    controller = WebHostController(tmp_path / "config", tmp_path / "data")
    try:
        assert host.bootstrap_url == host.origin + "/"
        assert controller.bootstrap_url() == host.origin + "/"
        assert controller.status().auth_mode == "password"
        assert controller.initial_admin_password() == password
        assert _request(host, "GET", "/api/v1/auth/method")[2] == {"method": "password"}
        assert _request(host, "GET", "/api/v1/session")[0] == 401
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/exchange",
                body={"code": host._bootstrap},
                origin=host.origin,
            )[0]
            == 401
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/login",
                body={
                    "username": "admin",
                    "password": password,
                },
                origin="http://attacker.test",
            )[0]
            == 403
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/login",
                body={
                    "username": "admin",
                    "password": "wrong password",
                },
                origin=host.origin,
            )[0]
            == 401
        )
        status, headers, login = _request(
            host,
            "POST",
            "/api/v1/auth/login",
            body={
                "username": "admin",
                "password": password,
            },
            origin=host.origin,
        )
        assert status == 200 and login["username"] == "admin"
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
        status, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
        assert status == 200 and password not in json.dumps(snapshot)
        assert "hash" not in json.dumps(snapshot)
        _, other_headers, _ = _request(
            host,
            "POST",
            "/api/v1/auth/login",
            body={
                "username": "admin",
                "password": password,
            },
            origin=host.origin,
        )
        other = other_headers["Set-Cookie"].split(";", 1)[0]
        replacement = "a new password for the browser"
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/password",
                body={
                    "current_password": password,
                    "new_password": replacement,
                },
                cookie=cookie,
                origin=host.origin,
            )[0]
            == 403
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/password",
                body={
                    "current_password": password,
                    "new_password": replacement,
                },
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        assert _request(host, "GET", "/api/v1/session", cookie=cookie)[0] == 401
        assert _request(host, "GET", "/api/v1/session", cookie=other)[0] == 401
        assert accounts.initial_password() is None
        status, headers, login = _request(
            host,
            "POST",
            "/api/v1/auth/login",
            body={
                "username": "admin",
                "password": replacement,
            },
            origin=host.origin,
        )
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/logout",
                body={},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        assert _request(host, "GET", "/api/v1/session", cookie=cookie)[0] == 401
    finally:
        control.close()
        host.stop()
        serving.join(3)


def test_account_login_throttles_and_local_reset_revokes_cookie(tmp_path):
    from klaude_webhost.accounts import AccountStore

    accounts = AccountStore(tmp_path / "config")
    accounts.initialize()
    host = LocalWebHost(_app(tmp_path), accounts=accounts)
    serving = threading.Thread(target=host.serve_forever, daemon=True)
    serving.start()
    try:
        _, headers, _ = _request(
            host,
            "POST",
            "/api/v1/auth/login",
            body={
                "username": "admin",
                "password": accounts.initial_password(),
            },
            origin=host.origin,
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        accounts.reset_password()
        assert _request(host, "GET", "/api/v1/auth", cookie=cookie)[0] == 401
        for _ in range(4):
            assert (
                _request(
                    host,
                    "POST",
                    "/api/v1/auth/login",
                    body={
                        "username": "unknown",
                        "password": "wrong password",
                    },
                    origin=host.origin,
                )[0]
                == 401
            )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/auth/login",
                body={
                    "username": "admin",
                    "password": accounts.initial_password(),
                },
                origin=host.origin,
            )[0]
            == 429
        )
    finally:
        host.stop()
        serving.join(3)


def test_settings_controller_launches_and_stops_detached_host(tmp_path, monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind(("127.0.0.1", 0))
        test_port = reserved.getsockname()[1]
    monkeypatch.setattr("klaude_webhost.hosting.WEBUI_PORT", test_port)
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("KLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("KLAUDE_DATA_DIR", str(data_dir))
    controller = WebHostController(config_dir, data_dir)
    try:
        url = controller.enable(tmp_path)
        assert url == f"http://127.0.0.1:{test_port}/"
        initial_password = controller.initial_admin_password()
        assert initial_password
        assert controller.status().running
        assert controller.diagnose().local == "reachable"
        parts = urlsplit(url)
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=3)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        connection.close()
        assert controller.ensure_started(tmp_path) == url
        candidates = lan_ipv4_addresses()
        if candidates:
            controller.set_lan(True, ip=candidates[0], workspace=tmp_path)
            lan_state = controller.status()
            assert lan_state.lan_origin.startswith(f"http://{candidates[0]}:{test_port}")
            assert not lan_state.lan_fingerprint
            diagnosis = controller.diagnose()
            assert diagnosis.lan == "reachable"
            assert diagnosis.device == "unverified from another device"
            assert not controller.status().lan_remote_peer
            lan_url = controller.bootstrap_url(lan=True)
            lan_parts = urlsplit(lan_url)
            connection = http.client.HTTPConnection(lan_parts.hostname, lan_parts.port, timeout=3)
            connection.request("GET", "/", headers={"Host": "attacker.test"})
            assert connection.getresponse().status == 403
            connection.close()
            connection = http.client.HTTPConnection(lan_parts.hostname, lan_parts.port, timeout=3)
            connection.request(
                "POST",
                "/api/v1/auth/login",
                json.dumps({"username": "admin", "password": controller.initial_admin_password()}),
                headers={
                    "Host": lan_parts.netloc,
                    "Origin": lan_state.lan_origin,
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            assert response.status == 200
            assert "HttpOnly" in response.getheader("Set-Cookie")
            assert "Secure" not in response.getheader("Set-Cookie")
            response.read()
            connection.close()
            controller.set_lan(False, workspace=tmp_path)
            assert not controller.status().lan_origin
            assert controller.status().running
    finally:
        controller.disable()
    deadline = time.monotonic() + 5
    while controller.status().running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not controller.status().running
    assert not controller.status().enabled
    deadline = time.monotonic() + 5
    while controller._request("status") is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert controller._request("status") is None
    if candidates:
        controller.set_lan(True, ip=candidates[0], workspace=tmp_path)
        try:
            controller.enable(tmp_path)
            assert controller.initial_admin_password() == initial_password
            assert controller.status().lan_origin.startswith(
                f"http://{candidates[0]}:{test_port}",
            )
        finally:
            controller.disable()
        deadline = time.monotonic() + 5
        while controller.status().running and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not controller.status().running


def test_lan_address_rejects_nonprivate_ips():
    for invalid in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "::1", "10.0.0.1/8"):
        with pytest.raises(ValueError):
            private_lan_ip(invalid)


def _request(
    host,
    method,
    path,
    *,
    body=None,
    cookie="",
    csrf="",
    origin=None,
    host_header=None,
    content_type="application/json",
    fetch_site=None,
    client_id="",
    expected_session_id="",
):
    conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
    headers = {"Host": host_header or host.authority}
    if origin is not None:
        headers["Origin"] = origin
    if fetch_site is not None:
        headers["Sec-Fetch-Site"] = fetch_site
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Klaude-CSRF"] = csrf
    if client_id:
        headers["X-Klaude-Client"] = client_id
    if expected_session_id:
        headers["X-Klaude-Session"] = expected_session_id
    if body is not None:
        headers["Content-Type"] = content_type
        body = json.dumps(body)
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    payload = response.read()
    result = response.status, dict(response.getheaders()), json.loads(payload) if payload else {}
    conn.close()
    return result


def test_webhost_auth_chat_replay_and_security(tmp_path):
    app = _app(tmp_path)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, _ = _request(host, "GET", "/api/v1/session")
        assert status == 401
        status, _, _ = _request(host, "GET", "/", host_header="attacker.example")
        assert status == 403
        status, _, _ = _request(host, "GET", "/api/v1/session", fetch_site="cross-site")
        assert status == 403
        code = host.bootstrap_url.partition("#")[2]
        status, _, _ = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin="http://evil.test"
        )
        assert status == 403
        status, headers, login = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert "HttpOnly" in headers["Set-Cookie"]
        assert "SameSite=Strict" in headers["Set-Cookie"]
        status, _, _ = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        assert status == 401
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "r", "text": "Hi"},
            cookie=cookie,
            origin=host.origin,
        )
        assert status == 403
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "r", "text": "Hi"},
            cookie=cookie,
            csrf=login["csrf"],
            origin="null",
        )
        assert status == 403
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "r", "text": "Hi"},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
            content_type="text/plain",
        )
        assert status == 415
        status, _, accepted = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "r", "text": "Hi"},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 202
        status, _, repeated = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "r", "text": "Hi"},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 202 and repeated["turn_id"] == accepted["turn_id"]
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "r", "text": "Different"},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 409
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status, headers, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
            if snapshot["state"] == "completed":
                break
            time.sleep(0.02)
        assert status == 200
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert [item["content"] for item in snapshot["messages"]] == ["Hi", "Ready."]
        cursor = snapshot["cursor"].split(":")[0] + ":0"
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", f"/api/v1/events?after={cursor}", headers={"Cookie": cookie})
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type").startswith("text/event-stream")
        assert response.fp.readline().startswith(b"id: ")
        assert b"turn.accepted" in response.fp.readline()
        conn.close()
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/auth/logout",
            body={},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 200
        assert _request(host, "GET", "/api/v1/session", cookie=cookie)[0] == 401
    finally:
        host.stop()
        thread.join(3)
        assert not thread.is_alive()
        assert host._stream_count == 0


def test_webhost_rejects_ambiguous_authority_and_body_framing(tmp_path):
    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.putrequest("GET", "/", skip_host=True)
        conn.putheader("Host", host.authority)
        conn.putheader("Host", "attacker.test")
        conn.endheaders()
        assert conn.getresponse().status == 403
        conn.close()

        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.putrequest("POST", "/api/v1/auth/exchange", skip_host=True)
        conn.putheader("Host", host.authority)
        conn.putheader("Origin", host.origin)
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "2")
        conn.putheader("Content-Length", "2")
        conn.endheaders(b"{}")
        assert conn.getresponse().status == 400
        conn.close()
    finally:
        host.stop()
        thread.join(3)


def test_webhost_factory_exposes_read_only_workspace_and_retrieval_tools(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(tmp_path)
    try:
        assert set(app.agent.tools) == {
            "read_file",
            "list_dir",
            "workspace_info",
            "grep",
            "git_status",
            "git_diff",
            "query_knowledge", "read_skill", "web_search", "fetch_url", "http_probe",
            "current_time",
        }
        assert app.agent.workspace.write_enabled is False
        assert host_main.WEB_CHAT_FORMATTING in app.agent.messages[0]["content"]
        assert app.allow_user_input_tool is True
        assert app.agent.gate.policies["request_user_input"] == "allow"
        assert app.allow_approvals is True
        assert app.turns.workspace(app.session_id)[0] == str(tmp_path.resolve())
    finally:
        asyncio.run(app.close())


def test_webhost_factory_resumes_saved_session_without_model_contact(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    first = host_main.create_application(tmp_path)
    assert host_main.WEB_CHAT_FORMATTING in first.agent.messages[0]["content"]

    def events(_message, scope=None):
        yield AgentEvent("text", {"content": "Saved answer"})

    first.agent.run = events
    identity = first.session_id

    async def finish():
        handle = first.submit("Saved prompt", request_id="saved-request")
        assert (await handle.result()).state == "completed"
        await first.close()

    asyncio.run(finish())
    resumed = host_main.create_application(tmp_path, session_id=identity)
    try:
        assert resumed.public_history()[-1]["content"] == "Saved answer"
        assert resumed.agent.workspace.write_enabled is False
    finally:
        asyncio.run(resumed.close())


def test_webhost_chat_runs_read_tool_through_shared_agent(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    (tmp_path / "note.txt").write_text("code evidence\n")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(tmp_path)

    class _ToolRuntime:
        calls = 0
        saw_result = False

        def chat(self, _model, messages, tools=None, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                assert any(tool["function"]["name"] == "read_file" for tool in tools)
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {"name": "read_file", "arguments": {"path": "note.txt"}},
                        }
                    ],
                }
            self.saw_result = "code evidence" in json.dumps(messages)
            self.messages = messages
            return {"role": "assistant", "content": "Read the note."}

        def close(self):
            pass

    app.agent.runtime.close()
    runtime = _ToolRuntime()
    app.agent.runtime = runtime
    app.agent.ollama = runtime
    app.agent.tool_selector = lambda _message, tools: list(tools)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    controller = WebHostController(tmp_path / "host-config", tmp_path / "host-data")
    control = ManagedControl(controller.directory, host, tmp_path)
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, login = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert (
            _request(
                host,
                "POST",
                "/api/v1/turns",
                body={"request_id": "read-note", "text": "Read note.txt"},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 202
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
            if snapshot["approvals"]:
                break
            time.sleep(0.02)
        assert snapshot["approvals"] and "path=note.txt" in snapshot["approvals"][0]["detail"]
        interaction = snapshot["approvals"][0]["id"]
        decision_path = f"/api/v1/interactions/{interaction}/decision"
        assert (
            _request(
                host,
                "POST",
                decision_path,
                body={"request_id": "approve-read", "decision": "allow_once"},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        assert (
            _request(
                host,
                "POST",
                decision_path,
                body={"request_id": "approve-read", "decision": "allow_once"},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        assert (
            _request(
                host,
                "POST",
                decision_path,
                body={"request_id": "approve-read", "decision": "deny"},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 409
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
            if snapshot["state"] == "completed":
                break
            time.sleep(0.02)
        assert runtime.calls > 0
        assert runtime.saw_result
        assert snapshot["messages"][-1]["content"] == "Read the note."
        epoch = snapshot["cursor"].split(":")[0]
        replay = app.replay(f"{epoch}:0")
        assert any(event["kind"] == "tool.started" for event in replay)
        assert any(event["kind"] == "tool.finished" and event["executed"] for event in replay)
        runtime.calls = 0
        terminal = controller.submit_hosted_turn("terminal-read-note", "Read note.txt")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            terminal_snapshot = controller.runtime_snapshot()
            if terminal_snapshot["approvals"]:
                break
            time.sleep(0.02)
        assert terminal_snapshot["approvals"]
        assert controller.decide_hosted_approval(
            terminal_snapshot["approvals"][0]["id"],
            "allow_once",
        )
        deadline = time.monotonic() + 3
        while controller.runtime_snapshot()["state"] != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert controller.runtime_snapshot()["messages"][-1]["content"] == "Read the note."
        assert not controller.cancel_hosted_turn(terminal["turn_id"])

        runtime.calls = 0
        pending = controller.submit_hosted_turn("terminal-cancel-note", "Read note.txt")
        deadline = time.monotonic() + 3
        while not controller.runtime_snapshot()["approvals"] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert controller.runtime_snapshot()["approvals"]
        assert controller.cancel_hosted_turn(pending["turn_id"])
        deadline = time.monotonic() + 3
        while controller.runtime_snapshot()["state"] != "idle" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert controller.runtime_snapshot()["state"] == "idle"
        deadline = time.monotonic() + 3
        cancelled = controller.submit_hosted_turn("terminal-cancel-note", "Read note.txt")
        while cancelled["state"] != "cancelled" and time.monotonic() < deadline:
            time.sleep(0.02)
            cancelled = controller.submit_hosted_turn("terminal-cancel-note", "Read note.txt")
        assert cancelled["turn_id"] == pending["turn_id"]
        assert cancelled["state"] == "cancelled"
    finally:
        control.close()
        host.stop()
        thread.join(3)


def test_browser_clients_queue_claim_and_steer_without_observer_control(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    class WaitingRuntime:
        calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                release.wait(5)
            return {"role": "assistant", "content": f"answer {self.calls}"}

        def close(self):
            pass

    app = _app(tmp_path)
    runtime = WaitingRuntime()
    app.agent.runtime = runtime
    app.agent.ollama = runtime
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:

        def login():
            code = host.new_bootstrap_url().partition("#")[2]
            status, headers, data = _request(
                host,
                "POST",
                "/api/v1/auth/exchange",
                body={"code": code},
                origin=host.origin,
            )
            assert status == 200
            return headers["Set-Cookie"].split(";", 1)[0], data["csrf"]

        first_cookie, first_csrf = login()
        second_cookie, second_csrf = login()
        status, _, accepted = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "first-browser-turn", "text": "first"},
            cookie=first_cookie,
            csrf=first_csrf,
            origin=host.origin,
        )
        assert status == 202 and entered.wait(2)
        _, _, first = _request(host, "GET", "/api/v1/session", cookie=first_cookie)
        _, _, second = _request(host, "GET", "/api/v1/session", cookie=second_cookie)
        assert first["has_control"] and not second["has_control"]
        cancel_path = f"/api/v1/turns/{accepted['turn_id']}/cancel"
        assert (
            _request(
                host,
                "POST",
                cancel_path,
                body={"request_id": "observer-cancel", "control_epoch": first["control_epoch"]},
                cookie=second_cookie,
                csrf=second_csrf,
                origin=host.origin,
            )[0]
            == 409
        )
        status, _, queued = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={
                "request_id": "observer-queue",
                "text": "queued private text",
                "disposition": "queue",
            },
            cookie=second_cookie,
            csrf=second_csrf,
            origin=host.origin,
        )
        assert status == 202 and queued["state"] == "queued"
        _, _, first = _request(host, "GET", "/api/v1/session", cookie=first_cookie)
        _, _, second = _request(host, "GET", "/api/v1/session", cookie=second_cookie)
        assert first["queue"][0]["text"] == ""
        assert second["queue"][0]["text"] == "queued private text"
        assert (
            _request(
                host,
                "POST",
                "/api/v1/control/claim",
                body={"request_id": "observer-claim", "expected_epoch": second["control_epoch"]},
                cookie=second_cookie,
                csrf=second_csrf,
                origin=host.origin,
            )[0]
            == 200
        )
        assert (
            _request(
                host,
                "POST",
                cancel_path,
                body={"request_id": "stale-cancel", "control_epoch": first["control_epoch"]},
                cookie=first_cookie,
                csrf=first_csrf,
                origin=host.origin,
            )[0]
            == 409
        )
        _, _, second = _request(host, "GET", "/api/v1/session", cookie=second_cookie)
        assert second["has_control"]
        status, _, steered = _request(
            host,
            "POST",
            f"/api/v1/turns/{accepted['turn_id']}/steer",
            body={
                "request_id": "priority-followup",
                "text": "priority",
                "control_epoch": second["control_epoch"],
            },
            cookie=second_cookie,
            csrf=second_csrf,
            origin=host.origin,
        )
        assert status == 202 and steered["state"] == "queued"
        release.set()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            receipt = app.receipt("observer-queue")
            if receipt is not None and receipt.state == "completed":
                break
            time.sleep(0.02)
        assert app.receipt("first-browser-turn").state == "cancelled"
        assert app.receipt("priority-followup").state == "completed"
        assert app.receipt("observer-queue").state == "completed"
        assert runtime.calls == 3
    finally:
        release.set()
        host.stop()
        thread.join(3)


def test_two_tabs_with_same_cookie_have_separate_approval_control(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    (tmp_path / "note.txt").write_text("visible\n")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(tmp_path)

    class ReadRuntime:
        calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {"name": "read_file", "arguments": {"path": "note.txt"}},
                        }
                    ],
                }
            return {"role": "assistant", "content": "Done."}

        def close(self):
            pass

    app.agent.runtime.close()
    app.agent.runtime = ReadRuntime()
    app.agent.ollama = app.agent.runtime
    app.agent.tool_selector = lambda _message, tools: list(tools)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, auth = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        def attach():
            status, _, result = _request(
                host,
                "POST",
                "/api/v1/clients",
                body={},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
            )
            assert status == 201
            return result["client_id"]

        first, second = attach(), attach()
        assert first != second
        assert _request(host, "GET", "/api/v1/session", cookie=cookie)[0] == 403
        status, _, _ = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "same-cookie-turn", "text": "Read note.txt"},
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
            client_id=first,
        )
        assert status == 202
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, _, owner = _request(host, "GET", "/api/v1/session", cookie=cookie, client_id=first)
            if owner["approvals"]:
                break
            time.sleep(0.02)
        assert owner["approvals"]
        _, _, watching = _request(host, "GET", "/api/v1/session", cookie=cookie, client_id=second)
        assert owner["has_control"] and not watching["has_control"]
        assert watching["approvals"] == owner["approvals"]
        assert (
            _request(
                host,
                "POST",
                "/api/v1/workspace/activate-edits",
                body={
                    "request_id": "observer-edit-activation",
                    "expected_revision": watching["workspace_revision"],
                    "acknowledge": True,
                },
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=second,
            )[0]
            == 409
        )
        path = f"/api/v1/interactions/{owner['approvals'][0]['id']}/decision"
        body = {
            "request_id": "same-cookie-decision",
            "decision": "allow_once",
            "control_epoch": owner["control_epoch"],
        }
        assert (
            _request(
                host,
                "POST",
                path,
                body=body,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=second,
            )[0]
            == 410
        )
        assert (
            _request(
                host,
                "POST",
                path,
                body=body,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=first,
            )[0]
            == 200
        )
        deadline = time.monotonic() + 3
        while app.receipt("same-cookie-turn").state != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert app.receipt("same-cookie-turn").state == "completed"
        reconnected = attach()
        _, _, resumed = _request(
            host, "GET", "/api/v1/session", cookie=cookie, client_id=reconnected
        )
        assert any(item["role"] == "assistant" for item in resumed["messages"])
        assert not resumed["has_control"]
        assert (
            _request(
                host,
                "POST",
                "/api/v1/control/claim",
                body={
                    "request_id": "reconnected-claim",
                    "expected_epoch": resumed["control_epoch"],
                },
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=reconnected,
            )[0]
            == 200
        )
        _, _, resumed = _request(
            host, "GET", "/api/v1/session", cookie=cookie, client_id=reconnected
        )
        assert resumed["has_control"]
        plan = {
            "request_id": "reconnected-plan",
            "enabled": True,
            "expected_revision": resumed["settings_revision"],
            "control_epoch": resumed["control_epoch"],
        }
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/plan-mode",
                body=plan,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=first,
            )[0]
            == 409
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/plan-mode",
                body=plan,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=reconnected,
            )[0]
            == 200
        )
    finally:
        host.stop()
        thread.join(3)


def test_browser_plan_mode_uses_idle_revision_and_client_control(tmp_path):
    app = _app(tmp_path)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, auth = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        first = _request(
            host,
            "POST",
            "/api/v1/clients",
            body={},
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2]["client_id"]
        second = _request(
            host,
            "POST",
            "/api/v1/clients",
            body={},
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2]["client_id"]
        _, _, initial = _request(host, "GET", "/api/v1/session", cookie=cookie, client_id=first)
        change = {
            "request_id": "plan-enable",
            "enabled": True,
            "expected_revision": initial["settings_revision"],
            "control_epoch": initial["control_epoch"],
        }
        status, _, saved = _request(
            host,
            "POST",
            "/api/v1/session/plan-mode",
            body=change,
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
            client_id=first,
        )
        assert status == 200 and saved["enabled"] is True
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/plan-mode",
                body=change,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=first,
            )[2]
            == saved
        )
        assert (
            _request(host, "GET", "/api/v1/session", cookie=cookie, client_id=first)[2]["plan_mode"]
            is True
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/plan-mode",
                body={**change, "request_id": "stale-plan", "enabled": False},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=first,
            )[0]
            == 409
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/turns",
                body={"request_id": "plan-owner-turn", "text": "Hello"},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=first,
            )[0]
            == 202
        )
        deadline = time.monotonic() + 3
        while app.receipt("plan-owner-turn").state != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        _, _, current = _request(host, "GET", "/api/v1/session", cookie=cookie, client_id=first)
        assert current["has_control"]
        disable = {
            "request_id": "plan-disable",
            "enabled": False,
            "expected_revision": current["settings_revision"],
            "control_epoch": current["control_epoch"],
        }
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/plan-mode",
                body=disable,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=second,
            )[0]
            == 409
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/plan-mode",
                body=disable,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=first,
            )[0]
            == 200
        )
    finally:
        host.stop()
        thread.join(3)


def test_browser_session_navigation_preserves_workspace_and_runtime(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    workspace = tmp_path / "work"
    workspace.mkdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "state")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(workspace)
    app.agent.runtime.close()
    app.agent.runtime = _Runtime()
    app.agent.ollama = app.agent.runtime
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, auth = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, client = _request(
            host,
            "POST",
            "/api/v1/clients",
            body={},
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )
        assert status == 201
        client_id = client["client_id"]

        first = app.session_id
        assert (
            _request(
                host,
                "POST",
                "/api/v1/turns",
                body={"request_id": "session-first-turn", "text": "First chat"},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=client_id,
            )[0]
            == 202
        )
        deadline = time.monotonic() + 3
        while (
            app.receipt("session-first-turn").state != "completed" and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert app.receipt("session-first-turn").state == "completed"
        status, _, listing = _request(
            host, "GET", "/api/v1/sessions", cookie=cookie, client_id=client_id
        )
        assert status == 200
        assert any(
            item["session_id"] == first and item["resumable"] for item in listing["sessions"]
        )

        _, _, old = _request(host, "GET", "/api/v1/session", cookie=cookie, client_id=client_id)
        choose = {
            "request_id": "new-browser-session",
            "expected_session_id": first,
            "session_id": "",
            "control_epoch": old["control_epoch"],
        }
        status, _, created = _request(
            host,
            "POST",
            "/api/v1/session/select",
            body=choose,
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
            client_id=client_id,
        )
        assert status == 200 and created["session_id"] != first
        second = created["session_id"]
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/select",
                body=choose,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=client_id,
            )[2]
            == created
        )
        assert app.turns.workspace(second)[0] == str(workspace.resolve())
        assert (
            _request(
                host,
                "POST",
                "/api/v1/turns",
                body={"request_id": "stale-tab-turn", "text": "Wrong session"},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=client_id,
                expected_session_id=first,
            )[0]
            == 409
        )
        assert app.receipt("stale-tab-turn") is None
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/select",
                body={**choose, "request_id": "stale-select", "session_id": first},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=client_id,
            )[0]
            == 409
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/select",
                body={
                    "request_id": "foreign-select",
                    "expected_session_id": second,
                    "session_id": "foreign-session",
                    "control_epoch": 0,
                },
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=client_id,
            )[0]
            == 409
        )
        app.choose_local_model(ModelInfo("ollama", "other", "other"), expected_revision=0)
        assert app.agent.model == "other"
        _, _, listing = _request(
            host, "GET", "/api/v1/sessions", cookie=cookie, client_id=client_id
        )
        assert any(
            item["session_id"] == first and item["resumable"] for item in listing["sessions"]
        )
        restored = {
            "request_id": "restore-browser-session",
            "expected_session_id": second,
            "session_id": first,
            "control_epoch": 0,
        }
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/select",
                body=restored,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
                client_id=client_id,
            )[0]
            == 200
        )
        _, _, snapshot = _request(
            host, "GET", "/api/v1/session", cookie=cookie, client_id=client_id
        )
        assert snapshot["session_id"] == first
        assert any(item["content"] == "First chat" for item in snapshot["messages"])
        assert snapshot["model"] == "fixture"
    finally:
        host.stop()
        thread.join(3)


def test_browser_local_model_and_thinking_choice_are_revisioned(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import host as host_module
    from klaude_webhost import main as host_main

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "state")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(tmp_path)
    app.agent.runtime.close()
    app.agent.runtime = _Runtime()
    app.agent.ollama = app.agent.runtime

    def catalog(connection):
        return [
            ModelInfo(
                "ollama",
                name,
                name,
                connection_id=connection.id,
                connection_revision=connection.revision,
            )
            for name in ("fixture", "other")
        ]

    monkeypatch.setattr(host_module, "discover_connection", catalog)
    monkeypatch.setattr(
        host_module,
        "read_capabilities",
        lambda _request: {
            "status": "ok",
            "models": [{"declared": ["completion", "tools", "thinking"]}],
        },
    )
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, auth = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, models = _request(host, "GET", "/api/v1/models/local", cookie=cookie)
        assert status == 200 and [item["id"] for item in models["models"]] == [
            "fixture",
            "other",
        ]
        _, _, initial = _request(host, "GET", "/api/v1/session", cookie=cookie)
        mode = {
            "request_id": "thinking-on",
            "mode": "thinking",
            "expected_revision": initial["settings_revision"],
            "control_epoch": 0,
        }
        assert _request(
            host,
            "POST",
            "/api/v1/session/mode",
            body=mode,
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2] == {
            "revision": 1,
        }
        assert _request(
            host,
            "POST",
            "/api/v1/session/mode",
            body=mode,
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2] == {
            "revision": 1,
        }
        assert app.agent.reasoning_mode == "thinking"
        assert app.agent.ollama_think == "medium"
        assert _request(
            host,
            "POST",
            "/api/v1/session/mode",
            body={
                "request_id": "thinking-off",
                "mode": "standard",
                "expected_revision": 1,
                "control_epoch": 0,
            },
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2] == {
            "revision": 2,
        }
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/mode",
                body=mode,
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
            )[0]
            == 409
        )
        assert app.agent.reasoning_mode == "standard"
        assert _request(
            host,
            "POST",
            "/api/v1/session/mode",
            body={
                "request_id": "thinking-on-again",
                "mode": "thinking",
                "expected_revision": 2,
                "control_epoch": 0,
            },
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2] == {
            "revision": 3,
        }
        _, _, thinking = _request(host, "GET", "/api/v1/session", cookie=cookie)
        assert thinking["mode"] == "thinking" and thinking["effort"] == "medium"
        selection = {
            "request_id": "local-model-choice",
            "model_id": "other",
            "expected_revision": 3,
            "control_epoch": 0,
        }
        assert _request(
            host,
            "POST",
            "/api/v1/session/model",
            body=selection,
            cookie=cookie,
            csrf=auth["csrf"],
            origin=host.origin,
        )[2] == {
            "revision": 4,
        }
        _, _, selected = _request(host, "GET", "/api/v1/session", cookie=cookie)
        assert selected["model"] == "other"
        assert app.memory.session_runtime(app.session_id)["model"].endswith("/other")
        assert app.memory.session_runtime(app.session_id)["mode"] == "thinking"
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/mode",
                body={
                    "request_id": "stale-mode",
                    "mode": "standard",
                    "expected_revision": 3,
                    "control_epoch": 0,
                },
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
            )[0]
            == 409
        )
        monkeypatch.setattr(
            host_module,
            "read_capabilities",
            lambda _request: {
                "status": "ok",
                "models": [{"declared": ["completion"]}],
            },
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/model",
                body={
                    **selection,
                    "request_id": "no-tool-choice",
                    "model_id": "fixture",
                    "expected_revision": 4,
                },
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
            )[0]
            == 409
        )
        assert app.agent.model == "other"
        assert (
            _request(
                host,
                "POST",
                "/api/v1/turns",
                body={"request_id": "after-model-choice", "text": "Save choice"},
                cookie=cookie,
                csrf=auth["csrf"],
                origin=host.origin,
            )[0]
            == 202
        )
        deadline = time.monotonic() + 3
        while (
            app.receipt("after-model-choice").state != "completed" and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert app.receipt("after-model-choice").state == "completed"
        session_id = app.session_id
    finally:
        host.stop()
        thread.join(3)
    resumed = host_main.create_application(tmp_path, session_id=session_id)
    try:
        assert resumed.agent.model == "other"
        assert resumed.agent.reasoning_mode == "thinking"
        assert resumed.agent.ollama_think == "medium"
        assert resumed.public_history()[0]["content"] == "Save choice"
    finally:
        asyncio.run(resumed.close())


def test_browser_workspace_reads_stay_bound_and_private(tmp_path):
    from klaude_tools import Workspace

    (tmp_path / "note.txt").write_text("visible note\n")
    (tmp_path / ".env").write_text("SECRET=private\n")
    app = _app(tmp_path)
    app.agent.workspace = Workspace(tmp_path)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        assert _request(host, "GET", "/api/v1/workspace/files")[0] == 401
        code = host.bootstrap_url.partition("#")[2]
        _, headers, _ = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, listing = _request(host, "GET", "/api/v1/workspace/files", cookie=cookie)
        assert status == 200 and "note.txt" in listing["text"]
        assert ".env" not in listing["text"]
        status, _, document = _request(
            host,
            "GET",
            "/api/v1/workspace/file?path=note.txt",
            cookie=cookie,
        )
        assert status == 200 and document["text"] == "visible note\n"
        assert _request(host, "GET", "/api/v1/workspace/file?path=.env", cookie=cookie)[0] == 400
        assert (
            _request(host, "GET", "/api/v1/workspace/file?path=..%2Foutside", cookie=cookie)[0]
            == 400
        )
        status, _, search = _request(
            host,
            "GET",
            "/api/v1/workspace/search?pattern=visible",
            cookie=cookie,
        )
        assert status == 200 and "visible note" in search["text"]
    finally:
        host.stop()
        thread.join(3)


def test_browser_question_answer_continues_same_turn_and_is_control_scoped(tmp_path):
    class InputRuntime:
        calls = 0
        saw_answer = False

        def chat(self, _model, messages, tools=None, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                assert any(tool["function"]["name"] == "request_user_input" for tool in tools)
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "request_user_input",
                                "arguments": {
                                    "question": "Choose a path",
                                    "options": [
                                        {"label": "A"},
                                        {"label": "B"},
                                    ],
                                },
                            },
                        }
                    ],
                }
            self.saw_answer = any(
                '"answer": "B"' in str(message.get("content", "")) for message in messages
            )
            return {"role": "assistant", "content": "Choice recorded."}

        def close(self):
            pass

    app = _app(tmp_path)
    runtime = InputRuntime()
    app.agent.runtime = runtime
    app.agent.ollama = runtime
    app.agent.gate.policies["request_user_input"] = "allow"
    app.allow_user_input_tool = True
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:

        def login():
            code = host.new_bootstrap_url().partition("#")[2]
            _, headers, data = _request(
                host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
            )
            return headers["Set-Cookie"].split(";", 1)[0], data["csrf"]

        owner, owner_csrf = login()
        observer, observer_csrf = login()
        status, _, receipt = _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "question-turn", "text": "Ask me"},
            cookie=owner,
            csrf=owner_csrf,
            origin=host.origin,
        )
        assert status == 202
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=owner)
            if snapshot["questions"]:
                break
            time.sleep(0.02)
        assert snapshot["questions"]
        assert snapshot["questions"][0]["question"] == "Choose a path"
        assert snapshot["questions"][0]["options"] == ["A", "B"]
        _, _, watching = _request(host, "GET", "/api/v1/session", cookie=observer)
        assert watching["questions"] == snapshot["questions"]
        path = f"/api/v1/interactions/{snapshot['questions'][0]['id']}/answer"
        answer = {
            "request_id": "question-answer",
            "answer": "B",
            "control_epoch": snapshot["control_epoch"],
        }
        assert (
            _request(
                host,
                "POST",
                path,
                body=answer,
                cookie=observer,
                csrf=observer_csrf,
                origin=host.origin,
            )[0]
            == 410
        )
        assert (
            _request(
                host, "POST", path, body=answer, cookie=owner, csrf=owner_csrf, origin=host.origin
            )[0]
            == 200
        )
        assert (
            _request(
                host, "POST", path, body=answer, cookie=owner, csrf=owner_csrf, origin=host.origin
            )[0]
            == 200
        )
        deadline = time.monotonic() + 3
        while app.receipt("question-turn").state != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert app.receipt("question-turn").turn_id == receipt["turn_id"]
        assert runtime.saw_answer
    finally:
        host.stop()
        thread.join(3)


def test_browser_file_edits_require_clean_activation_and_exact_approval(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    repo = tmp_path / "repo"
    repo.mkdir()
    for command in (
        ["git", "init"],
        ["git", "config", "user.email", "tests@example.test"],
        ["git", "config", "user.name", "Klaude Tests"],
    ):
        subprocess.run(command, cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("clean\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "state")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(repo)

    class WriteRuntime:
        calls = 0

        def chat(self, _model, _messages, tools=None, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                assert any(tool["function"]["name"] == "write_file" for tool in tools)
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "write_file",
                                "arguments": {
                                    "path": "generated.txt",
                                    "content": "approved content\n",
                                },
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "Created."}

        def close(self):
            pass

    runtime = WriteRuntime()
    app.agent.runtime.close()
    app.agent.runtime = runtime
    app.agent.ollama = runtime
    app.agent.tool_selector = lambda _message, tools: list(tools)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, login = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        _, _, initial = _request(host, "GET", "/api/v1/session", cookie=cookie)
        assert initial["tools"] == "read-only"
        assert "write_file" not in app.agent.tools
        activation = {
            "request_id": "enable-edits",
            "expected_revision": initial["workspace_revision"],
            "acknowledge": True,
        }
        assert (
            _request(
                host,
                "POST",
                "/api/v1/workspace/activate-edits",
                body={**activation, "acknowledge": False},
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 400
        )
        status, _, enabled = _request(
            host,
            "POST",
            "/api/v1/workspace/activate-edits",
            body=activation,
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 200 and enabled["enabled"] is True
        with pytest.raises(RuntimeError, match="before LAN preview"):
            host.start_lan("192.168.1.5", tmp_path / "control")
        assert (
            _request(
                host,
                "POST",
                "/api/v1/workspace/activate-edits",
                body=activation,
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[2]
            == enabled
        )
        assert subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() == ("klaude/session")
        assert _request(host, "GET", "/api/v1/session", cookie=cookie)[2]["tools"] == (
            "file edits enabled"
        )
        write_body = {"request_id": "browser-write", "text": "Create generated.txt"}
        status, _, accepted = _request(
            host,
            "POST",
            "/api/v1/turns",
            body=write_body,
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 202
        status, _, retried = _request(
            host,
            "POST",
            "/api/v1/turns",
            body=write_body,
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 202 and retried["turn_id"] == accepted["turn_id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
            if snapshot["approvals"]:
                break
            time.sleep(0.02)
        assert snapshot["approvals"] and snapshot["approvals"][0]["tool"] == "write_file"
        assert "generated.txt" in snapshot["approvals"][0]["detail"]
        assert (
            hashlib.sha256(b"approved content\n").hexdigest()
            in (snapshot["approvals"][0]["detail"])
        )
        assert not (repo / "generated.txt").exists()
        path = f"/api/v1/interactions/{snapshot['approvals'][0]['id']}/decision"
        assert (
            _request(
                host,
                "POST",
                path,
                body={
                    "request_id": "write-approval",
                    "decision": "allow_once",
                    "control_epoch": snapshot["control_epoch"],
                },
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        assert (
            _request(
                host,
                "POST",
                path,
                body={
                    "request_id": "write-approval",
                    "decision": "allow_once",
                    "control_epoch": snapshot["control_epoch"],
                },
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        deadline = time.monotonic() + 3
        while app.receipt("browser-write").state != "completed" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (repo / "generated.txt").read_text() == "approved content\n"
        changed = subprocess.run(
            ["git", "show", "--pretty=", "--name-only", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert changed.strip() == "generated.txt"
        assert runtime.calls == 2
        assert (
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            == ""
        )
        _, _, previous = _request(host, "GET", "/api/v1/session", cookie=cookie)
        assert (
            _request(
                host,
                "POST",
                "/api/v1/session/select",
                body={
                    "request_id": "new-after-edit",
                    "expected_session_id": previous["session_id"],
                    "session_id": "",
                    "control_epoch": previous["control_epoch"],
                },
                cookie=cookie,
                csrf=login["csrf"],
                origin=host.origin,
            )[0]
            == 200
        )
        _, _, fresh = _request(host, "GET", "/api/v1/session", cookie=cookie)
        assert fresh["tools"] == "read-only"
        assert "write_file" not in app.agent.tools
        assert (repo / "generated.txt").read_text() == "approved content\n"
    finally:
        host.stop()
        thread.join(3)


def test_browser_edit_activation_preserves_dirty_user_work(tmp_path, monkeypatch):
    from klaude_core import config as config_module
    from klaude_core.config import Config
    from klaude_webhost import main as host_main

    repo = tmp_path / "repo"
    repo.mkdir()
    for command in (
        ["git", "init"],
        ["git", "config", "user.email", "tests@example.test"],
        ["git", "config", "user.name", "Klaude Tests"],
    ):
        subprocess.run(command, cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("original\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("user edit\n")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "state")
    monkeypatch.setattr(host_main, "load_config", lambda: Config(models={"coder": "fixture"}))
    app = host_main.create_application(repo)
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, login = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        _, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
        status, _, result = _request(
            host,
            "POST",
            "/api/v1/workspace/activate-edits",
            body={
                "request_id": "dirty-activation",
                "expected_revision": snapshot["workspace_revision"],
                "acknowledge": True,
            },
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        assert status == 200 and result["enabled"] is False
        assert "DIRTY" in result["status"]
        assert "write_file" not in app.agent.tools
        assert (repo / "README.md").read_text() == "user edit\n"
        assert subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() != ("klaude/session")
    finally:
        host.stop()
        thread.join(3)


def test_webhost_readers_reject_large_nonregular_and_sensitive_files(tmp_path):
    from klaude_application.workspace_reads import bounded_grep, bounded_read
    from klaude_tools import Workspace

    workspace = Workspace(tmp_path)
    (tmp_path / "notes.txt").write_text("first\nsecond\n")
    assert "2: second" in bounded_read(workspace, "notes.txt", offset=2, limit=1)
    assert "second" in bounded_grep(workspace, "second")
    (tmp_path / "huge.txt").write_bytes(b"x" * (1_048_576 + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        bounded_read(workspace, "huge.txt")
    (tmp_path / "credentials.json").write_text("secret-canary")
    assert "secret-canary" not in bounded_grep(workspace, "secret-canary")
    with pytest.raises(PermissionError):
        bounded_read(workspace, "credentials.json")
    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(ValueError, match="regular"):
        bounded_read(workspace, "fifo")


def test_webhost_grep_caps_pipe_output_before_returning(tmp_path):
    from klaude_application.workspace_reads import bounded_grep
    from klaude_tools import Workspace

    for number in range(40):
        (tmp_path / f"match-{number}.txt").write_text(("needle " + "x" * 400 + "\n") * 3)
    result = bounded_grep(Workspace(tmp_path), "needle")
    assert len(result) <= 10_020 and result.endswith("...[truncated]")


def test_webhost_directory_listing_uses_opened_directory_and_hides_secrets(tmp_path, monkeypatch):
    from klaude_application import workspace_reads
    from klaude_tools import Workspace

    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "docs"
    source.mkdir()
    (source / "visible.txt").write_text("yes")
    (source / "credentials.json").write_text("secret")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("no")
    workspace = Workspace(root)
    real_scandir = workspace_reads.os.scandir

    def swap_path(directory):
        source.rename(root / "old-docs")
        source.symlink_to(outside, target_is_directory=True)
        return real_scandir(directory)

    monkeypatch.setattr(workspace_reads.os, "scandir", swap_path)
    result = workspace_reads.bounded_list_dir(workspace, "docs")
    assert "docs/visible.txt" in result
    assert "credentials.json" not in result
    assert "private.txt" not in result


def test_webhost_grep_keeps_opened_directory_when_path_is_swapped(tmp_path, monkeypatch):
    from klaude_application import workspace_reads
    from klaude_tools import Workspace

    root = tmp_path / "workspace"
    root.mkdir()
    source = root / "docs"
    source.mkdir()
    (source / "note.txt").write_text("needle-approved")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("needle-private")
    workspace = Workspace(root)
    real_popen = workspace_reads.subprocess.Popen

    def swap_path(*args, **kwargs):
        source.rename(root / "old-docs")
        source.symlink_to(outside, target_is_directory=True)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(workspace_reads.subprocess, "Popen", swap_path)
    result = workspace_reads.bounded_grep(workspace, "needle", "docs")
    assert "needle-approved" in result
    assert "needle-private" not in result


def test_webhost_git_reads_are_bounded_to_workspace_subdirectory(tmp_path):
    import subprocess

    from klaude_application.workspace_reads import WorkspaceReadService
    from klaude_tools import Workspace

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "tracked.txt").write_text("base\n")
    (tmp_path / "outside.txt").write_text("outside-base\n")
    (inside / ".env").write_text("API_KEY=secret-old-value\n")
    (inside / "private.pem").write_text("secret-old-key\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "baseline",
        ],
        check=True,
    )
    (inside / "tracked.txt").write_text("base\nsecret-new-value\n" + "inside " * 3000)
    (tmp_path / "outside.txt").write_text("outside-private\n")
    (inside / ".env").write_text("API_KEY=secret-new-value\n")
    (inside / "private.pem").write_text("secret-new-key\n")
    reads = WorkspaceReadService(Workspace(inside))
    assert "outside.txt" not in reads.git_status()
    assert "tracked.txt" in reads.git_status()
    assert ".env" not in reads.git_status()
    assert "private.pem" not in reads.git_status()
    diff = reads.git_diff()
    assert "outside-private" not in diff
    assert "secret-new-value" not in diff
    assert "[REDACTED]" in diff
    assert "secret-old-value" not in diff
    assert "secret-new-key" not in diff
    assert len(diff) <= 12_020 and diff.endswith("...[truncated]")


def test_webhost_git_read_keeps_opened_workspace_when_path_is_swapped(tmp_path, monkeypatch):
    import subprocess

    from klaude_application import workspace_reads
    from klaude_tools import Workspace

    root = tmp_path / "original"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "approved.txt").write_text("approved")
    workspace = Workspace(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    subprocess.run(["git", "init", "-q", str(outside)], check=True)
    (outside / "private.txt").write_text("private")
    real_popen = workspace_reads.subprocess.Popen

    def swap_path(*args, **kwargs):
        root.rename(tmp_path / "moved")
        root.symlink_to(outside, target_is_directory=True)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(workspace_reads.subprocess, "Popen", swap_path)
    status = workspace_reads.bounded_git(workspace, "status")
    assert "approved.txt" in status
    assert "private.txt" not in status


def test_webhost_git_read_fails_closed_on_oversized_secret_source(tmp_path):
    import subprocess

    from klaude_application.workspace_reads import WorkspaceReadService
    from klaude_tools import Workspace

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".env").write_bytes(b"x" * 65_537)
    with pytest.raises(ValueError, match="redaction limit"):
        WorkspaceReadService(Workspace(tmp_path)).git_status()


def test_webhost_public_routes_hide_private_model_content(tmp_path):
    app = _app(tmp_path)

    def events(_message, scope=None):
        assert "request_user_input" not in app.agent.tools
        assert app.agent.gate._structured_ask is None
        yield AgentEvent(
            "text",
            {
                "content": "Visible answer",
                "model_message": {"private_reasoning": "secret-canary"},
            },
        )

    app.agent.run = events
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, login = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        _request(
            host,
            "POST",
            "/api/v1/turns",
            body={"request_id": "private-test", "text": "Hello"},
            cookie=cookie,
            csrf=login["csrf"],
            origin=host.origin,
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            _, _, snapshot = _request(host, "GET", "/api/v1/session", cookie=cookie)
            if snapshot["state"] == "completed":
                break
            time.sleep(0.02)
        assert "Visible answer" in json.dumps(snapshot)
        assert "secret-canary" not in json.dumps(snapshot)
        epoch = snapshot["cursor"].split(":")[0]
        replay = app.replay(f"{epoch}:0")
        assert "secret-canary" not in json.dumps(replay)
    finally:
        host.stop()
        thread.join(3)


def test_message_link_reads_exact_older_public_row_in_current_session(tmp_path):
    app = _app(tmp_path)
    app.memory.log_turn(app.session_id, "assistant", "Earlier shared reply",
                        model_content={"secret": "private-link-canary"})
    row_id = app.memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
    for index in range(120):
        app.memory.log_turn(app.session_id, "user", f"Later message {index}")
    app.memory.log_turn("other", "assistant", "Other private conversation")
    other_id = app.memory.db.execute("SELECT max(rowid) FROM turns").fetchone()[0]
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        route = f"/api/v1/session?session={app.session_id}&message=stored:{row_id}"
        assert _request(host, "GET", route)[0] == 401
        _, headers, _ = _request(host, "POST", "/api/v1/auth/exchange",
                                 body={"code": host.bootstrap_url.partition("#")[2]},
                                 origin=host.origin)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        before = app.control()
        status, _, data = _request(host, "GET", route, cookie=cookie)
        assert status == 200
        assert all(item["id"] != f"stored:{row_id}" for item in data["messages"])
        assert data["linked_message"]["content"] == "Earlier shared reply"
        assert "private-link-canary" not in json.dumps(data)
        assert app.control() == before
        assert _request(host, "GET", route, cookie=cookie, fetch_site="cross-site")[0] == 403
        assert _request(host, "GET", route.replace(f"stored:{row_id}", f"stored:{other_id}"),
                        cookie=cookie)[0] == 404
        assert _request(host, "GET", route.replace(f"session={app.session_id}", "session=other"),
                        cookie=cookie)[0] == 409
        for invalid in ("stored:0", "stored:-1", "stored:01", "stored:9223372036854775808",
                        "partial", "stored:1&message=stored:2"):
            bad = f"/api/v1/session?session={app.session_id}&message={invalid}"
            assert _request(host, "GET", bad, cookie=cookie)[0] == 400
    finally:
        host.stop()
        thread.join(3)


def test_webhost_oversized_event_requires_snapshot_instead_of_dropping_text(tmp_path):
    app = _app(tmp_path)
    app.replay = lambda _cursor, limit=100: [
        {"cursor": "epoch:1", "kind": "message.delta", "text": "🙂" * 20_000},
    ]
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, _ = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", "/api/v1/events?after=epoch:0", headers={"Cookie": cookie})
        response = conn.getresponse()
        assert response.status == 200
        assert response.fp.readline() == b"id: epoch:1\n"
        frame = response.fp.readline()
        assert b"stream.reset_required" in frame
        assert "🙂".encode() not in frame
        conn.close()
    finally:
        host.stop()
        thread.join(3)


def test_webhost_launcher_starts_and_stops_without_model_contact(tmp_path):
    environment = {**os.environ, "KLAUDE_HOME": str(tmp_path / "profile")}
    # Worker tests can leave explicit roots in the parent environment. This
    # launcher must use its own temporary profile, including account storage.
    environment.pop("KLAUDE_CONFIG_DIR", None)
    environment.pop("KLAUDE_DATA_DIR", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "klaude_webhost.main", "--workspace", str(tmp_path), "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert process.stdout is not None
        assert select.select([process.stdout], [], [], 8)[0], "WebUI launcher did not become ready"
        line = process.stdout.readline().strip()
        assert line.startswith("Open http://127.0.0.1:")
        url = urlsplit(line.removeprefix("Open "))
        conn = http.client.HTTPConnection("127.0.0.1", url.port, timeout=3)
        conn.request("GET", "/")
        response = conn.getresponse()
        assert response.status == 200
        assert b"Klaude" in response.read()
        conn.close()
    finally:
        process.terminate()
        stdout, stderr = process.communicate(timeout=8)
        assert process.returncode == 0, stderr
        from klaude_webhost.accounts import AccountStore

        initial = AccountStore(tmp_path / "profile" / "config").initial_password()
        assert initial and initial not in stdout + stderr


def test_message_menu_actions_are_controlled_exact_and_keep_original(tmp_path):
    from klaude_tools.toolkit import Workspace

    app = _app(tmp_path)
    app.agent.workdir = tmp_path
    app.agent.workspace = Workspace(tmp_path)
    source = app.session_id
    app.turns.bind_workspace(source, str(tmp_path), expected_revision=0)
    app.memory.log_turn(source, "user", "Original question")
    app.memory.log_turn(source, "assistant", "Original answer")
    app.memory.log_turn(source, "user", "Later question")
    app.memory.log_turn(source, "assistant", "Later answer")
    original = app.memory.load_session(source)
    first_reply = app.snapshot()["messages"][1]
    host = LocalWebHost(app)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        code = host.bootstrap_url.partition("#")[2]
        _, headers, auth = _request(
            host, "POST", "/api/v1/auth/exchange", body={"code": code}, origin=host.origin
        )
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        body = {
            "request_id": "message-branch",
            "source_session_id": source,
            "message_id": first_reply["id"],
            "action": "branch",
            "control_epoch": 0,
        }
        args = {"cookie": cookie, "csrf": auth["csrf"], "origin": host.origin}
        assert (
            _request(
                host,
                "POST",
                "/api/v1/messages/action",
                body=body,
                cookie=cookie,
                origin=host.origin,
            )[0]
            == 403
        )
        invalid = dict(body, message_id="stored:9223372036854775808")
        assert _request(host, "POST", "/api/v1/messages/action", body=invalid, **args)[0] == 409
        assert app.session_id == source
        with app.memory._db_lock, app.memory.db:
            app.memory.db.execute(
                "INSERT INTO application_control VALUES (?,?,?,?)",
                (source, app.controller_id, 1, time.time()),
            )
        epoch = app.take_control("other-browser", expected_epoch=1)
        assert _request(host, "POST", "/api/v1/messages/action", body=body, **args)[0] == 409
        viewer = hashlib.sha256(cookie.partition("=")[2].encode()).hexdigest()
        body["control_epoch"] = app.take_control(viewer, expected_epoch=epoch)
        status, _, receipt = _request(host, "POST", "/api/v1/messages/action", body=body, **args)
        assert status == 200
        branch = receipt["session_id"]
        assert app.memory.load_session(branch) == original[:2]
        assert app.memory.load_session(source) == original
        assert app.turns.workspace(branch)[0] == str(tmp_path)
        assert not app.agent.workspace.write_enabled
        assert _request(host, "POST", "/api/v1/messages/action", body=body, **args)[2] == receipt
        changed = dict(body, action="retry")
        assert _request(host, "POST", "/api/v1/messages/action", body=changed, **args)[0] == 409
        snap = app.snapshot()
        assert snap["messages"][1]["created_at"] == first_reply["created_at"]
        retry = dict(
            body,
            request_id="message-retry",
            source_session_id=branch,
            message_id=snap["messages"][1]["id"],
            action="retry",
        )
        assert (
            _request(
                host,
                "POST",
                "/api/v1/messages/action",
                body=retry,
                expected_session_id=source,
                **args,
            )[0]
            == 409
        )
        assert _request(host, "POST", "/api/v1/messages/action", body=retry, **args)[0] == 200
        app._active.finished.wait(5)
        assert app._active.finished.is_set()
        assert app.memory.load_session(source) == original
        assert app.session_id == branch
        assert app.memory.load_session(branch)[:2] == original[:2]
        history = tuple(app.snapshot()["messages"])
        assert [item["content"] for item in history if item["role"] == "user"] == [
            "Original question"
        ]
        assert history[1]["content"] == "Original answer"
        assert history[1]["previous_response"] is True
        assert history[-1]["retry_root"] == history[1]["id"]
        assert history[-1]["previous_response"] is False
        assert history[-1]["content"] == "Ready."
        target = app.session_id
        assert _request(host, "POST", "/api/v1/messages/action", body=retry, **args)[0] == 200
        assert app.session_id == target
        assert tuple(app.snapshot()["messages"]) == history
        host._message_receipts.clear()
        assert _request(host, "POST", "/api/v1/messages/action", body=retry, **args)[0] == 200
        assert tuple(app.snapshot()["messages"]) == history
    finally:
        host.stop()
        thread.join(3)


def test_webhost_markdown_assets_are_local_pinned_and_keep_csp(tmp_path):
    from klaude_webhost.host import STATIC

    host = LocalWebHost(_app(tmp_path))
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        for path in ("/markdown.js", "/vendor/markdown-it.min.js", "/vendor/prism.min.js",
                     "/loading-indicator.js", "/vendor/material-loading-shapes.js"):
            conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
            conn.request("GET", path)
            response = conn.getresponse()
            assert response.status == 200
            assert response.getheader("Content-Type").startswith("text/javascript")
            policy = response.getheader("Content-Security-Policy")
            assert "script-src 'self'" in policy
            assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
            assert response.getheader("X-Content-Type-Options") == "nosniff"
            assert response.read() == (STATIC / path.removeprefix("/")).read_bytes()
            conn.close()
        manifest = json.loads((STATIC / "vendor/manifest.json").read_text())
        for name, digest in manifest["assets"].items():
            assert hashlib.sha256((STATIC / "vendor" / name).read_bytes()).hexdigest() == digest
        for name in ("markdown-it-LICENSE.txt", "markdown-it-THIRD-PARTY.txt", "prism-LICENSE.txt"):
            assert (STATIC / "vendor" / name).read_text().strip()
        material = json.loads((STATIC / "vendor/material-loading-manifest.json").read_text())
        assert material["graphics_shapes_version"] == "1.0.1"
        for name, digest in material["assets"].items():
            assert hashlib.sha256((STATIC / "vendor" / name).read_bytes()).hexdigest() == digest
        source = (STATIC / "vendor/material-loading-shapes.js").read_text()
        # The existing app route must be sufficient on a still-running legacy
        # host whose static allowlist does not know the two indicator paths.
        app_source = (STATIC / "app.js").read_text()
        assert source.strip() in app_source
        assert (STATIC / "loading-indicator.js").read_text().strip() in app_source
        html = (STATIC / "index.html").read_text()
        # The early appearance/startup bootstrap deliberately uses the fixed
        # loading route; geometry and Expressive dependencies stay in app.js.
        assert html.index('src="/loading-indicator.js"') < html.index('href="/style.css"')
        assert 'src="/vendor/material-loading-shapes.js"' not in html
        # Settings must initialize through the longstanding management route
        # even when an older running host cannot serve a new standalone asset.
        assert 'src="/settings.js"' not in html
        management = (STATIC / "management.js").read_text()
        assert management.index("window.SettingsDrafts =") < management.index(
            "window.BrowserManagement ="
        )
        shapes = json.loads(source.split("Object.freeze(", 1)[1].rsplit(");", 1)[0])
        assert shapes["names"] == [
            "soft-burst", "cookie-9", "pentagon", "pill", "sunny", "cookie-4", "oval",
        ]
        assert len(shapes["morphs"]) == 7
        assert set(shapes["shapes"]) == {
            "circle", "pill", "oval", "diamond", "cookie", "burst", "sunny", "flower", "soft-burst",
        }
        colors = json.loads((STATIC / "vendor/material-colors-manifest.json").read_text())
        assert colors["license"] == "Apache-2.0"
        for name, digest in colors["assets"].items():
            assert hashlib.sha256((STATIC / "vendor" / name).read_bytes()).hexdigest() == digest
        assert (STATIC / "vendor/material-colors.js").read_text().strip() in app_source
        assert (STATIC / "expressive.js").read_text().strip() in app_source
        for morph in shapes["morphs"]:
            assert len(morph["start"]) == len(morph["end"])
            assert len(morph["start"]) % 6 == 2
            for path in morph.values():
                assert path[:2] == path[-2:]  # Closed, native matched cubic outline.
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
        conn.request("GET", "/vendor/../host.py")
        assert conn.getresponse().status == 401
        conn.close()
    finally:
        host.stop()
        thread.join(3)
