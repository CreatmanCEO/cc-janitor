from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static

from ...cli._audit import audit_action
from ...core.schedule import (
    TEMPLATES,
    ScheduledJob,
    get_scheduler,
)
from .._confirm import ConfirmModal, tui_confirmed


class AddJobModal(ModalScreen[ScheduledJob | None]):
    """Modal for picking a template + (optional) custom cron expression."""

    DEFAULT_CSS = """
    AddJobModal { align: center middle; }
    #add-job-box {
        width: 60;
        height: auto;
        background: $panel;
        border: round $accent;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="add-job-box"):
            yield Static("[b]Add scheduled job[/]")
            yield Select(
                [(k, k) for k in TEMPLATES],
                prompt="Template",
                id="template-select",
            )
            yield Input(placeholder="cron (blank = template default)", id="cron-input")
            yield Static("", id="cron-error")
            yield Button("Add", variant="primary", id="add-btn")
            yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        if event.button.id != "add-btn":
            return
        sel = self.query_one("#template-select", Select)
        if sel.value is Select.BLANK:
            self.query_one("#cron-error", Static).update("[red]pick a template[/]")
            return
        template = str(sel.value)
        cron_input = self.query_one("#cron-input", Input).value.strip()
        cron_expr = cron_input or TEMPLATES[template]["default_cron"]
        try:
            from croniter import croniter

            croniter(cron_expr)
        except Exception as exc:
            self.query_one("#cron-error", Static).update(f"[red]invalid cron: {exc}[/]")
            return
        import sys

        job = ScheduledJob(
            name=f"cc-janitor-{template}",
            template=template,
            cron_expr=cron_expr,
            command=TEMPLATES[template]["command"],
            next_run=None,
            last_run=None,
            last_status="never",
            dry_run_pending=True,
            backend="schtasks" if sys.platform == "win32" else "cron",
        )
        self.dismiss(job)


class ScheduleScreen(Widget):
    """Scheduled-job manager (cron / Windows schtasks)."""

    DEFAULT_CSS = """
    ScheduleScreen { height: 100%; }
    #schedule-table { height: 70%; }
    #schedule-status { height: 30%; border: round green; padding: 1; }
    """

    BINDINGS = [
        ("a", "add", "Add"),
        ("r", "remove", "Remove"),
        ("n", "run_now", "Run now"),
        ("p", "promote", "Promote"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="schedule-table")
        yield Static("", id="schedule-status")

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#schedule-table", DataTable)
        table.add_columns(
            "Name", "Template", "Cron", "Next run", "Last run", "Status", "Dry-run"
        )
        table.cursor_type = "row"
        self._reload()

    def _reload(self) -> None:
        table: DataTable = self.query_one("#schedule-table", DataTable)
        table.clear()
        try:
            self._jobs = get_scheduler().list_jobs()
        except Exception as exc:
            self._jobs = []
            self.query_one("#schedule-status", Static).update(
                f"[yellow]scheduler unavailable: {exc}[/]"
            )
            return
        for j in self._jobs:
            table.add_row(
                j.name,
                j.template,
                j.cron_expr,
                j.next_run.strftime("%Y-%m-%d %H:%M") if j.next_run else "-",
                j.last_run.strftime("%Y-%m-%d %H:%M") if j.last_run else "-",
                j.last_status,
                "yes" if j.dry_run_pending else "",
                key=j.name,
            )
        self.query_one("#schedule-status", Static).update(
            f"[b]{len(self._jobs)}[/] scheduled job(s)"
        )

    def _highlighted(self) -> ScheduledJob | None:
        table = self.query_one("#schedule-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            return self._jobs[table.cursor_row]
        except IndexError:
            return None

    def action_add(self) -> None:
        def _on_picked(job: ScheduledJob | None) -> None:
            if job is None:
                return

            def _on_confirm(ok: bool | None) -> None:
                if not ok:
                    self.notify("Add cancelled", severity="warning")
                    return
                try:
                    with tui_confirmed(), audit_action(
                        "schedule add", [job.template, job.cron_expr], mode="tui"
                    ):
                        get_scheduler().add_job(job)
                    self.notify(f"Added {job.name} (dry-run-pending)")
                except Exception as exc:
                    self.notify(f"Add failed: {exc}", severity="error")
                self._reload()

            self.app.push_screen(
                ConfirmModal(f"Add scheduled job {job.name}?"), _on_confirm
            )

        self.app.push_screen(AddJobModal(), _on_picked)

    def action_remove(self) -> None:
        j = self._highlighted()
        if j is None:
            return

        def _on_confirm(ok: bool | None) -> None:
            if not ok:
                self.notify("Remove cancelled", severity="warning")
                return
            try:
                with tui_confirmed(), audit_action(
                    "schedule remove", [j.name], mode="tui"
                ):
                    get_scheduler().remove_job(j.name)
                self.notify(f"Removed {j.name}")
            except Exception as exc:
                self.notify(f"Remove failed: {exc}", severity="error")
            self._reload()

        self.app.push_screen(ConfirmModal(f"Remove scheduled job {j.name}?"), _on_confirm)

    def action_run_now(self) -> None:
        j = self._highlighted()
        if j is None:
            return
        try:
            rc = get_scheduler().run_now(j.name)
            self.notify(f"{j.name} exit={rc}")
        except Exception as exc:
            self.notify(f"Run failed: {exc}", severity="error")

    def action_promote(self) -> None:
        j = self._highlighted()
        if j is None or not j.dry_run_pending:
            self.notify("Nothing to promote", severity="warning")
            return

        def _on_confirm(ok: bool | None) -> None:
            if not ok:
                self.notify("Promote cancelled", severity="warning")
                return
            try:
                with tui_confirmed(), audit_action(
                    "schedule promote", [j.name], mode="tui"
                ):
                    sched = get_scheduler()
                    sched.remove_job(j.name)
                    j.dry_run_pending = False
                    sched.add_job(j)
                self.notify(f"Promoted {j.name} to live mode")
            except Exception as exc:
                self.notify(f"Promote failed: {exc}", severity="error")
            self._reload()

        self.app.push_screen(
            ConfirmModal(f"Promote {j.name} to live mode?"), _on_confirm
        )
