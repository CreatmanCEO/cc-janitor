from __future__ import annotations

import json as _json
import re
from datetime import UTC, datetime, timedelta

import typer

from ...core.audit import AuditLog
from ...core.state import get_paths

audit_app = typer.Typer(help="Inspect cc-janitor audit log")


_DURATION_RE = re.compile(r"^(\d+)([dhm])$")


def _parse_since(s: str) -> datetime:
    m = _DURATION_RE.match(s)
    if not m:
        raise typer.BadParameter(f"--since must be like 7d, 24h, 30m (got {s!r})")
    n = int(m.group(1))
    unit = m.group(2)
    delta = {"d": timedelta(days=n), "h": timedelta(hours=n), "m": timedelta(minutes=n)}[unit]
    return datetime.now(UTC) - delta


@audit_app.command("list")
def list_(
    since: str = typer.Option(None, "--since", help="e.g. 7d, 24h, 30m"),
    cmd: str = typer.Option(None, "--cmd", help="fnmatch pattern, e.g. session*"),
    failed: bool = typer.Option(False, "--failed", help="Only entries with non-zero exit"),
    json: bool = typer.Option(False, "--json", help="Emit JSONL"),
) -> None:
    paths = get_paths()
    log = AuditLog(paths.audit_log)
    cutoff = _parse_since(since) if since else None

    for e in log.read(cmd_glob=cmd):
        if cutoff:
            try:
                t = datetime.fromisoformat(e.ts)
                if t < cutoff:
                    continue
            except ValueError:
                continue
        if failed and e.exit_code == 0:
            continue
        if json:
            from dataclasses import asdict
            typer.echo(_json.dumps(asdict(e), ensure_ascii=False))
        else:
            mark = "✗" if e.exit_code else "✓"
            conf = "[user]" if e.user_confirmed else "[noconf]"
            typer.echo(
                f"{mark} {e.ts}  {conf:8}  {e.cmd:24}  "
                f"exit={e.exit_code}  args={' '.join(e.args)}"
            )
