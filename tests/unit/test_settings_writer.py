import json
import queue
import threading

import pytest
from klaude_cli.settings_writer import SettingsWriter


def test_appearance_writer_migrates_under_lock_and_merges_scoped_fields(tmp_path):
    from klaude_cli.main import _migrate_appearance

    path = tmp_path / "appearance.json"
    path.write_text(json.dumps({
        "theme": "hacker-green", "text_theme": "monokai", "future": 1,
        "permissions": {"run_shell": "allow"},
    }))
    events = queue.Queue()
    first = SettingsWriter(path, lambda *event: events.put(event),
                           prepare=_migrate_appearance, publish_permissions=False)
    second = SettingsWriter(path, lambda *event: events.put(event),
                            prepare=_migrate_appearance, publish_permissions=False)
    first.submit({("theme", "interface"): "crimson-red"})
    assert first.close(wait=True)
    second.submit({("input_field", "border"): False})
    assert second.close(wait=True)
    saved = json.loads(path.read_text())
    assert saved["theme"] == {"interface": "crimson-red", "text": "monokai"}
    assert saved["input_field"] == {"border": False}
    assert saved["future"] == 1
    assert [events.get_nowait() for _ in range(2)] == [
        ("settings_saved", (1, True)), ("settings_saved", (1, True)),
    ]
    assert events.empty()


def test_settings_writer_serializes_and_coalesces_scoped_changes(tmp_path, monkeypatch):
    import klaude_cli.settings_writer as module

    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"model": "unchanged"}))
    entered, release = threading.Event(), threading.Event()
    events = queue.Queue()
    calls = []
    original = module.update_settings
    def controlled(target, changes):
        calls.append(dict(changes))
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
        return original(target, changes)
    monkeypatch.setattr(module, "update_settings", controlled)
    writer = SettingsWriter(path, lambda kind, payload: events.put(payload))
    try:
        first = writer.submit({("runtime_options", "num_ctx"): 8192})
        assert entered.wait(2)
        writer.submit({("runtime_options", "num_ctx"): 16384})
        last = writer.submit({("runtime_options", "max_steps"): 40})
        release.set()
        assert events.get(timeout=2) == (first, True)
        assert events.get(timeout=2) == (last, True)
        assert len(calls) == 2
        assert json.loads(path.read_text()) == {
            "model": "unchanged", "runtime_options": {"num_ctx": 16384, "max_steps": 40},
        }
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        release.set()
        assert writer.close(wait=True)


def test_failed_settings_intent_is_retried_only_with_next_explicit_save(tmp_path, monkeypatch):
    import klaude_cli.settings_writer as module

    path = tmp_path / "preferences.json"
    events = queue.Queue()
    calls = []
    original = module.update_settings
    def fail_once(target, changes):
        calls.append(dict(changes))
        if len(calls) == 1:
            raise OSError("private diagnostic must not be emitted")
        return original(target, changes)
    monkeypatch.setattr(module, "update_settings", fail_once)
    writer = SettingsWriter(path, lambda kind, payload: events.put(payload))
    try:
        first = writer.submit({("runtime_options", "num_ctx"): 8192})
        assert events.get(timeout=2) == (first, False)
        assert len(calls) == 1
        last = writer.submit({("runtime_options", "max_steps"): 20})
        assert events.get(timeout=2) == (last, True)
        assert json.loads(path.read_text())["runtime_options"] == {"num_ctx": 8192, "max_steps": 20}
    finally:
        assert writer.close(wait=True)


def test_close_drains_accepted_writes_and_rejects_new_submissions(tmp_path, monkeypatch):
    import klaude_cli.settings_writer as module

    entered, release = threading.Event(), threading.Event()
    events = queue.Queue()
    original = module.update_settings
    def slow(path, changes):
        entered.set()
        assert release.wait(2)
        return original(path, changes)
    monkeypatch.setattr(module, "update_settings", slow)
    writer = SettingsWriter(
        tmp_path / "preferences.json", lambda kind, payload: events.put(payload)
    )
    try:
        first = writer.submit({("runtime_options", "num_ctx"): 8192})
        assert entered.wait(2)
        second = writer.submit({("runtime_options", "max_steps"): 40})
        assert not writer.close()
        with pytest.raises(RuntimeError):
            writer.submit({("runtime_options", "max_steps"): 12})
        release.set()
        assert writer.close(wait=True)
        assert events.get(timeout=2) == (first, True)
        assert events.get(timeout=2) == (second, True)
    finally:
        release.set()
        writer.close(wait=True)


