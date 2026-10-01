import errno
import json
import multiprocessing
import os
import time
from pathlib import Path

import pytest
from klaude_core.config import save_provider_secret
from klaude_core.mcp_client import MCPRegistry, MCPServerConfig
from klaude_core.settings_store import (
    DELETE,
    SettingsConflictError,
    settings_lock,
    update_settings,
)


def _writer(path, barrier, index):
    barrier.wait(timeout=5)
    for turn in range(10):
        deadline = time.monotonic() + 5
        while True:
            try:
                update_settings(Path(path), {("runtime_options", str(index)): turn})
                break
            except OSError as error:
                if error.errno != errno.EBUSY or time.monotonic() >= deadline:
                    raise
                # Contention is visible and bounded in the product. This test
                # explicitly retries like a user, without weakening that bound.
                time.sleep(0.01)


def _secret_writer(directory, barrier, name):
    barrier.wait(timeout=5)
    save_provider_secret(Path(directory), name, "test-only-secret")


def test_processes_merge_independent_fields_without_shared_temp_files(tmp_path):
    path = tmp_path / "preferences.json"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(4)
    workers = [context.Process(target=_writer, args=(path, barrier, i)) for i in range(4)]
    for worker in workers:
        worker.start()
    try:
        for worker in workers:
            worker.join(timeout=10)
        assert [worker.exitcode for worker in workers] == [0] * 4
        assert json.loads(path.read_text())["runtime_options"] == {str(i): 9 for i in range(4)}
        assert path.stat().st_mode & 0o777 == 0o600
        assert set(entry.name for entry in tmp_path.iterdir()) == {
            "preferences.json",
            ".preferences.json.lock",
        }
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)


def test_same_field_is_last_serialized_user_assignment_and_reset_is_scoped(tmp_path):
    path = tmp_path / "preferences.json"
    update_settings(path, {("last_model",): "first", ("runtime_options", "num_ctx"): 4096})
    update_settings(path, {("last_model",): "second", ("runtime_options", "max_steps"): 40})
    update_settings(path, {("runtime_options", "max_steps"): DELETE})
    assert json.loads(path.read_text()) == {
        "last_model": "second",
        "runtime_options": {"num_ctx": 4096},
    }


def test_lock_wait_is_bounded_and_failure_does_not_write(tmp_path):
    path = tmp_path / "preferences.json"
    with settings_lock(path):
        start = time.monotonic()
        with pytest.raises(OSError, match="busy in another client"):
            with settings_lock(path, timeout=0.02):
                pytest.fail("A second writer acquired the held lock")
        assert time.monotonic() - start < 0.5
        assert not path.exists()
    update_settings(path, {("ready",): True})


@pytest.mark.parametrize("payload", [b"not json", b"[]", b"\xff"])
def test_invalid_settings_fail_closed_without_disclosing_content(tmp_path, payload):
    path = tmp_path / "preferences.json"
    path.write_bytes(payload)
    with pytest.raises(OSError, match="Settings are invalid") as error:
        update_settings(path, {("new",): True})
    assert "not json" not in str(error.value)
    assert path.read_bytes() == payload


def test_failed_atomic_replace_preserves_original_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    update_settings(path, {("old",): True})
    original = path.read_bytes()

    def fail(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        update_settings(path, {("new",): True})
    assert path.read_bytes() == original
    assert set(entry.name for entry in tmp_path.iterdir()) == {
        "preferences.json",
        ".preferences.json.lock",
    }


@pytest.mark.parametrize("target", ["data", "lock"])
def test_settings_reject_symlink_targets(tmp_path, target):
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text('{"keep": true}')
    path = tmp_path / "preferences.json"
    link = path if target == "data" else tmp_path / ".preferences.json.lock"
    link.symlink_to(unrelated)
    with pytest.raises(OSError):
        update_settings(path, {("new",): True})
    assert unrelated.read_text() == '{"keep": true}'


def test_concurrent_secrets_preserve_comments_other_keys_and_private_mode(tmp_path, capsys):
    path = tmp_path / ".env"
    path.write_text("# keep URL documentation\nUNRELATED=value\n")
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    workers = [
        context.Process(target=_secret_writer, args=(tmp_path, barrier, name))
        for name in ("FIRST_API_KEY", "SECOND_API_KEY")
    ]
    for worker in workers:
        worker.start()
    try:
        for worker in workers:
            worker.join(timeout=10)
        assert [worker.exitcode for worker in workers] == [0, 0]
        value = path.read_text()
        assert value.startswith("# keep URL documentation\nUNRELATED=value\n")
        assert "FIRST_API_KEY=test-only-secret" in value
        assert "SECOND_API_KEY=test-only-secret" in value
        assert path.stat().st_mode & 0o777 == 0o600
        assert "test-only-secret" not in capsys.readouterr().out
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)


def server(name):
    return MCPServerConfig(
        name=name, transport="http", enabled=False, url=f"https://{name}.example/mcp"
    )


def test_stale_mcp_clients_merge_independent_servers_and_repeat_saves(tmp_path):
    path = tmp_path / "mcp.json"
    MCPRegistry(path).save({"one": server("one"), "two": server("two")})
    first, second = MCPRegistry(path), MCPRegistry(path)
    left, right = first.load(), second.load()
    left["one"].enabled = True
    first.save(left)
    right["two"].enabled = True
    second.save(right)
    first.save(left)
    assert all(item.enabled for item in MCPRegistry(path).load().values())


@pytest.mark.parametrize("mutation", ["change", "delete", "tools"])
def test_stale_mcp_change_cannot_overwrite_a_newer_definition(tmp_path, mutation):
    path = tmp_path / "mcp.json"
    MCPRegistry(path).save({"one": server("one")})
    first, second = MCPRegistry(path), MCPRegistry(path)
    left, right = first.load(), second.load()
    left["one"].url = "https://new.example/mcp"
    first.save(left)
    if mutation == "delete":
        right.pop("one")
    elif mutation == "tools":
        right["one"].tools.append({"name": "changed", "inputSchema": {"type": "object"}})
    else:
        right["one"].enabled = True
    with pytest.raises(SettingsConflictError, match="reload and retry"):
        second.save(right)
    assert MCPRegistry(path).load()["one"].url == "https://new.example/mcp"


def test_mcp_duplicate_add_is_not_silent_replacement(tmp_path):
    path = tmp_path / "mcp.json"
    first, second = MCPRegistry(path), MCPRegistry(path)
    first.load()
    second.load()
    first.save({"one": server("one")})
    with pytest.raises(SettingsConflictError):
        second.save({"one": server("one")})
