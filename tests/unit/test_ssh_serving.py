"""Actual SSH tunnels, remote owner leases and reviewed CPU serving boundaries."""

import json
import os
import queue
import signal
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path

import httpx
import pytest
from klaude_cli.serving_jobs import ServingJobs
from klaude_core.managed_serving import process_identity, read_log, records
from klaude_core.model_connections import connection_registry
from klaude_core.ssh_servers import arguments, change
from klaude_core.ssh_serving import inspect, program

from .test_managed_serving import lab, wait_for
from .test_ssh_servers import sshlab


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def remote_lab(tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    cfg, spec = lab.__wrapped__(local)
    remote = tmp_path / "ssh"
    remote.mkdir()
    fixture = sshlab.__wrapped__(remote)
    _, server, _, _ = next(fixture)
    try:
        server = replace(server, models_dir=str(Path(spec.model).parent))
        saved = change(cfg.config_dir, "add", definition=asdict(server))
        spec = replace(spec, ssh_server=server.id, local_port=port(), context=512, threads=2)
        request = {
            "config_dir": str(cfg.config_dir),
            "spec": asdict(spec),
            "operation": "prepare",
            "server_revision": saved["servers"][server.id]["revision"],
        }
        result = inspect(request)
        assert "error" not in result, result
        yield cfg, spec, request, result["evidence"], server
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass


def start(remote_lab, jobs, *, spec=None, evidence=None):
    cfg, initial, _, checked, _ = remote_lab
    request = {
        "id": uuid.uuid4().hex,
        "owner": "QA",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "spec": asdict(spec or initial),
        "evidence": evidence or checked,
    }
    jobs.start(request)
    return request


def gone(pid, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            process_identity(pid)
        except (OSError, ValueError):
            return True
        time.sleep(0.05)
    return False


def test_actual_remote_tunnel_health_and_acknowledged_owned_stop(remote_lab):
    cfg, spec, _, _, server = remote_lab
    originals = {
        path: Path(path).read_bytes()
        for path in (server.identity_file, server.known_hosts, spec.model, spec.executable)
    }
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        request = start(remote_lab, jobs)
        ready = wait_for(events, "ready")
        with httpx.Client(trust_env=False, timeout=2) as client:
            assert (
                client.get(ready["endpoint"]["base_url"] + "/models").json()["data"][0]["id"]
                == ready["model"]
            )
        assert ready["endpoint"]["base_url"].endswith(f":{spec.local_port}/v1")
        assert connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        jobs.stop(request["id"])
        jobs.close(wait=True)
        assert not jobs.owns(request["id"])
        assert records(cfg.data_dir)[request["id"]]["remote_cleanup"] == "confirmed"
        assert gone(ready["remote_pid"])
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        assert "private-engine-token" not in read_log(cfg.data_dir, request["id"])
        assert "[redacted]" in read_log(cfg.data_dir, request["id"])
        assert not (cfg.data_dir / "chat-preferences.json").exists()
        for path, data in originals.items():
            assert Path(path).read_bytes() == data
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize(
    "failure", ["local_port", "remote_port", "model", "executable", "definition"]
)
def test_reviewed_remote_changes_and_busy_ports_cannot_register(remote_lab, failure):
    cfg, spec, request, checked, server = remote_lab
    sock = None
    if failure.endswith("port"):
        sock = socket.socket()
        sock.bind(("127.0.0.1", spec.local_port if failure == "local_port" else spec.port))
        sock.listen()
    elif failure == "model":
        Path(spec.model).write_bytes(b"GGUFchanged")
    elif failure == "executable":
        Path(spec.executable).write_text("#!/bin/false\n")
    else:
        change(
            cfg.config_dir,
            "edit",
            definition=asdict(replace(server, name="Changed")),
            revision=request["server_revision"],
        )
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        start(remote_lab, jobs, evidence=checked)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert not connection_registry(cfg).path.exists()
        if failure in {"remote_port", "model", "executable"}:
            assert next(iter(records(cfg.data_dir).values()))["remote_cleanup"] == "not_started"
        if sock:
            assert sock.fileno() >= 0
    finally:
        jobs.close(wait=True)
        if sock:
            sock.close()


def test_remote_preflight_reuses_flags_but_rejects_new_engine_or_definition(remote_lab):
    cfg, spec, request, checked, server = remote_lab
    assert inspect({**request, "evidence": checked})["evidence"] == checked
    assert "error" in inspect({**request, "spec": asdict(replace(spec, engine="vllm"))})
    assert "error" in inspect({**request, "spec": asdict(replace(spec, gpu_layers=1))})
    change(
        cfg.config_dir,
        "edit",
        definition=asdict(replace(server, name="Changed")),
        revision=request["server_revision"],
    )
    assert "error" in inspect(request)


def test_remote_engine_stops_when_heartbeat_is_missing_even_with_open_ssh(remote_lab):
    _, spec, _, checked, server = remote_lab
    process = subprocess.Popen(
        arguments(server, program=program()),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        payload = {
            "operation": "serve",
            "id": uuid.uuid4().hex,
            "spec": asdict(spec),
            "models_dir": server.models_dir,
            "evidence": checked,
        }
        process.stdin.write((json.dumps(payload) + "\n").encode())
        process.stdin.flush()
        first = json.loads(process.stdout.readline())
        assert first["state"] == "starting"
        process.wait(timeout=10)
        events = [json.loads(line) for line in process.stdout.readlines()]
        assert events[-1]["cleanup"] == "confirmed"
        assert gone(first["pid"])
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
        process.stdin.close()
        process.stdout.close()


def test_killed_local_helper_expires_remote_owner_and_reconciles_endpoint(remote_lab):
    cfg, _, _, _, _ = remote_lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        request = start(remote_lab, jobs)
        ready = wait_for(events, "ready")
        os.kill(ready["helper_pid"], signal.SIGKILL)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert gone(ready["remote_pid"])
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        assert records(cfg.data_dir)[request["id"]]["state"] == "interrupted"
    finally:
        jobs.close(wait=True)


def test_cancelling_remote_startup_reaps_slow_engine_and_ignoring_descendants(remote_lab):
    cfg, spec, request, _, _ = remote_lab
    model = Path(spec.model).with_name("workers.gguf")
    model.write_bytes(b"GGUFfixture")
    # This fixture starts a worker ignoring SIGTERM and then delays HTTP startup.
    engine = Path(spec.executable)
    engine.write_text(engine.read_text().replace("class Handler", "time.sleep(30)\nclass Handler"))
    spec = replace(spec, model=str(model))
    checked = inspect({**request, "spec": asdict(spec)})["evidence"]
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(remote_lab, jobs, spec=spec, evidence=checked)
        wait_for(events, "starting")
        wait_for(events, "starting")
        deadline = time.monotonic() + 3
        child = None
        while time.monotonic() < deadline:
            try:
                import re

                found = re.search(r"descendant_pid=(\d+)", read_log(cfg.data_dir, accepted["id"]))
                if found:
                    child = int(found.group(1))
                    break
            except OSError:
                pass
            time.sleep(0.05)
        assert child is not None
        jobs.stop(accepted["id"])
        jobs.close(wait=True)
        saved = records(cfg.data_dir)[accepted["id"]]
        assert saved["remote_cleanup"] == "confirmed"
        assert gone(saved["remote_pid"]) and gone(child)
        assert not connection_registry(cfg).path.exists()
    finally:
        jobs.close(wait=True)


def test_health_request_cannot_block_remote_lease_expiry():
    import threading

    from klaude_core.ssh_serving_program import HealthCheck

    stalled = threading.Event()
    check = HealthCheck(lambda: stalled.wait(10))
    start_time = time.monotonic()
    try:
        assert not check.poll()
        first = check.thread
        for _ in range(10):
            assert not check.poll() and check.thread is first
        assert time.monotonic() - start_time < 0.5
    finally:
        stalled.set()


def test_lost_ssh_channel_reports_unconfirmed_cleanup_and_disables_endpoint(remote_lab):
    cfg, _, _, _, _ = remote_lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(remote_lab, jobs)
        ready = wait_for(events, "ready")
        children = Path(
            f"/proc/{ready['helper_pid']}/task/{ready['helper_pid']}/children"
        ).read_text()
        ssh = [
            int(pid)
            for pid in children.split()
            if Path(f"/proc/{pid}/comm").read_text().strip() == "ssh"
        ]
        assert len(ssh) == 1
        os.kill(ssh[0], signal.SIGKILL)
        wait_for(events, "failed")
        jobs.close(wait=True)
        saved = records(cfg.data_dir)[accepted["id"]]
        assert saved["remote_cleanup"] == "unconfirmed"
        assert gone(ready["remote_pid"])
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
    finally:
        jobs.close(wait=True)


def test_actual_cli_remote_review_uses_saved_configuration_and_cancel_does_not_launch(remote_lab):
    cfg, spec, _, _, _ = remote_lab
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from klaude_cli.main import app; app()",
            "model-manager",
            "serve",
            spec.model,
            "--executable",
            spec.executable,
            "--ssh-server",
            spec.ssh_server,
            "--port",
            str(spec.port),
            "--local-port",
            str(spec.local_port),
        ],
        input="n\n",
        env={
            **os.environ,
            "KLAUDE_CONFIG_DIR": str(cfg.config_dir),
            "KLAUDE_DATA_DIR": str(cfg.data_dir),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "remote loopback port" in result.stdout
    assert not records(cfg.data_dir) and not connection_registry(cfg).path.exists()


def test_remote_review_scrolls_all_details_without_changing_safe_back_focus(remote_lab):
    from types import SimpleNamespace

    from klaude_cli.serving_panel import ServingPanel
    from klaude_cli.settings_panel import PanelState, render_body

    _, spec, _, _, _ = remote_lab
    panel = ServingPanel(SimpleNamespace(host=SimpleNamespace()))
    panel.spec = spec
    panel.remote_name = "Remote QA"
    panel.view = "review"
    for width in (40, 120):
        state = PanelState(panel.page(), "back")
        body = render_body(state, width)
        assert state.picker.selected_id == "back"
        assert state.scroll_row(-10_000, body) and state.focus_line(body) == 0
        assert state.picker.selected_id == "back"
        assert state.scroll_row(10_000, body)
        assert state.focus_line(body) == len(body.lines) - 1


def test_stopped_remote_server_can_immediately_review_and_restart_same_ports(remote_lab):
    cfg, _, request, evidence, _ = remote_lab
    events = queue.Queue()
    for _ in range(2):
        jobs = ServingJobs(lambda *event: events.put(event))
        try:
            checked = inspect({**request, "evidence": evidence})
            assert "error" not in checked, checked
            accepted = start(remote_lab, jobs, evidence=checked["evidence"])
            ready = wait_for(events, "ready")
            jobs.stop(accepted["id"])
            jobs.close(wait=True)
            assert records(cfg.data_dir)[accepted["id"]]["remote_cleanup"] == "confirmed"
            assert gone(ready["remote_pid"])
        finally:
            jobs.close(wait=True)
