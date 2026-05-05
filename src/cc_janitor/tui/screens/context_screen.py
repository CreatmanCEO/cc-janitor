from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ...core.context import context_cost


class ContextScreen(Widget):
    """Context-cost inspector: CLAUDE.md + memory + skills with token totals."""

    DEFAULT_CSS = """
    ContextScreen { height: 100%; }
    DataTable { height: 70%; }
    #context-totals { height: 30%; border: round green; padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(id="context-table")
        yield Static("", id="context-totals")

    def on_mount(self) -> None:
        cost = context_cost(starting_from=Path.cwd())
        table: DataTable = self.query_one("#context-table", DataTable)
        table.add_columns("Kind", "Size", "Tokens", "Path")
        table.cursor_type = "row"

        for f in sorted(cost.files, key=lambda x: -x.tokens):
            table.add_row(
                f.kind,
                f"{f.size_bytes}b",
                f"{f.tokens}",
                str(f.path),
                key=str(f.path),
            )

        dollars = cost.total_tokens * 15 / 1_000_000
        text = (
            f"[b]Total bytes:[/] {cost.total_bytes}\n"
            f"[b]Total tokens:[/] {cost.total_tokens}\n"
            f"[b]Files:[/] {len(cost.files)}\n"
            f"[b]≈ ${dollars:.4f}[/] per request at Opus input rate"
        )
        self.query_one("#context-totals", Static).update(text)
