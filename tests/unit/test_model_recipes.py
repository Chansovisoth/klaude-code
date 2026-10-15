"""Real compiler/offline wheel installs, bounded recipes and UI continuity."""

import base64
import csv
import hashlib
import io
import os
import queue
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.dependency_panel import WORK, DependencyPanel
from klaude_cli.settings_panel import PanelAction
from klaude_core.model_dependencies import build, builds, prepare
from klaude_core.model_recipes import cuda, wheel

from .test_model_dependencies import commit
from .test_model_dependencies import source as source


def package(folder, name, content, *, dependencies=(), entry="", tag="py3-none-any"):
    version = "0.0.1"
    dist = f"{name}-{version}.dist-info"
    files = {
        name + "/__init__.py": content.encode(),
        dist + "/METADATA": (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            + "".join(f"Requires-Dist: {item}\n" for item in dependencies)
        ).encode(),
        dist + "/WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {tag}\n".encode(),
    }
    if entry:
        files[dist + "/entry_points.txt"] = f"[console_scripts]\nvllm = {entry}\n".encode()
    records = io.StringIO()
    writer = csv.writer(records)
    for path, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        writer.writerow([path, "sha256=" + digest, len(data)])
    writer.writerow([dist + "/RECORD", "", ""])
    files[dist + "/RECORD"] = records.getvalue().encode()
    path = folder / f"{name}-{version}-{tag}.whl"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for key, value in files.items():
            archive.writestr(key, value)
    path.chmod(0o600)
    return path


@pytest.fixture
def wheels(tmp_path):
    if not shutil.which("uv"):
        pytest.skip("Installed uv is required for offline environment fixtures")
    folder, data = tmp_path / "wheels", tmp_path / "data"
    folder.mkdir()
    data.mkdir()
    package(
        folder,
        "torch",
        """import os
from pathlib import Path
Path(__file__).with_name('credential.txt').write_text(os.environ.get('OPENAI_API_KEY',''))
class Version: cuda = '12.9'
version = Version()
class Cuda:
 @staticmethod
 def is_available(): return False
cuda = Cuda()
""",
    )
    package(
        folder,
        "vllm",
        """def main():
 print('--host --port --served-model-name --max-model-len --gpu-memory-utilization '
       '--max-num-seqs --tensor-parallel-size --load-format')
""",
        dependencies=["torch==0.0.1"],
        entry="vllm:main",
    )
    return folder, data


def test_real_offline_install_preserves_wheels_and_never_changes_app_environment(
    wheels, monkeypatch
):
    folder, data = wheels
    original = {path: path.read_bytes() for path in folder.iterdir()}
    monkeypatch.setenv("OPENAI_API_KEY", "private-install-canary")
    evidence = prepare(str(folder), data, profile="vllm_cuda")
    assert not (data / "model-builds").exists()
    events = []
    result = build(data, uuid.uuid4().hex, evidence, events.append)
    assert result["status"] == "ok", result
    record = result["build"]
    assert record["engine"] == "vllm" and record["compatibility"]["gpu_available"] is False
    installed = Path(record["executable"]).parents[1]
    credential = list(installed.glob("lib/python*/site-packages/torch/credential.txt"))
    assert len(credential) == 1 and credential[0].read_text() == ""
    assert {path: path.read_bytes() for path in folder.iterdir()} == original
    assert builds(data)[0]["state"] == "ready"
    assert not (data / "model-connections.json").exists()
    assert not (data / "chat-preferences.json").exists()
    assert any(event["stage"] == "Verify engine help" for event in events)


def test_uv_launcher_outside_standard_directories_supports_offline_install(wheels, monkeypatch):
    folder, data = wheels
    installed = shutil.which("uv")
    assert installed
    launcher = folder.parent / "tool-cache" / "uv"
    launcher.parent.mkdir()
    launcher.symlink_to(Path(installed).resolve())
    which = shutil.which

    def standard_directory_lookup(name, path=None):
        return None if name == "uv" and path is not None else which(name, path=path)

    monkeypatch.setattr(shutil, "which", standard_directory_lookup)
    monkeypatch.setenv("UV", str(launcher))
    evidence = prepare(str(folder), data, profile="vllm_cuda")
    assert evidence["tools"]["uv"] == str(launcher.resolve())
    result = build(data, uuid.uuid4().hex, evidence, lambda _: None)
    assert result["status"] == "ok" and result["build"]["state"] == "ready"


