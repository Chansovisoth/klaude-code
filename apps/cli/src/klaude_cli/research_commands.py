"""Bounded research CLI, sharing the real owned worker and Library reports."""

from __future__ import annotations

import os
import queue
import uuid
from typing import Any

import typer
from klaude_core.ai_defaults import read_defaults
from klaude_core.config import load_config
from klaude_core.research import ResearchStore, read_research_defaults
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .background_jobs import OwnedBackgroundJobs

app = typer.Typer(help="Run bounded web research and manage durable jobs.", no_args_is_help=True)
console = Console()


def execute(identity: str, cfg: Any) -> None:
    store = ResearchStore(cfg.data_dir / "library")
    item = store.get(identity)
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, payload: events.put((kind, payload)))
    # Private inherited credential values are never serialized in durable job specs.
    keys = {
        name: value
        for name, value in os.environ.items()
        if name.endswith("_API_KEY") and len(value) <= 8192
    }
    from klaude_core.model_connections import connection_registry, legacy_connections

    registry = connection_registry(cfg)
    connections = registry.load().values() if registry.path.exists() else legacy_connections(cfg)
    keys.update(
        {
            entry.key_env: os.environ[entry.key_env]
            for entry in connections
            if entry.key_env in os.environ and len(os.environ[entry.key_env]) <= 8192
        }
    )
    owner = uuid.uuid4().hex
    jobs.submit(
        "research",
        {
            "kind": "research_run",
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "target": identity,
            "owner": owner,
            "environment_keys": keys,
            "native_options": cfg.ollama_options,
        },
        timeout=item["spec"]["settings"]["timeout"] + 5,
        notify_cancel=True,
    )
    phase = ""
    try:
        while True:
            try:
                kind, payload = events.get(timeout=0.5)
            except queue.Empty:
                current = store.get(identity)
                if current["phase"] != phase:
                    phase = current["phase"]
                    console.print(Text(phase, style="dim"))
                continue
            if kind == "background_result":
                _key, _job, result, error = payload
                if error or not isinstance(result, dict):
                    console.print(
                        Text("Research interrupted; resume with fresh evidence", style="yellow")
                    )
                    raise typer.Exit(1)
                status = result.get("status")
                detail = (
                    result.get("report")
                    if status in {"completed", "partial"}
                    else result.get("phase")
                )
                console.print(
                    Text(
                        f"{status}: {detail}",
                        style="green"
                        if status == "completed"
                        else "yellow"
                        if status == "partial"
                        else "red",
                    )
                )
                if status == "partial":
                    raise typer.Exit(2)
                if status != "completed":
                    raise typer.Exit(1)
                return
    except KeyboardInterrupt:
        jobs.cancel("research")
        jobs.close(wait=True)
        store.stop(identity, owner=owner)
        console.print(Text("Research stopped; saved reports retained", style="yellow"))
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)


@app.command("list")
def list_jobs(offset: int = typer.Option(0, min=0, max=1000000)) -> None:
    """Read saved job metadata without model or network work."""
    cfg = load_config()
    data = ResearchStore(cfg.data_dir / "library").listing(offset)
    table = Table("QUESTION", "STATE", "JOB ID")
    for item in data["items"]:
        table.add_row(Text(item["question"]), Text(item["status"]), Text(item["id"]))
    console.print(table)


@app.command("run")
def run_research(
    question: str = typer.Argument(help="Research question"),
    model: str = typer.Option("", help="Qualified model override; otherwise Research/Chat default"),
    provider: str = typer.Option("", help="Search override; auto follows Web Search"),
    rounds: int = typer.Option(0, min=0, max=4, help="Round override; 0 keeps defaults"),
    format: str = typer.Option("report", help="report, brief or comparison"),
    queued: bool = typer.Option(False, "--queue", help="Save without model/search work"),
) -> None:
    """Create a captured job; generate and save a cited report unless queued."""
    cfg = load_config()
    defaults = read_defaults(cfg)
    reference = model or defaults.research or defaults.chat
    if not reference:
        console.print(Text("Select a Research or Chat model first", style="red"))
        raise typer.Exit(1)
    settings = read_research_defaults(cfg).public()
    if provider:
        settings["provider"] = provider
    if rounds:
        settings["rounds"] = rounds
    try:
        from klaude_core.research import execute_research_request

        result = execute_research_request(
            {
                "kind": "research_control",
                "operation": "create",
                "draft": {"question": question, "model": reference, "format": format},
                "settings": settings,
            }
        )
        if result.get("error"):
            raise ValueError(result["error"])
        item = result["item"]
        console.print(Text(f"Research job {item['id']}", style="dim"))
        if not queued:
            execute(item["id"], cfg)
    except (ValueError, OSError):
        console.print(
            Text("Research request rejected; check model, settings and question", style="red")
        )
        raise typer.Exit(1) from None


@app.command("resume")
def resume(identity: str = typer.Argument(help="Exact job ID from research list")) -> None:
    """Resume bounded work; required evidence is fetched again."""
    try:
        execute(identity, load_config())
    except (ValueError, OSError):
        console.print(Text("Job unavailable; check research list", style="red"))
        raise typer.Exit(1) from None
