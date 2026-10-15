"""Private SSH definitions and bounded read-only diagnostics CLI."""

from __future__ import annotations

import os
import queue
from dataclasses import asdict
from pathlib import Path

import typer
from klaude_core.config import load_config
from klaude_core.ssh_servers import TIMEOUT, SSHServer, change, load
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .background_jobs import OwnedBackgroundJobs

app = typer.Typer(
    help="SSH definitions, reviewed key setup and server diagnostics.", no_args_is_help=True
)
console = Console()


def configuration():
    try:
        cfg = load_config()
        return cfg, load(cfg.config_dir)
    except (OSError, ValueError, KeyError, TypeError):
        console.print(
            Text("SSH settings unreadable; check configuration before retrying", style="red")
        )
        raise typer.Exit(1) from None


def settings(operation: str, target: str, **values):
    try:
        cfg = load_config()
        current = load(cfg.config_dir)
        return change(
            cfg.config_dir,
            operation,
            target=target,
            revision=current["servers"].get(target, {}).get("revision", ""),
            default_revision=current["default_revision"],
            **values,
        )
    except (OSError, ValueError, KeyError, TypeError):
        console.print(Text("SSH settings failed or changed; reload and review again", style="red"))
        raise typer.Exit(1) from None


@app.command("list")
def list_servers():
    """List definitions without connecting."""
    _, current = configuration()
    table = Table("ID", "SERVER", "ADDRESS", "DEFAULT")
    table.add_row(
        "local", "This machine", "Local", "Current" if current["default"] == "local" else ""
    )
    for identity, record in current["servers"].items():
        server = SSHServer(**record["definition"])
        table.add_row(
            identity,
            Text(server.name),
            Text(f"{server.user}@{server.host}:{server.port}"),
            "Current" if current["default"] == identity else "",
        )
    console.print(table)


@app.command("add")
def add_server(
    identity: str,
    host: str = typer.Option(...),
    user: str = typer.Option(...),
    name: str = "SSH server",
    port: int = typer.Option(22, min=1, max=65535),
    identity_file: str = "",
    known_hosts: str = "",
    models_dir: str = "/opt/models",
    agent: bool = False,
):
    """Save metadata and existing key/known-hosts references; test explicitly afterwards."""
    server = SSHServer(
        identity,
        name,
        host,
        user,
        port,
        str(Path(identity_file).expanduser()) if identity_file else "",
        str(Path(known_hosts).expanduser())
        if known_hosts
        else str(Path.home() / ".ssh/known_hosts"),
        models_dir,
        agent,
    )
    settings("add", identity, definition=asdict(server))
    console.print(Text("SSH server saved; not connected or made default", style="green"))


@app.command("default")
def default_server(identity: str):
    """Choose the diagnostics default; local means This machine."""
    settings("default", identity)
    console.print(Text("Diagnostics default saved", style="green"))


@app.command("remove")
def remove_server(identity: str, yes: bool = False):
    """Remove only settings; retain remote files/processes and local keys."""
    if not yes and not typer.confirm(
        "Remove SSH settings and reset its default if selected?", default=False
    ):
        raise typer.Exit(0)
    settings("remove", identity)
    console.print(Text("SSH definition removed", style="green"))


def check(identity: str, operation: str):
    cfg, value = configuration()
    record = value["servers"].get(identity)
    if not record:
        console.print(Text("Choose a saved SSH server ID", style="red"))
        raise typer.Exit(1)
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, payload: events.put((kind, payload)))
    try:
        worker = jobs.submit(
            "ssh",
            {
                "kind": "ssh_servers",
                "operation": operation,
                "config_dir": str(cfg.config_dir),
                "target": identity,
                "revision": record["revision"],
                "agent_socket": os.environ.get("SSH_AUTH_SOCK", ""),
            },
            timeout=TIMEOUT,
        )
        _, payload = events.get()
        if payload[1] != worker or payload[3] or not isinstance(payload[2], dict):
            console.print(Text("SSH check interrupted or unavailable", style="red"))
            raise typer.Exit(1)
        result = payload[2]
        if result.get("status") != "ok":
            console.print(Text(result.get("message", "SSH check failed"), style="red"))
            raise typer.Exit(1)
        console.print(Text(result["message"], style="green"))
        if operation == "inspect":
            data = result["data"]
            console.print(
                Text(
                    f"CPU threads: {data.get('cpu_threads') or 'Unknown'} · "
                    f"RAM bytes: {data.get('ram') or 'Unknown'}\n"
                    f"Models directory: {data['directory_status']}"
                )
            )
            table = Table("MODEL", "TYPE", "STORED BYTES")
            for model in data["models"]:
                size = model["size"]
                table.add_row(
                    Text(model["name"]), model["kind"], "Unknown" if size is None else str(size)
                )
            console.print(table)
    except KeyboardInterrupt:
        jobs.cancel("ssh")
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)


