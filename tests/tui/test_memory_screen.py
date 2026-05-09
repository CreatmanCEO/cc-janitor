import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_memory_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "memory"
        await pilot.pause()
        table = app.query_one("#memory-table", DataTable)
        # Mock home should expose at least the global CLAUDE.md
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_memory_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "memory"
        await pilot.pause()
        table = app.query_one("#memory-table", DataTable)
        labels = [str(c.label) for c in table.columns.values()]
        assert "Type" in labels
        assert "Name" in labels
