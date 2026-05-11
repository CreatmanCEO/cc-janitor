from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Select, Static

from ...core.memory import discover_memory_files
from ._source_filter import source_filter_options


class MemoryScreen(Widget):
    """Memory files browser with preview and reinject action."""

    DEFAULT_CSS = """
    MemoryScreen { height: 100%; }
    #memory-source-filter { height: 3; }
    DataTable { height: 57%; }
    #memory-preview { height: 40%; border: round green; padding: 1; }
    """

    BINDINGS = [
        ("e", "edit", "Edit"),
        ("a", "archive", "Archive"),
        ("m", "move_type", "Move type"),
        ("r", "reinject", "Reinject"),
        ("f", "find_dupes", "Duplicates"),
    ]

    def compose(self) -> ComposeResult:
        yield Select(
            list(source_filter_options()),
            id="memory-source-filter",
            value="real",
            allow_blank=False,
        )
        yield DataTable(id="memory-table")
        yield Static("", id="memory-preview")

    def on_mount(self) -> None:
        self._source_filter = "real"
        self._reload()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "memory-source-filter":
            return
        self._source_filter = str(event.value)
        self._reload()

    def _reload(self) -> None:
        table: DataTable = self.query_one("#memory-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Type", "Size", "Modified", "Name", "Project")
        table.cursor_type = "row"
        self._items = discover_memory_files()
        for idx, m in enumerate(self._items):
            table.add_row(
                m.type,
                f"{m.size_bytes}b",
                m.last_modified.strftime("%Y-%m-%d"),
                m.path.name,
                m.project or "(global)",
                key=str(idx),
            )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        try:
            idx = int(event.row_key.value)
            m = self._items[idx]
        except (ValueError, IndexError):
            return
        preview = self.query_one("#memory-preview", Static)
        body = m.body[:4000] if m.body else ""
        preview.update(f"[b]{m.path.name}[/]  ({m.type})\n\n{body}")

    def action_reinject(self) -> None:
        import os

        from ...core.reinject import queue_reinject

        os.environ.setdefault("CC_JANITOR_USER_CONFIRMED", "1")
        queue_reinject()
        self.notify("Reinject queued — fires on next Claude Code tool call")