@pytest.mark.parametrize("hint", ["./uv", "/missing-klaude-uv-fixture"])
def test_invalid_explicit_uv_hint_cannot_silently_select_another_installer(
    wheels, monkeypatch, hint
):
    folder, data = wheels
    monkeypatch.setenv("UV", hint)
    with pytest.raises((ValueError, OSError)):
        prepare(str(folder), data, profile="vllm_cuda")
    assert not (data / "model-builds").exists()


@pytest.mark.parametrize("changed", ["wheel", "python"])
def test_changed_wheels_or_interpreter_cannot_install_without_a_new_review(wheels, changed):
    folder, data = wheels
    evidence = prepare(str(folder), data, profile="vllm_cuda")
    if changed == "wheel":
        path = next(folder.glob("vllm*.whl"))
        path.write_bytes(path.read_bytes() + b"changed")
    else:
        evidence["revisions"]["python"] = "old"
    with pytest.raises(ValueError):
        build(data, uuid.uuid4().hex, evidence, lambda _: None)
    assert not (data / "model-builds").exists()


@pytest.mark.parametrize("failure", ["missing", "platform", "cpu", "help"])
def test_incomplete_or_incompatible_install_never_publishes_a_ready_engine(wheels, failure):
    folder, data = wheels
    if failure == "missing":
        package(
            folder,
            "vllm",
            "def main(): pass",
            dependencies=["missing-fixture==0.0.1"],
            entry="vllm:main",
        )
    elif failure == "platform":
        next(folder.glob("vllm*.whl")).unlink()
        package(folder, "vllm", "def main(): pass", entry="vllm:main", tag="cp399-cp399-win32")
    elif failure == "cpu":
        package(
            folder,
            "torch",
            "class Version: cuda=None\nversion=Version()\n"
            "class Cuda:\n def is_available(self):return False\ncuda=Cuda()",
        )
    else:
        package(folder, "vllm", "def main(): print('no serving flags')", entry="vllm:main")
    if failure in {"missing", "platform"}:
        with pytest.raises(ValueError, match="Wheel closure"):
            prepare(str(folder), data, profile="vllm_cuda")
        assert not (data / "model-builds").exists()
        return
    evidence = prepare(str(folder), data, profile="vllm_cuda")
    with pytest.raises(ValueError):
        build(data, uuid.uuid4().hex, evidence, lambda _: None)
    assert builds(data)[0]["state"] == "failed" and not builds(data)[0].get("executable")


def test_url_dependencies_fail_before_creating_an_environment(wheels):
    folder, data = wheels
    package(
        folder,
        "vllm",
        "def main(): pass",
        dependencies=["private @ https://example.test/a"],
        entry="vllm:main",
    )
    with pytest.raises(ValueError, match="URL"):
        prepare(str(folder), data, profile="vllm_cuda")
    assert list(data.iterdir()) == []


def test_wheel_path_traversal_and_symlink_are_rejected(wheels):
    folder, _ = wheels
    path = next(folder.glob("vllm*.whl"))
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("../outside", "invalid")
    with pytest.raises(ValueError, match="paths"):
        wheel(path)
    link = folder / "linked.whl"
    link.symlink_to(next(folder.glob("torch*.whl")))
    with pytest.raises(OSError):
        wheel(link)


def test_low_disk_rejects_install_before_mutation(wheels, monkeypatch):
    folder, data = wheels
    monkeypatch.setattr(
        "klaude_core.model_recipes.shutil.disk_usage", lambda _: SimpleNamespace(free=1024)
    )
    with pytest.raises(ValueError, match="GiB free"):
        prepare(str(folder), data, profile="vllm_cuda")
    assert list(data.iterdir()) == []


def test_real_cuda_compile_with_explicit_target_needs_no_working_gpu(source):
    folder, data = source
    host = shutil.which("g++-12")
    if not shutil.which("nvcc") or not host:
        pytest.skip("Local CUDA toolkit and GCC 12 required for native compiler fixture")
    with (folder / "CMakeLists.txt").open("a") as stream:
        stream.write(
            '\noption(GGML_CUDA "cuda" OFF)\nif(GGML_CUDA)\n'
            " enable_language(CUDA)\n target_sources(llama-server PRIVATE kernel.cu)\nendif()\n"
        )
    (folder / "kernel.cu").write_text("__global__ void klaude_fixture_kernel() {}\n")
    commit(folder)
    evidence = prepare(str(folder), data, profile="cuda", architectures="75", host_compiler=host)
    assert evidence["flags"]["GGML_CUDA"] == "ON"
    result = build(data, uuid.uuid4().hex, evidence, lambda _: None)
    assert result["build"]["profile"] == "cuda" and result["build"]["state"] == "ready"
    assert result["build"]["devices"] is None
    assert "untested" in result["message"]


