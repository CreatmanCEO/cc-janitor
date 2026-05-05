from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from ...core.safety import NotConfirmedError
from ...core.sessions import (
    delete_session,
    discover_sessions,
    enrich_with_indexer_summaries,
)
from .._audit import audit_action

session_app = typer.Typer(help="Manage Claude Code sessions")


@session_app.command("list")
def list_(project: str = typer.Option(None, "--project")) -> None:
    rows = discover_sessions(project=project)
    for s in sorted(rows, key=lambda x: x.last_activity, reverse=True):
        msg = (s.first_user_msg or "").replace("\n", " ")[:60]
        typer.echo(
            f"{s.id}  {s.project:24}  {s.size_bytes:>10}b  {s.message_count:>4}msg  {msg}"
        )


@session_app.command("show")
def show(session_id: str) -> None:
    s = next((x for x in discover_sessions() if x.id == session_id), None)
    if not s:
        raise typer.BadParameter(f"No session {session_id}")
    typer.echo(f"ID: {s.id}")
    typer.echo(f"Project: {s.project}")
    typer.echo(f"Messages: {s.message_count}")
    typer.echo(f"Compactions: {s.compactions}")
    typer.echo(f"Size: {s.size_bytes}b")
    typer.echo(f"Last activity: {s.last_activity}")
    typer.echo(f"\nFirst user msg:\n  {s.first_user_msg}")
    if s.last_user_msg:
        typer.echo(f"\nLast user msg:\n  {s.last_user_msg}")


@session_app.command("summary")
def summary(session_id: str) -> None:
    sessions = enrich_with_indexer_summaries(
        discover_sessions(),
        indexer_root=Path.home() / "Conversations" / "claude-code",
    )
    s = next((x for x in sessions if x.id == session_id), None)
    if not s:
        raise typer.BadParameter(f"No session {session_id}")
    if not s.summaries:
        typer.echo("(no summaries)")
        return
    for sm in s.summaries:
        ts = sm.timestamp.isoformat() if sm.timestamp else ""
        typer.echo(f"\n[{sm.source}] {ts}")
        typer.echo(sm.text[:500])


@session_app.command("delete")
def delete(session_ids: list[str]) -> None:
    with audit_action("session delete", list(session_ids)) as changed:
        sessions = {s.id: s for s in discover_sessions()}
        deleted: list[dict] = []
        failures = 0
        for sid in session_ids:
            if sid not in sessions:
                typer.echo(f"skip {sid}: not found", err=True)
                failures += 1
                continue
            try:
                tid = delete_session(sessions[sid])
                typer.echo(f"deleted {sid} -> trash:{tid}")
                deleted.append({"id": sid, "trash_id": tid})
            except NotConfirmedError as e:
                typer.echo(str(e), err=True)
                raise typer.Exit(code=2) from e
        changed["deleted"] = deleted
        if failures:
            raise typer.Exit(code=1)


@session_app.command("prune")
def prune(
    older_than: str = typer.Option("90d", "--older-than"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    days = int(older_than.rstrip("d"))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = [s for s in discover_sessions() if s.last_activity < cutoff]
    typer.echo(f"{len(rows)} sessions older than {older_than}")
    for s in rows:
        typer.echo(f"  {s.id}  {s.last_activity.date()}  {s.first_user_msg[:50]}")
    if dry_run:
        return
    with audit_action("session prune", [older_than]) as changed:
        deleted: list[dict] = []
        for s in rows:
            try:
                tid = delete_session(s)
                deleted.append({"id": s.id, "trash_id": tid})
            except NotConfirmedError as e:
                typer.echo(str(e), err=True)
                raise typer.Exit(code=2) from e
        changed["deleted"] = deleted


@session_app.command("search")
def search(query: str) -> None:
    pat = re.compile(re.escape(query), re.IGNORECASE)
    for s in discover_sessions():
        if pat.search(s.first_user_msg or "") or pat.search(s.last_user_msg or ""):
            typer.echo(f"{s.id}  {s.first_user_msg[:80]}")
