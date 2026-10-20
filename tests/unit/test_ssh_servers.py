"""Private definitions and actual loopback OpenSSH diagnostics with temporary keys."""

import os
import pwd
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.session_actions import SessionActionWriter, SSHServerChange
from klaude_cli.ssh_panel import SSHPanel
from klaude_core.ssh_servers import SSHServer, arguments, change, decoded, execute, load, run


def test_shared_ssh_commands_reject_unlisted_operations(tmp_path):
    from klaude_application.ssh_operations import (
        SSHDefinitionChange,
        SSHDiagnostic,
        SSHSetupCommand,
    )

    cfg = SimpleNamespace(config_dir=tmp_path / "config")
    diagnostic = SSHDiagnostic.for_client(cfg, "inspect", target="ssh-example", revision="r")
    assert SSHDiagnostic.from_worker(diagnostic.worker_request()) == diagnostic
    setup = SSHSetupCommand.for_client(
        cfg, "review", target="ssh-example", revision="r",
        public_file=str(tmp_path / "key.pub"),
    )
    assert SSHSetupCommand.from_worker(setup.worker_request()) == setup
    with pytest.raises(ValueError, match="Invalid SSH diagnostic"):
        SSHDiagnostic.from_worker({**diagnostic.worker_request(), "operation": "remove"})
    with pytest.raises(ValueError, match="Invalid SSH setup"):
        SSHSetupCommand.from_worker({**setup.worker_request(), "operation": "shell"})
    with pytest.raises(ValueError, match="Invalid SSH definition"):
        SSHDefinitionChange.reviewed(cfg.config_dir, "shell")


def test_shared_ssh_definition_change_rechecks_reviewed_revision(tmp_path):
    from klaude_application.ssh_operations import SSHDefinitionChange

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer("ssh-example", "Example", "example.com", "tester",
                       identity_file=str(tmp_path / "key"),
                       known_hosts=str(tmp_path / "known_hosts"))
    added = SSHDefinitionChange.reviewed(
        root, "add", definition=asdict(server)
    ).apply()
    old_revision = added["servers"][server.id]["revision"]
    SSHDefinitionChange.reviewed(
        root, "edit", definition=asdict(replace(server, name="Updated")),
        target=server.id, revision=old_revision,
    ).apply()
    with pytest.raises(ValueError, match="changed"):
        SSHDefinitionChange.reviewed(
            root, "remove", target=server.id, revision=old_revision,
            default_revision=added["default_revision"],
        ).apply()


def test_journaled_ssh_definition_recovery_never_replays_change(tmp_path, monkeypatch):
    from klaude_application.operation_journal import OperationJournal
    from klaude_application.ssh_operations import (
        SSHChangeUnconfirmed,
        SSHDefinitionChange,
        recover_ssh_definition,
        ssh_resource,
    )

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    journal = OperationJournal(tmp_path / "operations.db")
    request_id = uuid.uuid4().hex

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    with pytest.raises(SSHChangeUnconfirmed, match="recover"):
        SSHDefinitionChange.reviewed(root, "add", definition=asdict(server)).apply_journaled(
            journal, request_id, "cli",
        )
    original = load(root)
    assert server.id in original["servers"]
    assert journal.resource_busy(ssh_resource(root))
    assert b"example.com" not in journal.path.read_bytes()
    recovered = OperationJournal(journal.path)
    receipt = recover_ssh_definition(root, recovered, request_id, "cli")
    assert receipt.state == "completed"
    assert not recovered.resource_busy(ssh_resource(root))
    assert load(root) == original


