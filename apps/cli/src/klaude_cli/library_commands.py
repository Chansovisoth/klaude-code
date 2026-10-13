"""Explicit durable-artifact commands; knowledge-library commands stay separate."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from klaude_core.config import load_config
from klaude_core.library_artifacts import ArtifactStore, execute_artifact_change
from rich.console import Console
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    help="Manage document and image copies; no automatic indexing.", no_args_is_help=True
)
console = Console()
ArtifactID = Annotated[str, typer.Argument(help="Exact typed artifact ID from library list")]


def store() -> ArtifactStore:
    return ArtifactStore(load_config().data_dir / "library")


def run(action: Callable[[], Any]) -> Any:
    try:
        return action()
    except ValueError as exc:
        console.print(Text(str(exc), style="red"))
    except FileExistsError:
        console.print(Text("Export file already exists; choose a new filename", style="red"))
    except FileNotFoundError:
        console.print(Text("File or directory does not exist", style="red"))
    except (OSError, sqlite3.Error):
        console.print(Text("Artifact operation failed; reload before retrying", style="red"))
    raise typer.Exit(1)


@app.command("list")
def list_artifacts(
    kind: str = typer.Option("all", "--type", help="all, document, media or research"),
    archived: bool = typer.Option(False, "--archived", help="Show archived copies only"),
    search: str = typer.Option("", help="Names, tags, file types or source paths"),
    offset: int = typer.Option(0, min=0, max=1_000_000, help="Skip records; page size 100"),
    sort: str = typer.Option("newest", help="newest, oldest or name"),
) -> None:
    """Browse metadata without reading content, calling models or indexing."""
    data = run(
        lambda: store().listing(kind, archived=archived, query=search, offset=offset, sort=sort)
    )
    table = Table("ARTIFACT", "TYPE / SIZE", "TAGS", "ID")
    for item in data["items"]:
        table.add_row(
            Text(item["name"]),
            Text(f"{item['kind']} · {item['size']:,} B"),
            Text(", ".join(item["tags"])),
            Text(item["id"]),
        )
    console.print(table)
    if data["more"]:
        console.print(Text(f"More available · repeat with --offset {offset + 100}", style="dim"))


@app.command("import")
def import_artifact(
    path: Annotated[Path, typer.Argument(help="Regular file to copy; original retained")],
    kind: str = typer.Option("document", "--type", help="document or media"),
) -> None:
    """Store a private copy up to 32 MiB; imported does not mean learned."""
    item = run(lambda: store().import_file(path, kind))
    console.print(Text(f"Imported {item['id']} · original retained · not indexed", style="green"))


@app.command("info")
def artifact_info(identity: ArtifactID) -> None:
    """Show bounded metadata and a text or image-metadata preview."""
    data = run(lambda: store().preview(identity))
    for key, value in data["item"].items():
        console.print(Text(f"{key}: {value}"))
    for line in data.get("lines", []):
        console.print(Text(line))
    if data.get("fallback"):
        console.print(Text(data["fallback"], style="dim"))
    if data.get("truncated"):
        console.print(
            Text("Preview bounded to 100 lines / 16 KiB / 500 characters per line", style="dim")
        )


@app.command("export")
def export_artifact(
    identity: ArtifactID,
    destination: Annotated[Path, typer.Argument(help="New file inside current workspace")],
) -> None:
    """Export exact bytes; existing files are never overwritten."""
    result = run(
        lambda: execute_artifact_change(
            store().root,
            "export",
            target=identity,
            revision=store().get(identity)["revision"],
            value=str(destination),
            workspace=Path.cwd(),
        )
    )
    console.print(Text("Exported copy · " + result["path"], style="green"))


@app.command("tags")
def tag_artifact(
    identity: ArtifactID,
    value: str = typer.Argument(..., help="Comma-separated tags; empty string removes tags"),
) -> None:
    """Replace manual tags without generating tags or altering content."""
    item = run(lambda: store().get(identity))
    run(lambda: store().change(identity, item["revision"], "tags", value))
    console.print(Text("Tags saved", style="green"))


def lifecycle(identity: str, operation: str) -> None:
    instance = store()
    item = run(lambda: instance.get(identity))
    if operation == "delete":
        if not item["archived"]:
            console.print(Text("Archive the artifact before permanent deletion", style="red"))
            raise typer.Exit(1)
        if not typer.confirm(
            "Delete the managed copy and metadata? Originals and learned knowledge remain",
            default=False,
        ):
            raise typer.Exit(0)
    run(lambda: instance.change(identity, item["revision"], operation))
    console.print(
        Text(
            {
                "archive": "Artifact archived · content retained",
                "restore": "Artifact restored",
                "delete": "Artifact deleted",
            }[operation],
            style="green",
        )
    )


@app.command("archive")
def archive_artifact(identity: ArtifactID) -> None:
    """Hide the managed copy; retain content for restore."""
    lifecycle(identity, "archive")


@app.command("restore")
def restore_artifact(identity: ArtifactID) -> None:
    """Return an archived managed copy to its original view."""
    lifecycle(identity, "restore")


@app.command("delete")
def delete_artifact(identity: ArtifactID) -> None:
    """Confirm permanent deletion of an archived managed copy."""
    lifecycle(identity, "delete")
