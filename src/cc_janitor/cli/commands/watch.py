from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from ...core import watcher as w
from ...core.safety import NotConfirmedError, require_confirmed
from ...core.state import get_paths
from .._audit import audit_action

watch_app = typer.Typer(
    no_args_is_help=True,
    help="Auto-reinject background watcher (opt-in)",
)


def _default_memory_dirs() -> list[Path]:
    """Discover ~/.claude/projects/*/memory/ directories."""
    proj_root = Path.home() / ".claude" / "projects"
    if not proj_root.exists():
        return []
    return [
        d / "memory"
        for d in proj_root.iterdir()
        if (d / "memory").is_dir()
    ]


@watch_app.command("start")
def start(
    interval: int = typer.Option(30, "--interval", min=1),
) -> None:
    with audit_action("watch start", [f"interval={interval}"]):
        try:
            require_confirmed()
        except NotConfirmedError as e:
            typer.echo(str(e), err=False)
            raise typer.Exit(code=2) from e
        pid_p = get_paths().home / "watcher.pid"
        if pid_p.exists():
            try:
                old_pid = int(pid_p.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                old_pid = 0
            if old_pid and w.is_pid_alive(old_pid):
                typer.echo(f"Watcher already running (pid {old_pid})")
                raise typer.Exit(code=1)
            pid_p.unlink(missing_ok=True)
        dirs = _default_memory_dirs()
        if not dirs:
            typer.echo(
                "No memory directories found under ~/.claude/projects/*/memory/"
            )
            raise typer.Exit(code=2)
        os.environ["CC_JANITOR_WATCH_DIRS"] = os.pathsep.join(
            str(d) for d in dirs
        )
        log = get_paths().home / "watcher.log"
        pid = w.spawn_daemon(
            [
                sys.executable,
                "-m",
                "cc_janitor.core.watcher_main",
                "--interval",
                str(interval),
            ],
            cwd=Path.cwd(),
            log_path=log,
        )
        pid_p.parent.mkdir(parents=True, exist_ok=True)
        pid_p.write_text(str(pid), encoding="utf-8")
        w.write_status(
            w.WatcherStatus(
                pid=pid,
                started_at=datetime.now(UTC),
                watching_paths=dirs,
                interval_seconds=interval,
                marker_writes_count=0,
                last_change_at=None,
                is_alive=True,
            )
        )
        typer.echo(
            f"Watcher started (pid {pid}, interval {interval}s, "
            f"{len(dirs)} memory dirs)"
        )


@watch_app.command("stop")
def stop() -> None:
    with audit_action("watch stop", []):
        try:
            require_confirmed()
        except NotConfirmedError as e:
            typer.echo(str(e), err=False)
            raise typer.Exit(code=2) from e
        pid_p = get_paths().home / "watcher.pid"
        if not pid_p.exists():
            typer.echo("Watcher not running")
            return
        try:
            pid = int(pid_p.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = 0
        if pid:
            w.kill_pid(pid)
        pid_p.unlink(missing_ok=True)
        status_p = get_paths().home / "watcher-status.json"
        status_p.unlink(missing_ok=True)
        typer.echo(f"Watcher stopped (pid {pid})")


@watch_app.command("status")
def status(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    s = w.read_status()
    if s is None:
        typer.echo("Watcher: not running")
        return
    if json_out:
        d = {
            "pid": s.pid,
            "started_at": s.started_at.isoformat(),
            "watching_paths": [str(p) for p in s.watching_paths],
            "interval_seconds": s.interval_seconds,
            "marker_writes_count": s.marker_writes_count,
            "last_change_at": (
                s.last_change_at.isoformat() if s.last_change_at else None
            ),
            "is_alive": s.is_alive,
        }
        typer.echo(json.dumps(d, indent=2))
        return
    state = "running" if s.is_alive else "stale (pid dead)"
    typer.echo(f"Watcher: {state}")
    typer.echo(f"  PID:             {s.pid}")
    typer.echo(f"  Started at:      {s.started_at.isoformat()}")
    typer.echo(f"  Interval:        {s.interval_seconds}s")
    typer.echo(f"  Watching:        {len(s.watching_paths)} dirs")
    typer.echo(f"  Marker writes:   {s.marker_writes_count}")
    if s.last_change_at:
        typer.echo(f"  Last change at:  {s.last_change_at.isoformat()}")
