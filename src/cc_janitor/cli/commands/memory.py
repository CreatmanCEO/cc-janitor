from __future__ import annotations

import json
from pathlib import Path

import typer

from ...core.memory import (
    archive_memory_file,
    discover_memory_files,
    find_duplicate_lines,
    move_memory_type,
    open_in_editor,
)
from .._audit import audit_action

memory_app = typer.Typer(no_args_is_help=True, help="Memory file management")


def _resolve(name: str) -> Path:
    for m in discover_memory_files(include_archived=True):
        if m.path.name == name or str(m.path) == name:
            return m.path
    raise typer.BadParameter(f"Memory file not found: {name}")


@memory_app.command("list")
def list_cmd(
    type_filter: str | None = typer.Option(None, "--type"),
    project: str | None = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
):
    items = discover_memory_files(type_filter=type_filter, project=project)
    if json_out:
        data = [
            {
                "path": str(m.path),
                "type": m.type,
                "size": m.size_bytes,
                "lines": m.line_count,
                "modified": m.last_modified.isoformat(),
                "title": m.title,
            }
            for m in items
        ]
        typer.echo(json.dumps(data, indent=2))
        return
    for m in items:
        typer.echo(f"{m.type:<10} {m.size_bytes:>7}  {m.path.name}")


@memory_app.command("show")
def show_cmd(name: str):
    p = _resolve(name)
    typer.echo(p.read_text(encoding="utf-8"))


@memory_app.command("edit")
def edit_cmd(name: str):
    p = _resolve(name)
    with audit_action("memory edit", [str(p)]):
        open_in_editor(p)


@memory_app.command("archive")
def archive_cmd(name: str):
    p = _resolve(name)
    with audit_action("memory archive", [str(p)]):
        dst = archive_memory_file(p)
    typer.echo(f"archived to {dst}")


@memory_app.command("move-type")
def move_type_cmd(name: str, new_type: str):
    p = _resolve(name)
    with audit_action("memory move-type", [str(p), new_type]):
        move_memory_type(p, new_type)
    typer.echo(f"moved {p.name} -> type={new_type}")


@memory_app.command("find-duplicates")
def find_duplicates_cmd():
    items = discover_memory_files()
    dups = find_duplicate_lines([m.path for m in items])
    if not dups:
        typer.echo("no duplicate lines found")
        return
    for d in dups:
        typer.echo(f"\n[{len(d.files)} files] {d.line[:80]}")
        for f in d.files:
            typer.echo(f"  - {f}")
