from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from ...core.stats import load_snapshots, render_sparkline


class AuditScreen(Widget):
    """Audit tab with a daily-stats sparkline sub-pane.

    Footer key `s` toggles the sub-pane.
    """

    DEFAULT_CSS = """
    AuditScreen { height: 100%; }
    #audit-header { height: auto; padding: 1; }
    #audit-sparklines {
        height: auto;
        border: round green;
        padding: 1;
    }
    """

    BINDINGS = [
        ("s", "toggle_sparklines", "Toggle stats"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Audit log viewer", id="audit-header")
        yield Static("", id="audit-sparklines")

    def on_mount(self) -> None:
        self._refresh_sparklines()

    def _refresh_sparklines(self) -> None:
        snaps = load_snapshots()
        panel = self.query_one("#audit-sparklines", Static)
        if not snaps:
            panel.update("No snapshots in window. Run `cc-janitor stats snapshot`.")
            return
        last = snaps[-1]
        lines = [
            f"Sessions:       {last.sessions_count:>6}  "
            f"{render_sparkline([s.sessions_count for s in snaps])}",
            f"Perm rules:     {last.perm_rules_count:>6}  "
            f"{render_sparkline([s.perm_rules_count for s in snaps])}",
            f"Context tokens: {last.context_tokens:>6}  "
            f"{render_sparkline([s.context_tokens for s in snaps])}",
            f"Trash bytes:    {last.trash_bytes:>6}  "
            f"{render_sparkline([s.trash_bytes for s in snaps])}",
        ]
        panel.update("\n".join(lines))

    def action_toggle_sparklines(self) -> None:
        panel = self.query_one("#audit-sparklines", Static)
        panel.display = not panel.display
