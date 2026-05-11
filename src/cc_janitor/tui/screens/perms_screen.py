from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Select, Static

from ...core.permissions import analyze_usage, discover_rules, find_duplicates
from ...core.sessions import discover_sessions
from ._source_filter import source_filter_options


class PermsScreen(Widget):
    """Effective permission rules + source summary."""

    DEFAULT_CSS = """
    PermsScreen { height: 100%; }
    #perms-source-filter { height: 3; }
    DataTable { height: 62%; }
    #perms-summary { height: 35%; border: round green; padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Select(
            list(source_filter_options()),
            id="perms-source-filter",
            value="real",
            allow_blank=False,
        )
        yield DataTable(id="perms-table")
        yield Static("", id="perms-summary")

    def on_mount(self) -> None:
        self._source_filter = "real"
        self._reload()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "perms-source-filter":
            return
        self._source_filter = str(event.value)
        self._reload()

    def _reload(self) -> None:
        rules = analyze_usage(
            discover_rules(scope=getattr(self, "_source_filter", None)),
            discover_sessions(),
        )
        dups = find_duplicates(rules)
        dup_set = {id(r) for d in dups for r in d.rules}

        table: DataTable = self.query_one("#perms-table", DataTable)
        table.clear(columns=True)
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
