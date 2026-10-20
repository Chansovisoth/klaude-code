"""CLI access to the same reviewed Model Manager operations and owned workers."""

from __future__ import annotations

import os
import queue
import sqlite3
import uuid
from dataclasses import asdict, replace
from typing import Any

import typer
from klaude_application.model_dependencies import ModelDependencyCommand
from klaude_application.serving_jobs import ServingJobs
from klaude_application.serving_read import ServingRead
from klaude_core.config import load_config
from klaude_core.managed_serving import LaunchSpec, prepare
from klaude_core.model_dependencies import BUILD_TIMEOUT
from klaude_core.model_setup_removal import REMOVE_TIMEOUT
from klaude_core.ollama_manager import PULL_TIMEOUT, model_name
from klaude_core.ollama_manager import endpoint as manager_endpoint
from klaude_core.ssh_serving import preflight_timeout
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .background_jobs import OwnedBackgroundJobs
from .model_manager import size, worker_request
from .ssh_commands import app as ssh_app

app = typer.Typer(
    help="Manage model downloads, local serving and SSH settings.", no_args_is_help=True
)
app.add_typer(ssh_app, name="ssh")
console = Console()


@app.command("defaults-recover")
def defaults_recover(
    yes: bool = typer.Option(False, "--yes", "-y", help="Run exact-state recovery check"),
) -> None:
    """Reconcile an uncertain Model Defaults save without replaying it."""
    from klaude_application.model_default_settings import (
        model_defaults_resource,
        recover_model_defaults,
    )
    from klaude_application.operation_journal import OperationConflict, OperationJournal

    cfg = load_config()
    path = cfg.data_dir / "operations.db"
    if not path.exists():
        console.print("No journaled Model Defaults changes to recover.")
        return
    try:
        journal = OperationJournal(path)
        fenced = journal.fenced_operation(model_defaults_resource(cfg.data_dir))
        if fenced is None:
            console.print("No unresolved Model Defaults change.")
            return
        receipt = fenced.receipt
        if receipt.state != "unknown":
            raise OperationConflict("Model Defaults save is still active")
        console.print(f"Uncertain Model Defaults change: request {receipt.request_id}")
        if not yes and not typer.confirm(
            "Check the saved Model Defaults and reconcile?", default=False
        ):
            raise typer.Abort()
        resolved = recover_model_defaults(
            cfg, journal, receipt.request_id, fenced.owner_id,
        )
    except (OSError, ValueError, sqlite3.Error, OperationConflict) as exc:
        console.print(f"[yellow]Model Defaults change remains fenced:[/] {exc}")
        raise typer.Exit(1) from None
    if resolved.state == "completed":
        console.print("[green]Recovered:[/] Model Defaults match the reviewed saved state.")
    else:
        console.print("[yellow]Recovered:[/] Model Defaults match the reviewed prior state.")


def dependency_execute(cfg: Any, operation: str, **values) -> dict:
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put((kind, value)))
    try:
        identity = jobs.submit(
            "dependencies",
            ModelDependencyCommand.for_client(
                cfg, operation, owner=os.getpid(), **values
            ).worker_request(),
            timeout=BUILD_TIMEOUT
            if operation == "build"
            else REMOVE_TIMEOUT
            if operation == "remove"
            else 40,
        )
        last_stage = ""
        while True:
            kind, payload = events.get()
            if payload[1] != identity:
                continue
            if kind == "background_progress":
                stage = payload[2]["stage"]
                if stage != last_stage:
                    console.print(Text(stage, style="dim"))
                    last_stage = stage
            elif kind == "background_result":
                result, error = payload[2:]
                if error or not isinstance(result, dict) or result.get("status") == "error":
                    console.print(
                        Text(
                            (result or {}).get(
                                "message",
                                "Removal outcome unconfirmed; reload built/installed engines"
                                if operation == "remove"
                                else "Build outcome unconfirmed; "
                                "reload builds and inspect retained logs",
                            ),
                            style="yellow" if error else "red",
                        )
                    )
                    raise typer.Exit(1)
                return result
    except KeyboardInterrupt:
        jobs.cancel("dependencies")
        console.print(
            Text(
                "Removal cancelled; some files may have been removed; "
                "reload built/installed engines"
                if operation == "remove"
                else "Build cancelled; partial build files retained",
                style="yellow",
            )
        )
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)


