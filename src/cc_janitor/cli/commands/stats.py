from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import asdict
from datetime import timedelta

import typer

from ...core.sleep_hygiene import compute_report
from ...core.stats import (
    load_snapshots,
    render_sparkline,
    take_snapshot,
    write_snapshot,
)

stats_app = typer.Typer(
    no_args_is_help=False,
    help="Stats dashboard with daily history",
    invoke_without_command=True,
)


def _parse_since(s: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([dwhm])", s)
    if not m:
        raise typer.BadParameter(f"Invalid --since: {s} (use 7d, 4w, 24h, 30m)")
    n, unit = int(m.group(1)), m.group(2)
    return {
        "d": timedelta(days=n),
        "w": timedelta(weeks=n),
        "h": timedelta(hours=n),
        "m": timedelta(minutes=n),
    }[unit]


@stats_app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    since: str = typer.Option("30d", "--since"),
    fmt: str = typer.Option("text", "--format"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    snaps = load_snapshots(since=_parse_since(since))
    if fmt == "json":
        typer.echo(json.dumps([
            {**asdict(s), "date": s.date.isoformat()} for s in snaps
        ], indent=2))
        return
    if fmt == "csv":
        w = csv.writer(sys.stdout)
        w.writerow(["date", "sessions", "perm_rules", "context_tokens",
                    "trash_bytes", "audit_entries_since_last"])
        for s in snaps:
            w.writerow([s.date.isoformat(), s.sessions_count,
                        s.perm_rules_count, s.context_tokens,
                        s.trash_bytes, s.audit_entries_since_last])
        return
    if not snaps:
        typer.echo("No snapshots in window. Run `cc-janitor stats snapshot` first.")
        return
    last = snaps[-1]
    typer.echo(f"Sessions:       {last.sessions_count:>6}  "
               f"{render_sparkline([s.sessions_count for s in snaps])}")
    typer.echo(f"Perm rules:     {last.perm_rules_count:>6}  "
               f"{render_sparkline([s.perm_rules_count for s in snaps])}")
    typer.echo(f"Context tokens: {last.context_tokens:>6}  "
               f"{render_sparkline([s.context_tokens for s in snaps])}")
    typer.echo(f"Trash bytes:    {last.trash_bytes:>6}  "
               f"{render_sparkline([s.trash_bytes for s in snaps])}")


@stats_app.command("snapshot")
def snapshot_cmd() -> None:
    s = take_snapshot()
    p = write_snapshot(s)
    typer.echo(f"Snapshot written: {p}")


@stats_app.command("sleep-hygiene")
def sleep_hygiene(
    project: str | None = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    report = compute_report()
    projects = report.projects
    if project:
        projects = [p for p in projects if p.project_slug == project]
    if json_out:
        typer.echo(json.dumps({
            "generated_at": report.generated_at.isoformat(),
            "totals": report.totals,
            "projects": [{
                "project_slug": p.project_slug,
                "memory_md_size_lines": p.memory_md_size_lines,
                "memory_md_cap": p.memory_md_cap,
                "relative_date_density": p.relative_date_density,
                "relative_date_match_count": len(p.relative_date_matches),
                "cross_file_dup_count": p.cross_file_dup_count,
                "contradicting_pair_count": len(p.contradicting_pairs),
            } for p in projects],
        }, indent=2))
        return
    typer.echo("Sleep hygiene report")
    typer.echo("-" * 70)
    for p in projects:
        typer.echo(
            f"  {p.project_slug:<25} "
            f"MEMORY.md {p.memory_md_size_lines}/{p.memory_md_cap}  "
            f"rel-date density {p.relative_date_density:.3f}  "
            f"dups {p.cross_file_dup_count}  "
            f"contradictions {len(p.contradicting_pairs)}"
        )
    typer.echo(f"Totals: {report.totals}")
