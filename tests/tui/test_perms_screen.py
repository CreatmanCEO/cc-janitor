import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_perms_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#perms-table", DataTable)
        assert table.row_count >= 4


@pytest.mark.asyncio
async def test_perms_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#perms-table", DataTable)
        assert len(table.columns) == 5
