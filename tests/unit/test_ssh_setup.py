"""Actual host-key pinning and preserved remote public-key enrollment policies."""

import base64
import queue
import signal
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.session_actions import SSHServerChange
from klaude_cli.settings_panel import PanelAction, RowKind
from klaude_cli.ssh_setup_panel import READ, WORK, SSHSetupPanel
from klaude_core import ssh_enrollment_program as remote_program
from klaude_core.ssh_servers import SSHServer, change, load, run
from klaude_core.ssh_setup import execute, key_info, pin, public_file

from .test_ssh_servers import sshlab


@pytest.fixture
def setup_lab(tmp_path):
    fixture = sshlab.__wrapped__(tmp_path)
    root, server, daemon, original = next(fixture)
    try:
        home = tmp_path / "account"
        home.mkdir(mode=0o700)
        folder = home / ".ssh"
        folder.mkdir(mode=0o700)
        authorized = folder / "authorized_keys"
        authorized.write_bytes(original.read_bytes())
        authorized.chmod(0o600)
        cfg = tmp_path / "sshd_config"
        cfg.write_text(
            cfg.read_text().replace(str(original), str(authorized)) + f"SetEnv HOME={home}\n"
        )
        daemon.send_signal(signal.SIGHUP)
        time.sleep(0.2)
        public = tmp_path / "new-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(public)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        saved = change(root, "add", definition=asdict(server))
        request = {
            "config_dir": str(root),
            "target": server.id,
            "revision": saved["servers"][server.id]["revision"],
            "public_file": str(public) + ".pub",
        }
        yield root, server, request, authorized, public
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass


def test_actual_scan_requires_verified_fingerprint_and_preserves_old_known_hosts(setup_lab):
    root, server, request, _, _ = setup_lab
    before = Path(server.known_hosts).read_bytes()
    result = execute({**request, "operation": "scan"})
    assert result["status"] == "ok", result
    known = Path(server.known_hosts).read_text().split()
    expected = key_info(" ".join(known[1:3]))["fingerprint"]
    assert result["keys"][0]["fingerprint"] == expected
    assert not (root / "model-ssh").exists()
    receipt = {
        **result["keys"][0],
        "host": server.host,
        "port": server.port,
        "observed_at": result["observed_at"],
        "expected_fingerprint": "SHA256:wrong",
    }
    with pytest.raises(ValueError, match="Fingerprint"):
        change(root, "trust", target=server.id, revision=request["revision"], definition=receipt)
    assert not (root / "model-ssh").exists()
    receipt["expected_fingerprint"] = expected
    updated = change(
        root, "trust", target=server.id, revision=request["revision"], definition=receipt
    )
    pinned = SSHServer(**updated["servers"][server.id]["definition"])
    assert pinned.known_hosts != server.known_hosts
    assert Path(pinned.known_hosts).stat().st_mode & 0o077 == 0
    assert run(pinned, "test")["status"] == "ok"
    assert Path(server.known_hosts).read_bytes() == before


def test_actual_enrollment_appends_preserves_bytes_and_enables_new_identity(setup_lab):
    root, server, request, authorized, private = setup_lab
    before = authorized.read_bytes()
    review = execute({**request, "operation": "review"})
    assert review["status"] == "ok", review
    assert review["review"]["target"] == str(authorized)
    assert authorized.read_bytes() == before
    result = execute({**request, "operation": "enroll", "review": review["review"]})
    assert result["status"] == "ok", result
    assert authorized.read_bytes().startswith(before)
    assert authorized.stat().st_mode & 0o077 == 0
    assert run(replace(server, identity_file=str(private)), "test")["status"] == "ok"
    saved = load(root)["servers"][server.id]["definition"]
    assert saved == asdict(server)  # Enrollment does not select the new identity.


def test_enrollment_retains_existing_restricted_key_without_duplicate(setup_lab):
    _, _, request, authorized, private = setup_lab
    addition = (
        b'command="printf restricted",no-port-forwarding '
        + private.with_suffix(".pub").read_bytes()
    )
    authorized.write_bytes(authorized.read_bytes() + addition)
    before = authorized.read_bytes()
    review = execute({**request, "operation": "review"})
    assert review["review"]["present"] is True
    result = execute({**request, "operation": "enroll", "review": review["review"]})
    assert result["status"] == "ok" and result["review"]["effect"] == "already_present"
    assert authorized.read_bytes() == before


@pytest.mark.parametrize("changed", ["remote", "public", "definition"])
def test_stale_review_cannot_overwrite_remote_or_enroll_a_changed_key(setup_lab, changed):
    root, server, request, authorized, private = setup_lab
    review = execute({**request, "operation": "review"})["review"]
    if changed == "remote":
        authorized.write_bytes(authorized.read_bytes() + b"# User policy retained\n")
    elif changed == "public":
        private.with_suffix(".pub").write_text("bad public key\n")
    else:
        change(
            root,
            "edit",
            revision=request["revision"],
            definition=asdict(replace(server, name="Edited")),
        )
    before = authorized.read_bytes()
    result = execute({**request, "operation": "enroll", "review": review})
    assert result["status"] != "ok" and authorized.read_bytes() == before


