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


def preparation_review(spec: dict, index: int) -> None:
    prepared = spec.get("preparation", [])
    if index < len(prepared):
        item = prepared[index]
        console.print(Text(f"Prepared: {item['source_width']}×{item['source_height']} → "
                           f"{item['width']}×{item['height']} · {item['detail']}"
                           " · original retained",
                           style="dim"))


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


def vision_work(cfg: Any, operation: str, **values: Any) -> dict:
    import os
    import queue

    from klaude_core.model_connections import connection_registry, legacy_connections
    from klaude_core.vision import ANALYSIS_TIMEOUT, PREPARE_TIMEOUT

    from .background_jobs import OwnedBackgroundJobs

    registry = connection_registry(cfg)
    connections = registry.load().values() if registry.path.exists() else legacy_connections(cfg)
    keys = {
        c.key_env: os.environ[c.key_env]
        for c in connections
        if c.key_env in os.environ and len(os.environ[c.key_env]) <= 8192
    }
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put((kind, value)))
    try:
        identity = jobs.submit(
            "vision",
            {
                "kind": "vision",
                "operation": operation,
                "config_dir": str(cfg.config_dir),
                "data_dir": str(cfg.data_dir),
                "ollama_url": cfg.ollama_url,
                "roles": dict(cfg.models),
                "environment_keys": keys,
                **values,
            },
            timeout=PREPARE_TIMEOUT if operation in {"prepare", "tags_prepare"}
            else 20 if operation == "tags_apply"
            else ANALYSIS_TIMEOUT * len(values["spec"]["models"]),
        )
        while True:
            kind, payload = events.get()
            if kind != "background_result" or payload[1] != identity:
                continue
            result, error = payload[2:]
            if error or not isinstance(result, dict) or result.get("status") == "error":
                console.print(
                    Text(
                        result.get("message", "Vision request failed")
                        if isinstance(result, dict)
                        else "Vision request failed",
                        style="red",
                    )
                )
                raise typer.Exit(1)
            return result
    except KeyboardInterrupt:
        jobs.cancel("vision")
        raise typer.Exit(130) from None
    finally:
        jobs.close(wait=True)


@app.command("analyze")
def analyze_image(
    identity: ArtifactID,
    question: str,
    yes: bool = False,
    context: int = 4096,
    output_tokens: int = 512,
) -> None:
    """Review explicit image analysis using Model Defaults Vision; no indexing or tools."""
    cfg = load_config()
    item = run(lambda: ArtifactStore(cfg.data_dir / "library").get(identity))
    spec = vision_work(
        cfg,
        "prepare",
        artifact=identity,
        revision=item["revision"],
        question=question,
        context=context,
        output_tokens=output_tokens,
    )["spec"]
    console.print(
        Text(
            f"{item['name']} · {item['size']:,} B\n{question}\n"
            f"{context} context · {output_tokens} output tokens · 90s per model"
        )
    )
    if any(model.get("backend") != "ollama" for model in spec["models"]):
        console.print(Text("Context bounds Klaude's input estimate; HTTP server allocation "
                           "stays unchanged.", style="dim"))
    for index, model in enumerate(spec["models"]):
        preparation_review(spec, index)
        console.print(
            Text(
                f"{'Model' if not index else 'Fallback ' + str(index)}: "
                f"{model['reference']} · {model['endpoint']}"
            )
        )
    if not yes and not typer.confirm("Send this image and question for analysis?", default=False):
        return
    result = vision_work(cfg, "analyze", spec=spec)
    console.print(Text("Used model: " + result["model"], style="dim"))
    console.print(Text(result["text"]))


