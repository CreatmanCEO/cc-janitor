from __future__ import annotations

from pathlib import Path

import typer

from ...core.bundle import export_bundle, import_bundle
from ...core.state import get_paths
from .._audit import audit_action

config_app = typer.Typer(
    no_args_is_help=True,
    help="Export/import cross-machine config bundle",
)


@config_app.command("export")
def export_cmd(
    out: Path = typer.Argument(..., help="Path to write the tar.gz bundle"),
    include_memory: bool = typer.Option(
        False, "--include-memory", help="Include per-project memory/*.md"
    ),
) -> None:
    """Export an explicit allowlist of Claude config files into a tar.gz."""
    with audit_action("config export", [str(out), f"memory={include_memory}"]) as changed:
        n = export_bundle(out, include_memory=include_memory)
        changed["files"] = n
    typer.echo(f"Exported {n} files to {out}")


@config_app.command("import")
def import_cmd(
    bundle: Path = typer.Argument(..., help="Path to the tar.gz bundle"),
    apply: bool = typer.Option(
        False, "--apply", help="Actually write files (default: dry-run only)"
    ),
) -> None:
    """Import a bundle. Defaults to dry-run; pass --apply to write."""
    if not apply:
        with audit_action("config import", [str(bundle), "dry-run"]) as changed:
            result = import_bundle(bundle, dry_run=True, force=False)
            changed["would_write"] = result["would_write"]
        typer.echo(
            f"DRY RUN: would write {result['would_write']} files. "
            f"Re-run with --apply to write."
        )
        return
    with audit_action("config import", [str(bundle), "apply"]) as changed:
        result = import_bundle(bundle, dry_run=False, force=True)
        changed["written"] = result["written"]
        changed["backups"] = len(result["backups"])
    typer.echo(
        f"Imported {result['written']} files. "
        f"Backups: {len(result['backups'])} at {get_paths().backups}"
    )
