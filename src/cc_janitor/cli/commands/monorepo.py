from __future__ import annotations

import json
from pathlib import Path

import typer

from ...core.monorepo import discover_locations

monorepo_app = typer.Typer(no_args_is_help=True,
                           help="Discover nested .claude/ directories")


@monorepo_app.command("scan")
def scan(
    root: Path = typer.Option(Path.cwd(), "--root", help="Tree root to scan"),
    include_junk: bool = typer.Option(False, "--include-junk"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    locs = discover_locations(root, include_junk=include_junk)
    if json_out:
        typer.echo(json.dumps([
            {
                "path": str(loc.path),
                "scope_kind": loc.scope_kind,
                "has_settings": loc.has_settings,
                "has_skills": loc.has_skills,
                "has_hooks": loc.has_hooks,
                "has_mcp": loc.has_mcp,
                "size_bytes": loc.size_bytes,
                "last_modified": loc.last_modified.isoformat(),
                "project_marker": loc.project_marker,
            }
            for loc in locs
        ], indent=2))
        return
    typer.echo(f"{'KIND':<8} {'SETTINGS':<10} {'HOOKS':<7} {'PATH'}")
    for loc in locs:
        typer.echo(
            f"{loc.scope_kind:<8} "
            f"{'yes' if loc.has_settings else '-':<10} "
            f"{'yes' if loc.has_hooks else '-':<7} "
            f"{loc.path}"
        )


@monorepo_app.command("show")
def show(path: Path) -> None:
    from ...core.monorepo import classify_location
    loc = classify_location(path)
    typer.echo(f"Path:           {loc.path}")
    typer.echo(f"Scope:          {loc.scope_kind}")
    typer.echo(f"Project marker: {loc.project_marker}")
    typer.echo(f"Settings:       {loc.has_settings}")
    typer.echo(f"Skills:         {loc.has_skills}")
    typer.echo(f"Hooks:          {loc.has_hooks}")
    typer.echo(f"MCP:            {loc.has_mcp}")
    typer.echo(f"Size:           {loc.size_bytes} bytes")
    typer.echo(f"Last modified:  {loc.last_modified.isoformat()}")