def test_journaled_ssh_recovery_rejects_changed_definition(tmp_path, monkeypatch):
    from klaude_application.operation_journal import OperationConflict, OperationJournal
    from klaude_application.ssh_operations import (
        SSHChangeUnconfirmed,
        SSHDefinitionChange,
        recover_ssh_definition,
        ssh_resource,
    )

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    journal = OperationJournal(tmp_path / "operations.db")
    request_id = uuid.uuid4().hex

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    with pytest.raises(SSHChangeUnconfirmed):
        SSHDefinitionChange.reviewed(root, "add", definition=asdict(server)).apply_journaled(
            journal, request_id, "cli",
        )
    saved = load(root)
    change(root, "edit", definition=asdict(replace(server, name="Changed")),
           target=server.id, revision=saved["servers"][server.id]["revision"])
    with pytest.raises(OperationConflict, match="differs from both"):
        recover_ssh_definition(root, OperationJournal(journal.path), request_id, "cli")
    assert journal.resource_busy(ssh_resource(root))


def test_journaled_ssh_no_publish_reconciles_prior_state(tmp_path, monkeypatch):
    from klaude_application.operation_journal import OperationJournal
    from klaude_application.ssh_operations import (
        SSHChangeUnconfirmed,
        SSHDefinitionChange,
        recover_ssh_definition,
        ssh_resource,
    )
    from klaude_core import ssh_servers

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    journal = OperationJournal(tmp_path / "operations.db")
    request_id = uuid.uuid4().hex

    def fail_publish(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(ssh_servers, "atomic_write_private", fail_publish)
    with pytest.raises(SSHChangeUnconfirmed):
        SSHDefinitionChange.reviewed(root, "add", definition=asdict(server)).apply_journaled(
            journal, request_id, "cli",
        )
    assert load(root)["servers"] == {}
    assert journal.resource_busy(ssh_resource(root))
    receipt = recover_ssh_definition(root, OperationJournal(journal.path), request_id, "cli")
    assert receipt.state == "failed"
    assert not journal.resource_busy(ssh_resource(root))


def test_journaled_ssh_lost_start_ack_has_recovery_path(tmp_path, monkeypatch):
    from klaude_application.operation_journal import OperationJournal
    from klaude_application.ssh_operations import (
        SSHChangeUnconfirmed,
        SSHDefinitionChange,
        recover_ssh_definition,
    )

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    journal = OperationJournal(tmp_path / "operations.db")
    request_id = uuid.uuid4().hex
    start = journal.start

    def lose_start_ack(*args):
        start(*args)
        raise OSError("start acknowledgement lost")

    monkeypatch.setattr(journal, "start", lose_start_ack)
    with pytest.raises(SSHChangeUnconfirmed, match="recover"):
        SSHDefinitionChange.reviewed(root, "add", definition=asdict(server)).apply_journaled(
            journal, request_id, "cli",
        )
    assert load(root)["servers"] == {}
    assert journal.status(request_id, "cli").state == "unknown"
    assert recover_ssh_definition(
        root, OperationJournal(journal.path), request_id, "cli",
    ).state == "failed"


def test_ssh_writer_requires_journal_when_configured(tmp_path):
    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    events = queue.Queue()
    writer = SessionActionWriter(
        None, lambda *value: events.put(value), require_ssh_journal=True,
    )
    assert writer.submit(SSHServerChange(
        "session", uuid.uuid4().hex, str(root), "add", asdict(server),
    ))
    assert not writer.close(wait=True)
    kind, payload = events.get(timeout=2)
    assert kind == "ssh_server_saved" and "journal unavailable" in payload[2]
    assert load(root)["servers"] == {}


def test_ssh_writer_records_completed_journal_receipt(tmp_path):
    from klaude_application.operation_journal import OperationJournal

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()
    writer = SessionActionWriter(
        None, lambda *value: events.put(value), ssh_journal=journal,
        require_ssh_journal=True,
    )
    request_id = uuid.uuid4().hex
    assert writer.submit(SSHServerChange(
        "session", request_id, str(root), "add", asdict(server),
    ))
    assert writer.close(wait=True)
    kind, payload = events.get(timeout=2)
    assert kind == "ssh_server_saved" and not payload[2]
    receipt = journal.status(request_id, "session")
    assert receipt is not None and receipt.state == "completed"
    assert server.id in load(root)["servers"]


def test_cli_ssh_settings_use_same_journaled_effect(tmp_path, monkeypatch):
    from klaude_application.operation_journal import OperationJournal
    from klaude_cli import ssh_commands

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    monkeypatch.setattr(
        ssh_commands, "load_config",
        lambda: SimpleNamespace(config_dir=root, data_dir=tmp_path),
    )
    saved = ssh_commands.settings("add", server.id, definition=asdict(server))
    assert server.id in saved["servers"]
    receipts = OperationJournal(tmp_path / "operations.db").recent("cli")
    assert len(receipts) == 1 and receipts[0].state == "completed"


def test_cli_ssh_recover_checks_exact_saved_state(tmp_path, monkeypatch, capsys):
    from klaude_application.operation_journal import OperationJournal
    from klaude_application.ssh_operations import SSHChangeUnconfirmed, SSHDefinitionChange
    from klaude_cli import ssh_commands

    root = tmp_path / "config"
    root.mkdir()
    server = SSHServer(
        "ssh-example", "Example", "example.com", "tester",
        identity_file=str(tmp_path / "key"), known_hosts=str(tmp_path / "known_hosts"),
    )
    journal = OperationJournal(tmp_path / "operations.db")
    request_id = uuid.uuid4().hex

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    with pytest.raises(SSHChangeUnconfirmed):
        SSHDefinitionChange.reviewed(root, "add", definition=asdict(server)).apply_journaled(
            journal, request_id, "cli",
        )
    monkeypatch.setattr(
        ssh_commands, "load_config",
        lambda: SimpleNamespace(config_dir=root, data_dir=tmp_path),
    )
    ssh_commands.recover_definitions(yes=True)
    assert "Recovered" in capsys.readouterr().out
    assert OperationJournal(journal.path).status(request_id, "cli").state == "completed"


def test_cli_host_trust_refuses_unresolved_definition_fence(tmp_path, monkeypatch):
    import typer
    from klaude_application.operation_journal import OperationJournal
    from klaude_cli import ssh_commands

    root = tmp_path / "config"
    root.mkdir()
    cfg = SimpleNamespace(config_dir=root, data_dir=tmp_path)
    monkeypatch.setattr(ssh_commands, "setup_operation", lambda *_args: (
        cfg, {"host": "example.com", "port": 22, "observed_at": time.time(),
              "server_revision": "a" * 32,
              "keys": [{"fingerprint": "SHA256:reviewed", "public_key": "ssh-ed25519 AAAA"}]},
    ))
    monkeypatch.setattr(OperationJournal, "resource_busy", lambda *_args: True)
    with pytest.raises(typer.Exit):
        ssh_commands.trust_host("ssh-example", "SHA256:reviewed", yes=True)
    assert load(root)["servers"] == {}


@pytest.fixture
def sshlab(tmp_path):
    tools = [shutil.which(name) for name in ("ssh", "sshd", "ssh-keygen")]
    if not all(tools):
        pytest.skip("Installed OpenSSH client/server/keygen required for local transport fixtures")
    root = tmp_path / "config"
    root.mkdir()
    key, host = tmp_path / "key", tmp_path / "host"
    for path in (key, host):
        subprocess.run(
            [tools[2], "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    authorized = tmp_path / "authorized"
    authorized.write_text(key.with_suffix(".pub").read_text())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    known = tmp_path / "known"
    known.write_text(f"[127.0.0.1]:{port} " + host.with_suffix(".pub").read_text())
    models = tmp_path / "models"
    models.mkdir()
    (models / "demo.gguf").write_bytes(b"GGUFfixture")
    (models / "original.txt").write_text("Remote user content retained")
    (models / "linked.gguf").symlink_to(models / "demo.gguf")
    packed = models / "packed"
    packed.mkdir()
    (packed / "config.json").write_text("{}")
    user = pwd.getpwuid(os.getuid()).pw_name
    cfg = tmp_path / "sshd_config"
    cfg.write_text(f"""ListenAddress 127.0.0.1
Port {port}
HostKey {host}
PidFile {tmp_path / "sshd.pid"}
AuthorizedKeysFile {authorized}
StrictModes no
UsePAM no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers {user}
LogLevel ERROR
""")
    log = (tmp_path / "sshd.log").open("w+")
    process = subprocess.Popen([tools[1], "-D", "-e", "-f", str(cfg)], stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.seek(0)
                pytest.fail("Temporary sshd could not start: " + log.read()[:300])
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.05)
        server = SSHServer(
            "lab", "SSH lab", "127.0.0.1", user, port, str(key), str(known), str(models)
        )
        yield root, server, process, authorized
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=3)
        log.close()


def test_actual_ssh_test_and_readonly_resource_model_inventory(sshlab):
    root, server, _, _ = sshlab
    key_before = open(server.identity_file, "rb").read()
    hosts_before = open(server.known_hosts, "rb").read()
    assert run(server, "test")["status"] == "ok"
    result = run(server, "inspect")
    assert result["status"] == "ok", result
    data = result["data"]
    assert data["ram"] > 0 and data["cpu_threads"] > 0
    assert {m["name"] for m in data["models"]} == {"demo.gguf", "packed"}
    assert data["directory_status"] == "Available"
    assert open(server.identity_file, "rb").read() == key_before
    assert open(server.known_hosts, "rb").read() == hosts_before
    assert not (root / "model-servers.json").exists()


def test_settings_are_private_revisioned_and_do_not_connect(sshlab):
    root, server, _, _ = sshlab
    value = change(root, "add", definition=asdict(server))
    record = value["servers"][server.id]
    assert value["default"] == "local"
    assert (root / "model-servers.json").stat().st_mode & 0o077 == 0
    payload = (root / "model-servers.json").read_text()
    assert "PRIVATE KEY" not in payload
    revised = change(
        root,
        "edit",
        definition=asdict(replace(server, name="Changed")),
        revision=record["revision"],
    )
    assert revised["servers"][server.id]["revision"] != record["revision"]
    with pytest.raises(ValueError, match="changed"):
        change(root, "remove", target=server.id, revision=record["revision"], default_revision="0")


def test_valid_dns_and_ipv6_hosts_are_normalized_for_review(sshlab):
    _, server, _, _ = sshlab
    assert replace(server, host="LAPTOP.Example.").validate().host == "laptop.example"
    assert replace(server, host="0:0:0:0:0:0:0:1").validate().host == "::1"


@pytest.mark.parametrize("failure", ["host_key", "authentication", "network"])
def test_ssh_failures_are_distinct_and_never_auto_trust(sshlab, failure):
    root, server, _, _ = sshlab
    if failure == "host_key":
        open(server.known_hosts, "w").close()
    elif failure == "authentication":
        other = root / "other-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)], check=True
        )
        server = replace(server, identity_file=str(other))
    else:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        server = replace(server, port=port)
    known = open(server.known_hosts, "rb").read()
    result = run(server, "test")
    assert result["status"] == "error" and result["code"] == failure
    assert open(server.known_hosts, "rb").read() == known


def test_remove_default_restores_local_without_changing_key_or_remote_files(sshlab):
    root, server, _, _ = sshlab
    value = change(root, "add", definition=asdict(server))
    value = change(
        root,
        "default",
        target=server.id,
        revision=value["servers"][server.id]["revision"],
        default_revision=value["default_revision"],
    )
    result = change(
        root,
        "remove",
        target=server.id,
        revision=value["servers"][server.id]["revision"],
        default_revision=value["default_revision"],
    )
    assert result["default"] == "local" and result["servers"] == {}
    assert os.path.isfile(server.identity_file) and os.path.isfile(
        server.models_dir + "/original.txt"
    )


def test_fixed_command_uses_stdin_for_shell_sensitive_directory(sshlab):
    _, server, _, _ = sshlab
    server = replace(server, models_dir="/tmp/no-directory; touch /tmp/should-not-be-created-ssh")
    assert server.models_dir not in " ".join(arguments(server))
    result = run(server, "inspect")
    assert result["data"]["directory_status"] == "Unavailable"
    assert not os.path.exists("/tmp/should-not-be-created-ssh")


def test_action_writer_drains_server_settings_without_session_database(sshlab):
    root, server, _, _ = sshlab
    writer = SessionActionWriter(None, lambda *value: events.put(value))
    events = queue.Queue()
    writer._session_unavailable = True
    assert writer.submit(SSHServerChange("session", "request", str(root), "add", asdict(server)))
    assert writer.close(wait=True)
    kind, payload = events.get(timeout=2)
    assert kind == "ssh_server_saved" and not payload[2]
    assert load(root)["servers"][server.id]["definition"] == asdict(server)


def test_owned_diagnostic_worker_uses_saved_definition_and_protocol(sshlab):
    root, server, _, _ = sshlab
    value = change(root, "add", definition=asdict(server))
    request = {
        "kind": "ssh_servers",
        "operation": "inspect",
        "config_dir": str(root),
        "target": server.id,
        "revision": value["servers"][server.id]["revision"],
    }
    assert execute({**request, "revision": "old"})["status"] == "error"
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *value: events.put(value))
    try:
        jobs.submit("ssh", request, timeout=15)
        kind, payload = events.get(timeout=15)
        assert kind == "background_result" and not payload[3]
        assert payload[2]["status"] == "ok"
    finally:
        jobs.close(wait=True)


