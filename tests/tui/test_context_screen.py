import pytest
from textual.widgets import DataTable, Static


@pytest.mark.asyncio
async def test_context_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#context-table", DataTable)
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_context_screen_totals(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        totals = app.query_one("#context-totals", Static)
        text = str(totals.render())
        assert "Total" in text or "tokens" in text.lower()