def test_two_settings_writers_preserve_independent_client_fields(tmp_path):
    path = tmp_path / "preferences.json"
    events = queue.Queue()
    first = SettingsWriter(path, lambda kind, payload: events.put(payload))
    second = SettingsWriter(path, lambda kind, payload: events.put(payload))
    try:
        first.submit({("runtime_options", "num_ctx"): 16384})
        second.submit({("runtime_options", "max_steps"): 40})
        assert events.get(timeout=2)[1]
        assert events.get(timeout=2)[1]
        assert json.loads(path.read_text())["runtime_options"] == {
            "num_ctx": 16384, "max_steps": 40,
        }
    finally:
        first.close(wait=True)
        second.close(wait=True)


def test_close_reports_unconfirmed_save_instead_of_claiming_rollback(tmp_path, monkeypatch):
    import klaude_cli.settings_writer as module

    events = queue.Queue()
    def failed(path, changes):
        raise OSError("fsync failed after possible publication")
    monkeypatch.setattr(module, "update_settings", failed)
    writer = SettingsWriter(
        tmp_path / "preferences.json", lambda kind, payload: events.put(payload)
    )
    revision = writer.submit({("runtime_options", "num_ctx"): 8192})
    assert events.get(timeout=2) == (revision, False)
    assert not writer.close(wait=True)
    assert not writer._thread.is_alive()


@pytest.mark.parametrize("operations,expected", [
    (["edit", "reset"], None),
    (["reset", "edit"], {"write_file": "allow"}),
    (["preset", "edit", "reset", "edit"], {"write_file": "allow"}),
    (["reset", "edit", "preset"], {"read_file": "deny"}),
])
def test_coalescing_respects_whole_section_reset_and_later_edits(tmp_path, operations, expected):
    from klaude_cli.settings_writer import merge_intent
    from klaude_core.settings_store import DELETE, update_settings

    changes = {}
    for operation in operations:
        change = {
            "edit": {("permissions", "write_file"): "allow"},
            "reset": {("permissions",): DELETE},
            "preset": {("permissions",): {"read_file": "deny"}},
        }[operation]
        changes = merge_intent(changes, change)
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"permissions": {"other": "ask"}, "composer_mode": "vim"}))
    update_settings(path, changes)
    saved = json.loads(path.read_text())
    assert saved.get("permissions") == expected
    assert saved["composer_mode"] == "vim"


def test_coalescing_freezes_mutable_preset_and_preserves_delete_identity():
    from klaude_cli.settings_writer import merge_intent
    from klaude_core.settings_store import DELETE

    policies = {"write_file": "ask"}
    result = merge_intent({}, {("permissions",): policies, ("runtime_options", "num_gpu"): DELETE})
    policies["write_file"] = "allow"
    assert result[("permissions",)] == {"write_file": "ask"}
    assert result[("runtime_options", "num_gpu")] is DELETE


def test_writer_permission_ack_contains_policies_not_private_settings(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({
        "private": "must-not-cross", "permissions": {"read_file": "allow", "secret": "token-value"}
    }))
    events = queue.Queue()
    writer = SettingsWriter(path, lambda kind, payload: events.put((kind, payload)))
    try:
        revision = writer.submit({("permissions", "write_file"): "ask"})
        assert events.get(timeout=2) == ("settings_saved", (revision, True))
        assert events.get(timeout=2) == (
            "settings_permissions", (revision, {"read_file": "allow", "write_file": "ask"})
        )
    finally:
        assert writer.close(wait=True)


def test_writer_tool_ack_is_bounded_boolean_metadata_only(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({
        "private": "token", "display": {"future": "secret", "reasoning_activity": False},
        "tool_availability": {"fetch_url": False, "secret": "token", "numeric": 0},
        "web_provider_availability": {f"provider-{i}": False for i in range(300)},
    }))
    events = queue.Queue()
    writer = SettingsWriter(path, lambda *event: events.put(event), publish_tools=True)
    writer.submit({("tool_validation", "web_search"): False})
    assert writer.close(wait=True)
    assert events.get_nowait() == ("settings_saved", (1, True))
    kind, (revision, values) = events.get_nowait()
    assert kind == "settings_tools" and revision == 1
    assert values["tool_availability"] == {"fetch_url": False}
    assert values["tool_validation"] == {"web_search": False}
    assert values["display"] == {"activity_updates": False}
    assert len(values["web_provider_availability"]) == 256
    assert "token" not in repr(values) and "secret" not in repr(values)
    assert events.empty()
