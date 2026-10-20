"""Real Git/CMake fixtures for reviewed source snapshots and owned build cleanup."""

import json
import os
import queue
import select
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_core.managed_serving import process_identity
from klaude_core.model_dependencies import TOOLS, build, builds, inspection, prepare, tool_paths


def test_shared_dependency_command_roundtrip_and_fixed_operations(tmp_path):
    from klaude_application.model_dependencies import ModelDependencyCommand

    cfg = type("Config", (), {"config_dir": tmp_path / "config",
                               "data_dir": tmp_path / "data"})()
    command = ModelDependencyCommand.for_client(cfg, "prepare_remove", id="record")
    request = command.worker_request()
    assert ModelDependencyCommand.from_worker(request).worker_request() == request
    assert "record" not in repr(command)
    with pytest.raises(ValueError, match="Invalid model dependency"):
        ModelDependencyCommand.from_worker({**request, "operation": "shell"})
    with pytest.raises(ValueError, match="Invalid model dependency"):
        ModelDependencyCommand.from_worker({**request, "payload": "unexpected"})


@pytest.fixture
def source(tmp_path):
    if set(tool_paths()) != set(TOOLS):
        pytest.skip("Installed local Git/CMake/Ninja/C/C++ tools required")
    folder = tmp_path / "checkout"
    folder.mkdir()
    for name in ("ggml", "tools/server"):
        (folder / name).mkdir(parents=True)
        (folder / name / "CMakeLists.txt").write_text("# fixture\n")
    (folder / "CMakeLists.txt").write_text("""cmake_minimum_required(VERSION 3.16)
project(EngineFixture LANGUAGES C CXX)
option(LLAMA_BUILD_SERVER "server" ON)
option(LLAMA_BUILD_WEBUI "web" OFF)
option(BUILD_SHARED_LIBS "shared" OFF)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
add_executable(llama-server server.cpp)
file(WRITE "${CMAKE_BINARY_DIR}/credential.txt" "$ENV{OPENAI_API_KEY}")
""")
    (folder / "server.cpp").write_text("""#include <iostream>
int main() {
 std::cout << "--host --port --alias --model --ctx-size --threads --n-gpu-layers --parallel";
 return 0;
}
""")
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    subprocess.run(["git", "-C", str(folder), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(folder),
            "-c",
            "user.name=QA",
            "-c",
            "user.email=qa@example.test",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    data = tmp_path / "data"
    data.mkdir()
    return folder, data


def commit(folder):
    subprocess.run(["git", "-C", str(folder), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(folder),
            "-c",
            "user.name=QA",
            "-c",
            "user.email=qa@example.test",
            "commit",
            "-qm",
            "fixture change",
        ],
        check=True,
    )


def test_inspection_has_no_build_or_install_side_effects(source):
    folder, data = source
    report = inspection(executable="/tmp/no-dependency-engine")
    assert report["engine"]["status"] == "Unavailable"
    assert {t["name"] for t in report["tools"]} == {"cmake", "ninja", "git", "cc", "c++"}
    assert list(data.iterdir()) == [] and not (folder / "output").exists()


def test_real_cpu_build_snapshots_commit_retains_dirty_source_and_excludes_credentials(
    source, monkeypatch
):
    folder, data = source
    monkeypatch.setenv("OPENAI_API_KEY", "private-build-credential")
    evidence = prepare(str(folder), data)
    (folder / "server.cpp").write_text("dirty user edits that cannot compile")
    stages = []
    identity = uuid.uuid4().hex
    result = build(data, identity, evidence, stages.append)
    assert result["status"] == "ok" and result["build"]["state"] == "ready"
    assert Path(result["build"]["executable"]).is_file()
    assert (folder / "server.cpp").read_text() == "dirty user edits that cannot compile"
    assert (data / "model-builds" / identity / "output/credential.txt").read_text() == ""
    assert stages[0]["stage"] == "Snapshot committed source"
    assert builds(data)[0]["commit"] == evidence["commit"]
    assert not (data / "model-connections.json").exists()
    assert not (data / "chat-preferences.json").exists()


def test_changed_commit_requires_new_review(source):
    folder, data = source
    evidence = prepare(str(folder), data)
    (folder / "new-file.txt").write_text("new commit")
    commit(folder)
    with pytest.raises(ValueError, match="changed"):
        build(data, uuid.uuid4().hex, evidence, lambda _: None)
    assert not (data / "model-builds").exists()


def test_insufficient_disk_space_blocks_build_review(source, monkeypatch):
    from types import SimpleNamespace

    folder, data = source
    monkeypatch.setattr(
        "klaude_core.model_dependencies.shutil.disk_usage", lambda _: SimpleNamespace(free=1024**3)
    )
    with pytest.raises(ValueError, match="2 GiB"):
        prepare(str(folder), data)
    assert not (data / "model-builds").exists()


def test_fresh_data_directory_can_be_reviewed_without_creating_files(source):
    folder, data = source
    fresh = data / "fresh" / "data"
    assert prepare(str(folder), fresh)["source"] == str(folder)
    assert not fresh.parent.exists()


def test_modified_executable_is_not_offered_as_a_verified_build(source):
    folder, data = source
    result = build(data, uuid.uuid4().hex, prepare(str(folder), data), lambda _: None)
    Path(result["build"]["executable"]).write_text("changed")
    assert builds(data)[0]["state"] == "changed"


def test_corrupt_build_metadata_is_rejected_before_rendering(source):
    _, data = source
    identity = uuid.uuid4().hex
    folder = data / "model-builds" / identity
    folder.mkdir(parents=True)
    (folder / "status.json").write_text(json.dumps({"id": identity, "state": "ready"}))
    with pytest.raises(ValueError, match="Invalid build record"):
        builds(data)


@pytest.mark.parametrize("failure", ["configure", "compile", "flags", "symlink"])
def test_failed_build_never_publishes_verified_executable(source, failure):
    folder, data = source
    if failure == "configure":
        with (folder / "CMakeLists.txt").open("a") as stream:
            stream.write('\nmessage(FATAL_ERROR "fixture failure")\n')
    elif failure == "compile":
        (folder / "server.cpp").write_text("not C++")
    elif failure == "flags":
        (folder / "server.cpp").write_text("int main() { return 0; }")
    else:
        (folder / "escape").symlink_to("/tmp")
    commit(folder)
    evidence = prepare(str(folder), data)
    with pytest.raises(ValueError):
        build(data, uuid.uuid4().hex, evidence, lambda _: None)
    assert builds(data)[0]["state"] == "failed"
    assert not builds(data)[0].get("executable")


def test_owned_build_cancel_reaps_compilers_and_keeps_partial_record(source):
    folder, data = source
    with (folder / "CMakeLists.txt").open("a") as stream:
        stream.write("""\nadd_custom_target(wait
 COMMAND ${CMAKE_COMMAND} -E sleep 60)
add_dependencies(llama-server wait)
""")
    commit(folder)
    evidence = prepare(str(folder), data)
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *value: events.put(value))
    identity = uuid.uuid4().hex
    try:
        worker = jobs.submit(
            "build",
            {
                "kind": "model_dependencies",
                "operation": "build",
                "data_dir": str(data),
                "evidence": evidence,
                "id": identity,
                "owner": os.getpid(),
            },
            timeout=20,
            notify_cancel=True,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            kind, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if kind == "background_progress" and payload[2]["stage"] == "Compile llama-server":
                break
        else:
            pytest.fail("Build never reached compiler")
        jobs.cancel("build")
        while time.monotonic() < deadline:
            kind, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if kind == "background_stopped":
                assert payload == ("build", worker)
                break
        else:
            pytest.fail("Compiler cleanup never acknowledged")
        assert builds(data)[0]["state"] == "interrupted"
        raw = json.loads((data / "model-builds" / identity / "status.json").read_text())
        with pytest.raises(ProcessLookupError):
            os.killpg(raw["pid"], 0)
    finally:
        jobs.close(wait=True)


def test_client_death_stops_owned_build_and_never_publishes_an_executable(source):
    folder, data = source
    with (folder / "CMakeLists.txt").open("a") as stream:
        stream.write("""\nadd_custom_target(wait COMMAND ${CMAKE_COMMAND} -E sleep 60)
add_dependencies(llama-server wait)
""")
    commit(folder)
    request = {
        "kind": "model_dependencies",
        "operation": "build",
        "data_dir": str(data),
        "evidence": prepare(str(folder), data),
        "id": uuid.uuid4().hex,
    }
    script = """import json,os,sys,time
from klaude_cli.background_jobs import OwnedBackgroundJobs
def emit(kind,value):
 if kind=='background_progress' and value[2]['stage']=='Compile llama-server':
  print('compiler',flush=True)
request=json.loads(sys.stdin.readline());request['owner']=os.getpid()
jobs=OwnedBackgroundJobs(emit);jobs.submit('build',request,timeout=60)
time.sleep(60)
"""
    owner = subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    assert owner.stdin is not None and owner.stdout is not None
    record = data / "model-builds" / request["id"] / "status.json"
    try:
        owner.stdin.write(json.dumps(request) + "\n")
        owner.stdin.flush()
        assert select.select([owner.stdout], [], [], 12)[0], "Build never reached compiler"
        assert owner.stdout.readline().strip() == "compiler"
        owner.kill()
        owner.wait(timeout=3)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            item = json.loads(record.read_text())
            if item["state"] == "failed":
                break
            time.sleep(0.1)
        assert item["state"] == "failed" and not item.get("executable")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                process_identity(item["pid"])
            except (OSError, ValueError):
                break
            time.sleep(0.1)
        with pytest.raises((OSError, ValueError)):
            process_identity(item["pid"])
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.wait(timeout=3)
        owner.stdin.close()
        owner.stdout.close()
        if record.exists():
            try:
                os.killpg(json.loads(record.read_text())["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_cancelled_engine_probe_cannot_escape_its_owned_worker_group(tmp_path):
    engine = tmp_path / "slow-engine"
    marker = tmp_path / "engine.pid"
    engine.write_text(
        f"#!{sys.executable}\nimport os,time,signal\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        f"open({str(marker)!r},'w').write(str(os.getpid()))\ntime.sleep(60)\n"
    )
    engine.chmod(0o700)
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *value: events.put(value))
    pid = None
    try:
        jobs.submit(
            "probe",
            {
                "kind": "serving_read",
                "operation": "probe",
                "engine": "llama_cpp",
                "executable": str(engine),
            },
            timeout=20,
            notify_cancel=True,
        )
        deadline = time.monotonic() + 4
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "Probe did not start"
        pid = int(marker.read_text())
        jobs.cancel("probe")
        kind, _ = events.get(timeout=4)
        assert kind == "background_stopped"
        with pytest.raises((OSError, ValueError)):
            process_identity(pid)
    finally:
        jobs.close(wait=True)
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize("jobs", [0, 9, True])
def test_invalid_build_resources(source, jobs):
    folder, data = source
    with pytest.raises(ValueError, match="Build jobs"):
        prepare(str(folder), data, jobs)
