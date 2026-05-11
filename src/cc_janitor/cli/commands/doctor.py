from __future__ import annotations

import sys
from pathlib import Path

import typer

from ...core.permissions import discover_rules
from ...core.sessions import discover_sessions
from ...core.state import get_paths


def doctor() -> None:
    """Print a health-check summary; exit 0 if all green, non-zero otherwise."""
    paths = get_paths()
    paths.ensure_dirs()

    typer.echo(f"Python:     {sys.version.split()[0]}")
    home = Path.home() / ".claude"
    typer.echo(f"~/.claude:  {'OK' if home.exists() else 'MISSING'}  ({home})")

    sessions = discover_sessions()
    typer.echo(f"Sessions:   {len(sessions)}")

    rules = discover_rules()
    typer.echo(f"Perm rules: {len(rules)}")

    audit_size = paths.audit_log.stat().st_size if paths.audit_log.exists() else 0
    typer.echo(f"Audit log:  {audit_size}b at {paths.audit_log}")

    trash_size = (
        sum(p.stat().st_size for p in paths.trash.rglob("*") if p.is_file())
        if paths.trash.exists()
        else 0
    )
    typer.echo(f"Trash size: {trash_size}b")

    from ...core.watcher import read_status

    s = read_status()
    if s is None:
        typer.echo("Watcher:    not running")
    elif s.is_alive:
        typer.echo(
            f"Watcher:    running (pid {s.pid}, since "
            f"{s.started_at.isoformat()}, {s.marker_writes_count} reinjects)"
        )
    else:
        typer.echo(f"Watcher:    stale (pid {s.pid} dead — run `watch stop`)")
