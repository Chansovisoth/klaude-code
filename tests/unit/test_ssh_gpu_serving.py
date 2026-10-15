"""Observed-device GPU profiles through real SSH, without assuming fixture GPU inference."""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from klaude_cli.serving_jobs import ServingJobs
from klaude_core.managed_serving import records
from klaude_core.ssh_serving import decoded, inspect
from klaude_core.ssh_serving_program import selection

from .test_managed_serving import wait_for
from .test_ssh_serving import gone, start
from .test_ssh_serving import remote_lab as remote_lab


@pytest.fixture
def gpu_lab(remote_lab):
    cfg, spec, request, _, server = remote_lab
    engine = Path(spec.executable)
    inventory = engine.with_name("devices.json")
    inventory.write_text(json.dumps(["CUDA0", "CUDA1"]))
    # Devices come from the executable's API, not a client-host GPU probe.
    text = engine.read_text().replace(
        "--n-gpu-layers --parallel --device ", "--n-gpu-layers --parallel --device --list-devices "
    )
    text = text.replace(
        "args=sys.argv",
        f"""if '--list-devices' in sys.argv:
 print('Available devices:')
 for name in json.loads(open({str(inventory)!r}).read()):print(name+': QA device')
 sys.exit(0)
open({str(engine.with_name("launch.json"))!r},'w').write(json.dumps(
 {{'args':sys.argv,'provider_key':os.environ.get('OPENAI_API_KEY'),
   'ambient_gpu':os.environ.get('CUDA_VISIBLE_DEVICES'),
   'offline':os.environ.get('HF_HUB_OFFLINE')}}))
args=sys.argv""",
    ).replace("import json,sys,time", "import json,sys,time,os")
    engine.write_text(text)
    spec = replace(spec, gpu_layers=99, gpu="1,0")
    request = {**request, "spec": asdict(spec)}
    checked = inspect(request)
    assert "error" not in checked, checked
    yield cfg, spec, request, checked["evidence"], server


def test_real_ssh_gpu_profile_uses_exact_selected_devices_and_keeps_environment_private(
    gpu_lab, monkeypatch
):
    cfg, spec, _, checked, _ = gpu_lab
    assert checked["devices"] == ["CUDA0", "CUDA1"]
    assert checked["selected_devices"] == ["CUDA1", "CUDA0"]
    monkeypatch.setenv("OPENAI_API_KEY", "private-provider-canary")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "other-device")
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        request = start(gpu_lab, jobs)
        ready = wait_for(events, "ready")
        launch = json.loads(Path(spec.executable).with_name("launch.json").read_text())
        args = launch["args"]
        assert args[args.index("--device") + 1] == "CUDA1,CUDA0"
        assert args[args.index("--n-gpu-layers") + 1] == "99"
        assert launch["provider_key"] is None and launch["ambient_gpu"] is None
        assert launch["offline"] == "1"
        jobs.stop(request["id"])
        jobs.close(wait=True)
        assert gone(ready["remote_pid"])
        assert records(cfg.data_dir)[request["id"]]["remote_cleanup"] == "confirmed"
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("inventory", [[], ["CUDA1", "CUDA0"], ["CUDA0"], ["CUDA0", "CUDA0"]])
def test_device_loss_or_reordering_invalidates_review_before_launch(gpu_lab, inventory):
    cfg, spec, request, checked, _ = gpu_lab
    Path(spec.executable).with_name("devices.json").write_text(json.dumps(inventory))
    assert "error" in inspect({**request, "evidence": checked})
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(gpu_lab, jobs)
        failed = wait_for(events, "failed")
        assert "GPU inventory changed" in failed["message"]
        jobs.close(wait=True)
        assert records(cfg.data_dir)[accepted["id"]]["remote_cleanup"] == "not_started"
        assert not Path(spec.executable).with_name("launch.json").exists()
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("ids", ["2", "0,0", "0,00", "-1", "0;echo bad", "none", "a"])
def test_invalid_gpu_ids_report_preflight_error_without_a_launch(gpu_lab, ids):
    _, spec, request, _, _ = gpu_lab
    result = inspect({**request, "spec": asdict(replace(spec, gpu=ids))})
    assert "error" in result
    assert not Path(spec.executable).with_name("launch.json").exists()


