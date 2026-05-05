import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_sessions_screen_table_populated(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#sessions-table", DataTable)
        assert table.row_count >= 2  # abc123 + def456 from fixture


@pytest.mark.asyncio
async def test_sessions_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#sessions-table", DataTable)
        assert len(table.columns) == 6
