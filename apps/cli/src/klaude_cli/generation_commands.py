"""CLI image jobs using the same owned worker as Library Media."""

from __future__ import annotations

import queue
import uuid
from typing import Any

import typer
from klaude_application.image_generation import ImageGenerationCommand
from klaude_core.image_generation import DEADLINE
from rich.console import Console
from rich.text import Text

from .background_jobs import OwnedBackgroundJobs

console = Console()


def work(cfg: Any, operation: str, **values: Any) -> dict:
    events: queue.Queue = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda kind, value: events.put((kind, value)))
    interrupted = False
    if operation == "save":
        values = {**values, "request_id": uuid.uuid4().hex, "owner_id": "cli"}
    request = ImageGenerationCommand.for_client(cfg, operation, **values).worker_request()
    try:
        identity = jobs.submit(
            "image-generation:cli", request, timeout=DEADLINE + 30 if operation == "run" else 20
        )
        while True:
            kind, payload = events.get()
            if kind == "background_result" and payload[1] == identity:
                result, error = payload[2:]
                return (
                    result
                    if not error and isinstance(result, dict)
                    else {
                        "status": "error",
                        "message": "Image worker unavailable; check job status before retrying",
                    }
                )
    except KeyboardInterrupt:
        interrupted = True
        jobs.cancel("image-generation:cli")
    finally:
        jobs.close(wait=True)
    if interrupted:
        if operation == "run":
            cleanup = work(cfg, "cancel", id=values["spec"]["id"])
            console.print(
                Text(cleanup.get("message", "Server cleanup unconfirmed"), style="yellow")
            )
        raise typer.Exit(130)
    raise typer.Exit(1)


def checked(cfg: Any, operation: str, **values: Any) -> dict:
    result = work(cfg, operation, **values)
    if result.get("status") == "error":
        console.print(Text(result.get("message", "Image operation failed"), style="red"))
        if operation == "run":
            cleanup = work(cfg, "cancel", id=values["spec"]["id"])
            console.print(
                Text(cleanup.get("message", "Server cleanup unconfirmed"), style="yellow")
            )
        raise typer.Exit(1)
    return result
