"""Real engine fixtures and lease/process/registration failure boundaries."""

import json
import os
import queue
import re
import select
import signal
import socket
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
from klaude_core.managed_serving import (
    LaunchSpec,
    adoption_identity,
    inventory,
    prepare,
    probe_engine,
    process_identity,
    read_log,
    records,
)
from klaude_core.model_connections import connection_registry


def test_shared_serving_read_request_roundtrip_and_fixed_operations(tmp_path):
    from klaude_application.serving_read import ServingRead

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    request = ServingRead.for_client(cfg, "inventory").worker_request()
    assert ServingRead.from_worker(request).worker_request() == request
    with pytest.raises(ValueError, match="Invalid serving read"):
        ServingRead.from_worker({**request, "operation": "start"})
    with pytest.raises(ValueError, match="Invalid serving read"):
        ServingRead.from_worker({**request, "command": "arbitrary"})


def test_shared_serving_owner_reaps_failed_launch_without_terminal_ui(tmp_path, monkeypatch):
    from klaude_application import serving_jobs

    monkeypatch.setattr(serving_jobs.subprocess, "Popen", lambda *a, **kw: (
        _ for _ in ()
    ).throw(OSError("fixture launch failure")))
    events = queue.Queue()
    jobs = serving_jobs.ServingJobs(lambda kind, value: events.put((kind, value)))
    request = {"id": uuid.uuid4().hex, "config_dir": str(tmp_path / "config"),
               "data_dir": str(tmp_path / "data"), "spec": {}, "evidence": {}}
    jobs.start(request)
    try:
        seen = []
        while True:
            event = events.get(timeout=2)
            seen.append(event)
            if event[0] == "serving_stopped":
                break
        assert seen[0][0] == "serving_event" and seen[0][1][1]["state"] == "failed"
        assert seen[-1][1] == (request["id"], True)
    finally:
        jobs.close(wait=True)
    assert not jobs.owns(request["id"])


@pytest.fixture
def lab(tmp_path):
    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    cfg.config_dir.mkdir()
    cfg.data_dir.mkdir()
    (cfg.config_dir / "config.toml").write_text("[ollama]\nthink=false\n")
    engine = tmp_path / "llama-server"
    engine.write_text(f"""#!{sys.executable}
import json,sys,time
import subprocess
from http.server import HTTPServer,BaseHTTPRequestHandler
if any(a.startswith('--help') for a in sys.argv):
 print('--host --port --alias --model --ctx-size --threads --n-gpu-layers --parallel --device '
       '--served-model-name --max-model-len --gpu-memory-utilization --max-num-seqs '
       '--tensor-parallel-size --load-format');sys.exit(0)
args=sys.argv
flag='--alias' if '--alias' in args else '--served-model-name'
model=args[args.index(flag)+1]
port=int(args[args.index('--port')+1])
print('token=private-engine-token',flush=True)
if any(a.endswith('failed.gguf') for a in args):sys.exit(9)
if any(a.endswith('slow.gguf') for a in args):time.sleep(30)
if any(a.endswith('workers.gguf') for a in args):
 child=subprocess.Popen([sys.executable,'-c',
  'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
 print('descendant_pid='+str(child.pid),flush=True)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  body=json.dumps({{'status':'ok'}} if self.path=='/health' else
   {{'data':[{{'id':model}}]}}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
  self.wfile.write(body)
HTTPServer(('127.0.0.1',port),Handler).serve_forever()
""")
    engine.chmod(0o700)
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUFfixture")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    spec = LaunchSpec("llama_cpp", str(engine), str(model), port=port)
    return cfg, spec


def launch(cfg, spec, jobs, evidence=None):
    checked = evidence or prepare(spec, probe_engine(spec.engine, spec.executable))
    request = {
        "id": uuid.uuid4().hex,
        "owner": "QA",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "spec": asdict(spec),
        "evidence": checked,
    }
    jobs.start(request)
    return request


