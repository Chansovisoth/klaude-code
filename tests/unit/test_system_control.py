"""Profile-scoped System review, process identity and lifecycle authorization."""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from klaude_core.settings_store import read_settings
from klaude_webhost import system_control as system

from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def controls(profile_browser, monkeypatch):
    host, service, _, auth = profile_browser
    control = system.SystemControl(host, service.cfg, service.workspace, managed=True)
    host.system_control = control
    peers = [{"pid": 12345, "birth": "123", "kind": "terminal"}]
    monkeypatch.setattr(system, "processes", lambda _cfg: peers[:])
    return host, service, auth, control, peers


def test_system_status_and_review_are_read_only_and_admin_only(controls):
    host, service, auth, control, _ = controls
    status, _, data = _request(host, "GET", "/api/v1/system", **auth)
    assert status == 200 and data["available"] and data["terminal_count"] == 1
    assert not data["busy"] and not control.action
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["system_control"]
    assert _request(host, "GET", "/api/v1/system/health")[2] == {
        "ready": True, "instance": control.instance,
    }
    for action in ("restart", "shutdown"):
        status, _, review = _request(host, "POST", "/api/v1/system/review",
                                     body={"action": action}, **auth)
        assert status == 200 and review["action"] == action
    assert not (service.cfg.data_dir / "webhost/lifecycle.json").exists()
    assert not host._stopping
    assert _request(host, "GET", "/api/v1/system", origin=host.origin)[0] == 401
    bad = {**auth, "csrf": "wrong"}
    assert _request(host, "POST", "/api/v1/system/review",
                    body={"action": "shutdown"}, **bad)[0] == 403
    host.http.host_lan = True
    assert _request(host, "GET", "/api/v1/system", **auth)[0] == 403
    assert _request(host, "POST", "/api/v1/system/review",
                    body={"action": "shutdown"}, **auth)[0] == 403
    assert _request(host, "POST", "/api/v1/system/apply", body={
        "review_id": review["review_id"], "request_id": uuid.uuid4().hex,
    }, **auth)[0] == 403
    assert not control.action and not host._stopping


def test_system_reviews_bind_owner_process_set_runtime_and_expiry(controls, monkeypatch):
    host, _, auth, control, peers = controls
    for action in ([], "poweroff", None):
        assert _request(host, "POST", "/api/v1/system/review",
                        body={"action": action}, **auth)[0] == 409
    review = control.review("one", "shutdown")
    with pytest.raises(ValueError):
        control.apply("two", review["review_id"], uuid.uuid4().hex)
    peers.append({"pid": 12346, "birth": "124", "kind": "terminal"})
    with pytest.raises(ValueError, match="runtime changed"):
        control.apply("one", review["review_id"], uuid.uuid4().hex)
    peers.pop()
    control.reviews[review["review_id"]]["expires_at"] = time.time() - 1
    with pytest.raises(ValueError, match="expired"):
        control.apply("one", review["review_id"], uuid.uuid4().hex)
    monkeypatch.setattr(control, "busy", lambda: True)
    with pytest.raises(ValueError, match="Wait for"):
        control.review("one", "restart")
    assert not host._stopping


def test_shutdown_is_persisted_and_disables_automatic_webui_start_once(controls, monkeypatch):
    host, service, auth, control, peers = controls
    review = control.review("owner", "shutdown")
    request = uuid.uuid4().hex
    stops = []
    monkeypatch.setattr(host, "begin_shutdown", lambda: stops.append("host"))
    accepted = control.apply("owner", review["review_id"], request)
    assert accepted["state"] == "accepted" and stops == ["host"]
    assert control.apply("owner", review["review_id"], request) == accepted
    assert stops == ["host"]
    assert read_settings(service.cfg.config_dir / "webui.json")["enabled"] is False
    targets = []
    monkeypatch.setattr(system, "stop_processes", lambda _cfg, values: targets.extend(values))
    control.finish()
    assert targets == peers
    receipt = json.loads((service.cfg.data_dir / "webhost/lifecycle.json").read_text())
    assert receipt["state"] == "completed" and receipt["request_id"] == request
    assert _request(host, "GET", "/api/v1/system", **auth)[0] == 200


def test_http_restart_ack_precedes_draining_and_revokes_old_sessions(controls):
    host, _, auth, control, _ = controls
    review = _request(host, "POST", "/api/v1/system/review",
                      body={"action": "restart"}, **auth)[2]
    status, _, accepted = _request(host, "POST", "/api/v1/system/apply", body={
        "review_id": review["review_id"], "request_id": uuid.uuid4().hex,
    }, **auth)
    assert status == 202 and accepted["action"] == "restart"
    assert host._stopping and control.action == "restart"
    assert not host._sessions


def test_process_identity_requires_exact_installation_and_profile(tmp_path):
    from types import SimpleNamespace

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    proc = tmp_path / "proc"
    item = proc / "12345"
    item.mkdir(parents=True)
    (item / "cwd").symlink_to(tmp_path, target_is_directory=True)
    (item / "exe").symlink_to(Path(sys.executable).resolve())
    (item / "stat").write_text("12345 (klaude) " + " ".join(["S", *(["0"] * 18), "999"]))
    (item / "cmdline").write_bytes(
        b"\0".join(os.fsencode(arg) for arg in [sys.executable, "-m", "klaude_cli.main", "chat"])
    )
    env = f"KLAUDE_CONFIG_DIR={cfg.config_dir}\0KLAUDE_DATA_DIR={cfg.data_dir}\0"
    (item / "environ").write_bytes(os.fsencode(env))
    expected = {"pid": 12345, "birth": "999", "kind": "terminal"}
    assert system.process_identity(cfg, 12345, proc=proc) == expected
    (item / "environ").write_bytes(os.fsencode(
        env.replace(str(cfg.data_dir), str(tmp_path / 'other')),
    ))
    assert system.process_identity(cfg, 12345, proc=proc) is None
    (item / "environ").write_bytes(os.fsencode(env))
    (item / "cmdline").write_bytes(b"\0".join(os.fsencode(arg) for arg in [
        sys.executable, "-m", "http.server",
    ]))
    assert system.process_identity(cfg, 12345, proc=proc) is None


def test_pidfd_shutdown_never_signals_changed_or_unrelated_processes(monkeypatch):
    first = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    other = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    target = {"pid": first.pid, "birth": "exact", "kind": "terminal"}
    try:
        monkeypatch.setattr(
            system, "process_identity", lambda _cfg, _pid: {**target, "birth": "new"},
        )
        system.stop_processes(None, [target], grace=.1)
        assert first.poll() is None and other.poll() is None
        monkeypatch.setattr(system, "process_identity", lambda _cfg, _pid: target)
        system.stop_processes(None, [target], grace=.5)
        assert first.wait(timeout=2) == -signal.SIGTERM
        assert other.poll() is None
    finally:
        for process in (first, other):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=2)
