import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_hooks_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "hooks"
        await pilot.pause()
        table = app.query_one("#hooks-table", DataTable)
        # Mock has at least one PreToolUse/Bash hook
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_hooks_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "hooks"
        await pilot.pause()
        table = app.query_one("#hooks-table", DataTable)
        labels = [str(c.label) for c in table.columns.values()]
        assert "Event" in labels
        assert "Matcher" in labels