def test_opted_in_ssh_agent_authenticates_without_forwarding_or_key_storage(sshlab):
    _, server, _, _ = sshlab
    if not shutil.which("ssh-agent") or not shutil.which("ssh-add"):
        pytest.skip("Local OpenSSH agent tools unavailable")
    directory = tempfile.mkdtemp(prefix="klaude-ssh-agent-")
    agent = directory + "/agent"
    process = subprocess.Popen(
        ["ssh-agent", "-D", "-a", agent], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 2
        while not os.path.exists(agent) and time.monotonic() < deadline:
            time.sleep(0.05)
        subprocess.run(
            ["ssh-add", server.identity_file],
            env={**os.environ, "SSH_AUTH_SOCK": agent},
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        selected = replace(server, use_agent=True, identity_file=server.identity_file + ".pub")
        assert run(selected, "test", agent)["status"] == "ok"
        assert "ForwardAgent=no" in arguments(selected, agent)
    finally:
        process.terminate()
        process.wait(timeout=2)
        shutil.rmtree(directory)


def test_malformed_remote_output_is_a_protocol_failure(sshlab):
    _, server, _, authorized = sshlab
    authorized.write_text('command="printf not-json" ' + authorized.read_text())
    result = run(server, "test")
    assert result["status"] == "error" and result["code"] == "protocol"


def test_unresponsive_peer_cancellation_reaps_owned_client(sshlab):
    root, server, _, _ = sshlab
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    accepted = threading.Event()
    stop = threading.Event()

    def peer():
        connection, _ = listener.accept()
        accepted.set()
        stop.wait(5)
        connection.close()

    thread = threading.Thread(target=peer, daemon=True)
    thread.start()
    server = replace(server, port=listener.getsockname()[1])
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *value: events.put(value))
    try:
        value = change(root, "add", definition=asdict(server))
        request = {
            "kind": "ssh_servers",
            "operation": "test",
            "config_dir": str(root),
            "target": server.id,
            "revision": value["servers"][server.id]["revision"],
        }
        worker = jobs.submit("ssh", request, timeout=15, notify_cancel=True)
        assert accepted.wait(3)
        jobs.cancel("ssh")
        kind, payload = events.get(timeout=3)
        assert kind == "background_stopped" and payload == ("ssh", worker)
    finally:
        jobs.close(wait=True)
        stop.set()
        listener.close()
        thread.join(timeout=1)


def test_unresponsive_peer_has_a_bounded_timeout(sshlab):
    _, server, _, _ = sshlab
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    stop = threading.Event()

    def peer():
        connection, _ = listener.accept()
        stop.wait(6)
        connection.close()

    thread = threading.Thread(target=peer, daemon=True)
    thread.start()
    try:
        start = time.monotonic()
        result = run(replace(server, port=listener.getsockname()[1]), "test")
        assert result["code"] == "timeout" and time.monotonic() - start < 6
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=1)


