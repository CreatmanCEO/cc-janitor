from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ...core.sessions import discover_sessions
from ...i18n import t


class SessionsScreen(Widget):
    """Sessions list + preview pane."""

    DEFAULT_CSS = """
    SessionsScreen { height: 100%; }
    DataTable { height: 60%; }
    #preview { height: 40%; border: round green; padding: 1; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(id="sessions-table")
        yield Static("", id="preview")

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#sessions-table", DataTable)
        table.add_columns("ID", "Project", "Date", "Size", "Msgs", "First msg")
        table.cursor_type = "row"

        for s in sorted(discover_sessions(), key=lambda x: x.last_activity, reverse=True):
            table.add_row(
                s.id,
                s.project,
                s.last_activity.strftime("%Y-%m-%d %H:%M"),
                f"{s.size_bytes // 1024}KB",
                str(s.message_count),
                (s.first_user_msg or "")[:50],
                key=s.id,
            )

    def on_data_table_row_highlighted(self, ev: DataTable.RowHighlighted) -> None:
        if ev.row_key is None or ev.row_key.value is None:
            return
        sid = ev.row_key.value
        s = next((x for x in discover_sessions() if x.id == sid), None)
        if not s:
            return
        prv = self.query_one("#preview", Static)
        text = (
            f"[b]{s.id}[/]\n"
            f"Project: {s.project}\n"
            f"Messages: {s.message_count}  Compactions: {s.compactions}\n\n"
            f"[b]{t('sessions.preview_first_msg')}[/]:\n{s.first_user_msg}\n"
        )
        prv.update(text)
