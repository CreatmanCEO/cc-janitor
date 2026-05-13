from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Select, Static

from ...cli._audit import audit_action
from ...core.memory import (
    archive_memory_file,
    discover_memory_files,
    find_duplicate_lines,
)
from .._confirm import ConfirmModal, tui_confirmed
from ._source_filter import source_filter_options


class MemoryScreen(Widget):
    """Memory files browser with preview and reinject action."""

    DEFAULT_CSS = """
    MemoryScreen { height: 100%; }
    #memory-source-filter { height: 3; }
    DataTable { height: 57%; }
    #memory-preview { height: 40%; border: round green; padding: 1; }
    """

    # 0.4.2: `e` (edit) and `m` (move-type) were declared but never
    # implemented in 0.4.x; they have been removed until the corresponding
    # Select widget / editor-spawn work lands (tracked for 0.5.x).
    BINDINGS = [
        ("r", "reinject", "Reinject"),
        ("a", "archive", "Archive"),
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
        self._items = discover_memory_files(
            scope=getattr(self, "_source_filter", None)
        )
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
        from ...core.reinject import queue_reinject

        def _on_confirm(ok: bool | None) -> None:
            if not ok:
                self.notify("Reinject cancelled", severity="warning")
                return
            try:
                with tui_confirmed(), audit_action(
                    "context reinject", [], mode="tui"
                ):
                    queue_reinject()
                self.notify("Reinject queued — fires on next Claude Code tool call")
            except Exception as exc:
                self.notify(f"Reinject failed: {exc}", severity="error")

        self.app.push_screen(
            ConfirmModal("Queue memory reinject on next tool call?"), _on_confirm
        )

    def _highlighted(self):
        try:
            table: DataTable = self.query_one("#memory-table", DataTable)
            row = table.cursor_row
            if row is None:
                return None
            return self._items[row]
        except (IndexError, AttributeError):
            return None

    def action_archive(self) -> None:
        m = self._highlighted()
        if m is None:
            self.notify("No memory file selected", severity="warning")
            return

        def _on_confirm(ok: bool | None) -> None:
            if not ok:
                self.notify("Archive cancelled", severity="warning")
                return
            try:
                with tui_confirmed(), audit_action(
                    "memory archive", [str(m.path)], mode="tui"
                ) as ch:
                    dst = archive_memory_file(m.path)
                    ch["archived"] = {
                        "original": str(m.path),
                        "archive_path": str(dst),
                    }
                self.notify(f"Archived {m.path.name}")
                self._reload()
            except Exception as exc:
                self.notify(f"Archive failed: {exc}", severity="error")

        self.app.push_screen(
            ConfirmModal(f"Archive {m.path.name}? (reversible via cc-janitor undo)"),
            _on_confirm,
        )

    def action_find_dupes(self) -> None:
        preview = self.query_one("#memory-preview", Static)
        if getattr(self, "_dupes_open", False):
            self._dupes_open = False
            preview.update("")
            return
        paths = [m.path for m in self._items]
        dups = find_duplicate_lines(paths, min_length=8)
        self._dupes_open = True
        if not dups:
            preview.update("[b]Duplicate lines[/]\n\n(no duplicates found)")
            return
        lines = ["[b]Duplicate lines across files[/]\n"]
        for d in dups[:50]:
            files = ", ".join(p.name for p in d.files)
            lines.append(f"  [{len(d.files)}x] {d.line[:80]}  →  {files}")
        preview.update("\n".join(lines))
