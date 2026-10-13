"""Model connection registration and diagnostics; settings forms follow in S2."""

from __future__ import annotations

import queue
from dataclasses import asdict
from typing import Any

import typer
from klaude_core.config import load_config, provider_secret_revision
from klaude_core.model_connections import (
    ModelConnection,
    connection_key,
    connection_registry,
    legacy_connections,
)
from klaude_core.model_runtime import model_cache_generation, models_from_records
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .background_jobs import OwnedBackgroundJobs

app = typer.Typer(help="Register and test model endpoints.", no_args_is_help=True)
console = Console()


@app.command("list")
def list_connections() -> None:
    """List endpoint identities without connecting or displaying credentials."""
    cfg = load_config()
    registry = connection_registry(cfg)
    try:
        connections = (
            registry.load()
            if registry.path.exists()
            else {item.id: item for item in legacy_connections(cfg)}
        )
    except (ValueError, OSError) as exc:
        console.print(Text(str(exc), style="red"))
        raise typer.Exit(1) from exc
    table = Table("ID", "ADAPTER", "ENDPOINT", "STATUS")
    for connection in connections.values():
        table.add_row(
            Text(connection.id),
            Text(connection.backend),
            Text(connection.base_url or "Codex account"),
            "Enabled" if connection.enabled else "Disabled",
        )
    console.print(table)


@app.command("add")
def add_connection(
    identity: str = typer.Argument(..., help="Stable lowercase connection ID"),
    adapter: str = typer.Option(
        ..., "--adapter", help="ollama, openai_compatible, deepseek or anthropic"
    ),
    url: str = typer.Option(..., "--url", help="HTTP(S) model API endpoint"),
    name: str = typer.Option("", "--name", help="Display name; defaults to ID"),
    key_env: str = typer.Option("", "--key-env", help="Private API-key environment reference"),
    cloud: bool = typer.Option(False, "--cloud", help="Require HTTPS and use cloud budgeting"),
) -> None:
    """Register a model endpoint without generation or downloading models."""
    if adapter not in {"ollama", "openai_compatible", "deepseek", "anthropic"}:
        raise typer.BadParameter(
            "Choose ollama, openai_compatible, deepseek or anthropic", param_hint="--adapter"
        )
    cfg = load_config()
    try:
        connection = ModelConnection(
            identity,
            name or identity,
            adapter,
            url,
            "Cloud" if cloud or adapter in {"deepseek", "anthropic"} else "Local",
            key_env
            or (
                {"deepseek": "DEEPSEEK_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(adapter, "")
            ),
        )
        registry = connection_registry(cfg)
        registry.migrate(cfg, cfg.data_dir / "chat-preferences.json")
        registry.add(connection)
    except (ValueError, OSError) as exc:
        console.print(Text(str(exc), style="red"))
        raise typer.Exit(1) from exc
    console.print(
        Text(
            f"Saved {connection.id}. Test with: klaude model-connections test {identity}",
            style="green",
        )
    )


@app.command("test")
def test_connection(identity: str = typer.Argument(..., help="Connection ID")) -> None:
    """Check a catalog in a cancellable worker; never generate or load a model."""
    cfg = load_config()
    try:
        registry = connection_registry(cfg)
        connection = registry.migrate(cfg, cfg.data_dir / "chat-preferences.json").get(identity)
        if connection is None:
            raise ValueError("Unknown model connection")
        cache = cfg.data_dir / "model-cache.json"
        scope = f"{connection.backend}@{connection.id}"
        request = {
            "kind": "connection_models",
            "connection": asdict(connection),
            "config_dir": str(cfg.config_dir),
            "key": connection_key(cfg, connection),
            "credential_revision": provider_secret_revision(cfg.config_dir, connection.key_env)
            if connection.key_env
            else "",
            "cache_file": str(cache),
            "generation": model_cache_generation(cache, scope),
        }
        results: queue.Queue[Any] = queue.Queue()
        jobs = OwnedBackgroundJobs(lambda _kind, event: results.put(event))
        try:
            jobs.submit(scope, request, timeout=15)
            with console.status("Checking model catalog…"):
                _scope, _identity, result, error = results.get(timeout=18)
        finally:
            jobs.close(wait=True)
        if error or not isinstance(result, dict):
            raise ValueError(error or "Connection check unavailable")
        if result.get("status") not in {"ok", "empty"}:
            raise ValueError(str(result.get("message") or "Connection check failed"))
        models = models_from_records(result.get("models"))
        console.print(
            Text(
                f"Connected · {len(models)} listed models · tool capabilities unknown",
                style="green",
            )
        )
        for model in models:
            console.print(Text(model.ref))
    except KeyboardInterrupt:
        console.print(Text("Connection check cancelled", style="yellow"))
        raise typer.Exit(130) from None
    except (ValueError, OSError, queue.Empty) as exc:
        console.print(Text(str(exc) or "Connection check timed out", style="red"))
        raise typer.Exit(1) from exc
