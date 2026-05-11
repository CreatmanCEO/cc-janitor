"""8th-tab DreamScreen — snapshot history list + per-pair diff viewer.

Read-only by design. Future mutations (rollback, prune) will route through
:class:`cc_janitor.tui._confirm.ConfirmModal` per the Phase 4 plan; this
screen only surfaces what :mod:`core.dream_snapshot` and
:mod:`core.dream_diff` already produce.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ...core.dream_diff import compute_diff
from ...core.dream_snapshot import _dream_root, history


class DreamScreen(Widget):
    DEFAULT_CSS = """
    DreamScreen { layout: horizontal; height: 100%; }
    DreamScreen DataTable { width: 60; }
    DreamScreen Static { width: 1fr; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(id="dream-list")
        yield Static(id="dream-diff", expand=True)

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#dream-list", DataTable)
        table.add_columns("Date", "Project", "ΔFiles", "ΔLines")
        table.cursor_type = "row"
        for pair in reversed(history()):
            table.add_row(
                pair.ts_pre[:19],
                pair.project_slug,
                str(pair.file_count_delta if pair.file_count_delta is not None else 0),
                str(pair.line_count_delta if pair.line_count_delta is not None else 0),
                key=pair.pair_id,
            )
        self._show_diff_for(None)

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        key = event.row_key.value if event.row_key else None
        self._show_diff_for(key)

    def _show_diff_for(self, pair_id: str | None) -> None:
        diff_widget: Static = self.query_one("#dream-diff", Static)
        if not pair_id:
            diff_widget.update("Select a snapshot pair on the left.")
            return
        pre = _dream_root() / f"{pair_id}-pre"
        post = _dream_root() / f"{pair_id}-post"
        if not pre.exists() or not post.exists():
            diff_widget.update(
                f"Mirrors missing for {pair_id} (may be in tar storage)."
            )
            return
        diff = compute_diff(pre, post)
        body: list[str] = [f"Pair {pair_id}  {diff.summary}\n"]
        for d in diff.deltas:
            body.append(
                f"  [{d.status}] {d.rel_path} "
                f"+{d.lines_added} -{d.lines_removed}"
            )
        for d in diff.deltas:
            if d.unified_diff:
                body.append("")
                body.append(d.unified_diff)
        diff_widget.update("\n".join(body))