def test_cpu_remains_available_when_gpu_inventory_is_empty(gpu_lab):
    _, spec, request, _, _ = gpu_lab
    Path(spec.executable).with_name("devices.json").write_text("[]")
    assert "GPU devices unavailable" in inspect(request)["error"]
    cpu = inspect({**request, "spec": asdict(replace(spec, gpu_layers=0))})
    assert cpu["evidence"]["selected_devices"] == []
    assert cpu["evidence"]["devices"] == []


def test_gpu_startup_failure_cleans_up_without_switching_to_cpu_or_selecting_a_model(gpu_lab):
    cfg, spec, request, _, _ = gpu_lab
    model = Path(spec.model).with_name("failed.gguf")
    model.write_bytes(b"GGUFfixture")
    spec = replace(spec, model=str(model))
    checked = inspect({**request, "spec": asdict(spec)})["evidence"]
    events = queue.Queue()
    jobs = ServingJobs(lambda *event: events.put(event))
    try:
        accepted = start(gpu_lab, jobs, spec=spec, evidence=checked)
        wait_for(events, "failed")
        jobs.close(wait=True)
        record = records(cfg.data_dir)[accepted["id"]]
        assert record["remote_cleanup"] == "confirmed"
        assert record["spec"]["gpu_layers"] == 99
        assert not (cfg.config_dir / "model-connections.json").exists()
        assert not (cfg.data_dir / "chat-preferences.json").exists()
        launch = json.loads(Path(spec.executable).with_name("launch.json").read_text())
        assert launch["args"][launch["args"].index("--n-gpu-layers") + 1] == "99"
    finally:
        jobs.close(wait=True)


@pytest.mark.parametrize("devices", [["CUDA0\n--model"], ["a"] * 33, ["same", "same"], "CUDA0"])
def test_client_and_remote_reject_malformed_gpu_evidence(gpu_lab, devices):
    _, spec, _, checked, _ = gpu_lab
    with pytest.raises(ValueError):
        decoded(
            {"version": 1, "connected": True, "evidence": {**checked, "devices": devices}},
            "prepare",
        )
    with pytest.raises(ValueError):
        selection(asdict(spec), devices)


