from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ...core.hooks import HookEntry, discover_hooks, simulate_hook


class HooksScreen(Widget):
    """Hook browser with simulate + logging-toggle actions."""

    DEFAULT_CSS = """
    HooksScreen { height: 100%; }
    DataTable { height: 60%; }
    #hooks-source { height: 40%; border: round green; padding: 1; }
    """

    BINDINGS = [
        ("t", "simulate", "Simulate"),
        ("l", "toggle_logging", "Toggle logging"),
        ("v", "view_source", "View source"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="hooks-table")
        yield Static("", id="hooks-source")

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#hooks-table", DataTable)
        table.add_columns("Event", "Matcher", "Type", "Command", "Scope", "Logged")
        table.cursor_type = "row"
        self._hooks: list[HookEntry] = discover_hooks()
        for idx, h in enumerate(self._hooks):
            cmd_preview = (h.command or h.url or "")[:60]
            table.add_row(
                h.event,
                h.matcher,
                h.type,
                cmd_preview,
                h.source_scope,
                "yes" if h.has_logging_wrapper else "",
                key=str(idx),
            )

    def _highlighted(self) -> HookEntry | None:
        table = self.query_one("#hooks-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            return self._hooks[table.cursor_row]
        except IndexError:
            return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        try:
            h = self._hooks[int(event.row_key.value)]
        except (ValueError, IndexError):
            return
        src = self.query_one("#hooks-source", Static)
        text = (
            f"[b]{h.event}[/]  matcher=[i]{h.matcher}[/]  scope={h.source_scope}\n"
            f"path: {h.source_path}\n\n"
            f"[b]command:[/]\n{h.command or h.url or ''}"
        )
        src.update(text)

    def action_simulate(self) -> None:
        h = self._highlighted()
        if h is None or not h.command:
            self.notify("No hook selected or command empty", severity="warning")
            return
        r = simulate_hook(h.command, event=h.event, matcher=h.matcher)
        out = f"exit={r.exit_code} {r.duration_ms}ms\n{r.stdout}\n{r.stderr}"
        self.query_one("#hooks-source", Static).update(out)

    def action_toggle_logging(self) -> None:
        h = self._highlighted()
        if h is None:
            return
        from ...core.hooks import disable_logging, enable_logging

        try:
            if h.has_logging_wrapper:
                disable_logging(h.event, matcher=h.matcher)
                self.notify(f"Logging disabled for {h.event}/{h.matcher}")
            else:
                enable_logging(h.event, matcher=h.matcher)
                self.notify(f"Logging enabled for {h.event}/{h.matcher}")
        except Exception as exc:
            self.notify(f"Failed: {exc}", severity="error")

    def action_view_source(self) -> None:
        h = self._highlighted()
        if h is None:
            return
        import os
        import subprocess

        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        if not editor:
            editor = "notepad.exe" if os.name == "nt" else "vi"
        try:
            subprocess.Popen([*editor.split(), str(h.source_path)])
        except Exception as exc:
            self.notify(f"Cannot open editor: {exc}", severity="error")