@app.command("test")
def test_server(identity: str):
    """Verify host key, authentication and the fixed diagnostic protocol."""
    check(identity, "test")


@app.command("inspect")
def inspect_server(identity: str):
    """Read bounded remote resource/model/process metadata without mutations."""
    check(identity, "inspect")


def setup_operation(identity: str, operation: str, **values):
    from klaude_core.ssh_setup import TIMEOUT as setup_timeout

    cfg, current = configuration()
    record = current["servers"].get(identity)
    if not record:
        console.print(Text("Choose a saved SSH server ID", style="red"))
        raise typer.Exit(1)
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, payload: events.put((kind, payload)))
    mutation = operation == "enroll"
    try:
        job = jobs.submit(
            "ssh-setup",
            {
                "kind": "ssh_setup",
                "operation": operation,
                "config_dir": str(cfg.config_dir),
                "target": identity,
                "revision": record["revision"],
                "agent_socket": os.environ.get("SSH_AUTH_SOCK", ""),
                **values,
            },
            timeout=setup_timeout,
        )
        _, payload = events.get()
        result = payload[2]
        if payload[1] != job or payload[3] or not isinstance(result, dict):
            console.print(
                Text(
                    "Enrollment unconfirmed; inspect remote keys before retrying"
                    if mutation
                    else "SSH setup check unavailable; retry",
                    style="yellow" if mutation else "red",
                )
            )
            raise typer.Exit(1)
        if result.get("status") != "ok":
            console.print(
                Text(
                    result.get("message", "SSH setup failed"),
                    style="yellow" if result.get("status") == "unknown" else "red",
                )
            )
            raise typer.Exit(1)
        return cfg, result
    except KeyboardInterrupt:
        jobs.cancel("ssh-setup")
        if mutation:
            console.print(Text("Enrollment cancelled; completed append may remain", style="yellow"))
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)


@app.command("host-key")
def host_key(identity: str):
    """Discover candidate public fingerprints; this does not establish trust."""
    _, result = setup_operation(identity, "scan")
    console.print(Text("Verify fingerprints from the server/admin before trusting", style="yellow"))
    for key in result["keys"]:
        console.print(Text(key["fingerprint"]))


@app.command("trust")
def trust_host(identity: str, fingerprint: str, yes: bool = False):
    """Pin an independently verified host fingerprint in private app storage."""
    cfg, result = setup_operation(identity, "scan")
    matching = next((item for item in result["keys"] if item["fingerprint"] == fingerprint), None)
    if not matching:
        console.print(Text("Verified fingerprint does not match the discovered host", style="red"))
        raise typer.Exit(1)
    console.print(Text(f"{result['host']}:{result['port']} · {fingerprint}"))
    if not yes and not typer.confirm(
        "Trust this fingerprint verified from the server/admin?", default=False
    ):
        raise typer.Exit(0)
    try:
        change(
            cfg.config_dir,
            "trust",
            target=identity,
            revision=result["server_revision"],
            definition={
                **matching,
                "expected_fingerprint": fingerprint,
                "host": result["host"],
                "port": result["port"],
                "observed_at": result["observed_at"],
            },
        )
    except (OSError, ValueError):
        console.print(Text("Host trust save failed or changed; reload and review", style="red"))
        raise typer.Exit(1) from None
    console.print(
        Text("Verified host pin saved; existing known-hosts file retained", style="green")
    )


@app.command("enroll")
def enroll_key(identity: str, public_key: str, yes: bool = False):
    """Review and append one existing public key using current verified SSH authentication."""
    public_path = str(Path(public_key).expanduser().absolute())
    _, result = setup_operation(identity, "review", public_file=public_path)
    review = result["review"]
    console.print(Text(f"Public key: {review['fingerprint']}\nRemote file: {review['target']}"))
    console.print(
        Text(
            "Grants SSH access to this account; existing entries/policies are retained", style="dim"
        )
    )
    if not yes and not typer.confirm("Append this public key?", default=False):
        raise typer.Exit(0)
    _, outcome = setup_operation(identity, "enroll", public_file=public_path, review=review)
    console.print(Text(outcome["message"], style="green"))