@app.command("dependencies")
def dependencies(engine: str = "llama_cpp", executable: str = "llama-server"):
    """Inspect local tools and test an installed engine without installation/generation."""
    result = dependency_execute(load_config(), "inspect", engine=engine, executable=executable)
    tested = result["engine"]
    console.print(
        Text(
            "Engine: "
            + tested["status"]
            + " · "
            + tested.get("message", tested.get("executable", "")),
            style="dim",
        )
    )
    table = Table("TOOL", "STATUS", "VERSION")
    for item in result["tools"]:
        table.add_row(item["name"], item["status"], Text(item.get("version", "")))
    console.print(table)


@app.command("builds")
def list_builds():
    """List retained local build results; interrupted records remain unverified."""
    table = Table("ID", "RECIPE", "REVISION", "STATE", "EXECUTABLE / SOURCE")
    for item in dependency_execute(load_config(), "inventory")["builds"]:
        table.add_row(
            item["id"],
            item.get("profile", "cpu"),
            item["commit"][:12],
            item["state"],
            Text(item.get("executable", item["source"])),
        )
    console.print(table)


@app.command("remove-build")
def remove_build(identity: str, yes: bool = False):
    """Review permanent removal of one unused retained build/install; keep originals."""
    cfg = load_config()
    evidence = dependency_execute(cfg, "prepare_remove", id=identity)["evidence"]
    console.print(
        Text(
            "Remove setup: "
            + identity
            + "\nDirectory: "
            + evidence["directory"]
            + "\nRecipe: "
            + evidence["profile"]
            + "\nState: "
            + evidence["state"]
            + "\nEstimated reclaimable storage: "
            + size(evidence["bytes"])
            + "\nEntries: "
            + str(evidence["entries"]),
        )
    )
    console.print(
        Text(
            "Permanently deletes all files in this setup directory. "
            "Original sources, wheel folders, external model weights, defaults "
            "and server history are retained.",
            style="dim",
        )
    )
    for warning in evidence.get("warnings", []):
        console.print(Text(warning, style="yellow"))
    if evidence["blockers"]:
        for reason in evidence["blockers"]:
            console.print(Text(reason, style="yellow"))
        raise typer.Exit(1)
    if not yes and not typer.confirm("Permanently remove this exact setup?", default=False):
        raise typer.Exit(0)
    result = dependency_execute(cfg, "remove", evidence=evidence)
    console.print(Text(result["message"], style="green"))


@app.command("build")
def build_engine(
    source: str,
    jobs: int = typer.Option(2, min=1, max=8),
    yes: bool = False,
    profile: str = "cpu",
    architectures: str = "",
    host_compiler: str = "",
):
    """Review a separate CPU/CUDA engine build from committed local llama.cpp source."""
    cfg = load_config()
    if profile not in {"cpu", "cuda"}:
        console.print(Text("Choose --profile cpu or cuda", style="red"))
        raise typer.Exit(1)
    evidence = dependency_execute(
        cfg,
        "prepare",
        source=source,
        jobs=jobs,
        profile=profile,
        architectures=architectures,
        host_compiler=host_compiler,
    )["evidence"]
    console.print(
        Text(
            "Build committed source: "
            + evidence["source"]
            + "\nCommit: "
            + evidence["commit"]
            + "\nRecipe: "
            + profile
            + "\nBuild jobs: "
            + str(jobs)
        )
    )
    if evidence.get("cuda"):
        console.print(
            Text(
                "CUDA targets: "
                + evidence["cuda"]["architectures"]
                + "\nCUDA host compiler: "
                + evidence["cuda"]["host_compiler"]
            )
        )
    console.print(
        Text(
            "Runs this commit's CMake/compiler instructions in a new private directory. "
            "Uncommitted edits are excluded; partial/failed builds are retained.",
            style="dim",
        )
    )
    if not yes and not typer.confirm("Build this trusted source?", default=False):
        raise typer.Exit(0)
    result = dependency_execute(cfg, "build", id=uuid.uuid4().hex, evidence=evidence)
    console.print(Text(result["message"], style="green"))
    console.print(Text("Executable: " + result["build"]["executable"]))


@app.command("install-vllm")
def install_vllm(wheelhouse: str, python: str = "", yes: bool = False):
    """Review a separate NVIDIA vLLM environment from trusted local wheels; no downloads."""
    cfg = load_config()
    evidence = dependency_execute(
        cfg, "prepare", source=wheelhouse, profile="vllm_cuda", python=python
    )["evidence"]
    console.print(
        Text(
            "Wheel folder: "
            + evidence["source"]
            + "\nvLLM: "
            + evidence["version"]
            + "\nSource revision: "
            + evidence["commit"]
            + "\nPython: "
            + evidence["tools"]["python"]
            + "\nWheels: "
            + str(len(evidence["wheels"]))
        )
    )
    console.print(
        Text(
            "Installs hash-checked local wheels into a new private environment. "
            "Runs trusted package code for backend/help checks. "
            "Retains partial installs; GPU inference remains untested.",
            style="dim",
        )
    )
    if not yes and not typer.confirm("Install these trusted wheels?", default=False):
        raise typer.Exit(0)
    result = dependency_execute(cfg, "build", id=uuid.uuid4().hex, evidence=evidence)
    console.print(Text(result["message"], style="green"))
    console.print(Text("Executable: " + result["build"]["executable"]))


