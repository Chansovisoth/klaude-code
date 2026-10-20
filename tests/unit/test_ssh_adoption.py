"""Reviewed remote takeover through real SSH; inspection cannot stop a server."""

import json
import os
import queue
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.serving_jobs import ServingJobs
from klaude_cli.serving_panel import ServingPanel
from klaude_cli.settings_panel import PanelState, render_body
from klaude_core import ssh_serving_program as remote
from klaude_core.managed_serving import records
from klaude_core.model_connections import connection_registry
from klaude_core.ssh_servers import arguments, change
from klaude_core.ssh_serving import decoded, inspect, program

from .test_managed_serving import wait_for
from .test_ssh_serving import gone, port, start
from .test_ssh_serving import remote_lab as remote_lab


@pytest.fixture
def adoption_lab(remote_lab, request):
    cfg, spec, review_request, _, server = remote_lab
    log = Path(spec.model).parent / "original-engine.log"
    with log.open("wb") as stream:
        process = subprocess.Popen(
            [spec.executable, "--port", str(spec.port), "--alias", "existing/model"]
            + (["--model", "workers.gguf"] if getattr(request, "param", False) else []),
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        deadline = time.monotonic() + 5
        while not remote.healthy(spec.port, "existing/model"):
            assert process.poll() is None
            if time.monotonic() > deadline:
                pytest.fail("Controlled external server did not start")
            time.sleep(0.05)
        spec = replace(spec, model="", adopt_pid=process.pid, model_id="existing/model")
        review_request = {**review_request, "spec": asdict(spec)}
        result = inspect(review_request)
        assert "error" not in result, result
        yield (cfg, spec, review_request, result["evidence"], server), process, log
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def test_remote_adoption_retains_identity_logs_and_defaults_and_stops_owned_group(
    adoption_lab, monkeypatch
):
    lab, process, log = adoption_lab
    cfg, spec, _, _, server = lab
    originals = {
        p: Path(p).read_bytes()
        for p in (server.identity_file, server.known_hosts, spec.executable, str(log))
    }
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    local_signals = []
    monkeypatch.setattr("klaude_application.serving_jobs.stop_adopted", local_signals.append)
    try:
        request = start(lab, jobs)
        ready = wait_for(events, "ready")
        assert ready["adopted"] and ready["remote_pid"] == process.pid
        assert ready["model"] == "existing/model"
        with httpx.Client(trust_env=False, timeout=2) as client:
            assert (
                client.get(ready["endpoint"]["base_url"] + "/models").json()["data"][0]["id"]
                == spec.model_id
            )
        jobs.close(wait=True)
        assert not jobs.owns(request["id"])
        assert not local_signals
        assert gone(process.pid)
        assert records(cfg.data_dir)[request["id"]]["remote_cleanup"] == "confirmed"
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        assert not (cfg.data_dir / "chat-preferences.json").exists()
        assert not (cfg.data_dir / "model-serving" / (request["id"] + ".log")).exists()
        for path, content in originals.items():
            assert Path(path).read_bytes() == content
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("failure", ["model_id", "executable", "nonisolated", "listener", "pid"])
def test_failed_remote_inspection_leaves_external_process_alive(adoption_lab, failure):
    lab, process, _ = adoption_lab
    _, spec, request, _, _ = lab
    if failure == "model_id":
        spec = replace(spec, model_id="wrong")
    elif failure == "executable":
        other = Path(spec.executable).with_name("other-engine")
        other.write_bytes(Path(spec.executable).read_bytes())
        other.chmod(0o700)
        spec = replace(spec, executable=str(other))
    elif failure == "nonisolated":
        spec = replace(spec, adopt_pid=os.getpid())
    elif failure == "listener":
        spec = replace(spec, port=spec.local_port)
    else:
        spec = replace(spec, adopt_pid=1)
    assert "error" in inspect({**request, "spec": asdict(spec)})
    assert process.poll() is None


@pytest.mark.parametrize("failure", ["start", "definition", "registry"])
def test_failed_remote_takeover_does_not_stop_the_original(adoption_lab, failure):
    lab, process, _ = adoption_lab
    cfg, _, request, evidence, server = lab
    evidence = json.loads(json.dumps(evidence))
    if failure == "start":
        evidence["adopt_identity"]["start"] = "0"
    elif failure == "definition":
        change(
            cfg.config_dir,
            "edit",
            definition=asdict(replace(server, name="Changed")),
            revision=request["server_revision"],
        )
    else:
        # A registry publication failure occurs after remote readiness, before ownership.
        registry = connection_registry(cfg)
        registry.path.mkdir(parents=True)
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(lab, jobs, evidence=evidence)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert process.poll() is None
        retained = records(cfg.data_dir).get(accepted["id"], {})
        assert not retained.get("adopted")
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("acknowledge", [False, True])
def test_remote_channel_eof_only_stops_after_takeover_acknowledgement(adoption_lab, acknowledge):
    lab, process, _ = adoption_lab
    _, spec, _, evidence, server = lab
    channel = subprocess.Popen(
        arguments(server, program=program()),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert channel.stdin and channel.stdout
        channel.stdin.write(
            json.dumps(
                {
                    "operation": "serve",
                    "spec": asdict(spec),
                    "models_dir": server.models_dir,
                    "evidence": evidence,
                    "id": uuid.uuid4().hex,
                }
            )
            + "\n"
        )
        channel.stdin.flush()
        assert json.loads(channel.stdout.readline())["state"] == "ready"
        if acknowledge:
            # Fragmented protocol writes must retain their exact meaning.
            channel.stdin.write("A")
            channel.stdin.flush()
            channel.stdin.write("\n")
            channel.stdin.flush()
            assert json.loads(channel.stdout.readline())["state"] == "owned"
        channel.stdin.close()
        terminal = json.loads(channel.stdout.readline())
        channel.wait(timeout=8)
        assert terminal["cleanup"] == ("confirmed" if acknowledge else "not_started")
        assert gone(process.pid, 2) if acknowledge else process.poll() is None
    finally:
        if channel.poll() is None:
            channel.kill()
        channel.wait(timeout=5)
        for pipe in (channel.stdout, channel.stderr):
            if pipe:
                pipe.close()


def test_second_remote_owner_is_rejected_without_harming_first_owner(adoption_lab):
    lab, process, _ = adoption_lab
    first_events, second_events = queue.Queue(), queue.Queue()
    first = ServingJobs(lambda *event: first_events.put(event))
    second = ServingJobs(lambda *event: second_events.put(event))
    try:
        start(lab, first)
        ready = wait_for(first_events, "ready")
        start(lab, second, spec=replace(lab[1], local_port=port()))
        failed = wait_for(second_events, "failed")
        assert "already has an adoption owner" in failed["message"]
        second.close(wait=True)
        assert process.poll() is None
        assert connection_registry(lab[0]).load()[ready["endpoint"]["id"]].enabled
        first.close(wait=True)
        assert gone(process.pid)
    finally:
        second.close(wait=True)
        first.close(wait=True)


def test_stale_identity_cannot_signal_a_live_server(adoption_lab):
    lab, process, _ = adoption_lab
    identity = dict(lab[3]["adopt_identity"], start="0")
    assert not remote.stop_adopted(identity)
    assert process.poll() is None


def test_remote_process_owned_by_another_account_is_rejected(adoption_lab, monkeypatch):
    _, process, _ = adoption_lab
    uid = os.getuid()
    monkeypatch.setattr(remote.os, "getuid", lambda: uid + 1)
    with pytest.raises(ValueError, match="owned by this account"):
        remote.process_identity(process.pid)
    assert process.poll() is None


@pytest.mark.parametrize("adoption_lab", [True], indirect=True)
def test_adopted_group_cleanup_reaps_descendant_after_leader_exits(adoption_lab):
    lab, process, log = adoption_lab
    child = int(log.read_text().split("descendant_pid=", 1)[1].splitlines()[0])
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(lab, jobs)
        wait_for(events, "ready")
        jobs.close(wait=True)
        assert gone(process.pid) and gone(child)
        assert records(lab[0].data_dir)[accepted["id"]]["remote_cleanup"] == "confirmed"
    finally:
        jobs.close(wait=True)


def test_killed_adoption_helper_expires_remote_owner_lease(adoption_lab):
    lab, process, _ = adoption_lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(lab, jobs)
        ready = wait_for(events, "ready")
        os.kill(ready["helper_pid"], signal.SIGKILL)
        assert gone(process.pid, 10)
        jobs.close(wait=True)
        assert not connection_registry(lab[0]).load()[ready["endpoint"]["id"]].enabled
        # A lost receipt cannot be retrospectively called confirmed cleanup.
        assert records(lab[0].data_dir)[accepted["id"]]["remote_cleanup"] == "unconfirmed"
    finally:
        jobs.close(wait=True)


def test_remote_adoption_review_has_private_fields_and_safe_wrapped_back_focus(adoption_lab):
    lab, _, _ = adoption_lab
    panel = ServingPanel(SimpleNamespace(host=SimpleNamespace()))
    panel.show = lambda view=None, *args, **kwargs: setattr(panel, "view", view or panel.view)
    panel.new_remote_draft("remote", "revision", "QA host", adopt=True)
    assert panel.adopting
    labels = [row.label for row in panel.page().rows]
    assert "Server PID" in labels and "Tunnel port" in labels
    assert "Context" not in labels and "GPU memory fraction" not in labels
    panel.spec, panel.evidence, panel.view = lab[1], lab[3], "review"
    for width in (40, 70, 120):
        state = PanelState(panel.page(), "back")
        body = render_body(state, width)
        assert state.picker.selected_id == "back"
        assert any("Retained unchanged" in text for line in body.lines for _, text in line)
        assert state.scroll_row(-10_000, body)
        assert state.scroll_row(10_000, body)
        assert state.focus_line(body) == len(body.lines) - 1


def test_actual_cli_remote_adoption_review_cancel_leaves_process_and_store_untouched(adoption_lab):
    lab, process, _ = adoption_lab
    cfg, spec, _, _, _ = lab
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from klaude_cli.main import app;app()",
            "model-manager",
            "adopt",
            str(process.pid),
            spec.model_id,
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
        text=True,
        capture_output=True,
        timeout=30,
        env={
            **os.environ,
            "KLAUDE_CONFIG_DIR": str(cfg.config_dir),
            "KLAUDE_DATA_DIR": str(cfg.data_dir),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "Adopt this existing server?" in result.stdout
        and "existing settings retained" in result.stdout
    )
    assert "context 8192" not in result.stdout and "CPU" not in result.stdout
    assert process.poll() is None and not records(cfg.data_dir)
    assert not connection_registry(cfg).path.exists()


def test_remote_identity_decoder_rejects_unbounded_or_foreign_identity(adoption_lab):
    evidence = adoption_lab[0][3]
    payload = {"version": 1, "connected": True, "evidence": evidence}
    assert decoded(payload, "prepare")["adopt_identity"] == evidence["adopt_identity"]
    for key, value in (("start", "0" * 30), ("group", 1), ("executable", "relative")):
        altered = {**evidence, "adopt_identity": {**evidence["adopt_identity"], key: value}}
        with pytest.raises(ValueError, match="identity"):
            decoded({**payload, "evidence": altered}, "prepare")