@app.command("suggest-tags")
def suggest_image_tags(
    identity: ArtifactID, save: bool = False, select: str = "", yes: bool = False,
    context: int = 4096, output_tokens: int = 512,
) -> None:
    """Review optional Vision tag suggestions; --save explicitly retains selected AI tags."""
    try:
        indices = [int(value.strip()) for value in select.split(",")] if select else []
        if len(indices) > 20 or any(not 1 <= value <= 20 for value in indices):
            raise ValueError
    except ValueError:
        raise typer.BadParameter("--select uses comma-separated tag numbers, 1–20") from None
    if select and not save:
        raise typer.BadParameter("--select requires --save")
    cfg = load_config()
    item = run(lambda: ArtifactStore(cfg.data_dir / "library").get(identity))
    spec = vision_work(cfg, "tags_prepare", artifact=identity, revision=item["revision"],
                       context=context, output_tokens=output_tokens)["spec"]
    console.print(Text(f"{item['name']} · {item['size']:,} B\n"
                       f"{context} context · {output_tokens} output tokens · 90s per model\n"
                       "Suggest visible objects, colors and style tags; no automatic save."))
    for index, model in enumerate(spec["models"]):
        preparation_review(spec, index)
        console.print(Text(f"{'Model' if not index else 'Fallback ' + str(index)}: "
                           f"{model['reference']} · {model['endpoint']}"))
    if not yes and not typer.confirm("Send this image for tag suggestions?", default=False):
        return
    result = vision_work(cfg, "tags_suggest", spec=spec)
    console.print(Text("Used model: " + result["model"], style="dim"))
    for index, tag in enumerate(result["tags"], 1):
        console.print(Text(f"{index}. {tag}"))
    if not save:
        console.print(Text("Suggestions not saved. Use --save or select tags in Media.",
                           style="dim"))
        return
    if any(index > len(result["tags"]) for index in indices):
        raise typer.BadParameter("--select refers to an unavailable suggestion; no tags saved")
    selected = [result["tags"][index - 1] for index in indices] if indices else result["tags"]
    console.print(Text("AI tags: " + ", ".join(selected) + "\nManual tags are retained."))
    if not yes and not typer.confirm("Save these AI tags?", default=False):
        return
    vision_work(cfg, "tags_apply", spec=spec, proposal=result, selected=selected)
    console.print(Text("AI tags saved; manual tags retained", style="green"))


@app.command("clear-ai-tags")
def clear_image_tags(identity: ArtifactID, yes: bool = False) -> None:
    """Remove AI tags and their provenance; retain manual tags, pixels and other artifacts."""
    item = run(lambda: store().get(identity))
    console.print(Text(item["name"] + "\nAI tags: " + ", ".join(item["ai_tags"])))
    if not yes and not typer.confirm("Clear AI tags and retain manual tags?", default=False):
        return
    run(lambda: store().change(identity, item["revision"], "clear_ai_tags"))
    console.print(Text("AI tags cleared; manual tags retained", style="green"))


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
            Text(", ".join(item["tags"]) + (" · AI: " + ", ".join(item["ai_tags"])
                                            if item["ai_tags"] else "")),
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
    if sources := run(lambda: store().tagging_info(identity)):
        console.print(Text("AI tag provenance: " + str(sources)))
    for line in data.get("lines", []):
        console.print(Text(line))
    if provenance := run(lambda: store().generation_info(identity)):
        console.print(Text("Generation prompt: " + provenance["prompt"]))
        console.print(Text("Generation endpoint: " + provenance["settings"]["endpoint"]))
        console.print(Text("Generation seed: " + str(provenance["seed"])))
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


@app.command("image-service")
def image_service(
    endpoint: str = typer.Option("", help="Existing stable-diffusion.cpp native server root"),
    enable: bool = typer.Option(False, help="Enable this tested service explicitly"),
    disable: bool = typer.Option(False, help="Disable generation; retain endpoint/model"),
    yes: bool = typer.Option(False, help="Confirm saving this exact service and model"),
) -> None:
    """Inspect or review/save a local image service; no generation or model loading."""
    from .generation_commands import checked

    cfg = load_config()
    saved = checked(cfg, "read")["settings"]
    if not endpoint and not enable and not disable:
        for key, value in saved.items():
            if key != "revision":
                console.print(Text(f"{key}: {value}"))
        return
    if enable and disable:
        raise typer.BadParameter("Choose --enable or --disable")
    candidate = dict(saved)
    if not disable:
        evidence = checked(cfg, "inspect", endpoint=endpoint or saved["endpoint"])["evidence"]
        candidate.update(endpoint=evidence["endpoint"], model=evidence["model"])
    candidate["enabled"] = False if disable else enable
    state = "ON" if candidate["enabled"] else "OFF"
    console.print(Text(
        f"stable-diffusion.cpp · {candidate['endpoint']}\n"
        f"Loaded model: {candidate['model']}\nGeneration: {state}\nNo chat/default model changes."
    ))
    if not yes and not typer.confirm("Save this image service?", default=False):
        return
    checked(cfg, "save", settings=candidate, revision=saved["revision"])
    console.print(Text("Image service saved", style="green"))


