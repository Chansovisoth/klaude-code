"""vLLM profile boundaries with real SSH and an explicitly synthetic CUDA environment."""

import json
import os
import queue
import shutil
import subprocess
import sys
import venv
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.serving_jobs import ServingJobs
from klaude_cli.serving_panel import ServingPanel
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.managed_serving import records
from klaude_core.model_connections import connection_registry
from klaude_core.ssh_serving import decoded, inspect, preflight_timeout

from .test_managed_serving import wait_for
from .test_model_recipes import package
from .test_ssh_serving import gone, start
from .test_ssh_serving import remote_lab as remote_lab


@pytest.fixture
def vllm_lab(remote_lab, tmp_path):
    if not shutil.which("uv"):
        pytest.skip("Installed uv is required for offline fixtures")
    cfg, old, request, _, server = remote_lab
    environment = tmp_path / "engine-env"
    venv.EnvBuilder(with_pip=False).create(environment)
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps({"available": True, "capability": [7, 5]}))
    package(
        wheels,
        "torch",
        f"""import json,os
class Version: cuda = '12.9'
version = Version()
class Cuda:
 @staticmethod
 def is_available():return json.load(open({str(runtime)!r}))['available']
 @staticmethod
 def device_count():return len(os.environ['CUDA_VISIBLE_DEVICES'].split(','))
 @staticmethod
 def get_device_capability(i):return json.load(open({str(runtime)!r}))['capability']
cuda = Cuda()
""",
    )
    launch = environment / "launch.json"
    child = environment / "child.pid"
    script = (
        Path(old.executable)
        .read_text()
        .split("\n", 1)[1]
        .replace(
            "'--tensor-parallel-size --load-format'",
            "'--tensor-parallel-size --load-format --dtype '\n"
            "       '--enforce-eager --distributed-executor-backend'",
        )
    )
    script = script.replace(
        "args=sys.argv",
        f"""import os
args=sys.argv
if '--qa-child' not in args:
 open({str(launch)!r},'w').write(json.dumps({{'args':args,'env':dict(os.environ)}}))
 process=subprocess.Popen([sys.executable,'-c',{script!r},'--qa-child',*args[1:]])
 open({str(child)!r},'w').write(str(process.pid))
 process.wait();sys.exit(process.returncode)
""",
    )
    package(
        wheels,
        "vllm",
        f'def main():\n exec({script!r},{{"__name__":"__main__"}})\n',
        dependencies=["torch==0.0.1"],
        entry="vllm:main",
    )
    result = subprocess.run(
        [
            shutil.which("uv"),
            "pip",
            "install",
            "--python",
            str(environment / "bin/python"),
            "--offline",
            "--no-index",
            *map(str, wheels.glob("*.whl")),
        ],
        env={**os.environ, "UV_CACHE_DIR": str(tmp_path / "uv-cache")},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    inventory = environment / "devices.json"
    inventory.write_text(json.dumps(["GPU-00000001", "GPU-00000002"]))
    tool = environment / "bin/nvidia-smi"
    tool.write_text(
        f'#!{sys.executable}\nimport json\nprint("\\n".join(json.load(open({str(inventory)!r}))))\n'
    )
    tool.chmod(0o700)
    model = Path(old.model).with_name("safetensors-model")
    model.mkdir()
    (model / "config.json").write_text(
        json.dumps({"model_type": "llama", "torch_dtype": "float16"})
    )
    (model / "model.safetensors").write_bytes(b"QA fixture; not inference weights")
    (model / "tokenizer.json").write_text("{}")
    spec = replace(
        old,
        engine="vllm",
        executable=str(environment / "bin/vllm"),
        model=str(model),
        gpu="1,0",
        memory=0.35,
        dtype="half",
        enforce_eager=True,
    )
    request = {**request, "spec": asdict(spec)}
    checked = inspect(request)
    assert "error" not in checked, checked
    yield cfg, spec, request, checked["evidence"], server


def test_vllm_ssh_child_listener_and_owned_cleanup_preserve_choices(vllm_lab):
    cfg, spec, _, checked, _ = vllm_lab
    assert checked["engine"] == "vllm"
    assert checked["selected_devices"] == ["GPU-00000002", "GPU-00000001"]
    assert checked["runtime"]["vllm"] == "0.0.1"
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(vllm_lab, jobs)
        ready = wait_for(events, "ready")
        with httpx.Client(trust_env=False, timeout=2) as client:
            assert (
                client.get(ready["endpoint"]["base_url"] + "/models").json()["data"][0]["id"]
                == ready["model"]
            )
        folder = Path(spec.executable).parent.parent
        launch = json.loads((folder / "launch.json").read_text())
        assert launch["args"][1:3] == ["serve", spec.model]
        for flag, value in [
            ("--host", "127.0.0.1"),
            ("--dtype", "half"),
            ("--gpu-memory-utilization", "0.35"),
            ("--tensor-parallel-size", "2"),
            ("--load-format", "safetensors"),
            ("--distributed-executor-backend", "mp"),
            ("--max-num-seqs", "1"),
        ]:
            assert launch["args"][launch["args"].index(flag) + 1] == value
        assert "--enforce-eager" in launch["args"] and "--trust-remote-code" not in launch["args"]
        env = launch["env"]
        assert env["CUDA_VISIBLE_DEVICES"] == "GPU-00000002,GPU-00000001"
        assert env["HF_HUB_OFFLINE"] == env["VLLM_NO_USAGE_STATS"] == "1"
        assert not any(k.endswith("API_KEY") for k in env)
        child = int((folder / "child.pid").read_text())
        assert child != ready["remote_pid"]
        assert not (cfg.data_dir / "chat-preferences.json").exists()
        jobs.stop(accepted["id"])
        jobs.close(wait=True)
        assert gone(ready["remote_pid"]) and gone(child)
        assert records(cfg.data_dir)[accepted["id"]]["remote_cleanup"] == "confirmed"
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("filename", ["config.json", "model.safetensors", "tokenizer.json"])
def test_bundle_change_after_review_never_launches(vllm_lab, filename):
    cfg, spec, _, _, _ = vllm_lab
    file = Path(spec.model) / filename
    file.write_bytes(file.read_bytes() + b" ")
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(vllm_lab, jobs)
        failed = wait_for(events, "failed")
        assert "changed" in failed["message"]
        jobs.close(wait=True)
        assert records(cfg.data_dir)[accepted["id"]]["remote_cleanup"] == "not_started"
        assert not (Path(spec.executable).parent.parent / "launch.json").exists()
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize(
    "mutation", ["symlink", "missing_shard", "bad_index", "missing_weights", "bad_config"]
)
def test_incomplete_or_unsafe_bundle_rejected(vllm_lab, mutation):
    _, spec, request, _, _ = vllm_lab
    model = Path(spec.model)
    if mutation == "symlink":
        (model / "external.json").symlink_to("/etc/passwd")
    elif mutation == "missing_shard":
        (model / "model.safetensors.index.json").write_text(
            '{"weight_map":{"a":"missing.safetensors"}}'
        )
    elif mutation == "bad_index":
        (model / "model.safetensors.index.json").write_text("[]")
    elif mutation == "missing_weights":
        (model / "model.safetensors").unlink()
    else:
        (model / "config.json").write_text("[]")
    assert "error" in inspect(request)
    assert not (Path(spec.executable).parent.parent / "launch.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("gpu", "9"),
        ("gpu", "0,00"),
        ("gpu_layers", 1),
        ("memory", float("nan")),
        ("memory", True),
        ("memory", 0.99),
        ("dtype", "half;bad"),
        ("enforce_eager", "yes"),
    ],
)
def test_invalid_resource_fields_never_launch(vllm_lab, field, value):
    _, spec, request, _, _ = vllm_lab
    assert "error" in inspect({**request, "spec": asdict(replace(spec, **{field: value}))})
    assert not (Path(spec.executable).parent.parent / "launch.json").exists()


