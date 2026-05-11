import pytest


@pytest.mark.asyncio
async def test_app_renders():
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.is_running


@pytest.mark.asyncio
async def test_app_has_eight_tabs():
    from textual.widgets import TabbedContent, TabPane

    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one(TabbedContent)
        panes = list(tabbed.query(TabPane))
        assert len(panes) == 8
