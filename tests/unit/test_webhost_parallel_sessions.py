"""Independent browser conversation workers retain their own queues and leases."""

import threading
import time
import uuid

import pytest
from klaude_application.browser_sessions import prepare_session_operation, run_session_operation
from klaude_core.config import Config
from klaude_core.model_runtime import ModelInfo
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost

from .test_webhost import _app


@pytest.fixture
def parallel_host(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config(models={"coder": "fixture"})
    runtimes = []

    class Runtime:
        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()
            self.closed = False

        def chat(self, *_args, **_kwargs):
            self.entered.set()
            assert self.release.wait(15), "Fixture was not released"
            return {"role": "assistant", "content": "Independent answer"}

        def close(self):
            self.closed = True

    def factory():
        app = _app(cfg.data_dir)
        app.agent.workdir, app.agent.workspace = tmp_path, Workspace(tmp_path)
        app.agent.tool_config = cfg
        runtime = Runtime()
        runtimes.append(runtime)
        app.agent.runtime = app.agent.ollama = runtime
        app.turns.bind_workspace(app.session_id, str(tmp_path), expected_revision=0)
        return app

    host = LocalWebHost(factory(), application_factory=factory)
    serving = threading.Thread(target=host.serve_forever, daemon=True)
    serving.start()
    try:
        yield host, runtimes
    finally:
        for runtime in runtimes:
            runtime.release.set()
        host.stop()
        serving.join(3)
        assert all(runtime.closed for runtime in runtimes)


def choose(host, target=""):
    source = host.application
    viewer, epoch = source.control() or ("viewer", 0)
    return host.switch_session(viewer, uuid.uuid4().hex, source.session_id, target, epoch)


def test_two_workers_continue_across_switches_with_independent_history_and_queue(parallel_host):
    host, runtimes = parallel_host
    first = host.application
    original = first.session_id
    handle = first.submit("First conversation", request_id="first-turn")
    assert runtimes[0].entered.wait(3)
    first.enqueue("Queued first message", request_id="first-queued")
    second_id = choose(host)
    second = host.application
    assert second is not first and second_id != original
    second_handle = second.submit("Second conversation", request_id="second-turn")
    assert runtimes[1].entered.wait(3)
    assert choose(host, original) == original
    assert host.application is first and first.active_turn_id() == handle.turn_id
    assert second.active_turn_id() == second_handle.turn_id
    rows = {row["session_id"]: row for row in host.sessions()}
    assert rows[original]["active"] and rows[second_id]["active"]
    fields, _, _ = prepare_session_operation(first.memory.sessions_db, first.agent.workdir,
                                             {"operation": "session-delete", "target": second_id})
    with pytest.raises(ValueError, match="active worker"):
        run_session_operation(first.memory, first.agent.workdir,
                              {"operation": "session-delete", **fields})
    runtimes[0].release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        records = first.memory.load_session(original)
        answers = [row for row in records if row["role"] == "assistant"]
        if len(answers) == 2 and not first.active_turn_id():
            break
        time.sleep(.02)
    assert [row["content"] for row in records if row["role"] == "user"] == [
        "First conversation", "Queued first message",
    ]
    assert len([row for row in records if row["role"] == "assistant"]) == 2
    assert second.active_turn_id() == second_handle.turn_id
    rows = {row["session_id"]: row for row in host.sessions()}
    assert not rows[original]["active"] and rows[second_id]["active"]
    assert choose(host, second_id) == second_id and host.application is second


def test_parallel_worker_bound_never_cancels_or_reuses_a_running_agent(parallel_host):
    host, runtimes = parallel_host
    applications = []
    for index in range(4):
        if index:
            choose(host)
        app = host.application
        applications.append(app)
        app.submit(f"Conversation {index}", request_id=f"turn-{index}")
        assert runtimes[index].entered.wait(3)
    with pytest.raises(RuntimeError, match="Four conversations"):
        choose(host)
    assert host.application is applications[-1]
    assert all(app.active_turn_id() for app in applications)
    assert len(host._applications) == 4
    runtimes[0].release.set()
    deadline = time.monotonic() + 3
    while applications[0].active_turn_id() and time.monotonic() < deadline:
        time.sleep(.02)
    choose(host)
    assert runtimes[0].closed
    assert applications[0] not in host._applications
    assert all(app.active_turn_id() for app in applications[1:])
    assert len(host._applications) == 4


def test_parallel_new_chat_preserves_the_chosen_model_without_sharing_runtime(parallel_host):
    host, runtimes = parallel_host
    source = host.application
    source.agent.model = "alternate"
    source.agent.model_info = ModelInfo("ollama", "alternate", "Alternate")
    source.submit("Keep using this model", request_id="alternate-turn")
    assert runtimes[0].entered.wait(3)
    choose(host)
    assert host.application.agent.model == "alternate"
    assert host.application.agent.model_info.ref == source.agent.model_info.ref
    assert host.application.agent.runtime is not source.agent.runtime
    assert source.active_turn_id()


def test_background_edit_activation_remains_isolated_and_still_blocks_lan(parallel_host, tmp_path):
    host, runtimes = parallel_host
    source = host.application
    source.agent.workspace.write_enabled = True
    host._edits_activated = True
    source.submit("Existing reviewed edit session", request_id="editing-turn")
    assert runtimes[0].entered.wait(3)
    choose(host)
    assert source.agent.workspace.write_enabled
    assert not host.application.agent.workspace.write_enabled
    assert not host._edits_activated
    with pytest.raises(RuntimeError, match="Disable file edits"):
        host.start_lan("192.168.1.10", tmp_path / "lan")
    choose(host, source.session_id)
    assert host.application is source and host._edits_activated
