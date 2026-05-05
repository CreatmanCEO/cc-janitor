from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ...core.permissions import discover_rules, analyze_usage, find_duplicates
from ...core.sessions import discover_sessions


class PermsScreen(Widget):
    """Effective permission rules + source summary."""

    DEFAULT_CSS = """
    PermsScreen { height: 100%; }
    DataTable { height: 65%; }
    #perms-summary { height: 35%; border: round green; padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(id="perms-table")
        yield Static("", id="perms-summary")

    def on_mount(self) -> None:
        rules = analyze_usage(discover_rules(), discover_sessions())
        dups = find_duplicates(rules)
        dup_set = {id(r) for d in dups for r in d.rules}

        table: DataTable = self.query_one("#perms-table", DataTable)
        table.add_columns("Tool", "Pattern", "Source", "Used90d", "Flags")
        table.cursor_type = "row"

        for r in sorted(rules, key=lambda x: (x.tool, x.pattern)):
            flags = []
            if r.stale:
                flags.append("STALE")
            if id(r) in dup_set:
                flags.append("DUP")
            table.add_row(
                r.tool,
                r.pattern or "*",
                r.source.scope,
                str(r.match_count_90d),
                ",".join(flags),
                key=f"{r.source.path}::{r.raw}",
            )

        # summary panel
        by_source: dict = {}
        for r in rules:
            by_source.setdefault(r.source.path, []).append(r)
        lines = [
            f"[b]Total rules:[/] {len(rules)}",
            f"[b]Stale:[/] {sum(1 for r in rules if r.stale)}",
            f"[b]Duplicates detected:[/] {len(dups)}",
            "",
        ]
        for path, rs in by_source.items():
            stale = sum(1 for r in rs if r.stale)
            line = f"  {path}  [{len(rs)} rules"
            if stale:
                line += f", {stale} stale"
            line += "]"
            lines.append(line)
        self.query_one("#perms-summary", Static).update("\n".join(lines))
