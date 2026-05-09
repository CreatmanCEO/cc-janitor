import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_schedule_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "schedule"
        await pilot.pause()
        # Mounts without crashing on a fresh home (no jobs yet).
        table = app.query_one("#schedule-table", DataTable)
        assert table is not None


@pytest.mark.asyncio
async def test_schedule_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "schedule"
        await pilot.pause()
        table = app.query_one("#schedule-table", DataTable)
        labels = [str(c.label) for c in table.columns.values()]
        assert "Name" in labels
        assert "Cron" in labels
