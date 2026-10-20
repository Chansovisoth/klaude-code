"""Shared preferences observe terminal writes and reject stale same-field edits."""

import json
import multiprocessing
from pathlib import Path

import pytest
from klaude_application.settings import ChatSettings
from klaude_core.settings_store import SettingsConflictError, update_settings


def test_shared_provider_secret_change_is_write_only_and_revisions_on_remove(tmp_path):
    from klaude_application.provider_secrets import ProviderSecretUpdate
    from klaude_core.config import provider_secret_revision, provider_secret_value

    root = tmp_path / "config"
    action = ProviderSecretUpdate(root, "TEST_PROVIDER_KEY", "private-key")
    assert "private-key" not in repr(action)
    action.apply()
    before = provider_secret_revision(root, "TEST_PROVIDER_KEY")
    assert provider_secret_value(root, "TEST_PROVIDER_KEY") == "private-key"
    ProviderSecretUpdate(root, "TEST_PROVIDER_KEY", "").apply()
    assert provider_secret_revision(root, "TEST_PROVIDER_KEY") != before
    assert provider_secret_value(root, "TEST_PROVIDER_KEY") == ""


def _competing_patch(path: str, barrier, output, value: str) -> None:
    shared = ChatSettings(Path(path))
    revision = shared.read("composer_mode").revision
    barrier.wait(timeout=5)
    try:
        shared.patch("composer_mode", value, expected_revision=revision)
        output.put("saved")
    except SettingsConflictError:
        output.put("conflict")


def _same_patch(path: str, barrier, output, revision: str) -> None:
    shared = ChatSettings(Path(path))
    barrier.wait(timeout=5)
    result = shared.patch("composer_mode", "vim", expected_revision=revision,
                          request_id="shared-patch")
    output.put((result.value, result.revision))


def test_two_processes_replay_one_settings_mutation(tmp_path):
    path = tmp_path / "chat-preferences.json"
    revision = ChatSettings(path).read("composer_mode").revision
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    output = context.Queue()
    workers = [context.Process(target=_same_patch,
                               args=(str(path), barrier, output, revision)) for _ in range(2)]
    for worker in workers:
        worker.start()
    try:
        for worker in workers:
            worker.join(10)
            assert worker.exitcode == 0
        assert output.get(timeout=2) == output.get(timeout=2)
        assert ChatSettings(path).read("composer_mode").value == "vim"
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)


def test_two_processes_cannot_both_commit_stale_same_field(tmp_path):
    path = tmp_path / "chat-preferences.json"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    output = context.Queue()
    workers = [
        context.Process(target=_competing_patch, args=(str(path), barrier, output, value))
        for value in ("vim", "standard")
    ]
    for worker in workers:
        worker.start()
    try:
        for worker in workers:
            worker.join(10)
            assert worker.exitcode == 0
        assert sorted(output.get(timeout=2) for _ in workers) == ["conflict", "saved"]
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)


def test_settings_merge_unrelated_terminal_edit_and_reject_stale_field(tmp_path):
    path = tmp_path / "chat-preferences.json"
    shared = ChatSettings(path)
    initial = shared.read("composer_mode")
    assert initial.value == "standard"
    update_settings(path, {("unrelated",): {"keep": True}})
    saved = shared.patch("composer_mode", "vim", expected_revision=initial.revision)
    assert saved.value == "vim"
    assert json.loads(path.read_text())["unrelated"] == {"keep": True}
    with pytest.raises(SettingsConflictError, match="reload and retry"):
        shared.patch("composer_mode", "standard", expected_revision=initial.revision)
    update_settings(path, {("composer_mode",): "standard"})
    with pytest.raises(SettingsConflictError):
        shared.patch("composer_mode", "vim", expected_revision=saved.revision)


def test_settings_request_receipt_is_atomic_and_survives_later_edits(tmp_path):
    path = tmp_path / "chat-preferences.json"
    shared = ChatSettings(path)
    original = shared.read("composer_mode")
    first = shared.patch("composer_mode", "vim", expected_revision=original.revision,
                         request_id="set-vim")
    assert shared.patch("composer_mode", "vim", expected_revision=original.revision,
                        request_id="set-vim") == first
    update_settings(path, {("composer_mode",): "standard"})
    assert shared.patch("composer_mode", "vim", expected_revision=original.revision,
                        request_id="set-vim") == first
    assert shared.read("composer_mode").value == "standard"
    with pytest.raises(ValueError, match="different input"):
        shared.patch("composer_mode", "standard",
                     expected_revision=original.revision, request_id="set-vim")
    receipts = json.loads(path.read_text())["_application_chat_setting_receipts"]
    assert list(receipts) == ["set-vim"]


def test_activity_setting_observes_legacy_value_and_validates_input(tmp_path):
    path = tmp_path / "chat-preferences.json"
    shared = ChatSettings(path)
    initial = shared.read("activity_updates")
    assert initial.value is True
    update_settings(path, {("display", "reasoning_activity"): False})
    assert shared.read("activity_updates").value is False
    with pytest.raises(SettingsConflictError):
        shared.patch("activity_updates", True, expected_revision=initial.revision)
    current = shared.read("activity_updates")
    saved = shared.patch("activity_updates", True, expected_revision=current.revision)
    assert saved.value is True
    assert json.loads(path.read_text())["display"] == {
        "reasoning_activity": False, "activity_updates": True,
    }
    with pytest.raises(ValueError, match="boolean"):
        shared.patch("activity_updates", "true", expected_revision=saved.revision)


def test_settings_reject_corrupt_or_symlinked_file(tmp_path):
    path = tmp_path / "chat-preferences.json"
    shared = ChatSettings(path)
    path.write_text("broken")
    with pytest.raises(OSError, match="invalid"):
        shared.read("composer_mode")
    path.unlink()
    target = tmp_path / "target.json"
    target.write_text("{}")
    path.symlink_to(target)
    with pytest.raises(PermissionError, match="symlink"):
        shared.patch("composer_mode", "vim", expected_revision="anything")
    assert target.read_text() == "{}"
