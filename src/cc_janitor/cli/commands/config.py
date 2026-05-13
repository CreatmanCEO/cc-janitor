from __future__ import annotations

from pathlib import Path

import typer

from ...core.bundle import export_bundle, import_bundle
from ...core.state import get_paths
from .._audit import audit_action

config_app = typer.Typer(
    no_args_is_help=True,
    help="Export/import cross-machine config bundle; scaffold config.toml",
)


CONFIG_TOML_TEMPLATE = """\
# cc-janitor user config. All keys are optional; values shown are defaults.
# Location: ~/.cc-janitor/config.toml. Reloaded on every CLI invocation.

[dream_doctor]
# Free-disk warning floor for ~/.cc-janitor/backups/ (MB).
disk_warning_mb = 100
# WARN when a project's memory dir exceeds this many .md files.
memory_file_count_threshold = 50
# WARN when MEMORY.md exceeds this many lines (Auto Dream input bloat).
memory_md_line_threshold = 180

[snapshots]
# Days to keep raw <pair_id>-{pre,post}/ mirrors before tar-compaction.
raw_retention_days = 7
# Days to keep <pair_id>.tar.gz before `dream prune --apply` drops them.
tar_retention_days = 30

[hygiene]
# Extra terms (Russian/English/etc.) flagged as relative-date by
# `stats sleep-hygiene`. Defaults already cover yesterday/today/recently
# and Russian equivalents.
relative_date_terms_extra = []
# Token-Jaccard threshold above which "never X" + "always X" pairs in
# feedback memory are flagged as contradictory. 0.0 = always pair; 1.0 = never.
contradiction_jaccard_threshold = 0.5
"""


@config_app.command("init")
def init_cmd(
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing config.toml"
    ),
) -> None:
    """Scaffold ``~/.cc-janitor/config.toml`` with documented defaults."""
    target = get_paths().home / "config.toml"
    if target.exists() and not force:
        typer.echo(
            f"config.toml already exists at {target}; pass --force to overwrite."
        )
        raise typer.Exit(code=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONFIG_TOML_TEMPLATE, encoding="utf-8")
    typer.echo(f"Wrote {target}")


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
