"""`cc-janitor dream` — Auto Dream safety-net subapp.

Read-only inspectors: ``history``, ``diff``, ``doctor``.
Mutating commands: ``rollback`` (restore from pre-mirror), ``prune``
(drop old artifacts). Mutations default to dry-run and require
``CC_JANITOR_USER_CONFIRMED=1`` via ``require_confirmed()`` before any
filesystem move; the resulting action is recorded through
``audit_action(mode="cli")``.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import typer

from ...core import dream_diff as dd
from ...core import dream_doctor as ddoc
from ...core.dream_snapshot import _dream_root, history, pair_paths
from ...core.safety import require_confirmed
from ...core.state import get_paths
from .._audit import audit_action

dream_app = typer.Typer(
    no_args_is_help=True,
    help="Auto Dream safety net (snapshot/diff/doctor/rollback)",
)


def _pair_storage(pair_id: str) -> str:
    root = _dream_root()
    if (root / f"{pair_id}-pre").exists():
        return "dir"
    if (root / f"{pair_id}.tar.gz").exists():
        return "tar"
    return "gone"


@dream_app.command("history", help="List recorded Dream snapshot pairs.")
def history_cmd(
    project: str | None = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    items = history()
    if project:
        items = [p for p in items if p.project_slug == project]
    if json_out:
        typer.echo(json.dumps([asdict(p) for p in items], indent=2))
        return
    typer.echo(
        f"{'PAIR_ID':<32} {'PROJECT':<20} "
        f"{'DFILES':<8} {'DLINES':<8} {'STORAGE':<8}"
    )
    for p in items:
        typer.echo(
            f"{p.pair_id:<32} {p.project_slug:<20} "
            f"{p.file_count_delta or 0!s:<8} "
            f"{p.line_count_delta or 0!s:<8} "
            f"{_pair_storage(p.pair_id):<8}"
        )


def _find_pair(pair_id: str):
    for p in history():
        if p.pair_id == pair_id:
            return p
    return None


@dream_app.command("diff", help="Show file deltas between pre and post snapshots.")
def diff_cmd(
    pair_id: str,
    file: str | None = typer.Option(None, "--file"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    pair = _find_pair(pair_id)
    if pair is None:
        typer.echo(f"No such pair: {pair_id}")
        raise typer.Exit(code=1)
    try:
        with pair_paths(pair_id) as (pre, post):
            diff = dd.compute_diff(pre, post)
            if file:
                diff.deltas = [d for d in diff.deltas if str(d.rel_path) == file]
            if json_out:
                typer.echo(json.dumps({
                    "summary": diff.summary,
                    "deltas": [{
                        "rel_path": str(d.rel_path),
                        "status": d.status,
                        "lines_added": d.lines_added,
                        "lines_removed": d.lines_removed,
                        "unified_diff": d.unified_diff,
                    } for d in diff.deltas],
                }, indent=2))
                return
            typer.echo(f"Pair: {pair_id}  Summary: {diff.summary}")
            for d in diff.deltas:
                typer.echo(
                    f"  [{d.status:<9}] {d.rel_path}  "
                    f"+{d.lines_added} -{d.lines_removed}"
                )
            for d in diff.deltas:
                if d.unified_diff:
                    typer.echo("")
                    typer.echo(d.unified_diff)
    except FileNotFoundError as e:
        typer.echo(str(e))
        raise typer.Exit(code=1) from e


@dream_app.command("doctor", help="Run Dream safety-net health checks.")
def doctor_cmd(json_out: bool = typer.Option(False, "--json")) -> None:
    checks = ddoc.run_checks()
    if json_out:
        typer.echo(json.dumps([asdict(c) for c in checks], indent=2))
        return
    typer.echo("cc-janitor dream doctor")
    typer.echo("-" * 60)
    for c in checks:
        typer.echo(f"  [{c.severity:<4}] {c.title}: {c.message}")


@dream_app.command(
    "rollback", help="Restore memory dir to a pre-snapshot state."
)
def rollback_cmd(
    pair_id: str,
    apply: bool = typer.Option(
        False, "--apply", help="Actually restore (otherwise dry-run)"
    ),
) -> None:
    pair = _find_pair(pair_id)
    if pair is None:
        typer.echo(f"No such pair: {pair_id}")
        raise typer.Exit(code=1)
    target = Path(pair.claude_memory_dir)
    if not apply:
        typer.echo(f"[dry-run] Would restore pre-snapshot of {pair_id} -> {target}")
        typer.echo(
            "          Current target post-state would be soft-deleted to trash."
        )
        typer.echo(
            "          Any Dream cycles applied AFTER this snapshot will be "
            "discarded; reversible via `cc-janitor undo`."
        )
        return
    require_confirmed()
    try:
        with pair_paths(pair_id) as (pre, _post):
            with audit_action(
                cmd="dream rollback", args=[pair_id, "--apply"], mode="cli",
            ) as changed:
                trash = (
                    get_paths().home / ".trash"
                    / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    / f"dream-rollback-{pair_id}"
                )
                trash.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    for f in target.rglob("*"):
                        if f.is_file():
                            rel = f.relative_to(target)
                            out = trash / rel
                            out.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(f), str(out))
                target.mkdir(parents=True, exist_ok=True)
                for f in pre.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(pre)
                        out = target / rel
                        out.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, out)
                changed["pair_id"] = pair_id
                changed["files_restored"] = sum(
                    1 for _ in pre.rglob("*") if _.is_file()
                )
                changed["trash_path"] = str(trash)
                changed["trash_id"] = trash.parent.name
                changed["target"] = str(target)
    except FileNotFoundError as e:
        typer.echo(str(e))
        raise typer.Exit(code=1) from e
    typer.echo(
        f"Restored {pair_id}; previous state preserved in {trash}."
    )
    typer.echo("Reversible via `cc-janitor undo --apply`.")


@dream_app.command("prune", help="Drop Dream artifacts older than N days.")
def prune_cmd(
    older_than_days: int = typer.Option(30, "--older-than-days"),
    apply: bool = typer.Option(False, "--apply"),
) -> None:
    root = _dream_root()
    if not root.exists():
        typer.echo("Nothing to prune.")
        return
    now = datetime.now(UTC).timestamp()
    cutoff = now - older_than_days * 86400
    victims = [d for d in root.iterdir() if d.stat().st_mtime < cutoff]
    if not apply:
        typer.echo(
            f"[dry-run] Would remove {len(victims)} dream artifact(s) "
            f"older than {older_than_days} days."
        )
        return
    require_confirmed()
    with audit_action(
        cmd="dream prune",
        args=[f"--older-than-days={older_than_days}"],
        mode="cli",
    ) as ch:
        for v in victims:
            if v.is_dir():
                shutil.rmtree(v)
            else:
                v.unlink()
        ch["removed"] = [str(v) for v in victims]
    typer.echo(f"Removed {len(victims)} artifact(s).")