@pytest.mark.parametrize("unsafe", ["link", "mode"])
def test_remote_unsafe_authorized_keys_fail_without_mutation(setup_lab, unsafe):
    _, _, request, authorized, _ = setup_lab
    original = authorized.read_bytes()
    if unsafe == "link":
        target = authorized.with_name("original-keys")
        authorized.rename(target)
        authorized.symlink_to(target)
    else:
        authorized.chmod(0o666)
    result = execute({**request, "operation": "review"})
    assert result["status"] == "error"
    assert authorized.read_bytes() == original


def test_private_and_symlink_files_are_not_accepted_as_public_keys(setup_lab):
    _, _, _, _, private = setup_lab
    with pytest.raises(ValueError, match="public"):
        public_file(str(private))
    link = private.with_name("link.pub")
    link.symlink_to(private.with_suffix(".pub"))
    with pytest.raises(OSError):
        public_file(str(link))


def test_owned_setup_worker_returns_only_public_metadata(setup_lab):
    _, _, request, _, _ = setup_lab
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    try:
        jobs.submit("setup", {**request, "kind": "ssh_setup", "operation": "review"}, timeout=20)
        kind, payload = events.get(timeout=20)
        assert kind == "background_result" and not payload[3]
        assert payload[2]["status"] == "ok"
        assert "PRIVATE KEY" not in str(payload[2])
    finally:
        jobs.close(wait=True)


@pytest.fixture
def public_key():
    return (
        "ssh-ed25519 " + base64.b64encode(b"\0\0\0\x0bssh-ed25519\0\0\0\x20" + b"K" * 32).decode()
    )


@pytest.fixture
def local_account(tmp_path, monkeypatch, public_key):
    home = tmp_path / "account"
    home.mkdir(mode=0o700)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home, {"operation": "review", "public_key": public_key}


@pytest.mark.parametrize("initial", [None, b"# User policy without final newline"])
def test_remote_program_creates_missing_files_only_after_review_and_preserves_prefix(
    local_account, initial
):
    home, request = local_account
    target = home / ".ssh/authorized_keys"
    if initial is not None:
        target.parent.mkdir(mode=0o700)
        target.write_bytes(initial)
        target.chmod(0o600)
    review = remote_program.execute(request)
    assert target.exists() is (initial is not None)
    outcome = remote_program.execute({**request, "operation": "enroll", **review})
    assert outcome["effect"] == "appended"
    assert target.read_bytes().startswith(initial or b"")
    assert target.stat().st_mode & 0o077 == 0
    assert target.parent.stat().st_mode & 0o077 == 0


def test_post_write_receipt_failure_is_unconfirmed_without_rollback(local_account, monkeypatch):
    home, request = local_account
    review = remote_program.execute(request)
    original = remote_program.present
    calls = []

    def broken_receipt(data, key):
        calls.append(data)
        if len(calls) > 1:
            raise ValueError("Remote receipt changed")
        return original(data, key)

    monkeypatch.setattr(remote_program, "present", broken_receipt)
    outcome = remote_program.execute({**request, **review, "operation": "enroll"})
    assert outcome["effect"] == "unconfirmed"
    assert request["public_key"].encode() in (home / ".ssh/authorized_keys").read_bytes()


def test_host_pin_cannot_bypass_an_existing_revocation(tmp_path, public_key):
    known = tmp_path / "known"
    known.write_text("@revoked |1|hashed|host " + public_key + "\n")
    server = SSHServer("qa", "QA", "localhost", "user", known_hosts=str(known))
    item = key_info(public_key)
    receipt = {
        **item,
        "expected_fingerprint": item["fingerprint"],
        "host": server.host,
        "port": server.port,
        "observed_at": time.time(),
    }
    with pytest.raises(ValueError, match="revoked"):
        pin(tmp_path, server, receipt)
    assert not (tmp_path / "model-ssh").exists()


def test_expired_host_discovery_cannot_create_a_pin(tmp_path, public_key):
    server = SSHServer("qa", "QA", "localhost", "user", known_hosts=str(tmp_path / "missing"))
    item = key_info(public_key)
    receipt = {
        **item,
        "expected_fingerprint": item["fingerprint"],
        "host": server.host,
        "port": server.port,
        "observed_at": time.time() - 121,
    }
    with pytest.raises(ValueError, match="stale"):
        pin(tmp_path, server, receipt)
    assert not (tmp_path / "model-ssh").exists()