def test_cli_review_displays_actual_devices_and_default_no_does_not_launch(gpu_lab):
    cfg, spec, _, _, _ = gpu_lab
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
            "--gpu-layers",
            "99",
            "--gpu",
            "1,0",
        ],
        input="n\n",
        env={
            **os.environ,
            "KLAUDE_CONFIG_DIR": str(cfg.config_dir),
            "KLAUDE_DATA_DIR": str(cfg.data_dir),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CUDA1, CUDA0" in result.stdout and "GPU layers: 99" in result.stdout
    assert records(cfg.data_dir) == {}


def test_device_probe_timeout_keeps_cpu_available_and_kills_probe_children(gpu_lab):
    _, spec, request, _, _ = gpu_lab
    engine = Path(spec.executable)
    marker = engine.with_name("probe-pid")
    engine.write_text(
        engine.read_text()
        .replace(
            "print('Available devices:')",
            f"""signal.signal(signal.SIGTERM,signal.SIG_IGN)
 open({str(marker)!r},'w').write(str(os.getpid()))
 time.sleep(30)
 print('Available devices:')""",
        )
        .replace("import json,sys,time,os", "import json,sys,time,os,signal")
    )
    started = time.monotonic()
    assert "GPU devices unavailable" in inspect(request)["error"]
    assert time.monotonic() - started < 12
    assert gone(int(marker.read_text()))


def test_remote_gpu_review_is_scoped_and_defaults_cpu_without_automatic_selection():
    from types import SimpleNamespace

    from klaude_cli.serving_panel import ServingPanel
    from klaude_cli.settings_panel import PanelState, render_body

    host = SimpleNamespace()
    panel = ServingPanel(SimpleNamespace(host=host))
    shown = []

    def show(view=None, *args, **kwargs):
        if view:
            panel.view = view
        shown.append((view, args, kwargs))

    panel.show = show
    panel.new_remote_draft("remote", "revision", "Remote QA")
    assert panel.spec.gpu_layers == 0
    assert "GPU layers" in [row.label for row in panel.page().rows]
    panel.spec = replace(panel.spec, gpu_layers=12)
    panel.evidence = {"devices": ["CUDA0"], "selected_devices": ["CUDA0"]}
    assert "GPU IDs" in [row.label for row in panel.page().rows]
    assert next(r for r in panel.page().rows if r.id == "devices").value == "0: CUDA0"
    panel.view = "review"
    for width in (40, 70, 120):
        state = PanelState(panel.page(), "back")
        body = render_body(state, width)
        assert state.picker.selected_id == "back"
        assert any("CUDA0" in text for line in body.lines for _, text in line)
        assert next(row for row in state.page.rows if row.id == "layers").value == "12"


@pytest.mark.parametrize("key", ["previous_page", "next_page"])
def test_paging_review_boundaries_never_moves_back_focus_to_launch(key):
    from types import SimpleNamespace

    from klaude_cli.settings_panel import (
        PanelAction,
        PanelPage,
        PanelRow,
        PanelState,
        RowKind,
        render_body,
    )

    from .test_cli_commands import _fake_persistent_tui

    tui = _fake_persistent_tui()
    page = PanelPage(
        "gpu-review",
        ("Review launch",),
        (
            PanelRow("detail", RowKind.INFO, "Reviewed model", description="Long details " * 30),
            PanelRow(
                "launch", RowKind.ACTION, "Launch server", action=PanelAction("serving-launch")
            ),
            PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("back")),
        ),
        scrollable_body=True,
    )
    tui._panel = PanelState(page, "back")
    tui._choice_kind = "model manager serving review"
    tui.panel_body_window = SimpleNamespace(render_info=SimpleNamespace(window_height=8))
    tui._panel_body = lambda: render_body(tui._panel, 40)
    handler = next(b.handler for b in tui.key_bindings.bindings if b.handler.__name__ == key)
    for _ in range(20):
        handler(None)
        assert tui._panel.picker.selected_id == "back"


def test_cancelled_device_check_stops_child_without_waiting_for_the_deadline(tmp_path, monkeypatch):
    from klaude_core import ssh_serving_program as program

    marker = tmp_path / "started"
    engine = tmp_path / "device-check"
    engine.write_text(f"""#!{sys.executable}
import os,signal,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path({str(marker)!r}).write_text(str(os.getpid()))
time.sleep(30)
""")
    engine.chmod(0o700)
    monkeypatch.setattr(program, "cancelled", False)
    ending = threading.Event()

    def cancel():
        while not ending.wait(0.02):
            if marker.exists():
                program.interrupt()
                return

    thread = threading.Thread(target=cancel)
    thread.start()
    started = time.monotonic()
    try:
        with pytest.raises(ValueError, match="cancelled"):
            program.command_output(engine, "--list-devices", time.monotonic() + 8, 65536)
        assert time.monotonic() - started < 3
        assert gone(int(marker.read_text()))
    finally:
        ending.set()
        thread.join(timeout=1)


def test_narrow_selected_gpu_field_keeps_both_label_and_value_in_view():
    from klaude_cli.settings_panel import (
        PanelAction,
        PanelPage,
        PanelRow,
        PanelState,
        RowKind,
        render_body,
    )

    page = PanelPage(
        "gpu-form",
        ("Serve",),
        tuple(
            [PanelRow("info:" + str(i), RowKind.INFO, "Earlier field " + str(i)) for i in range(12)]
            + [
                PanelRow(
                    "gpu", RowKind.ACTION, "GPU IDs", "1,0", action=PanelAction("serving-field:gpu")
                ),
                PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("back")),
            ]
        ),
        scrollable_body=True,
    )
    state = PanelState(page, "gpu")
    body = render_body(state, 35)
    top = state.viewport(8, body)
    visible = "\n".join("".join(text for _, text in line) for line in body.lines[top : top + 8])
    assert "GPU IDs" in visible and "1,0" in visible