def test_vllm_cuda_environment_failure_has_no_cpu_fallback(vllm_lab):
    _, spec, request, checked, _ = vllm_lab
    runtime = Path(spec.executable).parent.parent.parent / "runtime.json"
    runtime.write_text('{"available":false,"capability":[7,5]}')
    assert "no CPU fallback" in inspect({**request, "evidence": checked})["error"]
    assert not (Path(spec.executable).parent.parent / "launch.json").exists()


def test_changed_gpu_inventory_and_torch_installation_invalidate_review(vllm_lab):
    _, spec, request, checked, _ = vllm_lab
    folder = Path(spec.executable).parent.parent
    devices = folder / "devices.json"
    devices.write_text('["GPU-00000002","GPU-00000001"]')
    assert "inventory changed" in inspect({**request, "evidence": checked})["error"]
    devices.write_text('["GPU-00000001","GPU-00000002"]')
    torch = next(folder.glob("lib/python*/site-packages/torch/__init__.py"))
    torch.write_text(torch.read_text() + "\n# changed installation\n")
    assert "environment changed" in inspect({**request, "evidence": checked})["error"]


def test_bfloat16_on_turing_requires_explicit_precision(vllm_lab):
    _, spec, request, _, _ = vllm_lab
    assert (
        "half precision"
        in inspect({**request, "spec": asdict(replace(spec, dtype="bfloat16"))})["error"]
    )
    (Path(spec.model) / "config.json").write_text('{"torch_dtype":"bfloat16"}')
    assert (
        "choose half precision"
        in inspect({**request, "spec": asdict(replace(spec, dtype="auto"))})["error"]
    )
    assert "error" not in inspect(request)


