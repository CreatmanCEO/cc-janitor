from __future__ import annotations

import typer

from ...core.permissions import (
    add_rule,
    analyze_usage,
    discover_rules,
    find_duplicates,
    remove_rule,
)
from ...core.safety import NotConfirmedError
from ...core.sessions import discover_sessions
from .._audit import audit_action

perms_app = typer.Typer(help="Audit and prune permission rules")


def _rules_with_usage(scope: str | None = None):
    return analyze_usage(discover_rules(scope=scope), discover_sessions())


@perms_app.command("audit")
def audit() -> None:
    rules = _rules_with_usage()
    by_source: dict = {}
    for r in rules:
        by_source.setdefault(r.source.path, []).append(r)
    typer.echo(f"Total rules: {len(rules)}")
    stale = sum(1 for r in rules if r.stale)
    typer.echo(f"Stale (no match in 90d): {stale}")
    dups = find_duplicates(rules)
    typer.echo(f"Duplicates detected: {len(dups)}")
    typer.echo("\nBy source:")
    for path, rs in by_source.items():
        typer.echo(f"  {path}: {len(rs)} rules")


@perms_app.command("list")
def list_(
    stale: bool = typer.Option(False, "--stale"),
    dup: bool = typer.Option(False, "--dup"),
    source: str = typer.Option(None, "--source"),
    scope: str = typer.Option(
        None, "--scope",
        help="Filter by monorepo scope: real|nested|junk|real+nested|all",
    ),
) -> None:
    rules = _rules_with_usage(scope=scope)
    if source:
        rules = [r for r in rules if r.source.scope == source]
    if stale:
        rules = [r for r in rules if r.stale]
    if dup:
        dup_set = {id(r) for d in find_duplicates(rules) for r in d.rules}
        rules = [r for r in rules if id(r) in dup_set]
    for r in rules:
        flag = "STALE" if r.stale else ""
        typer.echo(
            f"{r.tool:6}  {r.pattern:30}  {r.source.scope:14}  hits90d={r.match_count_90d}  {flag}"
        )


@perms_app.command("dedupe")
def dedupe(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    rules = _rules_with_usage()
    dups = find_duplicates(rules)
    for d in dups:
        typer.echo(f"[{d.kind}] {d.suggestion}")
    if dry_run or not dups:
        return
    with audit_action("perms dedupe", []) as changed:
        removed: list[dict] = []
        for d in dups:
            try:
                if d.kind == "exact":
                    for r in d.rules[1:]:
                        remove_rule(r)
                        typer.echo(f"removed exact dup: {r.raw} from {r.source.path}")
                        removed.append(
                            {"raw": r.raw, "source": str(r.source.path), "kind": "exact"}
                        )
                elif d.kind == "subsumed":
                    narrow = d.rules[1]
                    remove_rule(narrow)
                    typer.echo(f"removed subsumed: {narrow.raw}")
                    removed.append(
                        {"raw": narrow.raw, "source": str(narrow.source.path), "kind": "subsumed"}
                    )
                # conflict + empty: warn-only / require manual review
            except NotConfirmedError as e:
                typer.echo(str(e), err=True)
                raise typer.Exit(code=2) from e
        changed["removed"] = removed


@perms_app.command("prune")
def prune(
    older_than: str = typer.Option("90d", "--older-than"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    rules = _rules_with_usage()
    stale = [r for r in rules if r.stale]
    typer.echo(f"{len(stale)} stale rules (no match 90d):")
    for r in stale:
        typer.echo(f"  {r.tool}({r.pattern})  in {r.source.path}")
    if dry_run:
        return
    with audit_action("perms prune", [older_than]) as changed:
        removed: list[dict] = []
        for r in stale:
            try:
                remove_rule(r)
                removed.append({"raw": r.raw, "source": str(r.source.path)})
            except NotConfirmedError as e:
                typer.echo(str(e), err=True)
                raise typer.Exit(code=2) from e
        changed["removed"] = removed


@perms_app.command("remove")
def remove(
    raw: str,
    from_: str = typer.Option(..., "--from"),
) -> None:
    with audit_action("perms remove", [raw, from_]) as changed:
        rules = discover_rules()
        target = next(
            (r for r in rules if r.raw == raw and str(r.source.path) == from_), None
        )
        if not target:
            raise typer.BadParameter("Rule not found in given source")
        try:
            remove_rule(target)
            typer.echo(f"removed {raw}")
            changed["removed"] = [{"raw": raw, "source": from_}]
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e


@perms_app.command("add")
def add(
    raw: str,
    to: str = typer.Option(..., "--to"),
    decision: str = typer.Option("allow", "--decision"),
) -> None:
    with audit_action("perms add", [raw, to, decision]) as changed:
        try:
            add_rule(raw, scope=to, decision=decision)
            typer.echo(f"added {raw} -> {to}")
            changed["added"] = [{"raw": raw, "scope": to, "decision": decision}]
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e
