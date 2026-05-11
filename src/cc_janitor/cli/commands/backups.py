"""``cc-janitor backups`` — manage the ``~/.cc-janitor/backups/`` tree.

Backups are timestamped copies of mutated files (settings.json edits via
:func:`core.permissions._backup`, bundle imports via
:func:`core.bundle.import_bundle`). They accumulate over time and need a
periodic prune to keep disk usage in check — this command pair drives the
scheduled ``backup-rotate`` job and gives users a manual surface to inspect
or prune.
"""

from __future__ import annotations

import shutil
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from ...core.safety import NotConfirmedError, require_confirmed
from ...core.state import get_paths
from .._audit import audit_action

backups_app = typer.Typer(
    no_args_is_help=True, help="Inspect/prune the ~/.cc-janitor/backups/ tree"
)


@backups_app.command("list")
def list_cmd() -> None:
    """List every backup bucket and its size + age."""
    paths = get_paths()
    root = paths.backups
    if not root.exists():
        typer.echo("No backups directory yet.")
        return
    buckets = sorted(p for p in root.iterdir() if p.is_dir())
    if not buckets:
        typer.echo("No backup buckets.")
        return
    for bucket in buckets:
        files = list(bucket.glob("*"))
        if not files:
            continue
        newest_mtime = max(f.stat().st_mtime for f in files)
        age_days = (datetime.now(UTC).timestamp() - newest_mtime) / 86400
        total_bytes = sum(f.stat().st_size for f in files)
        typer.echo(
            f"{bucket.name}  files={len(files):<3}  "
            f"size={total_bytes:>8}b  newest={age_days:.1f}d ago"
        )


@backups_app.command("prune")
def prune_cmd(
    older_than_days: int = typer.Option(
        30,
        "--older-than-days",
        help="Delete backup buckets whose newest file is older than N days.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting."),
) -> None:
    """Permanently delete old backup buckets.

    A bucket is considered prunable when its NEWEST file is older than N days.
    Requires ``CC_JANITOR_USER_CONFIRMED=1`` unless ``--dry-run``.
    """
    paths = get_paths()
    root = paths.backups
    if not root.exists():
        typer.echo("No backups directory.")
        return

    cutoff_ts = (datetime.now(UTC) - timedelta(days=older_than_days)).timestamp()
    targets: list = []
    for bucket in sorted(p for p in root.iterdir() if p.is_dir()):
        files = list(bucket.glob("*"))
        if not files:
            targets.append(bucket)
            continue
        newest = max(f.stat().st_mtime for f in files)
        if newest < cutoff_ts:
            targets.append(bucket)

    if not targets:
        typer.echo(f"No backup buckets older than {older_than_days}d.")
        return

    if dry_run:
        typer.echo(
            f"DRY RUN: would delete {len(targets)} bucket(s) "
            f"older than {older_than_days}d:"
        )
        for b in targets:
            typer.echo(f"  - {b.name}")
        return

    with audit_action("backups prune", [f"--older-than-days={older_than_days}"]) as changed:
        try:
            require_confirmed()
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e
        for bucket in targets:
            shutil.rmtree(bucket, ignore_errors=True)
        changed["deleted_buckets"] = [b.name for b in targets]
    typer.echo(f"Deleted {len(targets)} backup bucket(s).")


@backups_app.command("tar-compact")
def tar_compact_cmd(
    kind: str = typer.Option(
        "dream",
        "--kind",
        help="Backup subtree to compact (currently only `dream`).",
    ),
    older_than_days: int = typer.Option(
        7,
        "--older-than-days",
        help="Tar pairs whose pre/post mirrors are all older than N days.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Actually create tar.gz and remove raw mirrors (default: dry-run).",
    ),
) -> None:
    """Tar-compact aged pre/post mirror pairs into ``<pair_id>.tar.gz``.

    Groups ``<pair_id>-pre`` / ``<pair_id>-post`` directories under the chosen
    backup subtree, archives them as ``<pair_id>.tar.gz`` with ``pre/`` and
    ``post/`` prefixes, and removes the raw mirrors. Drives the weekly
    ``dream-tar-compact`` scheduler template.
    """
    root: Path = get_paths().home / "backups" / kind
    if not root.exists():
        typer.echo("Nothing to compact.")
        return

    cutoff = datetime.now(UTC).timestamp() - older_than_days * 86400
    pair_dirs: dict[str, list[Path]] = {}
    for d in root.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if name.endswith("-pre"):
            pair_dirs.setdefault(name[:-4], []).append(d)
        elif name.endswith("-post"):
            pair_dirs.setdefault(name[:-5], []).append(d)
    old_pairs: dict[str, list[Path]] = {
        pid: dirs
        for pid, dirs in pair_dirs.items()
        if dirs and all(d.stat().st_mtime < cutoff for d in dirs)
    }

    if not apply:
        typer.echo(
            f"[dry-run] Would tar-compact {len(old_pairs)} pair(s) "
            f"older than {older_than_days}d under {root}."
        )
        for pid in sorted(old_pairs):
            typer.echo(f"  - {pid}")
        return

    try:
        require_confirmed()
    except NotConfirmedError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=2) from e

    with audit_action(
        "backups tar-compact",
        [f"--kind={kind}", f"--older-than-days={older_than_days}"],
    ) as changed:
        archived: list[str] = []
        for pid, dirs in old_pairs.items():
            archive_path = root / f"{pid}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tf:
                for d in dirs:
                    arc = "pre" if d.name.endswith("-pre") else "post"
                    for f in d.rglob("*"):
                        if f.is_file():
                            tf.add(f, arcname=f"{arc}/{f.relative_to(d)}")
            for d in dirs:
                shutil.rmtree(d, ignore_errors=True)
            archived.append(pid)
        changed["archived"] = archived
    typer.echo(f"Compacted {len(old_pairs)} pair(s).")