def test_corrupt_runtime_evidence_is_rejected(vllm_lab):
    _, _, _, checked, _ = vllm_lab
    for bad in (
        {},
        {**checked["runtime"], "capabilities": [[7, 0]]},
        {**checked["runtime"], "cuda": "bad\nvalue"},
    ):
        with pytest.raises(ValueError):
            decoded(
                {"version": 1, "connected": True, "evidence": {**checked, "runtime": bad}},
                "prepare",
            )


def test_remote_engine_switch_preserves_scope_and_review_is_safe_and_wrapped():
    panel = ServingPanel(SimpleNamespace(host=SimpleNamespace()))

    def show(view=None, *args, **kwargs):
        if view:
            panel.view = view

    panel.show = show
    panel.new_remote_draft("remote", "revision", "Host")
    assert "Engine" in [r.label for r in panel.page().rows]
    panel.action(PanelAction("serving-field:engine"))
    assert panel.spec.engine == "vllm" and panel.spec.ssh_server == "remote"
    assert panel.ssh_revision == "revision" and panel.spec.enforce_eager
    panel.spec = replace(panel.spec, model="/models/model", gpu="0", dtype="half")
    panel.evidence = {
        "devices": ["GPU-00000001"],
        "selected_devices": ["GPU-00000001"],
        "runtime": {"vllm": "0.0.1", "cuda": "12.9"},
    }
    panel.view = "review"
    for width in (40, 70, 120):
        state = PanelState(panel.page(), "back")
        body = render_body(state, width)
        assert state.picker.selected_id == "back"
        assert any("GPU-00000001" in text for line in body.lines for _, text in line)
        assert next(r for r in state.page.rows if r.id == "eager").value == "ON"
    assert preflight_timeout(panel.spec) == 60
    assert preflight_timeout(replace(panel.spec, engine="llama_cpp")) == 20
    assert preflight_timeout(replace(panel.spec, ssh_server="")) == 40


def test_cli_review_default_no_shows_vllm_resources_without_launch(vllm_lab):
    cfg, spec, _, _, _ = vllm_lab
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from klaude_cli.main import app;app()",
            "model-manager",
            "serve",
            spec.model,
            "--engine",
            "vllm",
            "--executable",
            spec.executable,
            "--ssh-server",
            spec.ssh_server,
            "--port",
            str(spec.port),
            "--local-port",
            str(spec.local_port),
            "--gpu",
            "1,0",
            "--memory",
            "0.35",
            "--dtype",
            "half",
            "--enforce-eager",
        ],
        input="n\n",
        env={
            **os.environ,
            "KLAUDE_CONFIG_DIR": str(cfg.config_dir),
            "KLAUDE_DATA_DIR": str(cfg.data_dir),
        },
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GPU-00000002, GPU-00000001" in result.stdout and "precision: half" in result.stdout
    assert records(cfg.data_dir) == {}