def test_payload_projection_keeps_only_typed_metadata_and_cleans_controls():
    payload = {
        "version": 1,
        "connected": True,
        "models": [{"name": "\x1b[31mx.gguf", "kind": "GGUF", "size": -1}],
        "processes": [],
        "tools": [],
        "ram": True,
        "private_key": "private-token",
        "directory_status": "Available",
    }
    result = decoded(payload, "inspect")
    assert "private_key" not in result and result["ram"] is None
    assert result["models"] == [{"name": "x.gguf", "kind": "GGUF", "size": None}]


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "-oProxyCommand=evil"),
        ("host", "user@host"),
        ("user", "x;echo bad"),
        ("port", True),
        ("port", 0),
        ("models_dir", "/tmp/../etc"),
        ("known_hosts", "${KEY}"),
    ],
)
def test_invalid_ssh_fields_never_become_command_options(sshlab, field, value):
    _, server, _, _ = sshlab
    with pytest.raises(ValueError):
        replace(server, **{field: value}).validate()


@pytest.mark.parametrize("changed", ["draft", "session", "config"])
def test_late_diagnostics_cannot_replace_a_new_page_source_or_draft(sshlab, changed):
    root, server, _, _ = sshlab
    value = change(root, "add", definition=asdict(server))
    host = SimpleNamespace(
        cfg=SimpleNamespace(config_dir=root), _choice_kind=None, _settings_input_request=None
    )
    manager = SimpleNamespace(host=host, scope=("old-session", "data"))
    panel = SSHPanel(manager)
    panel.inventory = value
    panel.target = server.id
    panel.read = ("request", manager.scope, panel.revision, "inspect", server.id, str(root))
    if changed == "draft":
        panel.revision += 1
    elif changed == "session":
        manager.scope = ("new-session", "data")
    else:
        host.cfg.config_dir = root / "other-config"
    panel.accept("request", {"status": "ok", "data": {}, "message": "late"}, "")
    assert panel.reports == {}


