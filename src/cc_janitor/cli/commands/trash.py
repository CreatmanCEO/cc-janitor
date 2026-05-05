from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta

import typer

from ...core.safety import NotConfirmedError, list_trash, restore_from_trash
from ...core.state import get_paths
from .._audit import audit_action

trash_app = typer.Typer(help="Inspect and manage soft-deleted items in cc-janitor trash")


@trash_app.command("list")
def list_() -> None:
    paths = get_paths()
    items = list_trash(paths)
    if not items:
        typer.echo("Trash is empty.")
        return
    for it in items:
        typer.echo(f"{it.id}  {it.deleted_at}  {it.original_path}")


@trash_app.command("restore")
def restore(trash_id: str) -> None:
    paths = get_paths()
    with audit_action("trash restore", [trash_id]) as changed:
        try:
            dst = restore_from_trash(trash_id, paths=paths)
            changed["restored_to"] = str(dst)
            typer.echo(f"restored → {dst}")
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e
        except FileNotFoundError as e:
            typer.echo(f"trash entry {trash_id} not found", err=True)
            raise typer.Exit(code=1) from e
        except FileExistsError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=1) from e


@trash_app.command("empty")
def empty(
    older_than_days: int = typer.Option(30, "--older-than-days"),
    all_: bool = typer.Option(False, "--all", help="Delete ALL trash, ignoring age"),
) -> None:
    from ...core.safety import require_confirmed
    paths = get_paths()
    items = list_trash(paths)
    if not items:
        typer.echo("Trash already empty.")
        return

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    target = []
    for it in items:
        try:
            t = datetime.fromisoformat(it.deleted_at)
        except ValueError:
            t = None
        if all_ or (t is not None and t < cutoff):
            target.append(it)

    if not target:
        typer.echo(f"Nothing to delete (all items younger than {older_than_days}d).")
        return

    typer.echo(f"Permanently deleting {len(target)} trash buckets.")
    with audit_action("trash empty", [f"--older-than-days={older_than_days}"]) as changed:
        try:
            require_confirmed()
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e
        for it in target:
            bucket = paths.trash / it.id
            shutil.rmtree(bucket, ignore_errors=True)
        changed["deleted_buckets"] = [it.id for it in target]