def execute(cfg: Any, operation: str, **values) -> dict:
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put((kind, value)))
    identity = jobs.submit(
        "manager",
        worker_request(cfg, operation, **values),
        timeout=PULL_TIMEOUT if operation in {"pull", "delete"} else 20,
        notify_cancel=True,
    )
    last_stage = ""
    display = (
        Live(console=console, transient=True, auto_refresh=False)
        if console.is_terminal and operation in {"pull", "delete"}
        else None
    )
    try:
        if display is not None:
            display.start()
        while True:
            kind, payload = events.get()
            if kind == "background_progress":
                _, returned, progress = payload
                if returned == identity:
                    line = progress["stage"]
                    if progress.get("completed") is not None:
                        line += (
                            " · current file "
                            + size(progress["completed"])
                            + " / "
                            + size(progress.get("total"))
                        )
                    if display is not None:
                        display.update(Text(line, style="dim"), refresh=True)
                    elif progress["stage"] != last_stage:
                        console.print(Text(line, style="dim"))
                    last_stage = progress["stage"]
            elif kind == "background_result":
                _, returned, result, error = payload
                if returned != identity:
                    continue
                if error or not isinstance(result, dict):
                    console.print(
                        Text(
                            "Operation outcome unknown; reload the selected server", style="yellow"
                        )
                    )
                    raise typer.Exit(1)
                if result.get("status") not in {None, "ok"}:
                    console.print(Text(result["message"], style="red"))
                    raise typer.Exit(1)
                return result
    except KeyboardInterrupt:
        jobs.cancel("manager")
        console.print(Text("Request cancelled; Ollama may retain download data", style="yellow"))
        raise typer.Exit(130) from None
    finally:
        if display is not None:
            display.stop()
        jobs.close(wait=True)


def inventory(cfg: Any, endpoint: str) -> dict:
    try:
        connection, _ = manager_endpoint(cfg, endpoint)
    except (ValueError, OSError):
        console.print(Text("Choose an enabled native Ollama endpoint", style="red"))
        raise typer.Exit(1) from None
    result = execute(cfg, "inventory", endpoint=endpoint, key_env=connection.key_env)
    if result.get("models") is None:
        console.print(
            Text(result.get("models_error", "Installed inventory unavailable"), style="red")
        )
        raise typer.Exit(1)
    return result


@app.command("list")
def list_models(endpoint: str = "default-ollama", offset: int = typer.Option(0, min=0, max=1000)):
    """List up to 100 downloaded models on one enabled native endpoint."""
    result = inventory(load_config(), endpoint)
    table = Table("MODEL", "STORED SIZE", "STATE")
    loaded = {m["name"] for m in result.get("running") or []}
    for item in result["models"][offset : offset + 100]:
        table.add_row(
            Text(item["name"]),
            Text(size(item["size"])),
            "Unknown"
            if result.get("running") is None
            else "Loaded"
            if item["name"] in loaded
            else "Installed",
        )
    console.print(table)


@app.command("status")
def status(endpoint: str = "default-ollama"):
    """Check catalog, loaded-model status and server version without generation."""
    result = inventory(load_config(), endpoint)
    console.print(Text("Endpoint: " + result["endpoint"]["base_url"]))
    console.print(Text("Ollama version: " + result.get("version", "Unknown")))
    console.print(Text("Installed: " + str(len(result["models"]))))
    console.print(
        Text(
            "Loaded: "
            + (str(len(result["running"])) if result.get("running") is not None else "Unknown")
        )
    )