def test_cancel_loading_reaps_vllm_frontend_and_children_without_publication(vllm_lab):
    import time

    cfg, spec, request, _, _ = vllm_lab
    slow = Path(spec.model).with_name("slow.gguf")
    shutil.copytree(spec.model, slow)
    spec = replace(spec, model=str(slow))
    checked = inspect({**request, "spec": asdict(spec)})["evidence"]
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(vllm_lab, jobs, spec=spec, evidence=checked)
        wait_for(events, "starting")
        wait_for(events, "starting")
        marker = Path(spec.executable).parent.parent / "child.pid"
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        child = int(marker.read_text())
        jobs.stop(accepted["id"])
        jobs.close(wait=True)
        saved = records(cfg.data_dir)[accepted["id"]]
        assert saved["remote_cleanup"] == "confirmed"
        assert gone(saved["remote_pid"]) and gone(child)
        assert not connection_registry(cfg).path.exists()
    finally:
        jobs.close(wait=True)


def test_helper_death_expires_vllm_lease_and_reaps_frontend_child(vllm_lab):
    import signal

    cfg, spec, _, _, _ = vllm_lab
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(vllm_lab, jobs)
        ready = wait_for(events, "ready")
        child = int((Path(spec.executable).parent.parent / "child.pid").read_text())
        os.kill(ready["helper_pid"], signal.SIGKILL)
        wait_for(events, "failed")
        jobs.close(wait=True)
        assert gone(ready["remote_pid"]) and gone(child)
        assert records(cfg.data_dir)[accepted["id"]]["state"] == "interrupted"
        assert not connection_registry(cfg).load()[ready["endpoint"]["id"]].enabled
    finally:
        jobs.close(wait=True)


def test_review_metadata_alignment_and_narrow_labels_are_complete():
    from klaude_cli.settings_panel import PanelPage, PanelRow, RowKind

    rows = (
        PanelRow("port", RowKind.INFO, "Remote loopback port", "18080"),
        PanelRow("precision", RowKind.INFO, "Precision", "half"),
        PanelRow("model", RowKind.INFO, "Remote model", "/weights/model"),
    )
    page = PanelPage("review", ("Review",), rows, align_info_values=True, scrollable_body=True)
    wide = render_body(PanelState(page), 120)
    rendered = ["".join(text for _, text in line) for line in wide.lines]
    assert (
        rendered[0].index("18080")
        == rendered[1].index("half")
        == rendered[2].index("/weights/model")
    )
    narrow = render_body(PanelState(page), 40)
    text = "\n".join("".join(text for _, text in line) for line in narrow.lines)
    assert "Remote loopback port" in text and "18080" in text and "Precision" in text
    assert all(sum(len(text) for _, text in line) <= 40 for line in narrow.lines)


def test_cuda_import_warning_does_not_hide_valid_runtime_record(vllm_lab):
    _, spec, request, _, _ = vllm_lab
    torch = next(
        Path(spec.executable).parent.parent.glob("lib/python*/site-packages/torch/__init__.py")
    )
    torch.write_text(
        "print('QA torch import warning: not a capability failure')\n" + torch.read_text()
    )
    result = inspect(request)
    assert "error" not in result, result
    assert result["evidence"]["runtime"]["cuda"] == "12.9"


@pytest.mark.parametrize("remote", [True, False])
def test_cold_vllm_help_can_exceed_old_deadline_without_model_loading(vllm_lab, remote):
    import time

    _, spec, request, _, _ = vllm_lab
    executable = Path(spec.executable)
    text = executable.read_text().splitlines(keepends=True)
    text.insert(1, "import sys,time\nif '--help=all' in sys.argv: time.sleep(16)\n")
    executable.write_text("".join(text))
    started = time.monotonic()
    if remote:
        result = inspect(request)
        assert "error" not in result, result
        assert result["evidence"]["runtime"]["vllm"] == "0.0.1"
    else:
        from klaude_core.managed_serving import probe_engine

        assert probe_engine("vllm", str(executable))["engine"] == "vllm"
    assert time.monotonic() - started >= 16
    assert not (executable.parent.parent / "launch.json").exists()