def test_connection_retest_preserves_the_real_age_of_inspected_metadata(sshlab):
    root, server, _, _ = sshlab
    value = change(root, "add", definition=asdict(server))
    host = SimpleNamespace(
        cfg=SimpleNamespace(config_dir=root), _choice_kind=None, _settings_input_request=None
    )
    manager = SimpleNamespace(host=host, scope=("session", "data"))
    panel = SSHPanel(manager)
    panel.inventory = value
    panel.target = server.id
    panel.reports[server.id] = {
        "revision": value["servers"][server.id]["revision"],
        "inspected_at": 10,
        "checked_at": 10,
        "data": {"ram": 1024},
    }
    panel.read = ("request", manager.scope, panel.revision, "test", server.id, str(root))
    panel.accept(
        "request",
        {
            "status": "ok",
            "data": {"connected": True},
            "checked_at": 100,
            "message": "SSH connection verified",
        },
        "",
    )
    assert panel.report()["inspected_at"] == 10
    assert panel.report()["data"]["ram"] == 1024 and panel.report()["checked_at"] == 100


def test_definition_changed_during_check_rejects_old_evidence(sshlab, monkeypatch):
    root, server, _, _ = sshlab
    value = change(root, "add", definition=asdict(server))
    old = value["servers"][server.id]["revision"]

    def replace_during_check(*_):
        change(
            root, "edit", definition=asdict(replace(server, name="New definition")), revision=old
        )
        return {"status": "ok", "message": "old evidence"}

    monkeypatch.setattr("klaude_core.ssh_servers.run", replace_during_check)
    result = execute(
        {"config_dir": str(root), "target": server.id, "revision": old, "operation": "test"}
    )
    assert result["status"] == "error" and "changed while checking" in result["message"]