def test_public_file_rejects_multiple_keys(tmp_path, public_key):
    path = tmp_path / "multi.pub"
    path.write_text(public_key + "\n" + public_key + "\n")
    path.chmod(0o600)
    with pytest.raises(ValueError, match="one public key"):
        public_file(str(path))


@pytest.fixture
def setup_panel(tmp_path):
    shown, queued, cancelled, inventories = [], [], [], []
    host = SimpleNamespace(
        cfg=SimpleNamespace(config_dir=tmp_path),
        _choice_kind="model manager ssh setup progress",
        _settings_input_request=None,
        _start_next=lambda: queued.append(True),
        _background_jobs=SimpleNamespace(cancel=lambda key: cancelled.append(key)),
    )
    manager = SimpleNamespace(host=host, scope=("session", "data"))
    parent = SimpleNamespace(
        manager=manager,
        host=host,
        inventory={"servers": {}},
        adopt_inventory=lambda value: inventories.append(value),
    )
    panel = SSHSetupPanel(parent)
    panel.target = "qa"
    panel.view = "progress"
    panel.show = lambda *args, **kwargs: shown.append((args, kwargs))
    return panel, shown, queued, cancelled, inventories


@pytest.mark.parametrize("changed", ["draft", "session", "config", "target"])
def test_late_setup_reads_and_enrollment_do_not_steal_new_navigation(setup_panel, changed):
    panel, shown, queued, _, _ = setup_panel
    captured = {
        "id": "work",
        "scope": panel.scope,
        "target": panel.target,
        "revision": panel.revision,
    }
    panel.task = captured
    panel.read = "read", panel.scope, panel.revision, panel.target, "review"
    if changed == "draft":
        panel.revision += 1
    elif changed == "session":
        panel.manager.scope = ("new", "data")
    elif changed == "config":
        panel.host.cfg.config_dir /= "new"
    else:
        panel.target = "new"
    panel.feedback = ("New form", "neutral")
    panel.accept(READ, "read", {"status": "ok", "review": {"target": "old"}}, "")
    panel.accept(WORK, "work", {"status": "ok", "message": "Old success"}, "")
    assert shown == [] and panel.review == {} and panel.feedback[0] == "New form"
    assert panel.task is None and queued == [True]


def test_late_host_save_adopts_inventory_without_replacing_new_form(setup_panel):
    panel, shown, queued, _, inventories = setup_panel
    panel.write = {
        "id": "save",
        "scope": panel.scope,
        "target": panel.target,
        "revision": panel.revision,
    }
    panel.target = "new"
    panel.feedback = ("New form", "neutral")
    update = SSHServerChange("session", "save", str(panel.host.cfg.config_dir), "trust", {})
    panel.saved(update, {"servers": {}}, "")
    assert inventories == [{"servers": {}}] and shown == []
    assert panel.feedback == ("New form", "neutral") and queued == [True]


def test_setup_cancel_keeps_gate_until_worker_acknowledges_cleanup(setup_panel):
    panel, shown, queued, cancelled, _ = setup_panel
    panel.task = {
        "id": "work",
        "scope": panel.scope,
        "target": panel.target,
        "revision": panel.revision,
    }
    panel.stop()
    assert panel.busy and panel.stopping and cancelled == [WORK] and queued == []
    panel.stopped("work")
    assert not panel.busy and not panel.stopping and queued == [True]
    assert panel.feedback[1] == "warning" and "may remain" in panel.feedback[0]
    assert shown[-1][0] == ("home",)


def test_cancel_does_not_replace_a_new_private_editor(setup_panel):
    panel, shown, queued, _, _ = setup_panel
    panel.task = {
        "id": "work",
        "scope": panel.scope,
        "target": panel.target,
        "revision": panel.revision,
    }
    panel.host._settings_input_request = {"field": "new public key"}
    panel.stop()
    panel.stopped("work")
    assert shown == [] and queued == [True] and not panel.busy


def test_back_cancels_pending_setup_review_and_does_not_open_late_result(setup_panel):
    panel, shown, _, cancelled, _ = setup_panel
    panel.read = "read", panel.scope, panel.revision, panel.target, "review"
    panel.action(PanelAction("ssh-setup-back", "home"))
    panel.accept(READ, "read", {"status": "ok", "review": {}}, "")
    assert cancelled == [READ] and len(shown) == 1 and panel.review == {}


def test_setup_review_has_back_and_paging_and_controls_above_fingerprints(setup_panel):
    panel, _, _, _, _ = setup_panel
    panel.view = "enroll-review"
    assert panel.page().scrollable_body and panel.page().scroll_wrapped_rows
    assert panel.page().rows[-1].action.target == "public"
    panel.view = "host"
    panel.read = ("pending",)
    assert panel.page().rows[0].action.kind == "ssh-setup-cancel-check"
    assert panel.page().rows[1].kind is RowKind.ACTION
