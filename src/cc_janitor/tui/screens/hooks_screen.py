from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Select, Static

from ...cli._audit import audit_action
from ...core.hooks import HookEntry, discover_hooks, simulate_hook
from .._confirm import ConfirmModal, tui_confirmed
from ._source_filter import source_filter_options


class HooksScreen(Widget):
    """Hook browser with simulate + logging-toggle actions."""

    DEFAULT_CSS = """
    HooksScreen { height: 100%; }
    #hooks-source-filter { height: 3; }
    DataTable { height: 57%; }
    #hooks-source { height: 40%; border: round green; padding: 1; }
    """

    BINDINGS = [
        ("t", "simulate", "Simulate"),
        ("l", "toggle_logging", "Toggle logging"),
        ("v", "view_source", "View source"),
    ]

    def compose(self) -> ComposeResult:
        yield Select(
            list(source_filter_options()),
            id="hooks-source-filter",
            value="real",
            allow_blank=False,
        )
        yield DataTable(id="hooks-table")
        yield Static("", id="hooks-source")

    def on_mount(self) -> None:
        self._source_filter = "real"
        self._reload()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "hooks-source-filter":
            return
        self._source_filter = str(event.value)
        self._reload()

    def _reload(self) -> None:
        table: DataTable = self.query_one("#hooks-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Event", "Matcher", "Type", "Command", "Scope", "Logged")
        table.cursor_type = "row"
        self._hooks: list[HookEntry] = discover_hooks(
            scope=getattr(self, "_source_filter", None)
        )
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

        will_enable = not h.has_logging_wrapper
        verb = "Enable" if will_enable else "Disable"
        question = f"{verb} logging for {h.event}/{h.matcher}?"

        def _on_confirm(ok: bool | None) -> None:
            if not ok:
                self.notify("Toggle cancelled", severity="warning")
                return
            try:
                with tui_confirmed(), audit_action(
                    "hooks toggle-logging",
                    [h.event, h.matcher, "enable" if will_enable else "disable"],
                    mode="tui",
                ):
                    if will_enable:
                        enable_logging(h.event, matcher=h.matcher)
                    else:
                        disable_logging(h.event, matcher=h.matcher)
                self.notify(
                    f"Logging {'enabled' if will_enable else 'disabled'} "
                    f"for {h.event}/{h.matcher}"
                )
                self._reload()
            except Exception as exc:
                self.notify(f"Failed: {exc}", severity="error")

        self.app.push_screen(ConfirmModal(question), _on_confirm)

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
