"""Local inspection and conditional recovery of Skill Store receipts."""

import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import typer
from klaude_core.config import load_config

app = typer.Typer(help="Inspect and reconcile uncertain Skill Store installs.")


def _run(request_id: str, apply: bool, as_json: bool) -> None:
    from klaude_application.library_management import LibraryManagement

    service = None
    try:
        service = LibraryManagement(load_config(), Path.cwd())
        result = service.reconcile_skill(request_id)
        if apply and result["decision"] in {"proven_no_effect", "verified_complete"}:
            try:
                # Click's input echo can also write to stdout, even with err=True.
                with contextlib.redirect_stdout(sys.stderr if as_json else sys.stdout):
                    confirmed = typer.confirm(result["message"] + " Apply this recovery?",
                                              err=as_json)
            except typer.Abort:
                confirmed = False
            if not confirmed:
                if as_json:
                    typer.echo(json.dumps({**result, "applied": False}, sort_keys=True))
                else:
                    typer.echo("Recovery declined; the resource remains reserved.")
                raise typer.Exit(1)
            result = service.reconcile_skill(
                request_id, apply=True, fingerprint=result["fingerprint"],
            )
        if as_json:
            typer.echo(json.dumps(result, sort_keys=True))
        else:
            typer.echo(f"{request_id}: {result['state']} — {result['message']}")
        if result["decision"] in {"manual_review", "active"}:
            raise typer.Exit(2)
    except typer.Exit:
        raise
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        if as_json:
            typer.echo(json.dumps({"error": "recovery_unavailable", "request_id": request_id}))
        else:
            typer.echo("Recovery unavailable: active work or changed evidence. Inspect again.")
        raise typer.Exit(2) from None
    finally:
        if service is not None:
            service.close()


@app.command("inspect")
def inspect(request_id: str, as_json: bool = typer.Option(False, "--json")) -> None:
    """Inspect local evidence without replaying installation or releasing a fence."""
    _run(request_id, False, as_json)


@app.command("reconcile")
def reconcile(
    request_id: str,
    apply: bool = typer.Option(False, "--apply/--dry-run",
                               help="Review and apply a verified recovery; defaults to dry-run."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect by default; --apply confirms only proven recovery outcomes."""
    _run(request_id, apply, as_json)