def mutation(operation: str, model: str, endpoint: str, yes: bool):
    cfg = load_config()
    name = model_name(model)
    snapshot = inventory(cfg, endpoint)
    selected = snapshot["endpoint"]
    existing = next((m for m in snapshot["models"] if m["name"] == name), None)
    console.print(Text(("Delete " if operation == "delete" else "Download ") + name))
    console.print(Text("Server: " + selected["name"] + " · " + selected["base_url"]))
    if not yes and not typer.confirm("Continue?", default=False):
        raise typer.Exit(0)
    result = execute(
        cfg,
        operation,
        endpoint=endpoint,
        model=name,
        revision=selected["revision"],
        credential_revision=selected["credential_revision"],
        key_env=selected.get("key_env", ""),
        digest=existing["digest"] if existing else "",
    )
    console.print(Text(result["message"], style="green"))
    if not result.get("cache_invalidated"):
        console.print(Text("Model cache refresh unconfirmed; reload model choices", style="yellow"))


@app.command("pull")
def pull(model: str, endpoint: str = "default-ollama", yes: bool = False):
    """Review a download; do not load or select the model."""
    try:
        mutation("pull", model, endpoint, yes)
    except ValueError:
        console.print(Text("Invalid Ollama model:tag", style="red"))
        raise typer.Exit(1) from None


@app.command("delete")
def delete(model: str, endpoint: str = "default-ollama", yes: bool = False):
    """Review server-side deletion; selected or loaded models are protected."""
    try:
        mutation("delete", model, endpoint, yes)
    except ValueError:
        console.print(Text("Invalid Ollama model:tag", style="red"))
        raise typer.Exit(1) from None


@app.command("hardware")
def hardware():
    """Inspect this machine's hardware, not a remote server or model-fit guarantee."""
    data = execute(load_config(), "hardware")["hardware"]
    console.print(Text("This machine · RAM " + size(data.get("ram"))))
    for cpu in data.get("cpu", []):
        console.print(Text("CPU: " + (cpu.get("name") or "Unknown")))
    for gpu in data.get("gpu", []):
        console.print(
            Text(
                "GPU: "
                + (gpu.get("name") or "Unknown")
                + " · VRAM "
                + size(gpu.get("memory_bytes"))
            )
        )
    if not data.get("gpu"):
        console.print(Text("GPU information unavailable", style="dim"))


@app.command("search")
def search(query: str):
    """Search up to 20 Hugging Face GGUF repositories using existing credentials."""
    results = execute(load_config(), "search", query=query)["results"]
    table = Table("REPOSITORY", "DOWNLOADS")
    for item in results:
        table.add_row(Text(item["id"]), str(item.get("downloads") or 0))
    console.print(table)


def serving_read(cfg: Any, operation: str, **values) -> dict:
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda _kind, value: events.put(value))
    try:
        jobs.submit(
            "serving",
            ServingRead.for_client(cfg, operation, **values).worker_request(),
            timeout=preflight_timeout(LaunchSpec(**values["spec"]))
            if values.get("spec")
            else preflight_timeout(
                LaunchSpec(values.get("engine", "llama_cpp"), values.get("executable", ""), "")
            ),
        )
        _, _, result, error = events.get()
        if error or not isinstance(result, dict) or result.get("error"):
            message = (
                result.get("error", "Serving inspection failed; check installation")
                if isinstance(result, dict)
                else "Serving inspection failed; retry"
            )
            console.print(Text(message, style="red"))
            raise typer.Exit(1)
        return result
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)


@app.command("adopt")
def adopt_server(
    pid: int,
    model_id: str,
    engine: str = "llama_cpp",
    executable: str = "llama-server",
    port: int = 8080,
    name: str = "Adopted model server",
    yes: bool = False,
    ssh_server: str = "",
    local_port: int = 18080,
):
    """Review ownership of a standalone server; stopping/exiting ends that process."""
    serve_model(
        "",
        engine,
        executable,
        name,
        port,
        adopt_pid=pid,
        model_id=model_id,
        yes=yes,
        ssh_server=ssh_server,
        local_port=local_port,
    )


@app.command("engines")
def engines(engine: str = "llama_cpp", executable: str = "llama-server"):
    """Test an installed engine's help/flags without loading a model."""
    result = serving_read(load_config(), "probe", engine=engine, executable=executable)
    console.print(Text("Engine ready: " + result["executable"], style="green"))


@app.command("servers")
def servers():
    """List managed server records; status remains scoped to the owning client."""
    data = serving_read(load_config(), "inventory")["servers"]
    table = Table("SERVER", "ENGINE", "LAST STATUS", "ENDPOINT")
    for item in data:
        table.add_row(
            Text(item["spec"]["name"]),
            item["spec"]["engine"],
            item["state"],
            Text(item["endpoint"]["base_url"]),
        )
    console.print(table)


@app.command("logs")
def logs(identity: str):
    """Read a bounded private log tail without adding it to model context."""
    console.print(Text(serving_read(load_config(), "logs", id=identity)["logs"]))


