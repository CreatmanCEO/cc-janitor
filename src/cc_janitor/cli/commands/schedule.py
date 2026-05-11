from __future__ import annotations

import json
import sys

import typer

from ...core.schedule import (
    TEMPLATES,
    ScheduledJob,
    _load_manifest,
    get_scheduler,
)
from .._audit import audit_action

schedule_app = typer.Typer(no_args_is_help=True, help="Cross-platform scheduler")


@schedule_app.command("list")
def list_cmd(json_out: bool = typer.Option(False, "--json")):
    jobs = get_scheduler().list_jobs()
    if json_out:
        typer.echo(
            json.dumps(
                [
                    {
                        "name": j.name,
                        "template": j.template,
                        "cron": j.cron_expr,
                        "next_run": j.next_run.isoformat() if j.next_run else None,
                        "dry_run_pending": j.dry_run_pending,
                        "last_status": j.last_status,
                    }
                    for j in jobs
                ],
                indent=2,
            )
        )
        return
    for j in jobs:
        flag = " [dry-run-pending]" if j.dry_run_pending else ""
        typer.echo(f"{j.name:<32} {j.cron_expr:<14} {j.last_status}{flag}")


@schedule_app.command("add")
def add_cmd(
    template: str,
    cron: str | None = typer.Option(None, "--cron"),
):
    if template not in TEMPLATES:
        raise typer.BadParameter(
            f"unknown template: {template}; choose from {list(TEMPLATES)}"
        )
    spec = TEMPLATES[template]
    cron_expr = cron or spec["default_cron"]
    job = ScheduledJob(
        name=f"cc-janitor-{template}",
        template=template,
        cron_expr=cron_expr,
        command=spec["command"],
        next_run=None,
        last_run=None,
        last_status="never",
        dry_run_pending=True,
        backend="schtasks" if sys.platform == "win32" else "cron",
    )
    with audit_action("schedule add", [template, cron_expr]):
        get_scheduler().add_job(job)
    typer.echo(
        f"added {job.name} (first run is --dry-run; promote after success)"
    )


@schedule_app.command("remove")
def remove_cmd(name: str):
    with audit_action("schedule remove", [name]):
        get_scheduler().remove_job(name)


@schedule_app.command("run")
def run_cmd(name: str):
    rc = get_scheduler().run_now(name)
    typer.echo(f"exit={rc}")


@schedule_app.command("audit")
def audit_cmd(
    limit: int = typer.Option(20, "--limit", help="Show the last N scheduled runs"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Show recent scheduled-mode audit-log entries (i.e. ``mode=scheduled``)."""
    from ...core.audit import AuditLog
    from ...core.state import get_paths

    log = AuditLog(get_paths().audit_log)
    entries = [e for e in log.read() if e.mode == "scheduled"]
    entries = entries[-limit:]
    if not entries:
        typer.echo("no scheduled-mode audit entries yet")
        return
    if json_out:
        from dataclasses import asdict

        typer.echo(json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2))
        return
    for e in entries:
        mark = "✗" if e.exit_code else "✓"
        typer.echo(
            f"{mark} {e.ts}  {e.cmd:24}  exit={e.exit_code}  args={' '.join(e.args)}"
        )


@schedule_app.command("promote")
def promote_cmd(name: str):
    job = _load_manifest(name)
    if job is None:
        typer.echo(f"job not found: {name}", err=True)
        raise typer.Exit(1)
    with audit_action("schedule promote", [name]):
        sched = get_scheduler()
        sched.remove_job(name)
        job.dry_run_pending = False
        sched.add_job(job)
    typer.echo(f"promoted {name} to live mode")
