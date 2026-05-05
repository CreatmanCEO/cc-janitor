from __future__ import annotations
from pathlib import Path

import typer

from ...core.context import context_cost

context_app = typer.Typer(help="Inspect context cost (CLAUDE.md, memory, skills)")


@context_app.command("show")
def show(project: Path = typer.Option(Path.cwd(), "--project")) -> None:
    cost = context_cost(starting_from=project)
    for f in sorted(cost.files, key=lambda x: -x.tokens):
        typer.echo(
            f"{f.kind:10}  {f.size_bytes:>8}b  {f.tokens:>6}tok  {f.path}"
        )
    typer.echo(f"\nTOTAL: {cost.total_bytes}b  {cost.total_tokens} tokens")


@context_app.command("cost")
def cost(project: Path = typer.Option(Path.cwd(), "--project")) -> None:
    c = context_cost(starting_from=project)
    typer.echo(f"{c.total_bytes} bytes, {c.total_tokens} tokens")
    dollars = c.total_tokens * 15 / 1_000_000  # Opus input rate
    typer.echo(f"≈ ${dollars:.4f} per request at Opus input rate")


@context_app.command("find-duplicates")
def find_duplicates(project: Path = typer.Option(Path.cwd(), "--project")) -> None:
    c = context_cost(starting_from=project)
    seen: dict[str, list[Path]] = {}
    for f in c.files:
        try:
            text = f.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if len(line) < 40:
                continue
            seen.setdefault(line, []).append(f.path)
    dups = {k: v for k, v in seen.items() if len({str(p) for p in v}) > 1}
    if not dups:
        typer.echo("No duplicate substantial lines.")
        return
    for line, paths in dups.items():
        unique_paths = sorted({str(p) for p in paths})
        typer.echo(f"\n{len(unique_paths)}× {line[:80]}…")
        for p in unique_paths:
            typer.echo(f"  - {p}")