@app.command("serve")
def serve_model(
    model: str,
    engine: str = "llama_cpp",
    executable: str = "llama-server",
    name: str = "Local model server",
    port: int = 8080,
    context: int = 8192,
    threads: int = 4,
    gpu_layers: int = 0,
    gpu: str = "0",
    memory: float = 0.5,
    adopt_pid: int = 0,
    model_id: str = "",
    yes: bool = False,
    ssh_server: str = "",
    local_port: int = 18080,
    dtype: str = "auto",
    enforce_eager: bool = False,
):
    """Review an installed local/SSH llama.cpp or NVIDIA vLLM server; run until Ctrl+C."""
    cfg = load_config()
    evidence = (
        {} if ssh_server else serving_read(cfg, "probe", engine=engine, executable=executable)
    )
    spec = LaunchSpec(
        engine,
        executable if ssh_server else evidence["executable"],
        model,
        name,
        port,
        context,
        threads,
        gpu_layers,
        gpu,
        memory,
        adopt_pid,
        model_id,
        ssh_server,
        local_port,
        dtype,
        enforce_eager,
    )
    try:
        if ssh_server:
            from klaude_core.ssh_servers import load

            record = load(cfg.config_dir)["servers"].get(ssh_server)
            if not record:
                raise ValueError("Choose a saved SSH server ID")
            evidence = serving_read(
                cfg,
                "prepare",
                spec=asdict(spec),
                server_revision=record["revision"],
                agent_socket=os.environ.get("SSH_AUTH_SOCK", ""),
            )["evidence"]
            spec = replace(spec, executable=evidence["executable"], model=evidence.get("model", ""))
        else:
            evidence = prepare(spec, evidence)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        from klaude_core.managed_serving import clean

        console.print(
            Text(
                clean(str(exc), 240)
                if isinstance(exc, ValueError)
                else "Serving settings unavailable; check paths and configuration",
                style="red",
            )
        )
        raise typer.Exit(1) from None
    console.print(
        Text(
            f"{name} · {engine} · {spec.model_id if adopt_pid else spec.model}\n"
            f"127.0.0.1:{local_port if ssh_server else port}"
            + (f" · existing PID {adopt_pid}" if adopt_pid else f" · context {context}")
        )
    )
    if ssh_server:
        selected = evidence.get("selected_devices", [])
        device = (
            "existing settings retained"
            if adopt_pid
            else ", ".join(selected)
            if selected
            else "CPU"
        )
        console.print(Text(f"SSH server {ssh_server} · remote loopback port {port} · {device}"))
        if gpu_layers:
            console.print(Text(f"GPU layers: {gpu_layers} · tested device IDs: {gpu}"))
    if engine == "vllm" and not adopt_pid:
        console.print(
            Text(
                f"GPU memory fraction: {memory} · precision: {dtype} "
                f"· eager: {enforce_eager} · 1 sequence"
            )
        )
    console.print(
        Text("This server stops when this command exits; defaults stay unchanged", style="dim")
    )
    if adopt_pid:
        console.print(
            Text(
                "Takes control of this existing process/session; original logs remain unchanged",
                style="yellow",
            )
        )
        if ssh_server:
            console.print(
                Text(
                    "Connection loss stops the adopted server after its owner lease expires",
                    style="yellow",
                )
            )
    if not yes and not typer.confirm(
        "Adopt this existing server?" if adopt_pid else "Launch this server?", default=False
    ):
        raise typer.Exit(0)
    events: queue.Queue = queue.Queue()
    jobs = ServingJobs(lambda kind, value: events.put((kind, value)))
    failed = False
    try:
        jobs.start(
            {
                "id": uuid.uuid4().hex,
                "owner": "CLI",
                "spec": asdict(spec),
                "evidence": evidence,
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "agent_socket": os.environ.get("SSH_AUTH_SOCK", ""),
            }
        )
        while True:
            kind, payload = events.get()
            if kind == "serving_stopped":
                if failed or payload[1]:
                    raise typer.Exit(1)
                break
            event = payload[1]
            failed |= event["state"] == "failed"
            console.print(
                Text(
                    event["message"],
                    style="red"
                    if event["state"] == "failed"
                    else "green"
                    if event["state"] == "ready"
                    else "yellow"
                    if event["state"] == "warning"
                    else "dim",
                )
            )
            if event["state"] == "ready":
                reference = f"openai_compatible@{event['endpoint']['id']}/{event['model']}"
                console.print(
                    Text(f"Endpoint: {event['endpoint']['base_url']}\nModel: {reference}")
                )
    except KeyboardInterrupt:
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)