def wait_for(events, state, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        kind, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
        if kind == "serving_event" and payload[1]["state"] == state:
            return payload[1]
    pytest.fail("Missing serving state: " + state)


def test_real_server_health_registration_and_owned_stop_preserve_defaults(lab):
    cfg, spec = lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        request = launch(cfg, spec, jobs)
        ready = wait_for(events, "ready")
        assert ready["model"].startswith("klaude-")
        assert connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        assert not (cfg.data_dir / "chat-preferences.json").exists()
        assert "private-engine-token" not in read_log(cfg.data_dir, request["id"])
        assert "[redacted]" in read_log(cfg.data_dir, request["id"])
        jobs.stop(request["id"])
        jobs.close(wait=True)
        assert not jobs.owns(request["id"])
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        with pytest.raises(ProcessLookupError):
            os.kill(ready["pid"], 0)
    finally:
        jobs.close(wait=True)


def test_cancel_startup_does_not_register_endpoint_and_reaps(lab):
    cfg, spec = lab
    model = Path(spec.model).with_name("slow.gguf")
    model.write_bytes(b"GGUFfixture")
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        request = launch(cfg, replace(spec, model=str(model)), jobs)
        wait_for(events, "starting")
        jobs.stop(request["id"])
        jobs.close(wait=True)
        assert not connection_registry(cfg).path.exists()
        assert records(cfg.data_dir)[request["id"]]["state"] == "stopped"
        assert not jobs.owns(request["id"])
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("failure", ("port", "model", "executable", "crash"))
def test_failed_launch_never_registers_or_claims_success(lab, failure):
    cfg, spec = lab
    evidence = prepare(spec, probe_engine(spec.engine, spec.executable))
    sock = None
    if failure == "port":
        sock = socket.socket()
        sock.bind(("127.0.0.1", spec.port))
        sock.listen()
    elif failure == "model":
        Path(spec.model).write_bytes(b"GGUFchanged")
    elif failure == "executable":
        Path(spec.executable).write_text("#!/bin/false\n")
    else:
        model = Path(spec.model).with_name("failed.gguf")
        model.write_bytes(b"GGUFfixture")
        spec = replace(spec, model=str(model))
        evidence = prepare(spec, evidence)
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        launch(cfg, spec, jobs, evidence)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert not connection_registry(cfg).path.exists()
    finally:
        jobs.close(wait=True)
        if sock:
            sock.close()


def test_unexpected_helper_death_reaps_server_and_reconciles_endpoint(lab):
    cfg, spec = lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        launch(cfg, spec, jobs)
        ready = wait_for(events, "ready")
        os.kill(ready["helper_pid"], signal.SIGKILL)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        assert inventory(cfg.data_dir)[0]["state"] == "interrupted"
        # A killed engine can briefly be a zombie under this container's init.
        with pytest.raises(httpx.HTTPError):
            httpx.get(ready["endpoint"]["base_url"] + "/models", timeout=1, trust_env=False)
    finally:
        jobs.close(wait=True)


def test_abrupt_client_death_stops_engine_descendants_and_disables_endpoint(lab):
    cfg, spec = lab
    model = Path(spec.model).with_name("workers.gguf")
    model.write_bytes(b"GGUFfixture")
    spec = replace(spec, model=str(model))
    checked = prepare(spec, probe_engine(spec.engine, spec.executable))
    request = {
        "id": uuid.uuid4().hex,
        "owner": "QA",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "spec": asdict(spec),
        "evidence": checked,
    }
    script = """import json,sys,time
from klaude_cli.serving_jobs import ServingJobs
def emit(kind,payload):
 if kind=='serving_event' and payload[1]['state']=='ready':
  print(json.dumps(payload[1]),flush=True)
jobs=ServingJobs(emit)
jobs.start(json.loads(sys.stdin.readline()))
time.sleep(60)
"""
    owner = subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    assert owner.stdin is not None and owner.stdout is not None
    ready = None
    try:
        owner.stdin.write(json.dumps(request) + "\n")
        owner.stdin.flush()
        assert select.select([owner.stdout], [], [], 12)[0], "Client never registered server"
        ready = json.loads(owner.stdout.readline())
        log = read_log(cfg.data_dir, request["id"])
        match = re.search(r"descendant_pid=(\d+)", log)
        assert match is not None, "Engine did not launch its test worker"
        child = int(match.group(1))
        owner.kill()
        owner.wait(timeout=3)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if (
                not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
                and records(cfg.data_dir)[request["id"]]["state"] == "stopped"
            ):
                break
            time.sleep(0.1)
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        assert records(cfg.data_dir)[request["id"]]["state"] == "stopped"
        deadline = time.monotonic() + 3
        for pid in (ready["pid"], child):
            while time.monotonic() < deadline:
                try:
                    process_identity(pid)
                except (OSError, ValueError):
                    break
                time.sleep(0.1)
            with pytest.raises((OSError, ValueError)):
                process_identity(pid)
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=3)
        owner.stdin.close()
        owner.stdout.close()
        if ready:
            try:
                os.killpg(ready["helper_pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_stop_preserves_a_user_edited_endpoint(lab):
    from klaude_core.settings_store import atomic_write_private, settings_lock

    cfg, spec = lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        launch(cfg, spec, jobs)
        ready = wait_for(events, "ready")
        registry = connection_registry(cfg)
        with settings_lock(registry.path):
            payload = json.loads(registry.path.read_text())
            payload["connections"][ready["endpoint"]["id"]]["name"] = "User replacement"
            atomic_write_private(registry.path, json.dumps(payload))
        jobs.close(wait=True)
        current = registry.load()[ready["endpoint"]["id"]]
        assert current.enabled and current.name == "User replacement"
    finally:
        jobs.close(wait=True)


def test_explicit_adoption_matches_pid_engine_session_and_stops_only_that_server(lab):
    cfg, spec = lab
    process = subprocess.Popen(
        [spec.executable, "--port", str(spec.port), "--alias", "existing"],
        stdout=subprocess.DEVNULL,
        start_new_session=True,
    )
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        spec = replace(spec, adopt_pid=process.pid, model_id="existing")
        launch(cfg, spec, jobs)
        ready = wait_for(events, "ready")
        assert ready["adopted"] and ready["pid"] == process.pid
        jobs.close(wait=True)
        process.wait(timeout=3)
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
        shared_session = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=subprocess.DEVNULL,
        )
        try:
            with pytest.raises(ValueError):
                adoption_identity(shared_session.pid, Path(sys.executable))
        finally:
            shared_session.terminate()
            shared_session.wait(timeout=3)
    finally:
        jobs.close(wait=True)
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=3)