@app.command("generate")
def generate_image(
    prompt: str,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    seed: int = -1,
    yes: bool = typer.Option(False, help="Accept the exact reviewed generation and Media save"),
) -> None:
    """Review one local image generation; save PNG/provenance privately in Media."""
    from klaude_core.image_generation import cancellation_notice

    from .generation_commands import checked

    cfg = load_config()
    spec = checked(cfg, "prepare", prompt=prompt,
                   options={"width": width, "height": height, "steps": steps, "seed": seed})["spec"]
    console.print(Text(
                       f"{spec['settings']['endpoint']}\n"
                       f"Loaded model: {spec['settings']['model']}\n"
                       f"{spec['prompt']}\n{width} × {height} · {steps} steps · "
                       f"seed {spec['seed']}\n"
                       "One PNG · 5-minute deadline · saved in Media with provenance · "
                       "no automatic retry"))
    console.print(Text(
        cancellation_notice(spec["evidence"]),
        style="yellow" if not spec["evidence"]["cancel_generating"] else "",
    ))
    if not yes and not typer.confirm("Generate and save this image?", default=False):
        return
    console.print(Text("Job: " + spec["id"]))
    result = checked(cfg, "run", spec=spec)
    console.print(Text("Saved " + result["artifact"], style="green"))


@app.command("generation-status")
def generation_status(
    identity: str, cancel: bool = False, recover: bool = False, refresh: bool = False,
    forget: bool = False, abandon: bool = False, yes: bool = False,
) -> None:
    """Read a private local job receipt; never resubmit an unknown generation."""
    from .generation_commands import checked

    if sum((cancel, recover, refresh, forget)) > 1:
        raise typer.BadParameter("Choose one of --cancel, --recover, --refresh or --forget")
    if abandon and not forget:
        raise typer.BadParameter("--abandon requires --forget")
    cfg = load_config()
    result = checked(cfg, "status", id=identity)
    if recover:
        spec = checked(cfg, "recovery_review", id=identity)["spec"]
        console.print(Text(
            f"Job: {identity}\nEndpoint: {spec['settings']['endpoint']}\n"
            f"Model: {spec['settings']['model']}\n{spec['prompt']}\n"
            f"{spec['width']} × {spec['height']} · {spec['steps']} steps · seed {spec['seed']}\n"
            "Retrieve already-completed output into Media; never resubmit generation."
        ))
        if not yes and not typer.confirm("Recover this exact image output?", default=False):
            return
        result = checked(cfg, "recover", id=identity, spec=spec)
    elif cancel:
        console.print(Text(
            f"Job: {identity}\nEndpoint: {result['endpoint']}\nModel: {result['model']}"
        ))
        if not yes and not typer.confirm("Stop this exact saved image job?", default=False):
            return
        result = checked(cfg, "cancel", id=identity)
    elif refresh:
        console.print(Text(f"Job: {identity}\nEndpoint: {result['endpoint']}\n"
                           f"Model: {result['model']}"))
        if not yes and not typer.confirm("Check this exact job on its server?", default=False):
            return
        result = checked(cfg, "refresh", id=identity)
    elif forget:
        spec = checked(cfg, "review_job", id=identity)["record"]
        if spec["status"] not in {"complete", "completed_remote", "failed", "cancelled"}:
            if not abandon:
                raise typer.BadParameter("Outcome is unconfirmed; --abandon explicitly removes "
                                         "local tracking without stopping server work")
            console.print(Text("Server work may continue and an active client may recreate "
                               "its receipt. Only local tracking is being abandoned.",
                               style="yellow"))
        console.print(Text(f"Job: {identity}\nEndpoint: {result['endpoint']}\n"
                           f"Model: {result['model']}\n"
                           "Remove the private prompt/job receipt only. Media images remain. "
                           "Unrecovered output loses its local recovery reference. "
                           "No server cancellation is sent."))
        if not yes and not typer.confirm("Remove this exact private job receipt?", default=False):
            return
        result = checked(cfg, "forget", id=identity, spec=spec, abandon=abandon)
    for key, value in result.items():
        console.print(Text(f"{key}: {value}"))


@app.command("generation-jobs")
def generation_jobs(offset: int = typer.Option(0, min=0, max=1000)) -> None:
    """List private image job metadata; no network, prompt exposure or generation."""
    from rich.table import Column

    from .generation_commands import checked

    data = checked(load_config(), "history", offset=offset)
    table = Table(Column("JOB", min_width=32, no_wrap=True), "STATUS / MODEL")
    for item in data["items"]:
        detail = item["status"] + "\n" + item["model"]
        if item["artifact"]:
            detail += "\nSaved: " + item["artifact"]
        if console.width < 70:
            console.print(Text(item["job"] + "\n" + detail + "\n"))
        else:
            table.add_row(Text(item["job"]), Text(detail, overflow="fold"))
    if console.width >= 70:
        console.print(table)
    if data["invalid"]:
        console.print(Text(f"{data['invalid']} unreadable receipts omitted", style="yellow"))
    if data["more"]:
        console.print(Text(f"More available · repeat with --offset {offset + 100}", style="dim"))
