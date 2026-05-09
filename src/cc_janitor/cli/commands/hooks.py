from __future__ import annotations

import json
from pathlib import Path

import typer

from ...core.hooks import (
    disable_logging,
    discover_hooks,
    enable_logging,
    simulate_hook,
    validate_hooks,
)
from .._audit import audit_action

hooks_app = typer.Typer(no_args_is_help=True, help="Hook discovery/debugger")


@hooks_app.command("list")
def list_cmd(
    event: str | None = typer.Option(None, "--event"),
    json_out: bool = typer.Option(False, "--json"),
):
    items = discover_hooks()
    if event:
        items = [e for e in items if e.event == event]
    if json_out:
        typer.echo(
            json.dumps(
                [
                    {
                        "event": e.event,
                        "matcher": e.matcher,
                        "type": e.type,
                        "command": e.command,
                        "source": str(e.source_path),
                        "scope": e.source_scope,
                        "logging": e.has_logging_wrapper,
                    }
                    for e in items
                ],
                indent=2,
            )
        )
        return
    for e in items:
        cmd_preview = (e.command or "")[:60]
        typer.echo(
            f"{e.event:<14} {e.matcher:<10} {cmd_preview}  ({e.source_scope})"
        )


@hooks_app.command("show")
def show_cmd(event: str, matcher: str = typer.Argument("*")):
    for e in discover_hooks():
        if e.event == event and e.matcher == matcher:
            typer.echo(
                json.dumps(
                    {
                        "event": e.event,
                        "matcher": e.matcher,
                        "type": e.type,
                        "command": e.command,
                        "url": e.url,
                        "timeout": e.timeout,
                        "source": str(e.source_path),
                        "scope": e.source_scope,
                    },
                    indent=2,
                )
            )
            return
    raise typer.Exit(1)


@hooks_app.command("simulate")
def simulate_cmd(
    event: str,
    matcher: str = typer.Argument("*"),
    input_file: str | None = typer.Option(None, "--input-file"),
):
    target = next(
        (e for e in discover_hooks() if e.event == event and e.matcher == matcher),
        None,
    )
    if target is None or not target.command:
        typer.echo("no matching hook with command")
        raise typer.Exit(1)
    stdin_override = None
    if input_file:
        stdin_override = Path(input_file).read_text(encoding="utf-8")
    result = simulate_hook(
        target.command,
        event=event,
        matcher=matcher,
        stdin_override=stdin_override,
    )
    typer.echo(f"exit={result.exit_code} duration={result.duration_ms}ms")
    if result.stdout:
        typer.echo(f"--- stdout ---\n{result.stdout}")
    if result.stderr:
        typer.echo(f"--- stderr ---\n{result.stderr}")


@hooks_app.command("enable-logging")
def enable_logging_cmd(event: str, matcher: str = typer.Argument("*")):
    with audit_action("hooks enable-logging", [event, matcher]):
        enable_logging(event, matcher=matcher)


@hooks_app.command("disable-logging")
def disable_logging_cmd(event: str, matcher: str = typer.Argument("*")):
    with audit_action("hooks disable-logging", [event, matcher]):
        disable_logging(event, matcher=matcher)


@hooks_app.command("validate")
def validate_cmd():
    issues = validate_hooks()
    if not issues:
        typer.echo("no issues")
        return
    for i in issues:
        typer.echo(f"[{i.kind}] {i.source_path}: {i.detail}")