def test_failed_adoption_does_not_take_control_or_stop_existing_process(lab):
    cfg, spec = lab
    process = subprocess.Popen(
        [spec.executable, "--port", str(spec.port), "--alias", "existing"],
        stdout=subprocess.DEVNULL,
        start_new_session=True,
    )
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        launch(cfg, replace(spec, adopt_pid=process.pid, model_id="wrong-model"), jobs)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert process.poll() is None and not connection_registry(cfg).path.exists()
    finally:
        jobs.close(wait=True)
        process.terminate()
        process.wait(timeout=3)


def test_vllm_local_safetensors_adapter_registers_without_downloads(lab):
    cfg, spec = lab
    folder = Path(spec.model).parent / "weights"
    folder.mkdir()
    (folder / "config.json").write_text("{}")
    (folder / "model.safetensors").write_bytes(b"fixture")
    spec = replace(spec, engine="vllm", model=str(folder), gpu="0,1")
    checked = prepare(spec, probe_engine(spec.engine, spec.executable))
    argv, environment = spec.validate(checked)
    assert argv[1] == "serve" and "safetensors" in argv and "2" in argv
    assert environment["HF_HUB_OFFLINE"] == "1" and environment["CUDA_VISIBLE_DEVICES"] == "0,1"
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        launch(cfg, spec, jobs, checked)
        ready = wait_for(events, "ready")
        assert ready["spec"]["engine"] == "vllm"
        jobs.close(wait=True)
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
    finally:
        jobs.close(wait=True)


def test_missing_gpu_evidence_never_silently_falls_back(lab):
    _, spec = lab
    checked = probe_engine(spec.engine, spec.executable)
    with pytest.raises(ValueError, match="GPU devices unavailable"):
        replace(spec, gpu_layers=10).validate({**checked, "devices": []})


@pytest.mark.parametrize(
    "fields",
    ({"port": 0}, {"context": 100}, {"threads": True}, {"gpu": "0,0"}, {"memory": float("nan")}),
)
def test_invalid_resource_fields_fail_without_execution(lab, fields):
    _, spec = lab
    with pytest.raises(ValueError):
        replace(spec, **fields).validate(probe_engine(spec.engine, spec.executable))


def test_client_close_waits_for_slow_helper_cleanup_acknowledgement(lab, tmp_path, monkeypatch):
    from klaude_application import serving_jobs

    cfg, spec = lab
    helper = tmp_path / "slow-cleanup-helper.py"
    helper.write_text("""import json,sys,time
from pathlib import Path
from klaude_core.managed_serving import publish
request=json.loads(sys.stdin.buffer.readline())
identity=request['id'];root=Path(request['data_dir'])
value={'id':identity,'spec':request['spec'],'state':'ready','remote_cleanup':'unconfirmed'}
publish(root,identity,value)
print(json.dumps({'id':identity,'state':'ready'}),flush=True)
sys.stdin.buffer.read(1)
time.sleep(5)
value.update(state='stopped',remote_cleanup='confirmed')
publish(root,identity,value)
print(json.dumps({'id':identity,'state':'stopped','message':'Cleanup acknowledged'}),flush=True)
""")
    original = subprocess.Popen

    def launch_helper(args, **kwargs):
        assert args[-2:] == ["-m", "klaude_core.managed_serving"]
        return original([sys.executable, str(helper)], **kwargs)

    checked = prepare(spec, probe_engine(spec.engine, spec.executable))
    monkeypatch.setattr(serving_jobs.subprocess, "Popen", launch_helper)
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        request = launch(cfg, spec, jobs, evidence=checked)
        wait_for(events, "ready")
        jobs.close(wait=True)
        assert not jobs.owns(request["id"])
        saved = records(cfg.data_dir)[request["id"]]
        assert saved["state"] == "stopped" and saved["remote_cleanup"] == "confirmed"
    finally:
        jobs.close(wait=True)