@pytest.mark.parametrize("value", ["0", "86;touch", "999", "86;" + ";".join(["86"] * 9)])
def test_invalid_or_unsupported_cuda_targets_are_rejected(monkeypatch, value):
    monkeypatch.setattr(
        "klaude_core.model_recipes.shutil.which", lambda *args, **kwargs: "/usr/bin/true"
    )
    monkeypatch.setattr(
        "klaude_core.model_dependencies.read_command", lambda *args: b"compute_86\n"
    )
    with pytest.raises(ValueError):
        cuda(value, "/usr/bin/true", {"c++": "/usr/bin/true"})


def test_cancelled_install_probe_reaps_worker_and_child(wheels):
    folder, data = wheels
    marker = folder / "started"
    package(
        folder,
        "vllm",
        f"""def main():
 import signal,time
 from pathlib import Path
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 Path({str(marker)!r}).write_text('started')
 time.sleep(60)
""",
        dependencies=["torch==0.0.1"],
        entry="vllm:main",
    )
    evidence = prepare(str(folder), data, profile="vllm_cuda")
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *value: events.put(value))
    identity = uuid.uuid4().hex
    try:
        worker = jobs.submit(
            "install",
            {
                "kind": "model_dependencies",
                "operation": "build",
                "data_dir": str(data),
                "evidence": evidence,
                "id": identity,
                "owner": os.getpid(),
            },
            timeout=30,
            notify_cancel=True,
        )
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists()
        jobs.cancel("install")
        while time.monotonic() < deadline:
            kind, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if kind == "background_stopped":
                assert payload == ("install", worker)
                break
        else:
            pytest.fail("Install cancellation never acknowledged")
        item = builds(data)[0]
        assert item["state"] == "interrupted"
        with pytest.raises(ProcessLookupError):
            os.killpg(item["pid"], 0)
    finally:
        jobs.close(wait=True)


def panel(tmp_path):
    shown, drafts, queued = [], [], []
    host = SimpleNamespace(
        cfg=SimpleNamespace(data_dir=tmp_path),
        _choice_kind="model manager dependencies progress",
        _settings_input_request=None,
        _start_next=lambda: queued.append(True),
        _panel_states={},
    )
    manager = SimpleNamespace(
        host=host,
        scope=("session", str(tmp_path)),
        busy=False,
        serving=SimpleNamespace(new_draft=lambda **values: drafts.append(values)),
    )
    instance = DependencyPanel(manager)
    instance.show = lambda *args, **kwargs: shown.append((args, kwargs))
    return instance, shown, drafts, queued


def test_vllm_handoff_retains_engine_and_does_not_launch_or_select_a_model(tmp_path):
    instance, _, drafts, _ = panel(tmp_path)
    instance.result = {"state": "ready", "engine": "vllm", "executable": "/qa/venv/bin/vllm"}
    instance.action(PanelAction("dependency-serve"))
    assert drafts == [{"engine": "vllm", "executable": "/qa/venv/bin/vllm", "focus": "field:model"}]


@pytest.mark.parametrize("change", ["session", "editor", "draft"])
def test_late_setup_result_does_not_replace_new_session_or_editor(tmp_path, change):
    instance, shown, _, queued = panel(tmp_path)
    instance.task = {
        "worker": "job",
        "id": "setup",
        "scope": instance.manager.scope,
        "revision": instance.revision,
    }
    if change == "session":
        instance.manager.scope = ("other", "other data")
    elif change == "editor":
        instance.host._settings_input_request = {"field": "new path"}
    else:
        instance.revision += 1
    instance.feedback = ("Current", "neutral")
    instance.accept(
        WORK,
        "job",
        {"status": "ok", "message": "old", "build": {"id": "setup", "state": "ready"}},
        "",
    )
    assert instance.feedback == ("Current", "neutral") and queued == [True]
    if change != "draft":
        assert shown == []
    if change == "session":
        assert instance.result == {}
